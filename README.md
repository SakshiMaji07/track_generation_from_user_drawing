# IITRMS Autonomous Track Generator

A Python-based UI to draw, save, load, and run custom FSDS tracks.

## Features

- Draw a track in the UI
- Auto-generate blue, yellow, and orange cones
- Save map as FSDS CSV
- Auto-save paired path file as `<map_name>_path.csv`
- Load existing CSV maps with preview
- Run human driving in FSDS
- Run RAMS-e pure pursuit controller on saved path
- Show live lap stats and leaderboard
- Store lap results in SQLite

## Main Files

- `track_generator_app_updated.py` - main app and controller runner
- `fsds_cone_generation.py` - cone generation from drawn track
- `csv_writer.py` - exports FSDS map CSV
- `fsds_adapter.py` - launches and connects to FSDS
- `leaderboard_backend.py` - SQLite leaderboard backend
- `race_ui.py` - live race stats overlay
- `ui_components.py` - UI drawing and layout helpers

## How to Run

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run: ```python track_generator_app_updated.py```