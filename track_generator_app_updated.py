import csv
import os
import sys
import hashlib
import json
import math
import time
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog
import pathlib
import fsds
import pygame

from csv_writer import X_FORWARD_OFFSET, export_csv
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
from validate import validate_track, point_in_circle

# ============================================================
# GLOBAL FSDS / UI STATE
# ============================================================
fsds_client = None
last_doo_count = 0
last_lap_count = 0

FSDS_PYTHON_PATH = str(pathlib.Path(__file__).parent / "fsds")
FSDS_SIMULATOR_EXE = pathlib.Path(__file__).parent.parent / "fsds-v2.2.0-windows" / "FSDS.exe"
FSDS_SETTINGS_JSON = pathlib.Path(__file__).parent.parent / "fsds-v2.2.0-windows" / "settings.json"
FSDS_CUSTOM_MAP_TEMPLATE = '-CustomMapPath="{csv_path}"'

SMOOTHING_RESAMPLE_STEP_PX = 12.0
SMOOTHING_ITERATIONS = 3
CSV_PREVIEW_PADDING = 60

# ============================================================
# RAMS-e CONTROLLER CONFIG
# ============================================================
VEHICLE_NAME = "FSCar"
WHEELBASE = 1.5
TARGET_SPEED = 9.0
MAX_STEER_RAD = 0.4363

LD_MIN = 1.0
LD_K = 1.0

SPEED_KP = 0.4
SPEED_KI = 0.05
SPEED_KD = 0.1
BRAKE_THRESHOLD = 0.3
MAX_THROTTLE = 0.5

CONTROL_DT = 0.05
SEARCH_WINDOW = 20
LAP_THRESHOLD = 3.0

controller_thread = None
controller_stop_event = threading.Event()
controller_status = "Idle"

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

fsds_adapter = FSDSClientAdapter(
    fsds_python_path=FSDS_PYTHON_PATH,
    simulator_exe_path=FSDS_SIMULATOR_EXE,
    settings_json_path=FSDS_SETTINGS_JSON,
    custom_map_cli_template=FSDS_CUSTOM_MAP_TEMPLATE if FSDS_CUSTOM_MAP_TEMPLATE else None,
)

tk_root = tk.Tk()
tk_root.withdraw()

message = "Click inside GREEN to start drawing. Release inside RED to finish."
selected_csv_path = None
selected_path_csv_path = None
selected_map_name = "Untitled Map"

loaded_csv_preview_mode = False
preview_loaded_blue = []
preview_loaded_yellow = []
preview_loaded_orange = []

track_points = []
currently_drawing = False
pending_popup = None
show_leaderboard = False
leaderboard_tab = "map"

start_point = None
end_point = None
anchor_radius = 24

is_valid = False
current_map_hash = None

current_run_active = False
current_run_source = "Human"
telemetry_status = "Disconnected"

preview_blue = []
preview_yellow = []
preview_orange = []
preview_mode = "track"

live_run = None
live_driver_name = "Pending"
session_start_time = 0.0

# ============================================================
# HASHING / FINGERPRINTS
# ============================================================
def map_fingerprint(track_points_m, blue, yellow, orange):
    payload = {
        "track_points": track_points_m,
        "blue": blue,
        "yellow": yellow,
        "orange": orange,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def cone_only_fingerprint(blue, yellow, orange):
    return map_fingerprint([], blue, yellow, orange)


# ============================================================
# UI GEOMETRY
# ============================================================
def recalc_ui():
    global fonts, layout, sparks, anchor_radius, start_point, end_point

    width, height = screen.get_size()
    fonts = build_fonts(width, height)
    layout = build_layout(width, height)

    if len(sparks) < 10:
        sparks[:] = make_sparks(width, height, count=26)

    anchor_radius = max(20, int(min(width, height) * 0.018))
    draw_rect = layout["DRAW_RECT"]

    lane_half = max(60, int(draw_rect.width * 0.065))
    guide_y = draw_rect.top + max(90, int(draw_rect.height * 0.18))

    start_point = (draw_rect.centerx + lane_half, guide_y)
    end_point = (draw_rect.centerx - lane_half, guide_y)


# ============================================================
# TRACK HELPERS
# ============================================================
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def cumulative_lengths(points):
    vals = [0.0]
    for i in range(1, len(points)):
        vals.append(vals[-1] + dist(points[i - 1], points[i]))
    return vals


def resample_polyline(points, step_px):
    if len(points) < 2:
        return points[:]

    cum = cumulative_lengths(points)
    total = cum[-1]
    if total <= 1e-9:
        return points[:]

    out = [points[0]]
    s = step_px

    while s < total:
        for i in range(1, len(cum)):
            if s <= cum[i]:
                p0 = points[i - 1]
                p1 = points[i]
                seg = cum[i] - cum[i - 1]
                t = 0.0 if seg <= 1e-9 else (s - cum[i - 1]) / seg
                out.append((
                    p0[0] + t * (p1[0] - p0[0]),
                    p0[1] + t * (p1[1] - p0[1]),
                ))
                break
        s += step_px

    out.append(points[-1])
    return out


def chaikin_open(points, iterations=2):
    pts = points[:]
    if len(pts) < 3:
        return pts

    for _ in range(iterations):
        refined = [pts[0]]
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            q = (0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1])
            r = (0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1])
            refined.extend([q, r])
        refined.append(pts[-1])
        pts = refined

    return pts


def get_track_origin_pixels():
    return (
        (start_point[0] + end_point[0]) / 2.0,
        (start_point[1] + end_point[1]) / 2.0,
    )


def get_track_origin_meters():
    ox_px, oy_px = get_track_origin_pixels()
    return ox_px * METERS_PER_PIXEL, oy_px * METERS_PER_PIXEL


def smooth_finished_track(raw_points):
    if len(raw_points) < 3:
        return raw_points[:]

    midpoint = get_track_origin_pixels()

    pts = resample_polyline(raw_points, SMOOTHING_RESAMPLE_STEP_PX)
    pts = chaikin_open(pts, iterations=SMOOTHING_ITERATIONS)

    smoothed_body = []
    for p in pts[1:-1]:
        p = (float(p[0]), float(p[1]))
        if not smoothed_body or dist(p, smoothed_body[-1]) >= 3.0:
            smoothed_body.append(p)

    ordered = [midpoint, start_point]

    for p in smoothed_body:
        if dist(p, ordered[-1]) >= 3.0:
            ordered.append(p)

    if dist(end_point, ordered[-1]) >= 1.0:
        ordered.append(end_point)

    if dist(midpoint, ordered[-1]) >= 1.0:
        ordered.append(midpoint)
    else:
        ordered[-1] = midpoint

    return ordered


# ============================================================
# CSV PREVIEW
# ============================================================
def transform_csv_points_to_preview(points_local, draw_rect):
    if not points_local:
        return []

    world_pts = [(x - X_FORWARD_OFFSET, y) for x, y in points_local]
    xs = [p[0] for p in world_pts]
    ys = [p[1] for p in world_pts]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    width_m = max(max_x - min_x, 1e-6)
    height_m = max(max_y - min_y, 1e-6)

    usable_w = max(120, draw_rect.width - 2 * CSV_PREVIEW_PADDING)
    usable_h = max(120, draw_rect.height - 2 * CSV_PREVIEW_PADDING)
    scale = min(usable_w / width_m, usable_h / height_m)

    cx_m = (min_x + max_x) / 2.0
    cy_m = (min_y + max_y) / 2.0
    cx_px = draw_rect.centerx
    cy_px = draw_rect.centery

    preview = []
    for x, y in world_pts:
        px = cx_px + (x - cx_m) * scale
        py = cy_px + (y - cy_m) * scale
        preview.append((px, py))

    return preview


