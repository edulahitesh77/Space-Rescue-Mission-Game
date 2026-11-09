"""Space Rescue Mission: AI Search Challenge (Solara front end, Mesa back end).

Run from this folder:
    solara run app.py
then open the local link it prints (http://localhost:8765).

  index.html  -> page structure (parsed and rebuilt as Solara components, see html_bridge.py)
  style.css   -> the look (loaded straight from disk with solara.Style)
  space_model.py -> the Mesa model: grid, agents, rules, step()
  search.py   -> BFS, DFS and A* search
"""
import html as H
import random
import time
from functools import partial
from pathlib import Path

import solara

from html_bridge import Slot, Template
from search import ALGORITHMS
from space_model import (DIFFICULTY, MISSIONS, N, REFUEL, STATION, SpaceRescueModel, heuristic)

HERE = Path(__file__).parent
TEMPLATE = Template(HERE / "index.html")
STYLE_FILE = HERE / "style.css"

# Icons: the same line-icon paths as the original script.js
ICON_PATHS = {
    "ship": '<path d="M12 2c3 3 4 7 4 11l-4 3-4-3c0-4 1-8 4-11z"/><circle cx="12" cy="9" r="1.6"/><path d="M8 14l-3 4 3-1M16 14l3 4-3-1M12 17v4"/>',
    "astro": '<circle cx="12" cy="8" r="5"/><rect x="9" y="6.5" width="6" height="3.5" rx="1.7"/><path d="M5 21v-3a4 4 0 014-4h6a4 4 0 014 4v3"/>',
    "station": '<rect x="9" y="9" width="6" height="6" rx="1"/><path d="M2 10h5v4H2zM17 10h5v4h-5zM12 3v6M12 15v6"/>',
    "asteroid": '<path d="M7 4l6-1 5 4 2 6-3 5-7 2-5-4-1-6z"/><circle cx="10" cy="10" r="1.3"/><circle cx="15" cy="14" r="1"/>',
    "planet": '<circle cx="12" cy="12" r="5"/><path d="M3 15c3 3 15-2 18-6"/>',
    "danger": '<path d="M13 2L5 14h6l-1 8 8-12h-6z"/>',
    "fuel": '<path d="M5 21V5a2 2 0 012-2h5a2 2 0 012 2v16M4 21h11M14 9h2a2 2 0 012 2v5a1.5 1.5 0 003 0V9l-3-3M7 7h5"/>',
}
KIND_ICON = {"asteroid": "asteroid", "planet": "planet", "danger": "danger", "fuel": "fuel"}
KIND_CODE = {"asteroid": 1, "planet": 2, "danger": 3, "fuel": 4}     # matches .t1 .. .t4 in style.css
ALGO_COLORS = {"BFS": "#60a5fa", "DFS": "#fbbf24", "A*": "#34d399"}
LEGEND = [("ship", "Your ship"), ("astro", "Astronaut"), ("station", "Space Station"),
          ("asteroid", "Asteroid (blocked)"), ("planet", "Planet (blocked)"),
          ("danger", "Danger (cost 4)"), ("fuel", f"Fuel +{REFUEL}")]

LEARN = [
    ("Why BFS is uninformed", "BFS has no idea where the goal is. It simply expands the nearest nodes first (a queue), so it spreads out in every direction. With equal step costs the first time it reaches the goal is the shortest path."),
    ("Why DFS is uninformed", "DFS also has no knowledge of the goal. It follows one branch as deep as possible (a stack) then backtracks, so it may find a long, winding path."),
    ("Why A* is informed", "A* uses a heuristic h(n), an estimate of the distance to the goal, to choose the most promising node using f(n) = g(n) + h(n)."),
    ("What is a heuristic?", "An educated guess. Here it is the Manhattan distance: |row difference| + |column difference|. It never over-estimates, so A* stays optimal."),
    ("Why A* explores fewer nodes", "Nodes pointing away from the goal get a high f(n) and are postponed, so A* rarely wastes effort on them."),
    ("Why DFS can be longer", "DFS accepts the first route it stumbles on, not the best one, so path length and cost can be far higher than BFS or A*."),
    ("Danger zones (cost 4)", "BFS minimises the number of steps, not the cost, so it may cross danger zones. A* uses real costs g(n) and can find a cheaper route."),
]
FUNDAMENTALS = [
    ("State space", "Every free cell the ship could be in."), ("Initial state", "The starting ship location."),
    ("Goal state", "An astronaut or the Space Station."), ("Actions", "Move up, down, left or right."),
    ("Path cost", "Total fuel: 1 per move, 4 in a danger zone."), ("Search tree", "The tree of states the algorithm expands, shown as visited cells."),
    ("Uninformed search", "BFS and DFS: no goal knowledge."), ("Informed search", "Uses extra knowledge (a heuristic) about the goal."),
    ("Heuristic function", "h(n): estimated distance from a cell to the target."), ("A* search", "Expands the node with the lowest f(n) = g(n) + h(n)."),
]


