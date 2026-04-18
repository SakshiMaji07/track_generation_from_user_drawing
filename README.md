## Features

- **Freehand track drawing** — click and drag inside the canvas to draw a centerline. The track must start inside the green START circle and end inside the red END circle to form a valid closed loop.
- **Real-time self-intersection detection** — the canvas checks for crossovers as you draw. If the path would self-intersect, drawing stops immediately and a popup prompts you to clear and redraw.
- **Automatic cone generation** — once a valid track is drawn, blue (left), yellow (right), and big-orange (start gate) cones are placed along the track at configurable spacing using normal-offset geometry.
- **Load existing CSVs** — you can load a previously exported CSV back into the designer to preview its cones on the canvas.
- **One-click simulator launch** — the app launches FSDS directly with the selected CSV via subprocess, passing the custom map path as a CLI argument.
- **Live telemetry & lap validation** — in `track_generator_app_updated.py`, the FSDS adapter polls the simulator for car position and collision data. The lap validator tracks checkpoint progression, blocks reverse exploits, and detects lap completion.
- **Leaderboard** — lap results (time, cone hits, checkpoints) are stored in a local SQLite database keyed by a SHA-256 map fingerprint. The leaderboard modal shows results for the current map and an RAMS-e vs Human duel tab.
- **RAMS-e support** — a separate run mode enables API control for an autonomous agent (RAMS-e) to drive the track, with results tracked separately for head-to-head comparison against human drivers.

---

## Project structure

```
├── main.py                   # Standalone track designer (simpler, no telemetry)
├── track_generator_app.py    # Full app — FSDS integration, telemetry, leaderboard
│
├── cone_generation.py        # Basic cone placement (offset normals, simple)
├── fsds_cone_generation.py   # Production cone generator (spline sampling, spacing filters)
│
├── csv_writer.py             # Exports cone data to FSDS-compatible CSV
├── validate.py               # Track geometry validation + lap checkpoint logic
│
├── fsds_adapter.py           # Non-blocking FSDS client wrapper (no ROS required)
├── leaderboard_backend.py    # SQLite leaderboard — insert and query lap results
│
├── ui_components.py          # All Pygame drawing: panels, buttons, modals, sparks
│
├── leaderboard.db            # SQLite database (auto-created on first run)
└── requirements.txt          # Python dependencies
```

---

## How it works

### 1. Drawing the track

When you hold the mouse button down inside the **green START circle** and drag across the canvas, the app records each pixel position. While drawing:

- Points are appended only if they're at least 2px from the previous point (in `main.py`) or non-duplicate (in `track_generator_app.py`).
- On every new point, a `shapely.geometry.LineString` check runs to catch self-intersections before they're committed. Drawing halts immediately if a crossing is detected.
- When you release inside the **red END circle**, the raw point list is closed into a loop by appending the end and start anchor points.

The track is then validated against these rules:
- Minimum 4 distinct points
- Must start and end at the anchor circles
- No self-intersections
- Line length ≥ 80 pixels (`main.py`) or enclosed polygon area ≥ 1200 m² (`validate.py`)

### 2. Cone generation

`fsds_cone_generation.py` is the main cone engine. After the track passes validation:

1. The closed pixel path is converted to meters using `METERS_PER_PIXEL = 0.1`.
2. The centerline is resampled at uniform intervals (`CONE_STEP = 2.0 m`) using cumulative arc-length interpolation — this avoids clustering cones in sections where mouse input was denser.
3. At each sample point, the outward normal vector is computed. Blue cones go `+1.5 m` to the left and yellow cones `−1.5 m` to the right along the normal.
4. A spacing filter removes any cones closer than `MIN_CONE_SPACING` to their neighbours, preventing bunching.
5. **Start gate**: Four big-orange cones are placed at `±1.5 m` offset, 1.5 m behind and 1.5 m ahead of the track's first point. The zone around the start is then cleared of blue/yellow cones to avoid overlap.

### 3. Export

`csv_writer.py` centres all cone coordinates on the centroid of the orange (start gate) cones, then shifts everything 4.0 m forward along X so the car spawns slightly behind the start gate. Each row in the output CSV:

```
color, x, y, 0.0, 0.0, 0.0, 0.0
```

