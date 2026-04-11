import csv
import math
import os
import subprocess
import tkinter as tk
from tkinter import filedialog
import pathlib as pl
import pygame
import numpy as np
from shapely.geometry import LineString
from scipy.interpolate import splprep, splev

from fsds_cone_generation import generate_all_cones
from csv_writer import export_csv
from ui_components import (
    BG,
    BLUE,
    WHITE,
    YELLOW,
    ORANGE,
    build_fonts,
    build_layout,
    draw_loading_screen,
    draw_side_panel,
    draw_track_area,
    draw_track,
    draw_invalid_popup,
)


pygame.init()

# ============================================================
# Config
# ============================================================
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1280, 720
DISPLAY_INFO = pygame.display.Info()
DISPLAY_WIDTH = DISPLAY_INFO.current_w
DISPLAY_HEIGHT = DISPLAY_INFO.current_h

SCALE = 0.13
MIN_CONE_RADIUS_PX = 10
MIN_CONE_SPACING_M = MIN_CONE_RADIUS_PX * SCALE

ANCHOR_LINE_LENGTH = 50
ANCHOR_RADIUS = 20
ANCHOR_Y_OFFSET_FROM_CENTER = 100

FSDS_EXE_PATH = r"D:\Coding\Srishti_26\fsds-v2.2.0-windows\FSDS.exe"