def esc(s) -> str:
    return H.escape(str(s), quote=True)


def icon(name: str) -> str:
    return f'<svg class="ic" viewBox="0 0 24 24">{ICON_PATHS[name]}</svg>'


# ---------------------------------------------------------------- game controller
class Game:
    """Holds the Mesa model and the UI state shared by every part of the page.
    Module-level state: one shared game for the local app (open one browser tab at a time)."""

    def __init__(self):
        self.model = SpaceRescueModel(0, 0)
        self.screen = solara.reactive("home")          # home | game | lab | learn
        self.settings_open = solara.reactive(False)
        self.version = solara.reactive(0)              # bump to re-render after a model change
        self.run_token = solara.reactive(0)            # bump to (re)start the animation loop
        self.compare = None                            # (goal, results) from the AI Search Lab

    def touch(self):
        self.version.value += 1

    def restart_animation(self):
        self.run_token.value += 1
        self.touch()

    def new_map(self, mission=None, difficulty=None):
        old = self.model
        mi = old.mission_index if mission is None else mission
        di = old.difficulty_index if difficulty is None else difficulty
        self.model = SpaceRescueModel(mi, di)
        self.model.speed = old.speed
        self.model.algorithm = old.algorithm
        self.compare = None
        self.restart_animation()


GAME = Game()


@solara.component_vue(str(HERE / "key_listener.vue"))
def KeyListener(event_key_press=None):
    pass


def handle_key_press(key: str):
    if GAME.screen.value != "game":
        return
    if GAME.model.busy or GAME.model.over:
        return
    d_map = {
        "up": (-1, 0),
        "down": (1, 0),
        "left": (0, -1),
        "right": (0, 1),
    }
    if key in d_map:
        dr, dc = d_map[key]
        move(dr, dc)


# ---------------------------------------------------------------- actions (button callbacks)
def go(screen: str):
    GAME.screen.value = screen
    if screen == "lab" and GAME.compare is None:
        run_compare()


def run_compare():
    GAME.compare = GAME.model.run_compare()
    GAME.touch()


def find_path():
    if GAME.model.begin_search():
        GAME.restart_animation()
    else:
        GAME.touch()


def toggle_pause():
    GAME.model.paused = not GAME.model.paused
    GAME.touch()


def step_one():
    if GAME.model.step_forward():
        GAME.touch()


def reset_mission():
    GAME.model.reset()
    GAME.restart_animation()


def move(dr: int, dc: int):
    GAME.model.manual_move(dr, dc)                    # a blocked move simply bumps (no change)
    GAME.touch()


def choose_algorithm(key: str):
    if not GAME.model.busy:
        GAME.model.algorithm = key
        GAME.touch()


def set_speed(value: int):
    GAME.model.speed = int(value)
    GAME.touch()


def end_action(action: str):
    m = GAME.model
    if action == "next":
        GAME.new_map(mission=(m.mission_index + 1) % len(MISSIONS))
    elif action in ("retry", "algo"):
        reset_mission()
    elif action == "cmp":
        go("lab")
        run_compare()
    elif action == "menu":
        go("home")
    GAME.touch()


