"""Mesa model for the Space Rescue Mission.

Mesa owns the world: a 15x15 OrthogonalVonNeumannGrid whose cells hold CellAgents
(asteroids, planets, danger zones, fuel depots, astronauts, the space station and the
player's ship). Mesa's model.step() advances the simulation one animation frame at a time.
The search algorithms live in search.py and are called from here.
"""
import math
import time
from typing import Dict, List, Optional, Tuple

from mesa import Model
from mesa.discrete_space import CellAgent, OrthogonalVonNeumannGrid

from search import ALGORITHMS, a_star, heuristic

N = 15
START = (13, 1)                 # where the ship begins
STATION = (1, 13)               # the Space Station
REFUEL = 15                     # fuel gained at a fuel depot
DIRS = [(-1, 0), (0, 1), (1, 0), (0, -1)]          # up, right, down, left (the actions)
BLOCKING = ("asteroid", "planet")

MISSIONS = [
    {"name": "Lost Astronaut", "obj": "Navigate to the stranded astronaut.",
     "astronauts": 1, "station": False, "danger": 0},
    {"name": "Multiple Astronaut Rescue", "obj": "Rescue both astronauts, then dock at the Space Station.",
     "astronauts": 2, "station": True, "danger": 4},
    {"name": "Critical Rescue", "obj": "Rescue astronauts, avoid danger zones and minimise path cost.",
     "astronauts": 2, "station": True, "danger": 12},
]
DIFFICULTY = [
    {"name": "Easy", "obstacles": 24, "danger": 0, "fuel": 4, "factor": 2.6},
    {"name": "Medium", "obstacles": 44, "danger": 8, "fuel": 3, "factor": 2.0},
    {"name": "Hard", "obstacles": 64, "danger": 14, "fuel": 3, "factor": 1.6},
]


# ---------------------------------------------------------------- Mesa agents
class Terrain(CellAgent):
    label = "empty"
    cost = 1


class Asteroid(Terrain):
    label = "asteroid"


class Planet(Terrain):
    label = "planet"


class DangerZone(Terrain):
    label = "danger"
    cost = 4


class FuelDepot(Terrain):
    label = "fuel"


class Astronaut(Terrain):
    label = "astronaut"


class SpaceStation(Terrain):
    label = "station"


class Ship(CellAgent):
    label = "ship"


TERRAIN_CLASSES = {"asteroid": Asteroid, "planet": Planet, "danger": DangerZone, "fuel": FuelDepot}


# ---------------------------------------------------------------- map generation
def _grid_neighbors(terrain: Dict, node: Tuple[int, int]) -> List[Tuple[int, int]]:
    """Neighbours on a plain dict map (used before Mesa agents exist, during generation)."""
    r, c = node
    out = []
    for dr, dc in DIRS:
        nr, nc = r + dr, c + dc
        if 0 <= nr < N and 0 <= nc < N and terrain.get((nr, nc)) not in BLOCKING:
            out.append((nr, nc))
    return out