# ============================================================
# UI / Window
# ============================================================
screen = pygame.display.set_mode((DEFAULT_WIDTH, DEFAULT_HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Track Designer - Race Edition")
clock = pygame.time.Clock()
fonts = build_fonts()

# ============================================================
# Dialog root
# ============================================================
tk_root = tk.Tk()
tk_root.withdraw()

# ============================================================
# State
# ============================================================
points = []
drawing = False
valid = False
message = "Start in the right circle and end in the left circle"

selected_csv_path = None
last_saved_csv_path = None
loaded_csv_cones = {"blue": [], "yellow": [], "orange": []}

show_invalid_intersection_popup = False
popup_clear_rect = None


# ============================================================
# Dynamic layout helpers
# ============================================================
def get_window_size():
    return screen.get_width(), screen.get_height()


def get_layout():
    width, height = get_window_size()
    return build_layout(width, height, left_panel_w=300)


def get_draw_rect():
    return get_layout()["DRAW_RECT"]


def get_anchor_points():
    draw_rect = get_draw_rect()
    anchor_center_x = draw_rect.x + draw_rect.w // 2
    anchor_center_y = draw_rect.y + draw_rect.h // 2 - ANCHOR_Y_OFFSET_FROM_CENTER
    end_point = (anchor_center_x - ANCHOR_LINE_LENGTH // 2, anchor_center_y)
    start_point = (anchor_center_x + ANCHOR_LINE_LENGTH // 2, anchor_center_y)
    return start_point, end_point


# ============================================================
# Utilities
# ============================================================
def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def to_meters(pixel_points):
    return [(x * SCALE, y * SCALE) for x, y in pixel_points]


def to_pixels(meter_point):
    return int(meter_point[0] / SCALE), int(meter_point[1] / SCALE)


def world_to_screen_loaded(meter_point):
    start_point, _ = get_anchor_points()
    return (
        int(start_point[0] + meter_point[0] / SCALE),
        int(start_point[1] + meter_point[1] / SCALE),
    )


def in_start_circle(pos):
    start_point, _ = get_anchor_points()
    return distance(pos, start_point) <= ANCHOR_RADIUS


def in_end_circle(pos):
    _, end_point = get_anchor_points()
    return distance(pos, end_point) <= ANCHOR_RADIUS


def in_anchor_circle(pos):
    return in_start_circle(pos) or in_end_circle(pos)


def clear_track():
    global points, valid, drawing, message, show_invalid_intersection_popup, loaded_csv_cones
    points = []
    valid = False
    drawing = False
    show_invalid_intersection_popup = False
    loaded_csv_cones = {"blue": [], "yellow": [], "orange": []}
    message = "Track cleared"


def build_closed_loop(raw_points):
    start_point, end_point = get_anchor_points()

    loop = [start_point]
    for pt in raw_points[1:]:
        loop.append(pt)

    if not loop or loop[-1] != end_point:
        loop.append(end_point)

    if loop[-1] != start_point:
        loop.append(start_point)

    return loop


def strip_anchor_zone_points(loop_points):
    start_point, end_point = get_anchor_points()

    if len(loop_points) < 3:
        return loop_points

    cleaned = [loop_points[0]]

    for pt in loop_points[1:-2]:
        if not in_anchor_circle(pt):
            if pt != cleaned[-1]:
                cleaned.append(pt)

    cleaned.append(end_point)
    cleaned.append(start_point)

    deduped = [cleaned[0]]
    for pt in cleaned[1:]:
        if pt != deduped[-1]:
            deduped.append(pt)

    return deduped


def validate_track(loop_points):
    start_point, end_point = get_anchor_points()

    if len(loop_points) < 4:
        return False, "Too few points"

    if loop_points[0] != start_point:
        return False, "Track must start at the right start circle"

    if len(loop_points) < 2 or loop_points[-2] != end_point:
        return False, "Track must end at the left end circle"

    if loop_points[-1] != start_point:
        return False, "Track not properly closed"

    filtered_points = strip_anchor_zone_points(loop_points)

    if len(filtered_points) < 4:
        return False, "Track too short"

    try:
        line = LineString(filtered_points)
    except Exception:
        return False, "Invalid track geometry"

    if not line.is_simple:
        return False, "Self-intersecting track"

    if line.length < 80:
        return False, "Track too short"

    return True, "Valid track"


def would_create_invalid_intersection(candidate_points):
    if len(candidate_points) < 4:
        return False

    filtered = [candidate_points[0]]
    for pt in candidate_points[1:]:
        if not in_anchor_circle(pt):
            if pt != filtered[-1]:
                filtered.append(pt)

    if len(filtered) < 4:
        return False

    try:
        line = LineString(filtered)
    except Exception:
        return True

    return not line.is_simple


def remove_consecutive_duplicates(track_points):
    if not track_points:
        return []

    cleaned = [track_points[0]]
    for pt in track_points[1:]:
        if pt != cleaned[-1]:
            cleaned.append(pt)
    return cleaned


def smooth_path(track_points):
    if len(track_points) < 4:
        return track_points

    pts = np.array(remove_consecutive_duplicates(track_points), dtype=float)

    if len(pts) < 4:
        return [tuple(p) for p in pts]

    if not np.array_equal(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[0]])

    try:
        x = pts[:, 0]
        y = pts[:, 1]
        tck, _ = splprep([x, y], s=5, per=True)
        u_new = np.linspace(0, 1, 240)
        x_new, y_new = splev(u_new, tck)

        smooth_pts = list(zip(x_new, y_new))
        if smooth_pts[0] != smooth_pts[-1]:
            smooth_pts.append(smooth_pts[0])
        return smooth_pts
    except Exception:
        fallback = [tuple(p) for p in pts]
        if fallback[0] != fallback[-1]:
            fallback.append(fallback[0])
        return fallback


# ============================================================
# CSV load/save/run
# ============================================================
def save_track():
    global message, selected_csv_path, last_saved_csv_path

    if not valid:
        message = "Cannot save invalid track"
        return

    suggested_dir = os.path.dirname(selected_csv_path) if selected_csv_path else os.getcwd()
    save_path = filedialog.asksaveasfilename(
        title="Save track CSV",
        initialdir=suggested_dir,
        initialfile="track.csv",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv")],
    )

    if not save_path:
        message = "Save cancelled"
        return

    smooth_pixels = smooth_path(points)
    track_m = to_meters(smooth_pixels)

    blue_cones, yellow_cones, orange_cones = generate_all_cones(track_m)

    if not blue_cones or not yellow_cones:
        message = "Track too tight or invalid for cone export"
        return

    export_csv(save_path, blue_cones, yellow_cones, orange_cones)
    selected_csv_path = save_path
    last_saved_csv_path = save_path
    message = f"Saved CSV: {os.path.basename(save_path)}"


def load_csv():
    global selected_csv_path, loaded_csv_cones, message, points, valid, drawing, show_invalid_intersection_popup

    load_path = filedialog.askopenfilename(
        title="Load existing FSDS CSV",
        initialdir=os.getcwd(),
        filetypes=[("CSV files", "*.csv")],
    )

    if not load_path:
        message = "Load cancelled"
        return

    blue, yellow, orange = [], [], []

    try:
        with open(load_path, "r", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or len(row) < 3:
                    continue

                tag = row[0].strip()
                try:
                    x = float(row[1])
                    y = float(row[2])
                except ValueError:
                    continue

                if tag == "blue":
                    blue.append((x, y))
                elif tag == "yellow":
                    yellow.append((x, y))
                elif tag == "big_orange":
                    orange.append((x, y))

    except Exception as exc:
        message = f"Failed to load CSV: {exc}"
        return

    loaded_csv_cones = {"blue": blue, "yellow": yellow, "orange": orange}
    selected_csv_path = load_path

    points = []
    valid = False
    drawing = False
    show_invalid_intersection_popup = False
    message = f"Loaded CSV: {os.path.basename(load_path)}"


def can_run_fsds():
    return bool(selected_csv_path and os.path.isfile(selected_csv_path) and os.path.isfile(FSDS_EXE_PATH))


def run_fsds_with_selected_csv():
    global message

    if not can_run_fsds():
        message = "Run unavailable. Save or load a CSV first, and check FSDS.exe path."
        return

    try:
        subprocess.Popen(
            [FSDS_EXE_PATH, f'-CustomMapPath={selected_csv_path}'],
            cwd=os.path.dirname(FSDS_EXE_PATH),
        )
        message = f"Launching FSDS with {os.path.basename(selected_csv_path)}"
    except Exception as exc:
        message = f"Failed to run FSDS: {exc}"


# ============================================================
# Drawing / Preview
# ============================================================
def draw_preview_cones_from_current_track():
    if not valid:
        return

    smooth_pixels = smooth_path(points)
    track_m = to_meters(smooth_pixels)
    blue_cones, yellow_cones, orange_cones = generate_all_cones(track_m)

    for p in blue_cones:
        px = to_pixels(p)
        pygame.draw.circle(screen, BLUE, px, 5)
        pygame.draw.circle(screen, WHITE, px, 5, 1)

    for p in yellow_cones:
        px = to_pixels(p)
        pygame.draw.circle(screen, YELLOW, px, 5)
        pygame.draw.circle(screen, WHITE, px, 5, 1)

    for p in orange_cones:
        px = to_pixels(p)
        pygame.draw.circle(screen, ORANGE, px, 7)
        pygame.draw.circle(screen, WHITE, px, 7, 1)


def draw_loaded_csv_preview():
    if points:
        return

    for p in loaded_csv_cones["blue"]:
        px = world_to_screen_loaded(p)
        pygame.draw.circle(screen, BLUE, px, 5)
        pygame.draw.circle(screen, WHITE, px, 5, 1)

    for p in loaded_csv_cones["yellow"]:
        px = world_to_screen_loaded(p)
        pygame.draw.circle(screen, YELLOW, px, 5)
        pygame.draw.circle(screen, WHITE, px, 5, 1)

    for p in loaded_csv_cones["orange"]:
        px = world_to_screen_loaded(p)
        pygame.draw.circle(screen, ORANGE, px, 7)
        pygame.draw.circle(screen, WHITE, px, 7, 1)


# ============================================================
# Main
# ============================================================
def main():
    global screen, points, drawing, valid, message, show_invalid_intersection_popup, popup_clear_rect

    w, h = get_window_size()
    draw_loading_screen(screen, fonts, w, h, 500, clock)

    running = True
    while running:
        screen.fill(BG)

        layout = get_layout()
        draw_rect = layout["DRAW_RECT"]
        start_point, end_point = get_anchor_points()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                new_w = max(960, min(event.w, DISPLAY_WIDTH))
                new_h = max(720, min(event.h, DISPLAY_HEIGHT))
                screen = pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE)

            elif show_invalid_intersection_popup:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mouse_pos = pygame.mouse.get_pos()
                    if popup_clear_rect and popup_clear_rect.collidepoint(mouse_pos):
                        clear_track()
                continue

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = pygame.mouse.get_pos()

                if layout["SAVE_BUTTON"].collidepoint(mouse_pos):
                    save_track()

                elif layout["LOAD_BUTTON"].collidepoint(mouse_pos):
                    load_csv()

                elif layout["RUN_BUTTON"].collidepoint(mouse_pos):
                    run_fsds_with_selected_csv()

                elif layout["RAMSE_BUTTON"].collidepoint(mouse_pos):
                    message = "Try RAMS-e coming soon"

                elif layout["CLEAR_BUTTON"].collidepoint(mouse_pos):
                    clear_track()

                elif draw_rect.collidepoint(mouse_pos):
                    if in_start_circle(mouse_pos):
                        drawing = True
                        points = [start_point]
                        valid = False
                        loaded_csv_cones = {"blue": [], "yellow": [], "orange": []}
                        message = "Drawing track from forced start..."
                    else:
                        message = "You must start inside the right start circle"

            elif event.type == pygame.MOUSEBUTTONUP:
                if drawing:
                    drawing = False
                    mouse_pos = pygame.mouse.get_pos()

                    if not in_end_circle(mouse_pos):
                        valid = False
                        message = "Track must end inside the left end circle"
                    else:
                        if points[-1] != end_point:
                            points.append(end_point)

                        closed_points = build_closed_loop(points)
                        valid, message = validate_track(closed_points)

                        if valid:
                            points = closed_points

            elif event.type == pygame.MOUSEMOTION and drawing:
                pos = pygame.mouse.get_pos()

                if draw_rect.collidepoint(pos):
                    if distance(points[-1], pos) >= 2:
                        candidate = points + [pos]

                        if would_create_invalid_intersection(candidate):
                            drawing = False
                            valid = False
                            show_invalid_intersection_popup = True
                            message = "Invalid path. Clear track and redraw without intersection."
                        else:
                            points.append(pos)

        draw_side_panel(
            screen=screen,
            layout=layout,
            fonts=fonts,
            message=message,
            valid=valid,
            points_count=len(points),
            scale=SCALE,
            cone_spacing_m=MIN_CONE_SPACING_M,
            selected_csv_path=selected_csv_path,
            can_run_fsds=can_run_fsds(),
        )

        draw_track_area(screen, draw_rect)
        draw_track(screen, points, valid, drawing, start_point, end_point, ANCHOR_RADIUS, fonts)
        draw_preview_cones_from_current_track()
        draw_loaded_csv_preview()

        if show_invalid_intersection_popup:
            popup_clear_rect = draw_invalid_popup(screen, fonts, screen.get_width(), screen.get_height())
        else:
            popup_clear_rect = None

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()