# ---------------------------------------------------------------- HTML builders for dynamic parts
def tooltip(m: SpaceRescueModel, coord) -> str:
    r, c = coord
    kind = m.terrain.get(coord)
    if kind in ("asteroid", "planet"):
        state = "Obstacle"
    elif coord in m.shown_path:
        state = "Final path"
    elif coord in m.visited:
        state = "Visited"
    elif coord == m.ship_pos:
        state = "Ship"
    elif kind == "danger":
        state = "Danger zone"
    elif kind == "fuel":
        state = "Fuel station"
    else:
        state = "Unexplored"
    parts = [f"Node: ({r}, {c})", f"State: {state}"]
    entry = m.visited.get(coord)
    if entry is not None:
        parts.append(f"Cost g(n): {entry['g']}")
        if m.algorithm == "astar":
            parts += [f"Heuristic h(n): {entry['h']}", f"Total f(n): {entry['f']}", "f(n) = g(n) + h(n)"]
    elif kind not in ("asteroid", "planet") and m.target() is not None:
        parts.append(f"Heuristic h(n): {heuristic(coord, m.target())}")
    return esc(" · ".join(parts))


def board_html(m: SpaceRescueModel) -> str:
    cells = []
    for i in range(N * N):
        coord = divmod(i, N)
        kind = m.terrain.get(coord)
        classes = ["cell"]
        extra_style = ""
        if kind:
            classes.append(f"t{KIND_CODE[kind]}")
            body = icon(KIND_ICON[kind])
            if kind == "fuel" and coord in m.used_depots:
                extra_style = ' style="opacity:.5"'
        elif coord == STATION and m.mission["station"]:
            classes.append("goal")
            body = icon("station")
        elif coord in m.astronaut_coords and coord not in m.rescued:
            classes.append("goal")
            body = icon("astro")
        else:
            body = ""
        if coord in m.visited:
            classes.append("vis")
        if coord == m.current:
            classes.append("cur")
        if coord in m.shown_path:
            classes.append("path")
        cells.append(f'<div class="{" ".join(classes)}" title="{tooltip(m, coord)}"{extra_style}>{body}</div>')
    return "".join(cells)


def mini_board_svg(m: SpaceRescueModel, visited, path, start, goal) -> str:
    rects = []
    for i in range(N * N):
        r, c = divmod(i, N)
        kind = m.terrain.get((r, c))
        fill = "#3a2330" if kind in ("asteroid", "planet") else "#4a3a12" if kind == "danger" else "#0e1630"
        if (r, c) in visited:
            fill = "#0f6a8e"
        if (r, c) in path:
            fill = "#34d399"
        rects.append(f'<rect x="{c + .06}" y="{r + .06}" width=".88" height=".88" rx=".12" fill="{fill}"/>')
    for node, col in ((start, "#fff"), (goal, "#22d3ee")):
        if node is not None:
            rects.append(f'<circle cx="{node[1] + .5}" cy="{node[0] + .5}" r=".41" fill="{col}"/>')
    return f'<svg class="mini" viewBox="0 0 {N} {N}" role="img" aria-label="Search map">{"".join(rects)}</svg>'


def compare_cards_html(m: SpaceRescueModel) -> str:
    if GAME.compare is None:
        return ""
    goal, results = GAME.compare
    cards = []
    for key in ("bfs", "dfs", "astar"):
        r = results[key]
        cards.append(
            f'<div class="panel"><span class="tag">{ALGORITHMS[key]["kind"]}</span><h2>{r.name}</h2>'
            f'{mini_board_svg(m, {x["node"] for x in r.log}, set(r.path), m.ship_pos, goal)}'
            f'<dl><dt>Nodes Explored</dt><dd>{r.explored}</dd><dt>Path Length</dt><dd>{r.length if r.found else "–"}</dd>'
            f'<dt>Cost</dt><dd>{r.cost if r.found else "–"}</dd><dt>Time</dt><dd>{r.time:.4f} s</dd></dl></div>')
    return "".join(cards)


def compare_chart_html() -> str:
    if GAME.compare is None:
        return ""
    _goal, results = GAME.compare
    rows = list(results.values())

    def bars(key, label):
        mx = max(getattr(r, key) for r in rows) or 1
        items = "".join(
            f'<div class="barrow"><b>{r.name}</b><i style="width:{getattr(r, key) / mx * 100}%;'
            f'background:{ALGO_COLORS[r.name]}"></i><span>{getattr(r, key)}</span></div>' for r in rows)
        return f"<h3>{label}</h3>{items}"

    return (bars("explored", "Nodes explored (lower = more efficient)")
            + bars("cost", "Path cost (lower = better route)"))


