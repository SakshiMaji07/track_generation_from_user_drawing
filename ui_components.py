import math
import random
from dataclasses import dataclass
from typing import List, Tuple, Optional

import pygame

Color = Tuple[int, int, int]

BG = (8, 10, 14)
PANEL = (14, 17, 22)
PANEL_2 = (20, 24, 31)
TEXT = (235, 238, 244)
MUTED = (145, 155, 170)
SUBTLE = (90, 98, 112)

RED = (210, 35, 45)
RED_2 = (255, 72, 82)
GREEN = (70, 210, 120)
BLUE = (75, 160, 255)
YELLOW = (255, 210, 70)
ORANGE = (255, 145, 60)
WHITE = (245, 245, 245)
GRID = (28, 31, 38)
TRACK_DARK = (18, 18, 18)
TRACK_EDGE = (110, 115, 125)
OVERLAY = (0, 0, 0, 170)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def scale_value(value, width, height, base_w=1600, base_h=900):
    sx = width / base_w
    sy = height / base_h
    return int(value * min(sx, sy))


def build_fonts(width, height):
    title = clamp(scale_value(32, width, height), 24, 40)
    subtitle = clamp(scale_value(18, width, height), 15, 24)
    body = clamp(scale_value(19, width, height), 15, 24)
    small = clamp(scale_value(15, width, height), 12, 20)
    big = clamp(scale_value(50, width, height), 34, 72)

    font_name = "bahnschrift"
    alt_name = "segoeui"

    return {
        "title": pygame.font.SysFont(font_name, title, bold=True),
        "subtitle": pygame.font.SysFont(font_name, subtitle, bold=True),
        "font": pygame.font.SysFont(font_name, body),
        "small": pygame.font.SysFont(alt_name, small),
        "big": pygame.font.SysFont(font_name, big, bold=True),
    }