def load_csv_preview(path):
    blue_local, yellow_local, orange_local = [], [], []

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue

            color = row[0].strip().lower()
            try:
                x = float(row[1])
                y = float(row[2])
            except ValueError:
                continue

            if color == "blue":
                blue_local.append((x, y))
            elif color == "yellow":
                yellow_local.append((x, y))
            elif color in {"big_orange", "orange"}:
                orange_local.append((x, y))

    draw_rect = layout["DRAW_RECT"]
    return (
        transform_csv_points_to_preview(blue_local, draw_rect),
        transform_csv_points_to_preview(yellow_local, draw_rect),
        transform_csv_points_to_preview(orange_local, draw_rect),
        cone_only_fingerprint(blue_local, yellow_local, orange_local),
        len(blue_local),
        len(yellow_local),
        len(orange_local),
    )

import csv
import os
import sys
import hashlib
import json
import math
import time
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog
import pathlib
import fsds
import pygame

from csv_writer import X_FORWARD_OFFSET, export_csv
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
from validate import validate_track, point_in_circle

# ============================================================
# GLOBAL FSDS / UI STATE
# ============================================================
fsds_client = None
last_doo_count = 0
last_lap_count = 0

FSDS_PYTHON_PATH = str(pathlib.Path(__file__).parent / "fsds")
FSDS_SIMULATOR_EXE = pathlib.Path(__file__).parent.parent / "fsds-v2.2.0-windows" / "FSDS.exe"
FSDS_SETTINGS_JSON = pathlib.Path(__file__).parent.parent / "fsds-v2.2.0-windows" / "settings.json"
FSDS_CUSTOM_MAP_TEMPLATE = '-CustomMapPath="{csv_path}"'

SMOOTHING_RESAMPLE_STEP_PX = 12.0
SMOOTHING_ITERATIONS = 3
CSV_PREVIEW_PADDING = 60

# ============================================================
# RAMS-e CONTROLLER CONFIG
# ============================================================
VEHICLE_NAME = "FSCar"
WHEELBASE = 1.5
TARGET_SPEED = 9.0
MAX_STEER_RAD = 0.4363

LD_MIN = 1.0
LD_K = 1.0

SPEED_KP = 0.4
SPEED_KI = 0.05
SPEED_KD = 0.1
BRAKE_THRESHOLD = 0.3
MAX_THROTTLE = 0.5

CONTROL_DT = 0.05
SEARCH_WINDOW = 20
LAP_THRESHOLD = 3.0

controller_thread = None
controller_stop_event = threading.Event()
controller_status = "Idle"

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

fsds_adapter = FSDSClientAdapter(
    fsds_python_path=FSDS_PYTHON_PATH,
    simulator_exe_path=FSDS_SIMULATOR_EXE,
    settings_json_path=FSDS_SETTINGS_JSON,
    custom_map_cli_template=FSDS_CUSTOM_MAP_TEMPLATE if FSDS_CUSTOM_MAP_TEMPLATE else None,
)

tk_root = tk.Tk()
tk_root.withdraw()

message = "Click inside GREEN to start drawing. Release inside RED to finish."
selected_csv_path = None
selected_path_csv_path = None
selected_map_name = "Untitled Map"

loaded_csv_preview_mode = False
preview_loaded_blue = []
preview_loaded_yellow = []
preview_loaded_orange = []

track_points = []
currently_drawing = False
pending_popup = None
show_leaderboard = False
leaderboard_tab = "map"

start_point = None
end_point = None
anchor_radius = 24

is_valid = False
current_map_hash = None

current_run_active = False
current_run_source = "Human"
telemetry_status = "Disconnected"

preview_blue = []
preview_yellow = []
preview_orange = []
preview_mode = "track"

live_run = None
live_driver_name = "Pending"
session_start_time = 0.0


# ============================================================
# HASHING / FINGERPRINTS
# ============================================================
def map_fingerprint(track_points_m, blue, yellow, orange):
    payload = {
        "track_points": track_points_m,
        "blue": blue,
        "yellow": yellow,
        "orange": orange,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def cone_only_fingerprint(blue, yellow, orange):
    return map_fingerprint([], blue, yellow, orange)


# ============================================================
# UI GEOMETRY
# ============================================================
def recalc_ui():
    global fonts, layout, sparks, anchor_radius, start_point, end_point

    width, height = screen.get_size()
    fonts = build_fonts(width, height)
    layout = build_layout(width, height)

    if len(sparks) < 10:
        sparks[:] = make_sparks(width, height, count=26)

    anchor_radius = max(20, int(min(width, height) * 0.018))
    draw_rect = layout["DRAW_RECT"]

    lane_half = max(60, int(draw_rect.width * 0.065))
    guide_y = draw_rect.top + max(90, int(draw_rect.height * 0.18))

    start_point = (draw_rect.centerx + lane_half, guide_y)
    end_point = (draw_rect.centerx - lane_half, guide_y)


# ============================================================
# TRACK HELPERS
# ============================================================
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def cumulative_lengths(points):
    vals = [0.0]
    for i in range(1, len(points)):
        vals.append(vals[-1] + dist(points[i - 1], points[i]))
    return vals


def resample_polyline(points, step_px):
    if len(points) < 2:
        return points[:]

    cum = cumulative_lengths(points)
    total = cum[-1]
    if total <= 1e-9:
        return points[:]

    out = [points[0]]
    s = step_px

    while s < total:
        for i in range(1, len(cum)):
            if s <= cum[i]:
                p0 = points[i - 1]
                p1 = points[i]
                seg = cum[i] - cum[i - 1]
                t = 0.0 if seg <= 1e-9 else (s - cum[i - 1]) / seg
                out.append((
                    p0[0] + t * (p1[0] - p0[0]),
                    p0[1] + t * (p1[1] - p0[1]),
                ))
                break
        s += step_px

    out.append(points[-1])
    return out


def chaikin_open(points, iterations=2):
    pts = points[:]
    if len(pts) < 3:
        return pts

    for _ in range(iterations):
        refined = [pts[0]]
        for i in range(len(pts) - 1):
            p0 = pts[i]
            p1 = pts[i + 1]
            q = (0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1])
            r = (0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1])
            refined.extend([q, r])
        refined.append(pts[-1])
        pts = refined

    return pts


def get_track_origin_pixels():
    return (
        (start_point[0] + end_point[0]) / 2.0,
        (start_point[1] + end_point[1]) / 2.0,
    )


def get_track_origin_meters():
    ox_px, oy_px = get_track_origin_pixels()
    return ox_px * METERS_PER_PIXEL, oy_px * METERS_PER_PIXEL


