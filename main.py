import math
import pygame
import numpy as np
from shapely.geometry import LineString
from scipy.interpolate import splprep, splev

from fsds_cone_generation import generate_all_cones
from csv_writer import export_csv


pygame.init()

# ============================================================
# Window setup
# ============================================================
WIDTH, HEIGHT = 1200, 760
LEFT_PANEL_W = 280

DRAW_X = LEFT_PANEL_W + 20
DRAW_Y = 20
DRAW_W = WIDTH - LEFT_PANEL_W - 40
DRAW_H = HEIGHT - 40
DRAW_RECT = pygame.Rect(DRAW_X, DRAW_Y, DRAW_W, DRAW_H)

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Track Designer - Race Edition")
clock = pygame.time.Clock()

# ============================================================
# Theme / Colors
# ============================================================
BG = (18, 18, 18)
PANEL = (28, 28, 28)
PANEL_2 = (38, 38, 38)
WHITE = (240, 240, 240)
LIGHT = (200, 200, 200)
DARK = (100, 100, 100)
RED = (220, 70, 70)
GREEN = (70, 210, 120)
BLUE = (70, 140, 240)
YELLOW = (240, 220, 70)
ORANGE = (255, 160, 60)
GRID = (35, 35, 35)
ACCENT = (255, 60, 60)

# ============================================================
# Buttons
# ============================================================
SAVE_BUTTON = pygame.Rect(35, 560, 210, 46)
CLEAR_BUTTON = pygame.Rect(35, 620, 210, 46)

# ============================================================
# Fonts
# ============================================================
TITLE_FONT = pygame.font.SysFont("arial", 34, bold=True)
SUBTITLE_FONT = pygame.font.SysFont("arial", 20, bold=True)
FONT = pygame.font.SysFont("arial", 22)
SMALL_FONT = pygame.font.SysFont("arial", 18)
BIG_FONT = pygame.font.SysFont("arial", 56, bold=True)

# ============================================================
# Scale / geometry rules
# ============================================================
SCALE = 0.1  # 1 pixel = 0.1 meter
CLOSE_THRESHOLD = 30  # pixels
MIN_CONE_RADIUS_PX = 30
MIN_CONE_SPACING_M = MIN_CONE_RADIUS_PX * SCALE  # 3.0 meters

# ============================================================
# State
# ============================================================
points = []
drawing = False
valid = False
message = "Draw a closed racing line"

# ============================================================
# Utility helpers
# ============================================================
def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def to_meters(pixel_points):
    return [(x * SCALE, y * SCALE) for x, y in pixel_points]


def to_pixels(meter_point):
    return int(meter_point[0] / SCALE), int(meter_point[1] / SCALE)


def wrap_text(text, max_chars):
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]

    for word in words[1:]:
        if len(current) + 1 + len(word) <= max_chars:
            current += " " + word
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


def draw_text(text, x, y, color=WHITE, font=FONT):
    img = font.render(text, True, color)
    screen.blit(img, (x, y))