def end_stats_html(m: SpaceRescueModel) -> str:
    el = m.end_seconds
    mm = f"{el // 60:02d}:{el % 60:02d}"
    pct = max(0, round(m.fuel / m.fuel_max * 100))
    return (f"<dl><dt>Search Algorithm</dt><dd>{esc(', '.join(m.algorithms_used) or 'Manual')}</dd>"
            f"<dt>Total Nodes Explored</dt><dd>{m.total_explored}</dd>"
            f"<dt>Path Length (steps)</dt><dd>{m.steps}</dd><dt>Path Cost</dt><dd>{m.path_cost}</dd>"
            f"<dt>Fuel Remaining</dt><dd>{pct}%</dd>"
            f"<dt>Astronauts Rescued</dt><dd>{len(m.rescued)} / {m.mission['astronauts']}</dd>"
            f"<dt>Mission Time</dt><dd>{mm}</dd></dl>")


LEARN_HTML = (
    "<h2>AI explained simply</h2><div class=\"learn-grid\">"
    + "".join(f'<div class="panel"><h3>{t}</h3><p>{p}</p></div>' for t, p in LEARN)
    + "</div><h2>Fundamentals of AI used</h2><div class=\"learn-grid\">"
    + "".join(f'<div class="panel"><h3>{i + 1}. {t}</h3><p>{p}</p></div>' for i, (t, p) in enumerate(FUNDAMENTALS))
    + "</div>")


def stars_svg() -> str:
    rng = random.Random(7)                                   # fixed field: no JS animation needed
    dots = "".join(
        f'<circle cx="{rng.random() * 100:.2f}%" cy="{rng.random() * 100:.2f}%" r="{rng.choice([.9, 1.2, 1.6])}" '
        f'fill="#cfe8ff" opacity="{rng.uniform(.25, .8):.2f}"/>' for _ in range(160))
    return f'<svg width="100%" height="100%" aria-hidden="true">{dots}</svg>'