def smooth_finished_track(raw_points):
    if len(raw_points) < 3:
        return raw_points[:]

    midpoint = get_track_origin_pixels()

    pts = resample_polyline(raw_points, SMOOTHING_RESAMPLE_STEP_PX)
    pts = chaikin_open(pts, iterations=SMOOTHING_ITERATIONS)

    smoothed_body = []
    for p in pts[1:-1]:
        p = (float(p[0]), float(p[1]))
        if not smoothed_body or dist(p, smoothed_body[-1]) >= 3.0:
            smoothed_body.append(p)

    ordered = [midpoint, start_point]

    for p in smoothed_body:
        if dist(p, ordered[-1]) >= 3.0:
            ordered.append(p)

    if dist(end_point, ordered[-1]) >= 1.0:
        ordered.append(end_point)

    if dist(midpoint, ordered[-1]) >= 1.0:
        ordered.append(midpoint)
    else:
        ordered[-1] = midpoint

    return ordered


# ============================================================
# CSV PREVIEW
# ============================================================
def transform_all_csv_points_to_preview(blue_local, yellow_local, orange_local, draw_rect):
    all_local = blue_local + yellow_local + orange_local
    if not all_local:
        return [], [], []

    # Convert saved local FSDS coordinates back into one common world frame
    all_world = [(x - X_FORWARD_OFFSET, y) for x, y in all_local]

    xs = [p[0] for p in all_world]
    ys = [p[1] for p in all_world]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    width_m = max(max_x - min_x, 1e-6)
    height_m = max(max_y - min_y, 1e-6)

    usable_w = max(120, draw_rect.width - 2 * CSV_PREVIEW_PADDING)
    usable_h = max(120, draw_rect.height - 2 * CSV_PREVIEW_PADDING)
    scale = min(usable_w / width_m, usable_h / height_m)

    cx_m = (min_x + max_x) / 2.0
    cy_m = (min_y + max_y) / 2.0
    cx_px = draw_rect.centerx
    cy_px = draw_rect.centery

    def transform(points_local):
        out = []
        for x, y in points_local:
            wx = x - X_FORWARD_OFFSET
            wy = y
            px = cx_px + (wx - cx_m) * scale
            py = cy_px + (wy - cy_m) * scale
            out.append((px, py))
        return out

    return transform(blue_local), transform(yellow_local), transform(orange_local)


def load_csv_preview(path):
    blue_local, yellow_local, orange_local = [], [], []

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue

            color = row[0].strip().lower()
            try:
                x = float(row[1])
                y = float(row[2])
            except ValueError:
                continue

            if color == "blue":
                blue_local.append((x, y))
            elif color == "yellow":
                yellow_local.append((x, y))
            elif color in {"big_orange", "orange"}:
                orange_local.append((x, y))

    draw_rect = layout["DRAW_RECT"]
    blue_preview, yellow_preview, orange_preview = transform_all_csv_points_to_preview(
        blue_local, yellow_local, orange_local, draw_rect
    )

    return (
        blue_preview,
        yellow_preview,
        orange_preview,
        cone_only_fingerprint(blue_local, yellow_local, orange_local),
        len(blue_local),
        len(yellow_local),
        len(orange_local),
    )


# ============================================================
# PATH CSV SAVE / LOAD
# ============================================================
def build_paired_path_filename(map_csv_path):
    base, _ = os.path.splitext(map_csv_path)
    return f"{base}_path.csv"


def convert_track_points_to_local_path(track_points_m, origin_m):
    ox, oy = origin_m
    return [(x - ox + X_FORWARD_OFFSET, y - oy) for x, y in track_points_m]


def save_path_csv(path_file, path_points_local):
    with open(path_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["x", "y"])
        for x, y in path_points_local:
            writer.writerow([float(x), float(y)])
    return path_file


def load_path(filepath):
    path = []
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        prev = None
        for row in reader:
            point = (float(row["x"]), float(row["y"]))
            if prev is None or point != prev:
                path.append(point)
                prev = point
    return path


# ============================================================
# APP STATE RESET
# ============================================================
def clear_track():
    global track_points, is_valid, pending_popup, message, current_map_hash
    global preview_blue, preview_yellow, preview_orange, preview_mode
    global loaded_csv_preview_mode, preview_loaded_blue, preview_loaded_yellow, preview_loaded_orange

    track_points = []
    is_valid = False
    pending_popup = None
    current_map_hash = None

    preview_blue = []
    preview_yellow = []
    preview_orange = []

    loaded_csv_preview_mode = False
    preview_loaded_blue = []
    preview_loaded_yellow = []
    preview_loaded_orange = []

    preview_mode = "track"
    message = "Track cleared. Click inside GREEN to start drawing."


def rebuild_cone_preview():
    global preview_blue, preview_yellow, preview_orange, current_map_hash
    global preview_loaded_blue, preview_loaded_yellow, preview_loaded_orange
    global loaded_csv_preview_mode

    if loaded_csv_preview_mode:
        preview_blue = preview_loaded_blue[:]
        preview_yellow = preview_loaded_yellow[:]
        preview_orange = preview_loaded_orange[:]
        return

    if len(track_points) < 4 or not is_valid:
        preview_blue, preview_yellow, preview_orange = [], [], []
        return

    track_points_m = [(x * METERS_PER_PIXEL, y * METERS_PER_PIXEL) for x, y in track_points]
    blue_m, yellow_m, orange_m = generate_all_cones(track_points_m)

    preview_blue = [(x / METERS_PER_PIXEL, y / METERS_PER_PIXEL) for x, y in blue_m]
    preview_yellow = [(x / METERS_PER_PIXEL, y / METERS_PER_PIXEL) for x, y in yellow_m]
    preview_orange = [(x / METERS_PER_PIXEL, y / METERS_PER_PIXEL) for x, y in orange_m]

    current_map_hash = map_fingerprint(track_points_m, blue_m, yellow_m, orange_m)


# ============================================================
# SAVE / LOAD MAP
# ============================================================
def save_track_csv():
    global selected_csv_path, selected_path_csv_path, message, current_map_hash, selected_map_name

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
    origin_m = get_track_origin_meters()

    export_info = export_csv(file_path, blue, yellow, orange, origin=origin_m)

    path_points_local = convert_track_points_to_local_path(track_points_m, origin_m)
    path_file = build_paired_path_filename(file_path)
    save_path_csv(path_file, path_points_local)

    selected_csv_path = file_path
    selected_path_csv_path = path_file
    selected_map_name = os.path.splitext(os.path.basename(file_path))[0]
    current_map_hash = cone_only_fingerprint(
        export_info["blue_local"],
        export_info["yellow_local"],
        export_info["orange_local"],
    )
    message = (
        f"Saved map: {os.path.basename(file_path)} | "
        f"saved path: {os.path.basename(path_file)}"
    )


