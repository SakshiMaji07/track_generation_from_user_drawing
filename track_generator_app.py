import os
import sys
import hashlib
import json
import tkinter as tk
from tkinter import filedialog, simpledialog

import pygame

from csv_writer import export_csv
from fsds_cone_generation import generate_all_cones, METERS_PER_PIXEL, MIN_CONE_SPACING
from fsds_adapter import FSDSClientAdapter
from leaderboard_backend import LeaderboardDB
from ui_components import (
    build_fonts,
    build_layout,
    draw_cones,
    draw_custom_cursor,
    draw_invalid_popup,
    draw_leaderboard_modal,
    draw_loading_screen,
    draw_racing_background,
    draw_side_panel,
    draw_sparks,
    draw_track,
    draw_track_area,
    make_sparks,
    update_sparks,
)
from validate import validate_track, LapValidator, point_in_circle

import pathlib

# ============================================================
# CONFIGURE THESE FOR YOUR SYSTEM
# ============================================================
FSDS_PYTHON_PATH = str(pathlib.Path(__file__).parent / "fsds")
FSDS_SIMULATOR_EXE = str(pathlib.Path(__file__).parent.parent / "fsds-v2.2.0-windows/FSDS.exe")
FSDS_SETTINGS_JSON = str(pathlib.Path(__file__).parent.parent / "fsds-v2.2.0-windows/settings.json")
FSDS_CUSTOM_MAP_TEMPLATE = '-CustomMapPath="{csv_path}"'


# ============================================================

pygame.init()
pygame.display.set_caption("IITRMS Autonomous Track Generator")
pygame.mouse.set_visible(False)

DEFAULT_W, DEFAULT_H = 1440, 900
screen = pygame.display.set_mode((DEFAULT_W, DEFAULT_H), pygame.RESIZABLE)
clock = pygame.time.Clock()

fonts = build_fonts(DEFAULT_W, DEFAULT_H)
layout = build_layout(DEFAULT_W, DEFAULT_H)
sparks = make_sparks(DEFAULT_W, DEFAULT_H, count=26)

db = LeaderboardDB("leaderboard.db")

fsds = FSDSClientAdapter(
    fsds_python_path=FSDS_PYTHON_PATH,
    simulator_exe_path=FSDS_SIMULATOR_EXE,
    settings_json_path=FSDS_SETTINGS_JSON,
    custom_map_cli_template=FSDS_CUSTOM_MAP_TEMPLATE if FSDS_CUSTOM_MAP_TEMPLATE else None,
)

tk_root = tk.Tk()
tk_root.withdraw()

message = "Click inside GREEN to start drawing. Release inside RED to finish."
selected_csv_path = None
selected_map_name = "Untitled Map"

track_points = []
currently_drawing = False
pending_popup = None
show_leaderboard = False
leaderboard_tab = "map"

start_point = None
end_point = None
anchor_radius = 24

is_valid = False
lap_validator = None
current_map_hash = None

current_run_active = False
current_run_source = "Human"
telemetry_status = "Disconnected"

preview_blue = []
preview_yellow = []
preview_orange = []