# ---------------------------------------------------------------- HTML template hooks
class Hooks:
    """Tells the template bridge what each element means in this app."""

    def __init__(self):
        self.m = GAME.model
        self.screen = GAME.screen.value
        self.slots = self._slots()

    # what is visible
    def visible(self, node):
        nid = node.id
        if nid in ("home", "game", "lab", "learn"):
            return nid == self.screen
        if nid == "settings":
            return GAME.settings_open.value
        if nid == "end":
            return self.m.over
        if nid == "tip":
            return False
        return "hidden" not in node.attrs

    def skip(self, node):
        # The sound checkbox needed the original JavaScript; it is left out of the Python version.
        return node.tag == "label" and node.has_descendant(lambda n: n.id == "soundChk")

    def replace(self, node):
        if node.tag == "canvas" and node.id == "stars":
            return solara.HTML("div", unsafe_innerHTML=stars_svg(), attributes={"id": "stars", "aria-hidden": "true"})
        return None

    def slot(self, node):
        return self.slots.get(node.id)

    def is_live(self, node):
        """True for elements the bridge must build as Solara components (not copy as static HTML)."""
        return node.tag in ("button", "input", "canvas") or node.id in self.slots

    def widget(self, node):
        if node.id == "speed":
            return solara.SliderInt(label="", value=self.m.speed, min=1, max=100, on_value=set_speed)
        return None

    def button(self, node, parent_id):
        m = self.m
        label = node.text_content().strip()
        classes = list(node.classes)
        action = None
        if "data-go" in node.attrs:
            action = partial(go, node.attrs["data-go"])
        elif node.id == "findBtn":
            action = find_path
        elif node.id == "pauseBtn":
            label = "Resume" if m.paused else "Pause"
            action = toggle_pause
        elif node.id == "stepBtn":
            action = step_one
        elif node.id == "resetBtn":
            action = reset_mission
        elif node.id == "cmpBtn":
            action = lambda: (go("lab"), run_compare())
        elif node.id == "runCmp":
            action = run_compare
        elif node.id in ("openSettings", "openSettings2"):
            action = lambda: GAME.settings_open.set(True)
        elif node.id == "closeSettings":
            action = lambda: GAME.settings_open.set(False)
        elif parent_id == "missionSeg":
            i = int(node.attrs["data-m"])
            action = partial(GAME.new_map, mission=i)
            if i == m.mission_index:
                classes.append("is-on")
        elif parent_id == "diffSeg":
            i = int(node.attrs["data-d"])
            action = partial(GAME.new_map, difficulty=i)
            if i == m.difficulty_index:
                classes.append("is-on")
        elif "data-d" in node.attrs:
            dr, dc = (int(x) for x in node.attrs["data-d"].split(","))
            action = partial(move, dr, dc)
        return solara.Button(label=label, on_click=action, classes=classes)

    # what goes inside each element with an id
    def _slots(self):
        m = self.m
        mission = m.mission
        pct = max(0, m.fuel / m.fuel_max * 100)
        bar = "var(--bad)" if pct < 25 else "var(--warn)" if pct < 50 else "var(--ok)"
        if m.target() is None:
            obj = "Done"
        elif m.target() == STATION:
            obj = "Reach the Space Station"
        else:
            obj = f"Rescue astronaut {m.astronaut_coords.index(m.target()) + 1}"
        r, c = m.ship_pos
        a = ALGORITHMS[m.algorithm]
        algo_card = (f'<span class="tag">{a["kind"]} SEARCH</span><br><b>{a["name"]}</b> — {a["text"]}'
                     f'<br><code>{a["formula"]}</code>')
        t_min = m.stat_time
        s = {
            "mNum": Slot(html=esc(f"MISSION 0{m.mission_index + 1}")),
            "mName": Slot(html=esc(mission["name"])),
            "mObj": Slot(html=esc(mission["obj"])),
            "fuelBar": Slot(html="", attrs={"style": f"width:{pct:.1f}%;background:{bar}"}),
            "fuelTxt": Slot(html=esc(f"{m.fuel} / {m.fuel_max}") + ("  ⚠ LOW" if pct < 25 else "")),
            "resTxt": Slot(html=esc(f"{len(m.rescued)} / {mission['astronauts']}")),
            "objTxt": Slot(html=esc(obj)),
            "legend": Slot(html="".join(f"<li>{icon(k)}{esc(t)}</li>" for k, t in LEGEND)),
            "algos": Slot(children=[
                solara.Button(
                    on_click=partial(choose_algorithm, key),
                    disabled=m.busy,
                    classes=["algo"] + (["is-on"] if key == m.algorithm else []),
                    children=[solara.HTML("div", unsafe_innerHTML=f"<b>{v['name']}</b><span>{v['kind']}</span>")])
                for key, v in ALGORITHMS.items()]),
            "algoCard": Slot(html=algo_card),
            "grid": Slot(html=board_html(m)),
            "ship": Slot(html=icon("ship"), attrs={"style": f"transform:translate({c * 100}%,{r * 100}%)"}),
            "status": Slot(html=esc(m.message)),
            "sNodes": Slot(html=str(len(m.visited))),
            "sLen": Slot(html=str(m.stat_len)),
            "sCost": Slot(html=str(m.stat_cost)),
            "sTime": Slot(html=f"{t_min:.4f} s" if t_min else "0.000 s"),
            "sFuel": Slot(html=str(m.fuel_spent)),
            "heroArt": Slot(html=icon("ship")),
            "cmpCards": Slot(html=compare_cards_html(m)),
            "chart": Slot(html=compare_chart_html()),
            "learnBody": Slot(html=LEARN_HTML),
            "endBox": Slot(attrs={"class": "dialog good" if m.outcome == "won" else "dialog badx"},
                           children=self._end_children() if m.over else []),
        }
        return s

    def _end_children(self):
        m = GAME.model
        if m.outcome == "won":
            header = ("<p class=\"eyebrow\">🎉 Mission success</p><h2>MISSION COMPLETE</h2>"
                      f"<p class=\"muted\">{'All astronauts are safe on the station.' if m.mission['station'] else 'Astronaut rescued.'}</p>")
            buttons = [("Next Mission", partial(end_action, "next"), True),
                       ("Replay", partial(end_action, "retry"), False),
                       ("Compare Algorithms", partial(end_action, "cmp"), False)]
        else:
            header = ("<p class=\"eyebrow\">Out of fuel</p><h2>MISSION FAILED</h2>"
                      "<p class=\"muted\">Your spacecraft ran out of fuel before reaching the objective. "
                      "Tip: try A* — it avoids wasteful detours.</p>")
            buttons = [("Retry Mission", partial(end_action, "retry"), True),
                       ("Change Algorithm", partial(end_action, "algo"), False),
                       ("Return to Menu", partial(end_action, "menu"), False)]
        out = [solara.HTML("div", unsafe_innerHTML=header + end_stats_html(m))]
        for label, fn, primary in buttons:
            out.append(solara.Button(label=label, on_click=fn, classes=["btn", "primary"] if primary else ["btn"]))
        return out