A SHA-256 fingerprint of the entire cone set (track points + all three cone arrays, JSON-serialised and hashed) is computed and stored alongside the file path. This is the key the leaderboard uses to tie lap records to a specific map version, so renaming or moving the CSV file won't orphan results.

### 4. FSDS integration

`fsds_adapter.py` wraps the FSDS Python client in a non-blocking pattern so Pygame's event loop never freezes waiting for the simulator:

- `launch_simulator()` spawns FSDS in a separate console process (`CREATE_NEW_CONSOLE` on Windows) and returns immediately.
- `try_connect()` is called once per frame. It attempts `FSDSClient().confirmConnection()` and sets a connected flag when it succeeds, with a configurable timeout (default 25 seconds).
- `poll()` retrieves the car's estimated position and timestamp, and calls `simGetCollisionInfo()` to count cone hits — filtering by object name (`cone`, `yellow`, `blue`, `orange`) to ignore irrelevant collisions. Duplicate collision stamps are deduplicated so a single hit isn't counted multiple times.
- API control (for RAMS-e mode) is only enabled when the run is explicitly started in autonomous mode. In Human mode, the client explicitly disables API control so keyboard driving works normally.

### 5. Lap validation

`validate.py` implements a checkpoint-based validator that runs entirely on telemetry from the FSDS adapter:

- 10 checkpoints are distributed evenly along the track's arc length using the same cumulative interpolation as the cone generator.
- A checkpoint is "passed" when the car moves through it in the forward direction — detected by checking which side of the normal plane the car occupied in the previous frame versus the current one (sign change in dot product).
- Checkpoints must be passed in order. The lap is not completed until checkpoint 0 is crossed again after all others.
- Two anti-exploit rules are enforced: at least 95% of checkpoints must be passed, and total distance travelled must be ≥ 70% of the track's total arc length (blocks reversing back to the finish line).
- On a valid lap, the driver is prompted for their name, and the result is written to SQLite.

### 6. Leaderboard

`leaderboard_backend.py` manages a `laps` table in SQLite with these columns: `map_hash`, `map_name`, `player_name`, `source`, `lap_time_s`, `cone_hits`, `checkpoints_passed`, `total_checkpoints`, `created_at`.

Records are always queried by `map_hash` so scores are tied to a specific track layout regardless of filename. The duel tab compares RAMS-e and Human entries pairwise by insertion order — RAMS-e is only awarded a win if it beats the human on both lap time AND cone hits simultaneously. Mixed results (better time but more cones, or vice versa) are ignored.

---

## Setup

**Requirements:**
- Python 3.9+
- FSDS v2.2.0 for Windows — download separately from the FSDS project releases
- The `fsds` Python client library placed in a `fsds/` folder next to the scripts (gitignored)

**Install dependencies:**

```bash
pip install numpy scipy matplotlib shapely pygame
```

**Configure paths** in `track_generator_app.py` (top of file):

```python
FSDS_PYTHON_PATH        = "path/to/fsds"           # folder containing the fsds Python package
FSDS_SIMULATOR_EXE      = "path/to/FSDS.exe"
FSDS_SETTINGS_JSON      = "path/to/settings.json"
FSDS_CUSTOM_MAP_TEMPLATE = '-CustomMapPath="{csv_path}"'
```

If using `main.py` instead, set `FSDS_EXE_PATH` on line 49.

**Run:**

```bash
python track_generator_app.py   # full app with telemetry + leaderboard
# or
python main.py                  # simpler designer only
```

---

## Controls

| Action | How |
|---|---|
| Start drawing | Click and hold inside the **green START circle** |
| Draw track | Drag mouse across the canvas |
| Finish track | Release inside the **red END circle** |
| Save to CSV | Click **Save CSV** (only enabled when track is valid) |
| Load a CSV | Click **Load CSV** |
| Launch FSDS (human) | Click **Run FSDS** (requires a saved/loaded CSV) |
| Launch FSDS (RAMS-e) | Click **Try RAMS-e** (enables API control in the simulator) |
| Clear canvas | Click **Clear Track** or dismiss an error popup |
| View leaderboard | Opens automatically after a lap completes |

---

## Track rules (enforced automatically)

- Track must form a closed loop through the start/end anchor circles.
- No self-intersections — the path cannot cross itself at any point during drawing.
- Minimum enclosed area of 1200 m² (prevents trivially small or hairpin-only loops).
- Track must be long enough to place at least 10 meaningful checkpoints.