def map_fingerprint(track_points_m, blue, yellow, orange):
    payload = {
        "track_points": track_points_m,
        "blue": blue,
        "yellow": yellow,
        "orange": orange,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def recalc_ui():
    global fonts, layout, sparks, anchor_radius, start_point, end_point
    width, height = screen.get_size()
    fonts = build_fonts(width, height)
    layout = build_layout(width, height)

    if len(sparks) < 10:
        sparks[:] = make_sparks(width, height, count=26)

    # UI can resize, but track points are NOT rescaled.
    anchor_radius = max(20, int(min(width, height) * 0.018))
    draw_rect = layout["DRAW_RECT"]

    start_point = (draw_rect.centerx + 75, draw_rect.centery - 100)
    end_point = (draw_rect.centerx - 75, draw_rect.centery - 100)


recalc_ui()
draw_loading_screen(screen, fonts, *screen.get_size(), 1000, clock, sparks)


def clear_track():
    global track_points, is_valid, pending_popup, message, lap_validator, current_map_hash
    global preview_blue, preview_yellow, preview_orange
    track_points = []
    is_valid = False
    pending_popup = None
    lap_validator = None
    current_map_hash = None
    preview_blue = []
    preview_yellow = []
    preview_orange = []
    message = "Track cleared. Click inside GREEN to start drawing."


def rebuild_cone_preview():
    global preview_blue, preview_yellow, preview_orange, current_map_hash
    if len(track_points) < 4 or not is_valid:
        preview_blue, preview_yellow, preview_orange = [], [], []
        return

    track_points_m = [(x * METERS_PER_PIXEL, y * METERS_PER_PIXEL) for x, y in track_points]
    blue_m, yellow_m, orange_m = generate_all_cones(track_points_m)

    preview_blue = [(x / METERS_PER_PIXEL, y / METERS_PER_PIXEL) for x, y in blue_m]
    preview_yellow = [(x / METERS_PER_PIXEL, y / METERS_PER_PIXEL) for x, y in yellow_m]
    preview_orange = [(x / METERS_PER_PIXEL, y / METERS_PER_PIXEL) for x, y in orange_m]

    current_map_hash = map_fingerprint(track_points_m, blue_m, yellow_m, orange_m)


def save_track_csv():
    global selected_csv_path, message, current_map_hash, selected_map_name
    if not is_valid or len(track_points) < 4:
        message = "Track must be valid before saving."
        return

    file_path = filedialog.asksaveasfilename(
        title="Save FSDS CSV",
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv")],
    )
    if not file_path:
        return

    track_points_m = [(x * METERS_PER_PIXEL, y * METERS_PER_PIXEL) for x, y in track_points]
    blue, yellow, orange = generate_all_cones(track_points_m)
    export_csv(file_path, blue, yellow, orange)

    selected_csv_path = file_path
    selected_map_name = os.path.splitext(os.path.basename(file_path))[0]
    current_map_hash = map_fingerprint(track_points_m, blue, yellow, orange)
    message = f"Saved map: {os.path.basename(file_path)}"


def load_csv():
    global selected_csv_path, selected_map_name, message
    path = filedialog.askopenfilename(
        title="Open CSV",
        filetypes=[("CSV Files", "*.csv")],
    )
    if not path:
        return
    selected_csv_path = path
    selected_map_name = os.path.splitext(os.path.basename(path))[0]
    message = f"Selected CSV: {os.path.basename(path)}"


def start_fsds_run(source="Human"):
    global message, current_run_active, current_run_source, show_leaderboard
    global lap_validator, telemetry_status

    if not selected_csv_path:
        message = "Save or load a CSV first."
        return

    # If user loaded a CSV but did not draw a valid track in this session,
    # allow launch anyway. Leaderboard validation only works when we have track points.
    use_validator = is_valid and len(track_points) >= 4

    if use_validator:
        track_points_m = [(x * METERS_PER_PIXEL, y * METERS_PER_PIXEL) for x, y in track_points]
        try:
            lap_validator = LapValidator(track_points_m, checkpoint_count=10)
        except Exception as e:
            telemetry_status = "Disconnected"
            message = f"Lap validator failed: {e}"
            return
    else:
        lap_validator = None

    try:
        # Human = keep keyboard/manual driving alive
        # RAMS-e = allow API control
        enable_api = (source == "RAMS-e")
        fsds.start_run(selected_csv_path, enable_api_control=enable_api)
        telemetry_status = "Connected"
    except Exception as e:
        telemetry_status = "Disconnected"
        message = f"FSDS launch/connect failed: {e}"
        return

    current_run_active = True
    current_run_source = source
    show_leaderboard = True

    if lap_validator is None:
        message = f"{source} run launched. Telemetry connected. No drawn-track validator active for loaded CSV-only session."
    else:
        message = f"{source} run launched. Waiting for lap..."

def process_fsds():
    global message, current_run_active, show_leaderboard, telemetry_status

    if not current_run_active:
        return

    frame = fsds.poll()
    if frame is None:
        telemetry_status = "Waiting"
        return

    telemetry_status = "Connected"

    # If no in-memory drawn track validator exists, we only keep telemetry alive
    # and do not try to save leaderboard laps automatically.
    if lap_validator is None:
        return

    events = lap_validator.update(
        car_pos=frame.car_position_xy_m,
        sim_time_s=frame.sim_time_s,
        cone_hits=frame.cone_hits,
    )

    if events["lap_started"]:
        message = "Lap started. Checkpoints armed."

    if events["checkpoint_passed"] is not None:
        cp_idx = events["checkpoint_passed"]
        message = f"Checkpoint {cp_idx} passed."

    if events["lap_invalid"]:
        message = f'Lap invalid: {events["reason"]}'
        current_run_active = False
        fsds.stop()

    if events["lap_finished"]:
        lap_time = lap_validator.get_lap_time()
        summary = lap_validator.get_summary()

        name = simpledialog.askstring("Lap Complete", "Enter driver name:")
        if not name:
            name = "Anonymous"

        db.insert_lap(
            map_hash=current_map_hash,
            map_name=selected_map_name,
            player_name=name,
            source=current_run_source,
            lap_time_s=lap_time,
            cone_hits=summary["cone_hits"],
            checkpoints_passed=summary["checkpoints_passed"],
            total_checkpoints=summary["total_checkpoints"],
        )

        message = f'Lap saved: {name} | {lap_time:.3f}s | cones hit: {summary["cone_hits"]}'
        current_run_active = False
        fsds.stop()
        show_leaderboard = True


running = True
while running:
    width, height = screen.get_size()
    recalc_ui()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.VIDEORESIZE:
            screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            recalc_ui()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos

            if show_leaderboard:
                map_rows = db.get_current_map_leaderboard(current_map_hash, limit=20) if current_map_hash else []
                duel_stats = db.get_duel_stats(current_map_hash) if current_map_hash else {"ramse_wins": 0, "human_wins": 0, "comparisons": 0}
                modal = draw_leaderboard_modal(screen, fonts, width, height, leaderboard_tab, map_rows, duel_stats)

                if modal["close"].collidepoint((mx, my)):
                    show_leaderboard = False
                elif modal["tab_map"].collidepoint((mx, my)):
                    leaderboard_tab = "map"
                elif modal["tab_duel"].collidepoint((mx, my)):
                    leaderboard_tab = "duel"

            elif pending_popup:
                clear_rect = draw_invalid_popup(screen, fonts, width, height, pending_popup["title"], pending_popup["body"])
                if clear_rect.collidepoint((mx, my)):
                    clear_track()

            else:
                if layout["SAVE_BUTTON"].collidepoint((mx, my)):
                    save_track_csv()
                elif layout["LOAD_BUTTON"].collidepoint((mx, my)):
                    load_csv()
                elif layout["RUN_BUTTON"].collidepoint((mx, my)):
                    start_fsds_run(source="Human")
                elif layout["RAMSE_BUTTON"].collidepoint((mx, my)):
                    start_fsds_run(source="RAMS-e")
                elif layout["CLEAR_BUTTON"].collidepoint((mx, my)):
                    clear_track()
                elif layout["DRAW_RECT"].collidepoint((mx, my)):
                    if not point_in_circle((mx, my), start_point, anchor_radius):
                        pending_popup = {
                            "title": "Invalid Start",
                            "body": "You must begin drawing inside the GREEN start circle.",
                        }
                        continue

                    currently_drawing = True
                    track_points = [(mx, my)]
                    is_valid = False
                    preview_blue, preview_yellow, preview_orange = [], [], []

        elif event.type == pygame.MOUSEMOTION:
            if currently_drawing and layout["DRAW_RECT"].collidepoint(event.pos):
                if not track_points or event.pos != track_points[-1]:
                    track_points.append(event.pos)

        elif event.type == pygame.MOUSEBUTTONUP:
            if currently_drawing:
                currently_drawing = False

                if not point_in_circle(event.pos, end_point, anchor_radius):
                    pending_popup = {
                        "title": "Invalid Finish",
                        "body": "You must stop drawing inside the RED end circle.",
                    }
                    is_valid = False
                    continue

                if len(track_points) >= 3:
                    track_points.append(start_point)

                if len(track_points) >= 4:
                    valid, msg = validate_track(track_points)
                    is_valid = valid
                    message = msg
                    if valid:
                        pending_popup = None
                        rebuild_cone_preview()
                    else:
                        pending_popup = {
                            "title": "Invalid Path",
                            "body": msg,
                        }

    process_fsds()

    draw_racing_background(screen, width, height)
    update_sparks(sparks, width, height)
    draw_sparks(screen, sparks)

    draw_side_panel(
        screen,
        layout,
        fonts,
        message=message,
        valid=is_valid,
        points_count=len(track_points),
        scale=METERS_PER_PIXEL,
        cone_spacing_m=MIN_CONE_SPACING,
        selected_csv_path=selected_csv_path,
        can_run_fsds=bool(selected_csv_path),
        telemetry_status=telemetry_status,
    )

    draw_rect = layout["DRAW_RECT"]
    draw_track_area(screen, draw_rect)
    draw_track(screen, track_points, is_valid, currently_drawing, start_point, end_point, anchor_radius, fonts)
    draw_cones(screen, preview_blue, preview_yellow, preview_orange)

    if pending_popup:
        draw_invalid_popup(screen, fonts, width, height, pending_popup["title"], pending_popup["body"])

    if show_leaderboard:
        map_rows = db.get_current_map_leaderboard(current_map_hash, limit=20) if current_map_hash else []
        duel_stats = db.get_duel_stats(current_map_hash) if current_map_hash else {"ramse_wins": 0, "human_wins": 0, "comparisons": 0}
        draw_leaderboard_modal(screen, fonts, width, height, leaderboard_tab, map_rows, duel_stats)

    draw_custom_cursor(screen, pygame.mouse.get_pos())

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()