def draw_center_text(text, y, color=WHITE, font=BIG_FONT):
    img = font.render(text, True, color)
    rect = img.get_rect(center=(WIDTH // 2, y))
    screen.blit(img, rect)


# ============================================================
# Track validation
# ============================================================
def is_closed(track_points, threshold=CLOSE_THRESHOLD):
    if len(track_points) < 3:
        return False
    return distance(track_points[0], track_points[-1]) < threshold


def auto_close_loop(track_points, threshold=CLOSE_THRESHOLD):
    if len(track_points) < 3:
        return track_points, False

    if is_closed(track_points, threshold):
        if track_points[0] != track_points[-1]:
            return track_points + [track_points[0]], True
        return track_points, True

    return track_points, False


def validate_track(track_points):
    if len(track_points) < 4:
        return False, "Too few points"

    if track_points[0] != track_points[-1]:
        return False, "Track not closed"

    try:
        line = LineString(track_points)
    except Exception:
        return False, "Invalid track geometry"

    if not line.is_simple:
        return False, "Self-intersecting track"

    if line.length < 80:
        return False, "Track too short"

    return True, "Valid track"


# ============================================================
# Path smoothing
# ============================================================
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
# UI drawing helpers
# ============================================================
def draw_checkered_flag(x, y, cell=8, rows=4, cols=4):
    for r in range(rows):
        for c in range(cols):
            color = WHITE if (r + c) % 2 == 0 else (30, 30, 30)
            pygame.draw.rect(screen, color, (x + c * cell, y + r * cell, cell, cell))
    pygame.draw.rect(screen, LIGHT, (x, y, cols * cell, rows * cell), 1)


def draw_button(rect, text, enabled=True, icon=None):
    mouse = pygame.mouse.get_pos()
    hovered = rect.collidepoint(mouse)

    if enabled:
        fill = (55, 55, 55) if not hovered else (75, 75, 75)
        border = ACCENT if hovered else LIGHT
        txt = WHITE
    else:
        fill = (45, 45, 45)
        border = DARK
        txt = DARK

    pygame.draw.rect(screen, fill, rect, border_radius=14)
    pygame.draw.rect(screen, border, rect, 2, border_radius=14)

    label = FONT.render(text, True, txt)
    label_rect = label.get_rect(center=rect.center)
    screen.blit(label, label_rect)

    if icon == "save":
        pygame.draw.rect(screen, txt, (rect.x + 16, rect.y + 12, 14, 18), 2, border_radius=2)
        pygame.draw.rect(screen, txt, (rect.x + 19, rect.y + 15, 8, 5))
    elif icon == "clear":
        pygame.draw.line(screen, txt, (rect.x + 15, rect.y + 14), (rect.x + 28, rect.y + 27), 3)
        pygame.draw.line(screen, txt, (rect.x + 28, rect.y + 14), (rect.x + 15, rect.y + 27), 3)


def draw_grid():
    for x in range(DRAW_X, DRAW_X + DRAW_W, 32):
        pygame.draw.line(screen, GRID, (x, DRAW_Y), (x, DRAW_Y + DRAW_H))
    for y in range(DRAW_Y, DRAW_Y + DRAW_H, 32):
        pygame.draw.line(screen, GRID, (DRAW_X, y), (DRAW_X + DRAW_W, y))


def draw_track_area():
    pygame.draw.rect(screen, (24, 24, 24), DRAW_RECT, border_radius=18)
    pygame.draw.rect(screen, (60, 60, 60), DRAW_RECT, 2, border_radius=18)
    draw_grid()

    stripe_w = 18
    for i in range(10):
        color = WHITE if i % 2 == 0 else (30, 30, 30)
        pygame.draw.rect(screen, color, (DRAW_X + 20 + i * stripe_w, DRAW_Y + 8, stripe_w, 10))


def draw_side_panel():
    pygame.draw.rect(screen, PANEL, (0, 0, LEFT_PANEL_W, HEIGHT))
    pygame.draw.rect(screen, PANEL_2, (0, 0, LEFT_PANEL_W, 100))
    pygame.draw.line(screen, (55, 55, 55), (LEFT_PANEL_W, 0), (LEFT_PANEL_W, HEIGHT), 2)

    draw_checkered_flag(28, 24)
    draw_text("TRACK DESIGNER", 75, 24, WHITE, TITLE_FONT)
    draw_text("Race Edition", 78, 62, ACCENT, SUBTITLE_FONT)

    draw_text("Instructions", 35, 130, WHITE, SUBTITLE_FONT)
    draw_text("• Hold mouse and draw track", 35, 165, LIGHT, SMALL_FONT)
    draw_text("• End near start to auto-close", 35, 192, LIGHT, SMALL_FONT)
    draw_text(f"• Close threshold: {CLOSE_THRESHOLD}px", 35, 219, LIGHT, SMALL_FONT)
    draw_text(f"• Scale: 1 px = {SCALE:.1f} m", 35, 246, LIGHT, SMALL_FONT)
    draw_text(f"• Cone spacing: {MIN_CONE_SPACING_M:.1f} m", 35, 273, LIGHT, SMALL_FONT)

    draw_text("Status", 35, 330, WHITE, SUBTITLE_FONT)

    badge_color = GREEN if valid else ORANGE if len(points) > 1 else DARK
    badge_text = "VALID" if valid else "DRAWING" if len(points) > 1 else "IDLE"

    pygame.draw.rect(screen, badge_color, (35, 364, 110, 34), border_radius=10)
    draw_text(badge_text, 62, 371, (15, 15, 15), SMALL_FONT)

    draw_text("Message", 35, 430, WHITE, SUBTITLE_FONT)
    wrapped = wrap_text(message, 28)
    y = 466
    for line in wrapped[:5]:
        draw_text(line, 35, y, LIGHT, SMALL_FONT)
        y += 24

    draw_button(SAVE_BUTTON, "Save CSV", enabled=valid, icon="save")
    draw_button(CLEAR_BUTTON, "Clear Track", enabled=True, icon="clear")

    draw_text("Formula Student style preview", 35, 700, DARK, SMALL_FONT)


def draw_track(track_points, is_valid, currently_drawing):
    if len(track_points) < 2:
        return

    pygame.draw.lines(screen, (20, 20, 20), False, track_points, 12)

    base_color = GREEN if is_valid else RED
    pygame.draw.lines(screen, base_color, False, track_points, 4)

    pygame.draw.circle(screen, WHITE, track_points[0], 6)
    pygame.draw.circle(screen, ACCENT, track_points[0], 12, 2)
    pygame.draw.circle(screen, LIGHT, track_points[-1], 4)

    if currently_drawing and len(track_points) > 2:
        pygame.draw.circle(screen, BLUE, track_points[0], CLOSE_THRESHOLD, 1)
        if distance(track_points[0], track_points[-1]) < CLOSE_THRESHOLD:
            pygame.draw.circle(screen, GREEN, track_points[0], CLOSE_THRESHOLD, 2)


def draw_preview_cones():
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


# ============================================================
# Actions
# ============================================================
def clear_track():
    global points, valid, drawing, message
    points = []
    valid = False
    drawing = False
    message = "Track cleared"


def save_track():
    global message

    if not valid:
        message = "Cannot save invalid track"
        return

    smooth_pixels = smooth_path(points)
    track_m = to_meters(smooth_pixels)

    blue_cones, yellow_cones, orange_cones = generate_all_cones(track_m)

    if not blue_cones or not yellow_cones:
        message = "Track too tight or invalid for cone export"
        return

    export_csv("../track.csv", blue_cones, yellow_cones, orange_cones)
    message = "Track saved successfully as track.csv"


# ============================================================
# Loading screen
# ============================================================
def show_loading_screen(duration_ms=1500):
    start_time = pygame.time.get_ticks()

    while pygame.time.get_ticks() - start_time < duration_ms:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

        screen.fill((10, 10, 10))

        for i in range(0, WIDTH, 80):
            pygame.draw.line(screen, (25, 25, 25), (i, 0), (i - 200, HEIGHT), 2)

        draw_center_text("TRACK DESIGNER", HEIGHT // 2 - 80, WHITE, BIG_FONT)
        draw_center_text("Race Edition", HEIGHT // 2 - 20, ACCENT, TITLE_FONT)

        elapsed = pygame.time.get_ticks() - start_time
        progress = min(elapsed / duration_ms, 1.0)

        bar_w = 420
        bar_h = 24
        bar_x = WIDTH // 2 - bar_w // 2
        bar_y = HEIGHT // 2 + 60

        pygame.draw.rect(screen, (45, 45, 45), (bar_x, bar_y, bar_w, bar_h), border_radius=12)
        pygame.draw.rect(screen, ACCENT, (bar_x, bar_y, int(bar_w * progress), bar_h), border_radius=12)
        pygame.draw.rect(screen, LIGHT, (bar_x, bar_y, bar_w, bar_h), 2, border_radius=12)

        draw_center_text("Initializing racing surface...", HEIGHT // 2 + 130, LIGHT, SUBTITLE_FONT)

        cx = WIDTH // 2 - 22
        cy = HEIGHT // 2 - 170
        draw_checkered_flag(cx, cy, cell=11, rows=4, cols=4)

        pygame.display.flip()
        clock.tick(60)


# ============================================================
# Main loop
# ============================================================
def main():
    global points, drawing, valid, message

    show_loading_screen(3000)

    running = True
    while running:
        screen.fill(BG)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = pygame.mouse.get_pos()

                if SAVE_BUTTON.collidepoint(mouse_pos):
                    save_track()

                elif CLEAR_BUTTON.collidepoint(mouse_pos):
                    clear_track()

                elif DRAW_RECT.collidepoint(mouse_pos):
                    drawing = True
                    points = []
                    valid = False
                    message = "Drawing track..."

            elif event.type == pygame.MOUSEBUTTONUP:
                if drawing:
                    drawing = False
                    closed_points, was_closed = auto_close_loop(points)

                    if not was_closed:
                        valid = False
                        message = "Track not closed. End closer to the start."
                    else:
                        points = closed_points
                        valid, message = validate_track(points)

            elif event.type == pygame.MOUSEMOTION and drawing:
                pos = pygame.mouse.get_pos()

                if DRAW_RECT.collidepoint(pos):
                    if not points:
                        points.append(pos)
                    else:
                        if distance(points[-1], pos) >= 2:
                            points.append(pos)

        draw_side_panel()
        draw_track_area()
        draw_track(points, valid, drawing)
        draw_preview_cones()

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()