solara.lab.theme.dark = True

# ---------------------------------------------------------------- Solara page
EXTRA_CSS = """
/* Force deep space sea-blue background across all Solara & Vuetify wrappers */
:root {
  --bg: #04060d;
  --navy: #0a1020;
  --card: #0f1830;
  --line: #1d2a4a;
  --tx: #e6edf9;
  --mut: #8b9bb8;
  --cy: #22d3ee;
  --ok: #34d399;
  --warn: #fbbf24;
  --bad: #f87171;
  --r: 14px;
  --board: #070b17;
}

html, body, #app, .v-application, .theme--light.v-application, .theme--dark.v-application,
.v-application--wrap, .v-main, .v-main__wrap {
  background: radial-gradient(120% 90% at 50% 0, #0c1530, var(--bg) 60%) !important;
  background-color: var(--bg) !important;
  color: var(--tx) !important;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif !important;
  min-height: 100vh !important;
}

.v-btn {
  text-transform: none !important;
  letter-spacing: normal !important;
  box-shadow: none !important;
  font: inherit !important;
  min-width: 0 !important;
}
.v-btn::before, .v-btn::after { display: none !important; }
.v-btn .v-btn__content { display: flex; align-items: center; justify-content: center; gap: 6px; }

/* Keep sci-fi button appearance */
.v-btn:not(.primary):not(.is-on):not(.ghost) {
  background: var(--card) !important;
  color: var(--tx) !important;
  border: 1px solid var(--line) !important;
  border-radius: 10px !important;
}

.v-btn.primary, .btn.primary {
  background: linear-gradient(135deg, #0e7490, #0891b2) !important;
  border-color: #22d3ee66 !important;
  color: #fff !important;
  font-weight: 700 !important;
  border-radius: 10px !important;
}

.v-btn.ghost, .btn.ghost {
  background: transparent !important;
  border: 1px solid transparent !important;
}

.v-btn:hover:not(:disabled) {
  border-color: var(--cy) !important;
  transform: translateY(-1px);
}

.algo.v-btn { display: flex !important; width: 100%; justify-content: flex-start !important; height: auto !important; }
.algo.v-btn .v-btn__content { display: grid; justify-items: start; text-align: left; width: 100%; }
.seg button.is-on, .algo.is-on { border-color: var(--cy) !important; background: #0b3a4a !important; }
.algo.is-on span { color: var(--cy); }
.mini { width: 100%; aspect-ratio: 1; border-radius: 10px; background: var(--board); margin: 8px 0; display: block; }
.v-slider__track-container, .v-input--slider { margin-top: 6px; }
"""


@solara.component
def Page():
    GAME.version.value                                  # re-render after every model change
    token = GAME.run_token.value
    model = GAME.model

    def animate(cancel):
        """Mesa's step() drives every animation frame, on a background thread."""
        while (not cancel.is_set() and GAME.model is model and GAME.run_token.value == token
               and model.busy):
            if model.paused:
                time.sleep(0.1)
                continue
            model.step()
            GAME.touch()
            time.sleep(model.next_delay)

    solara.use_thread(animate, dependencies=[token])

    body = TEMPLATE.render(Hooks())
    return solara.Div(children=[
        solara.Title("Space Rescue Mission: AI Search Challenge"),
        solara.Style(STYLE_FILE),
        solara.Style(EXTRA_CSS),
        KeyListener(event_key_press=handle_key_press),
        *body,
    ])