def build_layout(width, height):
    panel_w = clamp(int(width * 0.24), 290, 420)
    margin = clamp(int(min(width, height) * 0.02), 12, 24)
    gap = clamp(int(min(width, height) * 0.014), 8, 18)
    btn_h = clamp(int(height * 0.055), 42, 62)

    draw_x = panel_w + margin
    draw_y = margin
    draw_w = max(500, width - panel_w - (2 * margin))
    draw_h = max(400, height - (2 * margin))

    btn_x = margin + 18
    btn_w = panel_w - 2 * (18 + margin // 3)

    base_y = height - (btn_h * 5 + gap * 4 + margin)

    def rect_at(i):
        return pygame.Rect(btn_x, base_y + i * (btn_h + gap), btn_w, btn_h)

    return {
        "WIDTH": width,
        "HEIGHT": height,
        "LEFT_PANEL_W": panel_w,
        "MARGIN": margin,
        "DRAW_RECT": pygame.Rect(draw_x, draw_y, draw_w, draw_h),
        "SAVE_BUTTON": rect_at(0),
        "LOAD_BUTTON": rect_at(1),
        "RUN_BUTTON": rect_at(2),
        "RAMSE_BUTTON": rect_at(3),
        "CLEAR_BUTTON": rect_at(4),
    }


@dataclass
class Spark:
    x: float
    y: float
    vx: float
    vy: float
    r: float


def make_sparks(width, height, count=24):
    sparks = []
    for _ in range(count):
        sparks.append(
            Spark(
                x=random.uniform(0, width),
                y=random.uniform(0, height),
                vx=random.uniform(-0.9, 0.9),
                vy=random.uniform(-0.7, 0.7),
                r=random.uniform(2.0, 5.0),
            )
        )
    return sparks


def update_sparks(sparks: List[Spark], width: int, height: int):
    for s in sparks:
        s.x += s.vx
        s.y += s.vy

        if s.x < 0 or s.x > width:
            s.vx *= -1
        if s.y < 0 or s.y > height:
            s.vy *= -1

        s.x = clamp(s.x, 0, width)
        s.y = clamp(s.y, 0, height)


def draw_sparks(screen, sparks: List[Spark]):
    for s in sparks:
        alpha_surf = pygame.Surface((int(s.r * 6), int(s.r * 6)), pygame.SRCALPHA)
        pygame.draw.circle(alpha_surf, (255, 45, 55, 60), (alpha_surf.get_width() // 2, alpha_surf.get_height() // 2), int(s.r * 2))
        pygame.draw.circle(alpha_surf, (255, 110, 110, 120), (alpha_surf.get_width() // 2, alpha_surf.get_height() // 2), int(s.r))
        screen.blit(alpha_surf, (s.x - alpha_surf.get_width() / 2, s.y - alpha_surf.get_height() / 2))


def wrap_text_to_width(text: str, font: pygame.font.Font, max_width: int):
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]

    for word in words[1:]:
        candidate = current + " " + word
        if font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


def draw_text(screen, text, x, y, font, color=TEXT):
    img = font.render(text, True, color)
    screen.blit(img, (x, y))


def draw_center_text(screen, text, y, font, width, color=TEXT):
    img = font.render(text, True, color)
    rect = img.get_rect(center=(width // 2, y))
    screen.blit(img, rect)


def draw_checkered_flag(screen, x, y, cell=8, rows=4, cols=4):
    for r in range(rows):
        for c in range(cols):
            color = WHITE if (r + c) % 2 == 0 else (20, 20, 20)
            pygame.draw.rect(screen, color, (x + c * cell, y + r * cell, cell, cell))
    pygame.draw.rect(screen, MUTED, (x, y, cols * cell, rows * cell), 1)


def draw_button(screen, rect, text, font, enabled=True, icon=None):
    mouse = pygame.mouse.get_pos()
    hovered = rect.collidepoint(mouse)

    fill = PANEL_2 if enabled else (32, 34, 40)
    border = RED_2 if hovered and enabled else (85, 90, 100)
    txt = TEXT if enabled else SUBTLE

    if hovered and enabled:
        glow = pygame.Surface((rect.width + 18, rect.height + 18), pygame.SRCALPHA)
        pygame.draw.rect(glow, (255, 45, 55, 45), glow.get_rect(), border_radius=18)
        screen.blit(glow, (rect.x - 9, rect.y - 9))

    pygame.draw.rect(screen, fill, rect, border_radius=16)
    pygame.draw.rect(screen, border, rect, 2, border_radius=16)

    label = font.render(text, True, txt)
    label_rect = label.get_rect(center=rect.center)
    screen.blit(label, label_rect)

    ix = rect.x + 16
    iy = rect.y + rect.height // 2

    if icon == "save":
        pygame.draw.rect(screen, txt, (ix, iy - 9, 14, 18), 2, border_radius=2)
        pygame.draw.rect(screen, txt, (ix + 3, iy - 6, 8, 5))
    elif icon == "load":
        pygame.draw.rect(screen, txt, (ix - 2, iy - 6, 16, 12), 2, border_radius=2)
        pygame.draw.line(screen, txt, (ix + 6, iy - 12), (ix + 6, iy + 2), 3)
        pygame.draw.polygon(screen, txt, [(ix + 6, iy + 7), (ix, iy - 1), (ix + 12, iy - 1)])
    elif icon == "run":
        pygame.draw.polygon(screen, txt, [(ix, iy - 10), (ix, iy + 10), (ix + 16, iy)])
    elif icon == "clear":
        pygame.draw.line(screen, txt, (ix, iy - 8), (ix + 12, iy + 8), 3)
        pygame.draw.line(screen, txt, (ix + 12, iy - 8), (ix, iy + 8), 3)
    elif icon == "rocket":
        pygame.draw.polygon(screen, txt, [(ix + 8, iy - 12), (ix + 15, iy), (ix + 8, iy + 12), (ix + 1, iy)])


def draw_racing_background(screen, width, height):
    screen.fill(BG)
    for i in range(-height, width, 90):
        pygame.draw.line(screen, (18, 20, 26), (i, 0), (i + height, height), 2)

    glow = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.ellipse(glow, (255, 25, 35, 22), (-width * 0.1, height * 0.72, width * 1.2, height * 0.45))
    screen.blit(glow, (0, 0))


def draw_grid(screen, draw_rect):
    step = 32
    for x in range(draw_rect.left, draw_rect.right, step):
        pygame.draw.line(screen, GRID, (x, draw_rect.top), (x, draw_rect.bottom))
    for y in range(draw_rect.top, draw_rect.bottom, step):
        pygame.draw.line(screen, GRID, (draw_rect.left, y), (draw_rect.right, y))


def draw_track_area(screen, draw_rect):
    pygame.draw.rect(screen, TRACK_DARK, draw_rect, border_radius=24)
    pygame.draw.rect(screen, TRACK_EDGE, draw_rect, 2, border_radius=24)
    draw_grid(screen, draw_rect)

    stripe_w = 18
    stripe_h = 10
    sx = draw_rect.x + 18
    sy = draw_rect.y + 10
    for i in range(10):
        color = WHITE if i % 2 == 0 else (35, 35, 35)
        pygame.draw.rect(screen, color, (sx + i * stripe_w, sy, stripe_w, stripe_h), border_radius=2)


def _draw_wrapped_block(screen, text, x, y, width, max_lines, font, color):
    lines = wrap_text_to_width(text, font, width)
    yy = y
    for line in lines[:max_lines]:
        draw_text(screen, line, x, yy, font, color)
        yy += font.get_height() + 4


def draw_side_panel(screen, layout, fonts, message, valid, points_count, scale, cone_spacing_m, selected_csv_path, can_run_fsds, telemetry_status):
    w = layout["LEFT_PANEL_W"]
    h = layout["HEIGHT"]
    pad = layout["MARGIN"]

    pygame.draw.rect(screen, PANEL, (0, 0, w, h))
    pygame.draw.rect(screen, PANEL_2, (0, 0, w, clamp(int(h * 0.12), 88, 120)))
    pygame.draw.line(screen, (48, 52, 60), (w, 0), (w, h), 2)

    draw_checkered_flag(screen, pad + 10, pad + 10, cell=8)
    draw_text(screen, "IITRMS", pad + 56, pad + 6, fonts["title"], TEXT)
    draw_text(screen, "Autonomous Track Generator", pad + 56, pad + 40, fonts["subtitle"], RED_2)

    y0 = clamp(int(h * 0.14), 115, 150)
    line_gap = clamp(int(h * 0.028), 22, 32)

    draw_text(screen, "Session", pad + 10, y0, fonts["subtitle"], TEXT)
    draw_text(screen, f"Scale: 1 px = {scale:.2f} m", pad + 10, y0 + line_gap, fonts["small"], MUTED)
    draw_text(screen, f"Cone spacing: {cone_spacing_m:.2f} m", pad + 10, y0 + 2 * line_gap, fonts["small"], MUTED)
    draw_text(screen, f"Points: {points_count}", pad + 10, y0 + 3 * line_gap, fonts["small"], MUTED)
    draw_text(screen, f"FSDS: {telemetry_status}", pad + 10, y0 + 4 * line_gap, fonts["small"], MUTED)

    badge_y = y0 + 5 * line_gap + 8
    badge_color = GREEN if valid else ORANGE if points_count > 1 else SUBTLE
    badge_text = "VALID" if valid else "DRAWING" if points_count > 1 else "IDLE"
    pygame.draw.rect(screen, badge_color, (pad + 10, badge_y, 120, 34), border_radius=10)
    draw_text(screen, badge_text, pad + 40, badge_y + 7, fonts["small"], (18, 18, 18))

    msg_y = badge_y + 52
    draw_text(screen, "Status", pad + 10, msg_y, fonts["subtitle"], TEXT)
    _draw_wrapped_block(
        screen,
        message,
        pad + 10,
        msg_y + 30,
        w - (2 * pad) - 12,
        5,
        fonts["small"],
        MUTED,
    )

    csv_y = msg_y + 150
    draw_text(screen, "Selected CSV", pad + 10, csv_y, fonts["subtitle"], TEXT)
    selected_display = selected_csv_path if selected_csv_path else "None"
    _draw_wrapped_block(
        screen,
        selected_display,
        pad + 10,
        csv_y + 30,
        w - (2 * pad) - 12,
        3,
        fonts["small"],
        MUTED if selected_csv_path else SUBTLE,
    )

    draw_button(screen, layout["SAVE_BUTTON"], "Save CSV", fonts["font"], enabled=valid, icon="save")
    draw_button(screen, layout["LOAD_BUTTON"], "Load CSV", fonts["font"], enabled=True, icon="load")
    draw_button(screen, layout["RUN_BUTTON"], "Run FSDS", fonts["font"], enabled=can_run_fsds, icon="run")
    draw_button(screen, layout["RAMSE_BUTTON"], "Try RAMS-e", fonts["font"], enabled=can_run_fsds, icon="rocket")
    draw_button(screen, layout["CLEAR_BUTTON"], "Clear Track", fonts["font"], enabled=True, icon="clear")


def draw_start_end_guides(screen, start_point, end_point, anchor_radius, fonts):
    pygame.draw.line(screen, WHITE, end_point, start_point, 3)

    pygame.draw.circle(screen, RED_2, end_point, anchor_radius, 3)
    pygame.draw.circle(screen, WHITE, end_point, 5)
    draw_text(screen, "END", end_point[0] - 16, end_point[1] - 38, fonts["small"], RED_2)

    pygame.draw.circle(screen, GREEN, start_point, anchor_radius, 3)
    pygame.draw.circle(screen, WHITE, start_point, 5)
    draw_text(screen, "START", start_point[0] - 24, start_point[1] - 38, fonts["small"], GREEN)


def draw_track(screen, track_points, is_valid, currently_drawing, start_point, end_point, anchor_radius, fonts):
    if len(track_points) >= 2:
        pygame.draw.lines(screen, (20, 20, 20), False, track_points, 12)
        base_color = GREEN if is_valid else RED_2
        pygame.draw.lines(screen, base_color, False, track_points, 4)

        pygame.draw.circle(screen, WHITE, track_points[0], 5)
        pygame.draw.circle(screen, RED_2, track_points[0], 11, 2)
        pygame.draw.circle(screen, MUTED, track_points[-1], 4)

    draw_start_end_guides(screen, start_point, end_point, anchor_radius, fonts)

    if currently_drawing:
        pygame.draw.circle(screen, GREEN, start_point, anchor_radius, 2)
        pygame.draw.circle(screen, RED_2, end_point, anchor_radius, 2)


def draw_cones(screen, blue_pts, yellow_pts, orange_pts):
    for x, y in blue_pts:
        pygame.draw.circle(screen, (70, 140, 255), (int(x), int(y)), 6)
    for x, y in yellow_pts:
        pygame.draw.circle(screen, (255, 220, 70), (int(x), int(y)), 6)
    for x, y in orange_pts:
        pygame.draw.circle(screen, (255, 145, 60), (int(x), int(y)), 7)


def draw_invalid_popup(screen, fonts, width, height, title, body):
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    overlay.fill(OVERLAY)
    screen.blit(overlay, (0, 0))

    popup_w, popup_h = min(500, width - 60), 240
    popup_x = width // 2 - popup_w // 2
    popup_y = height // 2 - popup_h // 2
    popup_rect = pygame.Rect(popup_x, popup_y, popup_w, popup_h)

    pygame.draw.rect(screen, PANEL_2, popup_rect, border_radius=20)
    pygame.draw.rect(screen, RED_2, popup_rect, 3, border_radius=20)

    draw_text(screen, title, popup_x + 26, popup_y + 24, fonts["title"], TEXT)
    _draw_wrapped_block(
        screen,
        body,
        popup_x + 26,
        popup_y + 82,
        popup_w - 52,
        5,
        fonts["font"],
        MUTED,
    )

    clear_rect = pygame.Rect(popup_x + popup_w // 2 - 95, popup_y + 180, 190, 42)
    draw_button(screen, clear_rect, "Clear Track", fonts["font"], enabled=True, icon="clear")
    return clear_rect


def draw_loading_screen(screen, fonts, width, height, duration_ms, clock, sparks):
    start_time = pygame.time.get_ticks()

    while pygame.time.get_ticks() - start_time < duration_ms:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

        draw_racing_background(screen, width, height)
        update_sparks(sparks, width, height)
        draw_sparks(screen, sparks)

        draw_center_text(screen, "IITRMS", height // 2 - 110, fonts["big"], width, TEXT)
        draw_center_text(screen, "Autonomous Track Generator", height // 2 - 46, fonts["title"], width, RED_2)

        elapsed = pygame.time.get_ticks() - start_time
        progress = min(elapsed / duration_ms, 1.0)

        bar_w = min(480, width - 120)
        bar_h = 24
        bar_x = width // 2 - bar_w // 2
        bar_y = height // 2 + 50

        pygame.draw.rect(screen, PANEL_2, (bar_x, bar_y, bar_w, bar_h), border_radius=12)
        pygame.draw.rect(screen, RED_2, (bar_x, bar_y, int(bar_w * progress), bar_h), border_radius=12)
        pygame.draw.rect(screen, MUTED, (bar_x, bar_y, bar_w, bar_h), 2, border_radius=12)

        draw_center_text(screen, "Initializing motorsport UI...", height // 2 + 112, fonts["subtitle"], width, MUTED)

        pygame.display.flip()
        clock.tick(60)


def draw_leaderboard_modal(screen, fonts, width, height, active_tab, current_map_rows, duel_stats):
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    modal_w = min(1020, width - 80)
    modal_h = min(650, height - 80)
    x = width // 2 - modal_w // 2
    y = height // 2 - modal_h // 2
    rect = pygame.Rect(x, y, modal_w, modal_h)

    pygame.draw.rect(screen, PANEL, rect, border_radius=24)
    pygame.draw.rect(screen, RED_2, rect, 2, border_radius=24)

    draw_text(screen, "Leaderboard", x + 26, y + 22, fonts["title"], TEXT)

    tab1 = pygame.Rect(x + 26, y + 74, 180, 42)
    tab2 = pygame.Rect(x + 214, y + 74, 220, 42)

    draw_button(screen, tab1, "Current Map", fonts["small"], enabled=True)
    draw_button(screen, tab2, "RAMS-e vs IITR", fonts["small"], enabled=True)

    header_y = y + 138

    if active_tab == "map":
        headers = ["Rank", "Name", "Source", "Lap Time (s)", "Cones", "Date"]
        xs = [x + 28, x + 90, x + 260, x + 410, x + 570, x + 650]

        for hx, htxt in zip(xs, headers):
            draw_text(screen, htxt, hx, header_y, fonts["small"], RED_2)

        row_y = header_y + 34
        for idx, row in enumerate(current_map_rows[:12], start=1):
            draw_text(screen, str(idx), xs[0], row_y, fonts["small"], TEXT)
            draw_text(screen, row["player_name"][:16], xs[1], row_y, fonts["small"], TEXT)
            draw_text(screen, row["source"], xs[2], row_y, fonts["small"], MUTED)
            draw_text(screen, f'{row["lap_time_s"]:.3f}', xs[3], row_y, fonts["small"], TEXT)
            draw_text(screen, str(row["cone_hits"]), xs[4], row_y, fonts["small"], TEXT)
            draw_text(screen, row["created_at"][:19].replace("T", " "), xs[5], row_y, fonts["small"], MUTED)
            row_y += 34
    else:
        draw_text(screen, f'RAMS-e Wins: {duel_stats["ramse_wins"]}', x + 34, header_y + 20, fonts["font"], TEXT)
        draw_text(screen, f'IITR Human Wins: {duel_stats["human_wins"]}', x + 34, header_y + 60, fonts["font"], TEXT)
        draw_text(screen, f'Total Comparisons: {duel_stats["comparisons"]}', x + 34, header_y + 100, fonts["font"], TEXT)

        rules = [
            "RAMS-e wins only if it has lower lap time and lower cone hits than the compared human entry.",
            "Human wins if the human entry beats RAMS-e on both metrics.",
            "Mixed results are ignored as no clear winner.",
        ]
        yy = header_y + 170
        for line in rules:
            draw_text(screen, line, x + 34, yy, fonts["small"], MUTED)
            yy += 30

    close_rect = pygame.Rect(x + modal_w - 130, y + modal_h - 62, 100, 40)
    draw_button(screen, close_rect, "Close", fonts["small"], enabled=True)
    return {"close": close_rect, "tab_map": tab1, "tab_duel": tab2}


def draw_custom_cursor(screen, pos):
    x, y = pos
    pygame.draw.circle(screen, RED_2, (x, y), 10, 2)
    pygame.draw.line(screen, WHITE, (x - 14, y), (x - 4, y), 2)
    pygame.draw.line(screen, WHITE, (x + 4, y), (x + 14, y), 2)
    pygame.draw.line(screen, WHITE, (x, y - 14), (x, y - 4), 2)
    pygame.draw.line(screen, WHITE, (x, y + 4), (x, y + 14), 2)
    pygame.draw.circle(screen, WHITE, (x, y), 2)