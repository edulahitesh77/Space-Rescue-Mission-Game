# Space Rescue Mission: AI Search Challenge

A sci-fi themed grid-world simulation and game built with Python, Mesa, and Solara.

## Features
- **AI Search Algorithms**: Breadth-First Search (BFS), Depth-First Search (DFS), and A* Search with Manhattan heuristic.
- **Mesa Simulation Engine**: Discrete 15x15 Von Neumann grid modeling ship movement, obstacle navigation, danger zones, fuel consumption, and refuelling.
- **Solara Interactive UI**: Preserves original CSS styling, glowing accents, real-time animation, interactive map, HUD, and live AI statistics.
- **Interactive Controls**:
  - Full keyboard support: `W`, `A`, `S`, `D` and `Arrow` keys for manual flight.
  - On-screen directional pad.
  - Find Path, Pause, Resume, Step, Reset, and Compare.
  - Mission selector (Missions 1, 2, and 3) & Difficulty selector (Easy, Medium, Hard).
  - Search animation speed slider.
  - AI Search Lab for side-by-side comparison of BFS, DFS, and A*.
  - AI Explanation / Learning mode.

## Installation & Running

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python -m solara run app.py
```

3. Open your browser and navigate to:
[http://localhost:8765](http://localhost:8765)