def load_csv():
    global selected_csv_path, selected_path_csv_path, selected_map_name, message
    global preview_blue, preview_yellow, preview_orange
    global current_map_hash, track_points, is_valid, preview_mode, pending_popup
    global loaded_csv_preview_mode, preview_loaded_blue, preview_loaded_yellow, preview_loaded_orange

    path = filedialog.askopenfilename(
        title="Open CSV",
        filetypes=[("CSV Files", "*.csv")],
    )
    if not path:
        return

    selected_csv_path = path
    selected_map_name = os.path.splitext(os.path.basename(path))[0]
    track_points = []
    is_valid = False
    pending_popup = None
    preview_mode = "csv"

    paired_path = build_paired_path_filename(path)
    selected_path_csv_path = paired_path if os.path.exists(paired_path) else None

    (
        preview_blue,
        preview_yellow,
        preview_orange,
        current_map_hash,
        blue_count,
        yellow_count,
        orange_count,
    ) = load_csv_preview(path)

    loaded_csv_preview_mode = True
    preview_loaded_blue = preview_blue[:]
    preview_loaded_yellow = preview_yellow[:]
    preview_loaded_orange = preview_orange[:]

    if selected_path_csv_path:
        message = (
            f"Loaded CSV: {os.path.basename(path)} | "
            f"blue {blue_count}, yellow {yellow_count}, orange {orange_count} | "
            f"path found: {os.path.basename(selected_path_csv_path)}"
        )
    else:
        message = (
            f"Loaded CSV: {os.path.basename(path)} | "
            f"blue {blue_count}, yellow {yellow_count}, orange {orange_count} | "
            f"no paired _path.csv found"
        )


# ============================================================
# PURE PURSUIT CONTROLLER
# ============================================================
def get_yaw_from_quaternion(q):
    x, y, z, w = q.x_val, q.y_val, q.z_val, q.w_val
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def get_speed(state):
    vx = state.kinematics_estimated.linear_velocity.x_val
    vy = state.kinematics_estimated.linear_velocity.y_val
    return math.hypot(vx, vy)


def update_closest_idx(path, car_x, car_y, last_idx, search_window=20):
    n = len(path)
    end = min(last_idx + search_window, n)
    best_dist = float("inf")
    best_idx = last_idx
    for i in range(last_idx, end):
        dx = path[i][0] - car_x
        dy = path[i][1] - car_y
        d = dx * dx + dy * dy
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx


def circle_segment_intersection(car_x, car_y, r, p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    fx = p1[0] - car_x
    fy = p1[1] - car_y
    a = dx * dx + dy * dy
    if a < 1e-10:
        return None
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return None
    sqrt_disc = math.sqrt(discriminant)
    t2 = (-b + sqrt_disc) / (2.0 * a)
    t1 = (-b - sqrt_disc) / (2.0 * a)
    for t in (t2, t1):
        if 0.0 <= t <= 1.0:
            return (p1[0] + t * dx, p1[1] + t * dy)
    return None


def find_lookahead_point(path, car_x, car_y, lookahead_dist, last_idx):
    n = len(path)
    for i in range(last_idx, n - 1):
        pt = circle_segment_intersection(car_x, car_y, lookahead_dist, path[i], path[i + 1])
        if pt is not None:
            return pt
    return path[-1]


def pure_pursuit_steering(car_x, car_y, yaw, target_x, target_y, lookahead_dist):
    angle_to_target = math.atan2(target_y - car_y, target_x - car_x)
    alpha = angle_to_target - yaw
    alpha = math.atan2(math.sin(alpha), math.cos(alpha))
    delta_rad = math.atan2(2.0 * WHEELBASE * math.sin(alpha), lookahead_dist)
    delta_rad = -delta_rad
    return max(-1.0, min(1.0, delta_rad / MAX_STEER_RAD))


class PIDController:
    def __init__(self, kp, ki, kd):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral = 0.0
        self.prev_error = None

    def reset(self):
        self.integral = 0.0
        self.prev_error = None

    def compute(self, current, target, dt):
        error = target - current
        self.integral += error * dt
        self.integral = max(-2.0, min(2.0, self.integral))
        derivative = 0.0 if self.prev_error is None else (error - self.prev_error) / dt
        self.prev_error = error
        return self.kp * error + self.ki * self.integral + self.kd * derivative


def compute_throttle_brake(pid, current_speed, target_speed, dt):
    pid_output = pid.compute(current_speed, target_speed, dt)
    overshoot = current_speed - target_speed
    if overshoot > BRAKE_THRESHOLD:
        pid.integral = 0.0
        return 0.0, min(0.4, overshoot * 0.3)
    elif overshoot > 0:
        return 0.0, 0.0
    else:
        return max(0.05, min(MAX_THROTTLE, pid_output)), 0.0


def stop_vehicle(client):
    stop = fsds.CarControls()
    stop.throttle = 0.0
    stop.steering = 0.0
    stop.brake = 1.0
    client.setCarControls(stop, VEHICLE_NAME)


def stop_ramse_controller():
    global controller_thread, controller_status
    controller_stop_event.set()
    controller_status = "Stopping"


def start_ramse_controller(path_csv_path):
    global controller_thread, controller_status

    if not path_csv_path or not os.path.exists(path_csv_path):
        controller_status = "No path file"
        return False

    stop_ramse_controller()
    time.sleep(0.1)
    controller_stop_event.clear()

    def control_loop():
        global controller_status

        try:
            path = load_path(path_csv_path)
            if len(path) < 2:
                controller_status = "Invalid path"
                return

            controller_status = "Connecting"

            client = fsds.FSDSClient()
            client.confirmConnection()
            client.enableApiControl(True, VEHICLE_NAME)

            pid = PIDController(SPEED_KP, SPEED_KI, SPEED_KD)
            last_idx = 0
            lap_complete_lock = False
            prev_time = time.time()
            n = len(path)

            state = client.getCarState(VEHICLE_NAME)
            car_x = state.kinematics_estimated.position.x_val
            car_y = state.kinematics_estimated.position.y_val

            best_dist = float("inf")
            best_idx = 0
            for i, (px, py) in enumerate(path):
                d = (px - car_x) ** 2 + (py - car_y) ** 2
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            last_idx = best_idx
            controller_status = "Running"

            while not controller_stop_event.is_set():
                now = time.time()
                dt = max(now - prev_time, 1e-3)
                prev_time = now

                state = client.getCarState(VEHICLE_NAME)
                car_x = state.kinematics_estimated.position.x_val
                car_y = state.kinematics_estimated.position.y_val
                yaw = get_yaw_from_quaternion(state.kinematics_estimated.orientation)
                speed = get_speed(state)

                lookahead_dist = LD_MIN + LD_K * speed
                last_idx = update_closest_idx(path, car_x, car_y, last_idx, search_window=SEARCH_WINDOW)

                dist_to_start = math.hypot(path[0][0] - car_x, path[0][1] - car_y)
                if last_idx > int(n * 0.9) and dist_to_start < LAP_THRESHOLD:
                    if not lap_complete_lock:
                        last_idx = 0
                        lap_complete_lock = True
                else:
                    if dist_to_start > LAP_THRESHOLD * 2:
                        lap_complete_lock = False

                target_x, target_y = find_lookahead_point(path, car_x, car_y, lookahead_dist, last_idx)
                steering = pure_pursuit_steering(car_x, car_y, yaw, target_x, target_y, lookahead_dist)
                throttle, brake = compute_throttle_brake(pid, speed, TARGET_SPEED, dt)

                controls = fsds.CarControls()
                controls.throttle = throttle
                controls.steering = steering
                controls.brake = brake
                client.setCarControls(controls, VEHICLE_NAME)

                time.sleep(CONTROL_DT)

            try:
                stop_vehicle(client)
                client.enableApiControl(False, VEHICLE_NAME)
            except Exception:
                pass

            controller_status = "Stopped"

        except Exception as e:
            controller_status = f"Error: {e}"

    controller_thread = threading.Thread(target=control_loop, daemon=True)
    controller_thread.start()
    return True


# ============================================================
# FSDS RUN CONTROL
# ============================================================
def start_fsds_run(source="Human"):
    global message, current_run_active, current_run_source, show_leaderboard
    global telemetry_status, live_run, live_driver_name, session_start_time
    global fsds_client, last_lap_count, last_doo_count

    if not selected_csv_path:
        message = "Save or load a CSV first."
        return

    if source == "RAMS-e" and (not selected_path_csv_path or not os.path.exists(selected_path_csv_path)):
        message = "Paired _path.csv not found. Save the map first or load a map with its paired path."
        return

    import tkinter.simpledialog as simpledialog

    name = simpledialog.askstring("Driver Entry", "Enter your name to start the session:")
    if not name:
        message = "Run cancelled: Name required."
        return

    live_driver_name = name
    session_start_time = time.time()

    fsds_client = None
    last_lap_count = 0
    last_doo_count = 0

    stop_ramse_controller()

    def launch_fsds():
        global telemetry_status, message
        try:
            fsds_adapter.launch_simulator(selected_csv_path, enable_api_control=False)
            telemetry_status = "Launching"
        except Exception as e:
            telemetry_status = "Disconnected"
            message = f"FSDS launch failed: {e}"

    threading.Thread(target=launch_fsds, daemon=True).start()

    if source == "RAMS-e":
        def delayed_controller_start():
            global message
            time.sleep(5.0)
            ok = start_ramse_controller(selected_path_csv_path)
            if ok:
                message = (
                    f"Session for {live_driver_name} started. "
                    f"FSDS launching with RAMS-e path follower."
                )
            else:
                message = "Failed to start RAMS-e controller."

        threading.Thread(target=delayed_controller_start, daemon=True).start()

    current_run_active = True
    current_run_source = source
    show_leaderboard = True

    live_run = {
        "player_name": live_driver_name,
        "source": source,
        "lap_time_s": 0.0,
        "cone_hits": 0,
        "is_live": True,
    }

    if source == "Human":
        message = f"Session for {live_driver_name} started. Waiting for connection..."
    else:
        message = f"Session for {live_driver_name} started. Preparing RAMS-e..."

    with open("live_data.json", "w") as f:
        json.dump({"time": 0.0, "cones": 0, "finished": False}, f)

    subprocess.Popen([sys.executable, "race_ui.py"])


def finalize_run(save_result: bool, final_message: str, time_to_save=0.0, cones_to_save=0):
    global current_run_active, telemetry_status, message, show_leaderboard, live_run, live_driver_name

    if save_result and live_run is not None:
        name = live_driver_name if live_driver_name else "Anonymous"
        live_run["player_name"] = name
        live_run["lap_time_s"] = float(time_to_save)
        live_run["cone_hits"] = int(cones_to_save)
        live_run["is_live"] = False

        db.insert_lap(
            map_hash=current_map_hash,
            map_name=selected_map_name,
            player_name=name,
            source=current_run_source,
            lap_time_s=float(time_to_save),
            cone_hits=int(cones_to_save),
            checkpoints_passed=1,
            total_checkpoints=1,
        )

        try:
            fsds_adapter.stop()
        except Exception:
            pass

        stop_ramse_controller()

    current_run_active = False
    telemetry_status = "Finished"
    message = final_message
    show_leaderboard = True


def process_fsds():
    global current_run_active, fsds_client, last_lap_count, live_run, telemetry_status, session_start_time
    global controller_status

    if not current_run_active:
        return

    try:
        if fsds_client is None:
            try:
                fsds_client = fsds.FSDSClient()
                fsds_client.confirmConnection()
                telemetry_status = "Connected"
                initial_ref = fsds_client.getRefereeState()
                if initial_ref:
                    last_lap_count = len(initial_ref.laps)
            except Exception:
                telemetry_status = "Waiting..."
                return

        ref = fsds_client.getRefereeState()
        if not ref:
            return

        if len(ref.laps) > last_lap_count:
            final_time = float(ref.laps[-1])
            final_cones = int(ref.doo_counter)
            last_lap_count = len(ref.laps)
            current_run_active = False

            with open("live_data.json", "w") as f:
                json.dump({"time": final_time, "cones": final_cones, "finished": True}, f)

            finalize_run(True, f"Finish! {final_time:.2f}s", final_time, final_cones)
            return

        sim_live_time = float(getattr(ref, "current_lap_time_s", 0.0))
        time_val = time.time() - session_start_time if sim_live_time == 0.0 else sim_live_time
        cone_val = int(ref.doo_counter)

        if live_run:
            live_run["lap_time_s"] = time_val
            live_run["cone_hits"] = cone_val

        with open("live_data.json", "w") as f:
            json.dump({"time": time_val, "cones": cone_val, "finished": False}, f)

        if current_run_source == "RAMS-e" and telemetry_status == "Connected":
            telemetry_status = f"Connected | RAMS-e: {controller_status}"

    except Exception:
        pass


# ============================================================
# MAIN LOOP
# ============================================================
recalc_ui()
draw_loading_screen(screen, fonts, *screen.get_size(), 1000, clock, sparks)

running = True
while running:
    process_fsds()
    width, height = screen.get_size()
    recalc_ui()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.VIDEORESIZE:
            screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            recalc_ui()
            if preview_mode == "csv" and selected_csv_path:
                try:
                    (
                        preview_blue,
                        preview_yellow,
                        preview_orange,
                        current_map_hash,
                        _,
                        _,
                        _,
                    ) = load_csv_preview(selected_csv_path)
                    preview_loaded_blue = preview_blue[:]
                    preview_loaded_yellow = preview_yellow[:]
                    preview_loaded_orange = preview_orange[:]
                except Exception:
                    pass

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos

            if show_leaderboard:
                map_rows = db.get_current_map_leaderboard(current_map_hash, limit=20) if current_map_hash else []
                duel_stats = db.get_duel_stats(current_map_hash) if current_map_hash else {"ramse_wins": 0, "human_wins": 0, "comparisons": 0}
                modal = draw_leaderboard_modal(screen, fonts, width, height, leaderboard_tab, map_rows, duel_stats, live_run)

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
                    preview_mode = "track"
                    loaded_csv_preview_mode = False
                    preview_loaded_blue = []
                    preview_loaded_yellow = []
                    preview_loaded_orange = []
                    track_points = [start_point]
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

                raw_track = track_points[:]
                if not raw_track or dist(raw_track[-1], end_point) > 1.0:
                    raw_track.append(end_point)

                track_points = smooth_finished_track(raw_track)

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

    draw_racing_background(screen, width, height)
    update_sparks(sparks, width, height)
    draw_sparks(screen, sparks)

    selected_display = selected_csv_path
    if selected_path_csv_path:
        selected_display = f"{selected_csv_path}\nPATH: {selected_path_csv_path}"

    draw_side_panel(
        screen,
        layout,
        fonts,
        message=message,
        valid=is_valid or bool(selected_csv_path and preview_mode == "csv"),
        points_count=len(track_points),
        scale=METERS_PER_PIXEL,
        cone_spacing_m=MIN_CONE_SPACING,
        selected_csv_path=selected_display,
        can_run_fsds=bool(selected_csv_path),
        telemetry_status=telemetry_status,
        preview_mode=preview_mode,
        smoothing_info=f"{SMOOTHING_ITERATIONS}x Chaikin",
    )

    draw_rect = layout["DRAW_RECT"]
    draw_track_area(screen, draw_rect)
    draw_track(
        screen,
        track_points,
        is_valid,
        currently_drawing,
        start_point,
        end_point,
        anchor_radius,
        fonts,
        preview_mode=preview_mode,
    )
    draw_cones(screen, preview_blue, preview_yellow, preview_orange)

    if pending_popup:
        draw_invalid_popup(screen, fonts, width, height, pending_popup["title"], pending_popup["body"])

    if show_leaderboard:
        map_rows = db.get_current_map_leaderboard(current_map_hash, limit=20) if current_map_hash else []
        duel_stats = db.get_duel_stats(current_map_hash) if current_map_hash else {"ramse_wins": 0, "human_wins": 0, "comparisons": 0}
        draw_leaderboard_modal(screen, fonts, width, height, leaderboard_tab, map_rows, duel_stats, live_run)

    draw_custom_cursor(screen, pygame.mouse.get_pos())
    pygame.display.flip()
    clock.tick(60)

stop_ramse_controller()
try:
    fsds.stop()
except Exception:
    pass
pygame.quit()
sys.exit()
# ============================================================
# PATH CSV SAVE / LOAD
# ============================================================
def build_paired_path_filename(map_csv_path):
    base, ext = os.path.splitext(map_csv_path)
    return f"{base}_path.csv"


def convert_track_points_to_local_path(track_points_m, origin_m):
    ox, oy = origin_m
    return [(x - ox + X_FORWARD_OFFSET, y - oy) for x, y in track_points_m]


def save_path_csv(path_file, path_points_local):
    with open(path_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["x", "y"])
        for x, y in path_points_local:
            writer.writerow([float(x), float(y)])
    return path_file


def load_path(filepath):
    path = []
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        prev = None
        for row in reader:
            point = (float(row["x"]), float(row["y"]))
            if prev is None or point != prev:
                path.append(point)
                prev = point
    return path


# ============================================================
# APP STATE RESET
# ============================================================
def clear_track():
    global track_points, is_valid, pending_popup, message, current_map_hash
    global preview_blue, preview_yellow, preview_orange, preview_mode
    global loaded_csv_preview_mode, preview_loaded_blue, preview_loaded_yellow, preview_loaded_orange

    track_points = []
    is_valid = False
    pending_popup = None
    current_map_hash = None

    preview_blue = []
    preview_yellow = []
    preview_orange = []

    loaded_csv_preview_mode = False
    preview_loaded_blue = []
    preview_loaded_yellow = []
    preview_loaded_orange = []

    preview_mode = "track"
    message = "Track cleared. Click inside GREEN to start drawing."


def rebuild_cone_preview():
    global preview_blue, preview_yellow, preview_orange, current_map_hash
    global preview_loaded_blue, preview_loaded_yellow, preview_loaded_orange
    global loaded_csv_preview_mode

    if loaded_csv_preview_mode:
        preview_blue = preview_loaded_blue[:]
        preview_yellow = preview_loaded_yellow[:]
        preview_orange = preview_loaded_orange[:]
        return

    if len(track_points) < 4 or not is_valid:
        preview_blue, preview_yellow, preview_orange = [], [], []
        return

    track_points_m = [(x * METERS_PER_PIXEL, y * METERS_PER_PIXEL) for x, y in track_points]
    blue_m, yellow_m, orange_m = generate_all_cones(track_points_m)

    preview_blue = [(x / METERS_PER_PIXEL, y / METERS_PER_PIXEL) for x, y in blue_m]
    preview_yellow = [(x / METERS_PER_PIXEL, y / METERS_PER_PIXEL) for x, y in yellow_m]
    preview_orange = [(x / METERS_PER_PIXEL, y / METERS_PER_PIXEL) for x, y in orange_m]

    current_map_hash = map_fingerprint(track_points_m, blue_m, yellow_m, orange_m)


# ============================================================
# SAVE / LOAD MAP
# ============================================================
def save_track_csv():
    global selected_csv_path, selected_path_csv_path, message, current_map_hash, selected_map_name

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
    origin_m = get_track_origin_meters()

    export_info = export_csv(file_path, blue, yellow, orange, origin=origin_m)

    path_points_local = convert_track_points_to_local_path(track_points_m, origin_m)
    path_file = build_paired_path_filename(file_path)
    save_path_csv(path_file, path_points_local)

    selected_csv_path = file_path
    selected_path_csv_path = path_file
    selected_map_name = os.path.splitext(os.path.basename(file_path))[0]
    current_map_hash = cone_only_fingerprint(
        export_info["blue_local"],
        export_info["yellow_local"],
        export_info["orange_local"],
    )
    message = (
        f"Saved map: {os.path.basename(file_path)} | "
        f"saved path: {os.path.basename(path_file)}"
    )


def load_csv():
    global selected_csv_path, selected_path_csv_path, selected_map_name, message
    global preview_blue, preview_yellow, preview_orange
    global current_map_hash, track_points, is_valid, preview_mode, pending_popup
    global loaded_csv_preview_mode, preview_loaded_blue, preview_loaded_yellow, preview_loaded_orange

    path = filedialog.askopenfilename(
        title="Open CSV",
        filetypes=[("CSV Files", "*.csv")],
    )
    if not path:
        return

    selected_csv_path = path
    selected_map_name = os.path.splitext(os.path.basename(path))[0]
    track_points = []
    is_valid = False
    pending_popup = None
    preview_mode = "csv"

    paired_path = build_paired_path_filename(path)
    selected_path_csv_path = paired_path if os.path.exists(paired_path) else None

    (
        preview_blue,
        preview_yellow,
        preview_orange,
        current_map_hash,
        blue_count,
        yellow_count,
        orange_count,
    ) = load_csv_preview(path)

    loaded_csv_preview_mode = True
    preview_loaded_blue = preview_blue[:]
    preview_loaded_yellow = preview_yellow[:]
    preview_loaded_orange = preview_orange[:]

    if selected_path_csv_path:
        message = (
            f"Loaded CSV: {os.path.basename(path)} | "
            f"blue {blue_count}, yellow {yellow_count}, orange {orange_count} | "
            f"path found: {os.path.basename(selected_path_csv_path)}"
        )
    else:
        message = (
            f"Loaded CSV: {os.path.basename(path)} | "
            f"blue {blue_count}, yellow {yellow_count}, orange {orange_count} | "
            f"no paired _path.csv found"
        )


# ============================================================
# PURE PURSUIT CONTROLLER
# ============================================================
def get_yaw_from_quaternion(q):
    x, y, z, w = q.x_val, q.y_val, q.z_val, q.w_val
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def get_speed(state):
    vx = state.kinematics_estimated.linear_velocity.x_val
    vy = state.kinematics_estimated.linear_velocity.y_val
    return math.hypot(vx, vy)


def update_closest_idx(path, car_x, car_y, last_idx, search_window=20):
    n = len(path)
    end = min(last_idx + search_window, n)
    best_dist = float("inf")
    best_idx = last_idx
    for i in range(last_idx, end):
        dx = path[i][0] - car_x
        dy = path[i][1] - car_y
        d = dx * dx + dy * dy
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx


def circle_segment_intersection(car_x, car_y, r, p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    fx = p1[0] - car_x
    fy = p1[1] - car_y
    a = dx * dx + dy * dy
    if a < 1e-10:
        return None
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return None
    sqrt_disc = math.sqrt(discriminant)
    t2 = (-b + sqrt_disc) / (2.0 * a)
    t1 = (-b - sqrt_disc) / (2.0 * a)
    for t in (t2, t1):
        if 0.0 <= t <= 1.0:
            return (p1[0] + t * dx, p1[1] + t * dy)
    return None


def find_lookahead_point(path, car_x, car_y, lookahead_dist, last_idx):
    n = len(path)
    for i in range(last_idx, n - 1):
        pt = circle_segment_intersection(car_x, car_y, lookahead_dist, path[i], path[i + 1])
        if pt is not None:
            return pt
    return path[-1]


def pure_pursuit_steering(car_x, car_y, yaw, target_x, target_y, lookahead_dist):
    angle_to_target = math.atan2(target_y - car_y, target_x - car_x)
    alpha = angle_to_target - yaw
    alpha = math.atan2(math.sin(alpha), math.cos(alpha))
    delta_rad = math.atan2(2.0 * WHEELBASE * math.sin(alpha), lookahead_dist)
    delta_rad = -delta_rad
    return max(-1.0, min(1.0, delta_rad / MAX_STEER_RAD))


class PIDController:
    def __init__(self, kp, ki, kd):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral = 0.0
        self.prev_error = None

    def reset(self):
        self.integral = 0.0
        self.prev_error = None

    def compute(self, current, target, dt):
        error = target - current
        self.integral += error * dt
        self.integral = max(-2.0, min(2.0, self.integral))
        derivative = 0.0 if self.prev_error is None else (error - self.prev_error) / dt
        self.prev_error = error
        return self.kp * error + self.ki * self.integral + self.kd * derivative


def compute_throttle_brake(pid, current_speed, target_speed, dt):
    pid_output = pid.compute(current_speed, target_speed, dt)
    overshoot = current_speed - target_speed
    if overshoot > BRAKE_THRESHOLD:
        pid.integral = 0.0
        return 0.0, min(0.4, overshoot * 0.3)
    elif overshoot > 0:
        return 0.0, 0.0
    else:
        return max(0.05, min(MAX_THROTTLE, pid_output)), 0.0


def stop_vehicle(client):
    stop = fsds.CarControls()
    stop.throttle = 0.0
    stop.steering = 0.0
    stop.brake = 1.0
    client.setCarControls(stop, VEHICLE_NAME)


def stop_ramse_controller():
    global controller_thread, controller_status
    controller_stop_event.set()
    controller_status = "Stopping"


def start_ramse_controller(path_csv_path):
    global controller_thread, controller_status

    if not path_csv_path or not os.path.exists(path_csv_path):
        controller_status = "No path file"
        return False

    stop_ramse_controller()
    time.sleep(0.1)
    controller_stop_event.clear()

    def control_loop():
        global controller_status

        try:
            path = load_path(path_csv_path)
            if len(path) < 2:
                controller_status = "Invalid path"
                return

            controller_status = "Connecting"

            client = fsds.FSDSClient()
            client.confirmConnection()
            client.enableApiControl(True, VEHICLE_NAME)

            pid = PIDController(SPEED_KP, SPEED_KI, SPEED_KD)
            last_idx = 0
            lap_complete_lock = False
            prev_time = time.time()
            n = len(path)

            state = client.getCarState(VEHICLE_NAME)
            car_x = state.kinematics_estimated.position.x_val
            car_y = state.kinematics_estimated.position.y_val

            best_dist = float("inf")
            best_idx = 0
            for i, (px, py) in enumerate(path):
                d = (px - car_x) ** 2 + (py - car_y) ** 2
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            last_idx = best_idx
            controller_status = "Running"

            while not controller_stop_event.is_set():
                now = time.time()
                dt = max(now - prev_time, 1e-3)
                prev_time = now

                state = client.getCarState(VEHICLE_NAME)
                car_x = state.kinematics_estimated.position.x_val
                car_y = state.kinematics_estimated.position.y_val
                yaw = get_yaw_from_quaternion(state.kinematics_estimated.orientation)
                speed = get_speed(state)

                lookahead_dist = LD_MIN + LD_K * speed
                last_idx = update_closest_idx(path, car_x, car_y, last_idx, search_window=SEARCH_WINDOW)

                dist_to_start = math.hypot(path[0][0] - car_x, path[0][1] - car_y)
                if last_idx > int(n * 0.9) and dist_to_start < LAP_THRESHOLD:
                    if not lap_complete_lock:
                        last_idx = 0
                        lap_complete_lock = True
                else:
                    if dist_to_start > LAP_THRESHOLD * 2:
                        lap_complete_lock = False

                target_x, target_y = find_lookahead_point(path, car_x, car_y, lookahead_dist, last_idx)
                steering = pure_pursuit_steering(car_x, car_y, yaw, target_x, target_y, lookahead_dist)
                throttle, brake = compute_throttle_brake(pid, speed, TARGET_SPEED, dt)

                controls = fsds.CarControls()
                controls.throttle = throttle
                controls.steering = steering
                controls.brake = brake
                client.setCarControls(controls, VEHICLE_NAME)

                time.sleep(CONTROL_DT)

            try:
                stop_vehicle(client)
                client.enableApiControl(False, VEHICLE_NAME)
            except Exception:
                pass

            controller_status = "Stopped"

        except Exception as e:
            controller_status = f"Error: {e}"

    controller_thread = threading.Thread(target=control_loop, daemon=True)
    controller_thread.start()
    return True


# ============================================================
# FSDS RUN CONTROL
# ============================================================
def start_fsds_run(source="Human"):
    global message, current_run_active, current_run_source, show_leaderboard
    global telemetry_status, live_run, live_driver_name, session_start_time
    global fsds_client, last_lap_count, last_doo_count

    if not selected_csv_path:
        message = "Save or load a CSV first."
        return

    if source == "RAMS-e" and (not selected_path_csv_path or not os.path.exists(selected_path_csv_path)):
        message = "Paired _path.csv not found. Save the map first or load a map with its paired path."
        return

    import tkinter.simpledialog as simpledialog

    name = simpledialog.askstring("Driver Entry", "Enter your name to start the session:")
    if not name:
        message = "Run cancelled: Name required."
        return

    live_driver_name = name
    session_start_time = time.time()

    fsds_client = None
    last_lap_count = 0
    last_doo_count = 0

    stop_ramse_controller()

    def launch_fsds():
        global telemetry_status, message
        try:
            fsds_adapter.launch_simulator(selected_csv_path, enable_api_control=False)
            telemetry_status = "Launching"
        except Exception as e:
            telemetry_status = "Disconnected"
            message = f"FSDS launch failed: {e}"

    threading.Thread(target=launch_fsds, daemon=True).start()

    if source == "RAMS-e":
        def delayed_controller_start():
            global message
            time.sleep(5.0)
            ok = start_ramse_controller(selected_path_csv_path)
            if ok:
                message = (
                    f"Session for {live_driver_name} started. "
                    f"FSDS launching with RAMS-e path follower."
                )
            else:
                message = "Failed to start RAMS-e controller."

        threading.Thread(target=delayed_controller_start, daemon=True).start()

    current_run_active = True
    current_run_source = source
    show_leaderboard = True

    live_run = {
        "player_name": live_driver_name,
        "source": source,
        "lap_time_s": 0.0,
        "cone_hits": 0,
        "is_live": True,
    }

    if source == "Human":
        message = f"Session for {live_driver_name} started. Waiting for connection..."
    else:
        message = f"Session for {live_driver_name} started. Preparing RAMS-e..."

    with open("live_data.json", "w") as f:
        json.dump({"time": 0.0, "cones": 0, "finished": False}, f)

    subprocess.Popen([sys.executable, "race_ui.py"])


def finalize_run(save_result: bool, final_message: str, time_to_save=0.0, cones_to_save=0):
    global current_run_active, telemetry_status, message, show_leaderboard, live_run, live_driver_name

    if save_result and live_run is not None:
        name = live_driver_name if live_driver_name else "Anonymous"
        live_run["player_name"] = name
        live_run["lap_time_s"] = float(time_to_save)
        live_run["cone_hits"] = int(cones_to_save)
        live_run["is_live"] = False

        db.insert_lap(
            map_hash=current_map_hash,
            map_name=selected_map_name,
            player_name=name,
            source=current_run_source,
            lap_time_s=float(time_to_save),
            cone_hits=int(cones_to_save),
            checkpoints_passed=1,
            total_checkpoints=1,
        )

        try:
            fsds_adapter.stop()
        except Exception:
            pass

        stop_ramse_controller()

    current_run_active = False
    telemetry_status = "Finished"
    message = final_message
    show_leaderboard = True


def process_fsds():
    global current_run_active, fsds_client, last_lap_count, live_run, telemetry_status, session_start_time
    global controller_status

    if not current_run_active:
        return

    try:
        if fsds_client is None:
            try:
                fsds_client = fsds.FSDSClient()
                fsds_client.confirmConnection()
                telemetry_status = "Connected"
                initial_ref = fsds_client.getRefereeState()
                if initial_ref:
                    last_lap_count = len(initial_ref.laps)
            except Exception:
                telemetry_status = "Waiting..."
                return

        ref = fsds_client.getRefereeState()
        if not ref:
            return

        if len(ref.laps) > last_lap_count:
            final_time = float(ref.laps[-1])
            final_cones = int(ref.doo_counter)
            last_lap_count = len(ref.laps)
            current_run_active = False

            with open("live_data.json", "w") as f:
                json.dump({"time": final_time, "cones": final_cones, "finished": True}, f)

            finalize_run(True, f"Finish! {final_time:.2f}s", final_time, final_cones)
            return

        sim_live_time = float(getattr(ref, "current_lap_time_s", 0.0))
        time_val = time.time() - session_start_time if sim_live_time == 0.0 else sim_live_time
        cone_val = int(ref.doo_counter)

        if live_run:
            live_run["lap_time_s"] = time_val
            live_run["cone_hits"] = cone_val

        with open("live_data.json", "w") as f:
            json.dump({"time": time_val, "cones": cone_val, "finished": False}, f)

        if current_run_source == "RAMS-e" and telemetry_status == "Connected":
            telemetry_status = f"Connected | RAMS-e: {controller_status}"

    except Exception:
        pass


# ============================================================
# MAIN LOOP
# ============================================================
recalc_ui()
draw_loading_screen(screen, fonts, *screen.get_size(), 1000, clock, sparks)

running = True
while running:
    process_fsds()
    width, height = screen.get_size()
    recalc_ui()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.VIDEORESIZE:
            screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            recalc_ui()
            if preview_mode == "csv" and selected_csv_path:
                try:
                    (
                        preview_blue,
                        preview_yellow,
                        preview_orange,
                        current_map_hash,
                        _,
                        _,
                        _,
                    ) = load_csv_preview(selected_csv_path)
                    preview_loaded_blue = preview_blue[:]
                    preview_loaded_yellow = preview_yellow[:]
                    preview_loaded_orange = preview_orange[:]
                except Exception:
                    pass

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos

            if show_leaderboard:
                map_rows = db.get_current_map_leaderboard(current_map_hash, limit=20) if current_map_hash else []
                duel_stats = db.get_duel_stats(current_map_hash) if current_map_hash else {"ramse_wins": 0, "human_wins": 0, "comparisons": 0}
                modal = draw_leaderboard_modal(screen, fonts, width, height, leaderboard_tab, map_rows, duel_stats, live_run)

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
                    preview_mode = "track"
                    loaded_csv_preview_mode = False
                    preview_loaded_blue = []
                    preview_loaded_yellow = []
                    preview_loaded_orange = []
                    track_points = [start_point]
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

                raw_track = track_points[:]
                if not raw_track or dist(raw_track[-1], end_point) > 1.0:
                    raw_track.append(end_point)

                track_points = smooth_finished_track(raw_track)

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

    draw_racing_background(screen, width, height)
    update_sparks(sparks, width, height)
    draw_sparks(screen, sparks)

    selected_display = selected_csv_path
    if selected_path_csv_path:
        selected_display = f"{selected_csv_path}\nPATH: {selected_path_csv_path}"

    draw_side_panel(
        screen,
        layout,
        fonts,
        message=message,
        valid=is_valid or bool(selected_csv_path and preview_mode == "csv"),
        points_count=len(track_points),
        scale=METERS_PER_PIXEL,
        cone_spacing_m=MIN_CONE_SPACING,
        selected_csv_path=selected_display,
        can_run_fsds=bool(selected_csv_path),
        telemetry_status=telemetry_status,
        preview_mode=preview_mode,
        smoothing_info=f"{SMOOTHING_ITERATIONS}x Chaikin",
    )

    draw_rect = layout["DRAW_RECT"]
    draw_track_area(screen, draw_rect)
    draw_track(
        screen,
        track_points,
        is_valid,
        currently_drawing,
        start_point,
        end_point,
        anchor_radius,
        fonts,
        preview_mode=preview_mode,
    )
    draw_cones(screen, preview_blue, preview_yellow, preview_orange)

    if pending_popup:
        draw_invalid_popup(screen, fonts, width, height, pending_popup["title"], pending_popup["body"])

    if show_leaderboard:
        map_rows = db.get_current_map_leaderboard(current_map_hash, limit=20) if current_map_hash else []
        duel_stats = db.get_duel_stats(current_map_hash) if current_map_hash else {"ramse_wins": 0, "human_wins": 0, "comparisons": 0}
        draw_leaderboard_modal(screen, fonts, width, height, leaderboard_tab, map_rows, duel_stats, live_run)

    draw_custom_cursor(screen, pygame.mouse.get_pos())
    pygame.display.flip()
    clock.tick(60)

stop_ramse_controller()
try:
    fsds.stop()
except Exception:
    pass
pygame.quit()
sys.exit()