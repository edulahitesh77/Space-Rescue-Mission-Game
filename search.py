"""AI search algorithms for the Space Rescue Mission (ported from the original script.js).

Pure Python. Every function works on grid coordinates (row, col) and receives two callbacks
supplied by the Mesa model:

    neighbors(node) -> list of reachable neighbouring nodes   (the ACTIONS: up, right, down, left)
    step_cost(node) -> cost of ENTERING that node             (1, or 4 in a danger zone)

Every statistic is measured from the real run. Nothing is hard-coded.

    bfs(...)     UNINFORMED  uses a QUEUE (FIFO)
    dfs(...)     UNINFORMED  uses a STACK (LIFO)
    a_star(...)  INFORMED    uses a MIN-HEAP priority queue ordered by f(n) = g(n) + h(n)
"""
import heapq
import itertools
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

Node = Tuple[int, int]


@dataclass
class SearchResult:
    name: str
    found: bool
    log: List[dict]     # expansion order: {"node", "g", "h", "f"}  (h and f are None for BFS/DFS)
    path: List[Node]    # start ... goal, empty when not found
    explored: int       # number of expanded nodes (len(log))
    length: int         # number of moves on the path
    cost: int           # sum of step costs along the path
    time: float         # wall-clock seconds spent searching


def heuristic(a: Node, b: Node) -> int:
    """h(n): Manhattan distance. Admissible for 4-way movement when the cheapest step costs 1."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _reconstruct(came_from: Dict[Node, Optional[Node]], node: Node) -> List[Node]:
    """Walk the parent links backwards from the goal to the start."""
    path = [node]
    while came_from.get(node) is not None:
        node = came_from[node]
        path.append(node)
    path.reverse()
    return path


def _result(name, found, came_from, goal, log, t0, step_cost) -> SearchResult:
    path = _reconstruct(came_from, goal) if found else []
    cost = sum(step_cost(n) for n in path[1:])
    return SearchResult(name, found, log, path, len(log), max(0, len(path) - 1), cost,
                        time.perf_counter() - t0)


def bfs(start: Node, goal: Node, neighbors: Callable, step_cost: Callable) -> SearchResult:
    """BREADTH-FIRST SEARCH (uninformed): QUEUE, expands level by level."""
    t0 = time.perf_counter()
    queue = deque([start])
    came_from: Dict[Node, Optional[Node]] = {start: None}
    g = {start: 0}
    log, found = [], False
    while queue:
        cur = queue.popleft()                              # dequeue (FIFO)
        log.append({"node": cur, "g": g[cur], "h": None, "f": None})
        if cur == goal:
            found = True
            break
        for n in neighbors(cur):
            if n not in came_from:
                came_from[n] = cur
                g[n] = g[cur] + step_cost(n)
                queue.append(n)
    return _result("BFS", found, came_from, goal, log, t0, step_cost)


def dfs(start: Node, goal: Node, neighbors: Callable, step_cost: Callable) -> SearchResult:
    """DEPTH-FIRST SEARCH (uninformed): STACK, dives deep then backtracks."""
    t0 = time.perf_counter()
    stack = [start]
    came_from: Dict[Node, Optional[Node]] = {start: None}
    g = {start: 0}
    seen, log, found = set(), [], False
    while stack:
        cur = stack.pop()                                  # pop (LIFO): newest first
        if cur in seen:
            continue
        seen.add(cur)
        log.append({"node": cur, "g": g[cur], "h": None, "f": None})
        if cur == goal:
            found = True
            break
        for n in reversed(neighbors(cur)):
            if n not in seen:
                came_from[n] = cur
                g[n] = g[cur] + step_cost(n)
                stack.append(n)
    return _result("DFS", found, came_from, goal, log, t0, step_cost)


def a_star(start: Node, goal: Node, neighbors: Callable, step_cost: Callable) -> SearchResult:
    """A* SEARCH (informed): priority queue ordered by f(n) = g(n) + h(n)."""
    t0 = time.perf_counter()
    tie = itertools.count()                                # keeps heap entries comparable
    h0 = heuristic(start, goal)
    open_heap = [(h0, h0, next(tie), start, 0)]            # (f, h, tie, node, g)
    came_from: Dict[Node, Optional[Node]] = {start: None}
    g = {start: 0}
    closed, log, found = set(), [], False
    while open_heap:
        f, h, _, cur, _g = heapq.heappop(open_heap)        # most promising node (lowest f, then h)
        if cur in closed:                                  # stale heap entry
            continue
        closed.add(cur)
        log.append({"node": cur, "g": g[cur], "h": h, "f": f})
        if cur == goal:
            found = True
            break
        for n in neighbors(cur):
            ng = g[cur] + step_cost(n)                     # g(n): real cost from the start
            if ng < g.get(n, float("inf")):
                g[n] = ng
                came_from[n] = cur
                hn = heuristic(n, goal)                    # h(n): estimate to the goal
                heapq.heappush(open_heap, (ng + hn, hn, next(tie), n, ng))
    return _result("A*", found, came_from, goal, log, t0, step_cost)


ALGORITHMS = {
    "bfs": {"fn": bfs, "name": "BFS", "kind": "UNINFORMED", "formula": "Queue (FIFO)",
            "text": "Explores the search space level by level. Guarantees the fewest steps when every move costs the same."},
    "dfs": {"fn": dfs, "name": "DFS", "kind": "UNINFORMED", "formula": "Stack (LIFO)",
            "text": "Explores deeply along one branch before backtracking. Not guaranteed to find the shortest path."},
    "astar": {"fn": a_star, "name": "A*", "kind": "INFORMED", "formula": "f(n) = g(n) + h(n)",
              "text": "Uses the actual cost so far plus a heuristic estimate to head efficiently towards the goal."},
}