def generate_layout(mission_index: int, difficulty_index: int, rng) -> dict:
    """Random map, retried until every leg of the mission is solvable.
    Fuel is sized from the optimal A* cost, as in the original game."""
    m, d = MISSIONS[mission_index], DIFFICULTY[difficulty_index]
    max_retries = 250
    for attempt in range(max_retries):
        used = {START, STATION}
        all_cells = [(r, c) for r in range(N) for c in range(N)]
        free_cells = [c for c in all_cells if c not in used]

        def pick(pred=None):
            candidates = [c for c in free_cells if pred is None or pred(c)]
            if not candidates:
                cell = rng.choice(free_cells)
            else:
                cell = rng.choice(candidates)
            free_cells.remove(cell)
            used.add(cell)
            return cell

        astronauts = [pick(lambda cell: heuristic(cell, START) >= 7) for _ in range(m["astronauts"])]
        terrain: Dict[Tuple[int, int], str] = {}
        # In late attempts, reduce obstacles to ensure a valid map is found
        obs_count = d["obstacles"] if attempt < 180 else max(10, d["obstacles"] // 2)
        for _ in range(obs_count):
            terrain[pick()] = "asteroid" if rng.random() < 0.65 else "planet"
        for _ in range(d["danger"] + m["danger"]):
            terrain[pick()] = "danger"
        for _ in range(d["fuel"]):
            terrain[pick()] = "fuel"

        points = [START, *astronauts, *([STATION] if m["station"] else [])]
        optimal, ok = 0, True
        for a, b in zip(points, points[1:]):
            res = a_star(a, b, lambda n: _grid_neighbors(terrain, n),
                         lambda n: 4 if terrain.get(n) == "danger" else 1)
            if not res.found:
                ok = False
                break
            optimal += res.cost
        if ok:
            return {"terrain": terrain, "astronauts": astronauts,
                    "fuel_max": math.ceil(optimal * d["factor"]) + 4}

    # Safe guaranteed fallback if max_retries exceeded
    return {"terrain": {}, "astronauts": [(3, 3)] if m["astronauts"] == 1 else [(3, 3), (7, 7)],
            "fuel_max": 50}


# ---------------------------------------------------------------- the Mesa model
class SpaceRescueModel(Model):
    def __init__(self, mission: int = 0, difficulty: int = 0):
        super().__init__()
        self.mission_index = mission
        self.difficulty_index = difficulty
        self.grid = OrthogonalVonNeumannGrid((N, N), torus=False, random=self.random)

        layout = generate_layout(mission, difficulty, self.random)
        self.fuel_max = layout["fuel_max"]
        self.astronaut_coords = list(layout["astronauts"])
        self.station_coord = STATION

        # Static terrain as a dict for fast lookups, and as Mesa agents placed on the grid.
        self.terrain: Dict[Tuple[int, int], str] = dict(layout["terrain"])
        for coord, kind in self.terrain.items():
            TERRAIN_CLASSES[kind](self).cell = self.grid[coord]
        for coord in self.astronaut_coords:
            Astronaut(self).cell = self.grid[coord]
        if self.mission["station"]:
            SpaceStation(self).cell = self.grid[STATION]
        self.ship = Ship(self)
        self.ship.cell = self.grid[START]

        self.speed = 55                 # animation speed slider, 1..100
        self.algorithm = "astar"        # selected search algorithm
        self.reset()

    # ----- static helpers
    @property
    def mission(self) -> dict:
        return MISSIONS[self.mission_index]

    @property
    def difficulty(self) -> dict:
        return DIFFICULTY[self.difficulty_index]

    @property
    def ship_pos(self) -> Tuple[int, int]:
        return self.ship.cell.coordinate

    @property
    def busy(self) -> bool:
        return self.phase in ("exploring", "goal", "reveal", "travel")

    @property
    def over(self) -> bool:
        return self.outcome is not None

    @property
    def explore_delay(self) -> float:
        """Seconds per exploration frame (same formula as the original: max(8, 150 - speed*1.4) ms)."""
        return max(8, 150 - self.speed * 1.4) / 1000

    def is_blocked(self, node) -> bool:
        return self.terrain.get(node) in BLOCKING

    def step_cost(self, node) -> int:
        """Cost of ENTERING a cell: 4 in a danger zone, otherwise 1."""
        return 4 if self.terrain.get(node) == "danger" else 1

    def neighbors(self, node) -> List[Tuple[int, int]]:
        """Mesa's grid connections, in the fixed action order up/right/down/left, minus blocked cells."""
        cell = self.grid[node]
        out = []
        for d in DIRS:
            nb = cell.connections.get(d)
            if nb is not None and not self.is_blocked(nb.coordinate):
                out.append(nb.coordinate)
        return out

    def target(self) -> Optional[Tuple[int, int]]:
        """The next objective: first unrescued astronaut, then the station (if this mission has one)."""
        for a in self.astronaut_coords:
            if a not in self.rescued:
                return a
        return self.station_coord if self.mission["station"] else None

    def run_compare(self):
        """AI Search Lab: run all three algorithms from the ship's current cell to the objective."""
        goal = self.target()
        if goal is None:
            if self.mission["station"]:
                goal = self.station_coord
            elif self.astronaut_coords:
                goal = self.astronaut_coords[-1]
            else:
                goal = self.ship_pos
        results = {k: ALGORITHMS[k]["fn"](self.ship_pos, goal, self.neighbors, self.step_cost)
                   for k in ("bfs", "dfs", "astar")}
        return goal, results

    def step_forward(self) -> bool:
        """Step one animation frame forward. Pauses continuous animation."""
        if self.over:
            return False
        if not self.busy:
            if not self.begin_search():
                return False
            self.paused = True
            return True
        self.paused = True
        self.step()
        return True

    # ----- state
    def reset(self):
        """resetMission(): back to the start with a full tank. The map itself is kept."""
        self.ship.cell = self.grid[START]
        self.fuel = self.fuel_max
        self.rescued = set()
        self.used_depots = set()
        self.steps = 0
        self.path_cost = 0
        self.fuel_spent = 0
        self.total_explored = 0
        self.algorithms_used: List[str] = []
        self.outcome: Optional[str] = None          # None | "won" | "lost"
        self.paused = False
        self.phase = "idle"
        self.search = None
        self.cursor = 0                             # next index in search.log
        self.path_cursor = 0
        self.visited: Dict[Tuple[int, int], dict] = {}
        self.current: Optional[Tuple[int, int]] = None
        self.shown_path: List[Tuple[int, int]] = []
        self.stat_len = self.stat_cost = 0
        self.stat_time = 0.0
        self.t0: Optional[float] = None
        self.end_seconds = 0
        self.message = "Ready. Pick an algorithm and press Find Path, or fly manually."
        self.next_delay = 0.0

    def _clear_visuals(self):
        self.visited = {}
        self.current = None
        self.shown_path = []
        self.search = None
        self.phase = "idle"

    # ----- player actions
    def begin_search(self) -> bool:
        """findPath(): the REAL search runs now; the animation then replays its log."""
        goal = self.target()
        if goal is None or self.busy or self.over:
            return False
        self._clear_visuals()
        self.search = ALGORITHMS[self.algorithm]["fn"](self.ship_pos, goal, self.neighbors, self.step_cost)
        if self.search.name not in self.algorithms_used:
            self.algorithms_used.append(self.search.name)
        self.total_explored += self.search.explored
        self.cursor = 0
        self.path_cursor = 0
        self.phase = "exploring"
        self.message = "Searching…"
        return True

    def manual_move(self, dr: int, dc: int) -> bool:
        """Arrow pad. Returns False when the move is blocked (the ship bumps)."""
        if self.busy or self.over:
            return False
        r, c = self.ship_pos
        dest = (r + dr, c + dc)
        if not (0 <= dest[0] < N and 0 <= dest[1] < N) or self.is_blocked(dest):
            return False
        self._clear_visuals()
        self._enter(dest)
        return True

    def _enter(self, coord):
        """stepTo(): fly one cell, then apply fuel, depots, rescues and the end-of-mission rules."""
        if self.t0 is None:
            self.t0 = time.time()
        cost = self.step_cost(coord)
        self.ship.cell = self.grid[coord]
        self.fuel -= cost
        self.fuel_spent += cost
        self.path_cost += cost
        self.steps += 1
        if self.terrain.get(coord) == "fuel" and coord not in self.used_depots:
            self.used_depots.add(coord)
            self.fuel = min(self.fuel_max, self.fuel + REFUEL)
            self.message = f"Fuel station reached: +{REFUEL} fuel."
        if coord in self.astronaut_coords and coord not in self.rescued:
            self.rescued.add(coord)
            self.message = "Astronaut rescued!"
        done = len(self.rescued) == self.mission["astronauts"] and (
            not self.mission["station"] or coord == self.station_coord)
        if done:
            self._finish(True)
        elif self.fuel <= 0:
            self._finish(False)

    def _finish(self, win: bool):
        self.outcome = "won" if win else "lost"
        self.phase = "idle"
        self.end_seconds = round(time.time() - self.t0) if self.t0 else 0

    # ----- Mesa tick: one animation frame
    def step(self):
        """Advance the current search animation by one frame and set self.next_delay (seconds)."""
        if self.phase == "exploring":
            entry = self.search.log[self.cursor]
            self.visited[entry["node"]] = entry
            self.current = entry["node"]
            self.cursor += 1
            self.message = ["Exploring node %d…" % self.cursor, "Evaluating neighbours…",
                            "Building search tree…"][(self.cursor - 1) % 3]
            self.next_delay = self.explore_delay
            if self.cursor >= len(self.search.log):
                self.current = None
                self.stat_time = self.search.time
                if self.search.found:
                    self.phase = "goal"
                else:
                    self.phase = "idle"
                    self.message = "No path exists to the objective."

        elif self.phase == "goal":
            self.message = "Goal detected!"
            self.phase = "reveal"
            self.next_delay = 0.45

        elif self.phase == "reveal":                       # draw the path one cell at a time
            path = self.search.path
            if self.path_cursor == 0:
                self.message = "Path reconstructed."
            if self.path_cursor < len(path):
                self.shown_path.append(path[self.path_cursor])
                self.path_cursor += 1
                self.next_delay = 0.025
            else:
                self.stat_len, self.stat_cost = self.search.length, self.search.cost
                self.stat_time = self.search.time
                self.phase = "travel"
                self.path_cursor = 1                       # path[0] is the ship's own cell
                self.message = f"{self.search.name}: travelling along the path…"
                self.next_delay = 0.5

        elif self.phase == "travel":                       # fly the path, one cell per frame
            path = self.search.path
            if self.path_cursor < len(path):
                self._enter(path[self.path_cursor])
                self.path_cursor += 1
                if self.over:
                    return
                self.next_delay = 0.15
            if self.phase == "travel" and self.path_cursor >= len(path):
                self.phase = "idle"
                self.message = ("" if self.target() is None
                                else "Objective reached. Press Find Path for the next target.")
