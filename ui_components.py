import pygame


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
OVERLAY = (0, 0, 0, 170)


# ============================================================
# Fonts
# ============================================================
def build_fonts():
    return {
        "title": pygame.font.SysFont("arial", 34, bold=True),
        "subtitle": pygame.font.SysFont("arial", 20, bold=True),
        "font": pygame.font.SysFont("arial", 22),
        "small": pygame.font.SysFont("arial", 18),
        "big": pygame.font.SysFont("arial", 56, bold=True),
    }


# ============================================================
# Layout
# ============================================================
def build_layout(width, height, left_panel_w=300):
    draw_x = left_panel_w + 20
    draw_y = 20
    draw_w = width - left_panel_w - 40
    draw_h = height - 40

    return {
        "WIDTH": width,
        "HEIGHT": height,
        "LEFT_PANEL_W": left_panel_w,
        "DRAW_RECT": pygame.Rect(draw_x, draw_y, draw_w, draw_h),
        "SAVE_BUTTON": pygame.Rect(35, 500, 230, 40),
        "LOAD_BUTTON": pygame.Rect(35, 548, 230, 40),
        "RUN_BUTTON": pygame.Rect(35, 596, 230, 40),
        "RAMSE_BUTTON": pygame.Rect(35, 644, 230, 40),
        "CLEAR_BUTTON": pygame.Rect(35, 692, 230, 40),
    }


# ============================================================
# Drawing helpers
# ============================================================
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


def draw_text(screen, text, x, y, font, color=WHITE):
    img = font.render(text, True, color)
    screen.blit(img, (x, y))


def draw_center_text(screen, text, y, font, width, color=WHITE):
    img = font.render(text, True, color)
    rect = img.get_rect(center=(width // 2, y))
    screen.blit(img, rect)


def draw_checkered_flag(screen, x, y, cell=8, rows=4, cols=4):
    for r in range(rows):
        for c in range(cols):
            color = WHITE if (r + c) % 2 == 0 else (30, 30, 30)
            pygame.draw.rect(screen, color, (x + c * cell, y + r * cell, cell, cell))
    pygame.draw.rect(screen, LIGHT, (x, y, cols * cell, rows * cell), 1)


def draw_button(screen, rect, text, font, enabled=True, icon=None):
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

    label = font.render(text, True, txt)
    label_rect = label.get_rect(center=rect.center)
    screen.blit(label, label_rect)

    if icon == "save":
        pygame.draw.rect(screen, txt, (rect.x + 14, rect.y + 10, 14, 18), 2, border_radius=2)
        pygame.draw.rect(screen, txt, (rect.x + 17, rect.y + 13, 8, 5))
    elif icon == "load":
        pygame.draw.rect(screen, txt, (rect.x + 13, rect.y + 12, 16, 12), 2, border_radius=2)
        pygame.draw.line(screen, txt, (rect.x + 21, rect.y + 8), (rect.x + 21, rect.y + 22), 3)
        pygame.draw.polygon(screen, txt, [(rect.x + 21, rect.y + 26), (rect.x + 15, rect.y + 18), (rect.x + 27, rect.y + 18)])
    elif icon == "run":
        pygame.draw.polygon(screen, txt, [(rect.x + 15, rect.y + 10), (rect.x + 15, rect.y + 30), (rect.x + 31, rect.y + 20)])
    elif icon == "clear":
        pygame.draw.line(screen, txt, (rect.x + 15, rect.y + 12), (rect.x + 28, rect.y + 25), 3)
        pygame.draw.line(screen, txt, (rect.x + 28, rect.y + 12), (rect.x + 15, rect.y + 25), 3)
    elif icon == "rocket":
        pygame.draw.polygon(screen, txt, [(rect.x + 22, rect.y + 8), (rect.x + 29, rect.y + 18), (rect.x + 22, rect.y + 30), (rect.x + 15, rect.y + 18)])


def draw_grid(screen, draw_rect):
    for x in range(draw_rect.left, draw_rect.right, 32):
        pygame.draw.line(screen, GRID, (x, draw_rect.top), (x, draw_rect.bottom))
    for y in range(draw_rect.top, draw_rect.bottom, 32):
        pygame.draw.line(screen, GRID, (draw_rect.left, y), (draw_rect.right, y))


def draw_track_area(screen, draw_rect):
    pygame.draw.rect(screen, (24, 24, 24), draw_rect, border_radius=18)
    pygame.draw.rect(screen, (60, 60, 60), draw_rect, 2, border_radius=18)
    draw_grid(screen, draw_rect)

    stripe_w = 18
    for i in range(10):
        color = WHITE if i % 2 == 0 else (30, 30, 30)
        pygame.draw.rect(screen, color, (draw_rect.x + 20 + i * stripe_w, draw_rect.y + 8, stripe_w, 10))


def draw_side_panel(
    screen,
    layout,
    fonts,
    message,
    valid,
    points_count,
    scale,
    cone_spacing_m,
    selected_csv_path,
    can_run_fsds,
):
    left_panel_w = layout["LEFT_PANEL_W"]

    pygame.draw.rect(screen, PANEL, (0, 0, left_panel_w, layout["HEIGHT"]))
    pygame.draw.rect(screen, PANEL_2, (0, 0, left_panel_w, 100))
    pygame.draw.line(screen, (55, 55, 55), (left_panel_w, 0), (left_panel_w, layout["HEIGHT"]), 2)

    draw_checkered_flag(screen, 28, 24)
    draw_text(screen, "TRACK DESIGNER", 75, 24, fonts["title"], WHITE)
    draw_text(screen, "Race Edition", 78, 62, fonts["subtitle"], ACCENT)

    draw_text(screen, "Instructions", 35, 120, fonts["subtitle"], WHITE)
    draw_text(screen, "• Start inside right circle", 35, 155, fonts["small"], LIGHT)
    draw_text(screen, "• Finish inside left circle", 35, 180, fonts["small"], LIGHT)
    draw_text(screen, "• Invalid intersection stops draw", 35, 205, fonts["small"], LIGHT)
    draw_text(screen, "• Load CSV = preview + run target", 35, 230, fonts["small"], LIGHT)
    draw_text(screen, f"• Scale: 1 px = {scale:.2f} m", 35, 255, fonts["small"], LIGHT)
    draw_text(screen, f"• Cone spacing: {cone_spacing_m:.2f} m", 35, 280, fonts["small"], LIGHT)

    draw_text(screen, "Status", 35, 325, fonts["subtitle"], WHITE)
    badge_color = GREEN if valid else ORANGE if points_count > 1 else DARK
    badge_text = "VALID" if valid else "DRAWING" if points_count > 1 else "IDLE"
    pygame.draw.rect(screen, badge_color, (35, 360, 110, 34), border_radius=10)
    draw_text(screen, badge_text, 62, 367, fonts["small"], (15, 15, 15))

    draw_text(screen, "Message", 35, 410, fonts["subtitle"], WHITE)
    wrapped = wrap_text(message, 30)
    yy = 445
    for line in wrapped[:4]:
        draw_text(screen, line, 35, yy, fonts["small"], LIGHT)
        yy += 22

    draw_text(screen, "Selected CSV", 35, 475, fonts["subtitle"], WHITE)
    selected_display = selected_csv_path if selected_csv_path else "None"
    selected_lines = wrap_text(selected_display, 28)
    yy = 505
    for line in selected_lines[:2]:
        draw_text(screen, line, 35, yy, fonts["small"], DARK if not selected_csv_path else LIGHT)
        yy += 20

    draw_button(screen, layout["SAVE_BUTTON"], "Save CSV", fonts["font"], enabled=valid, icon="save")
    draw_button(screen, layout["LOAD_BUTTON"], "Load CSV", fonts["font"], enabled=True, icon="load")
    draw_button(screen, layout["RUN_BUTTON"], "Run FSDS", fonts["font"], enabled=can_run_fsds, icon="run")
    draw_button(screen, layout["RAMSE_BUTTON"], "Try RAMS-e", fonts["font"], enabled=True, icon="rocket")
    draw_button(screen, layout["CLEAR_BUTTON"], "Clear Track", fonts["font"], enabled=True, icon="clear")


def draw_start_end_guides(screen, start_point, end_point, anchor_radius, fonts):
    pygame.draw.line(screen, WHITE, end_point, start_point, 4)

    pygame.draw.circle(screen, BLUE, end_point, anchor_radius, 3)
    pygame.draw.circle(screen, WHITE, end_point, 6)
    draw_text(screen, "END", end_point[0] - 18, end_point[1] - 42, fonts["small"], BLUE)

    pygame.draw.circle(screen, GREEN, start_point, anchor_radius, 3)
    pygame.draw.circle(screen, WHITE, start_point, 6)
    draw_text(screen, "START", start_point[0] - 26, start_point[1] - 42, fonts["small"], GREEN)


def draw_track(screen, track_points, is_valid, currently_drawing, start_point, end_point, anchor_radius, fonts):
    if len(track_points) >= 2:
        pygame.draw.lines(screen, (20, 20, 20), False, track_points, 12)
        base_color = GREEN if is_valid else RED
        pygame.draw.lines(screen, base_color, False, track_points, 4)

        pygame.draw.circle(screen, WHITE, track_points[0], 6)
        pygame.draw.circle(screen, ACCENT, track_points[0], 12, 2)
        pygame.draw.circle(screen, LIGHT, track_points[-1], 4)

    draw_start_end_guides(screen, start_point, end_point, anchor_radius, fonts)

    if currently_drawing:
        pygame.draw.circle(screen, GREEN, start_point, anchor_radius, 2)
        pygame.draw.circle(screen, BLUE, end_point, anchor_radius, 2)


def draw_loading_screen(screen, fonts, width, height, duration_ms, clock):
    start_time = pygame.time.get_ticks()

    while pygame.time.get_ticks() - start_time < duration_ms:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

        screen.fill((10, 10, 10))

        for i in range(0, width, 80):
            pygame.draw.line(screen, (25, 25, 25), (i, 0), (i - 200, height), 2)

        draw_center_text(screen, "TRACK DESIGNER", height // 2 - 80, fonts["big"], width, WHITE)
        draw_center_text(screen, "Race Edition", height // 2 - 20, fonts["title"], width, ACCENT)

        elapsed = pygame.time.get_ticks() - start_time
        progress = min(elapsed / duration_ms, 1.0)

        bar_w = 420
        bar_h = 24
        bar_x = width // 2 - bar_w // 2
        bar_y = height // 2 + 60

        pygame.draw.rect(screen, (45, 45, 45), (bar_x, bar_y, bar_w, bar_h), border_radius=12)
        pygame.draw.rect(screen, ACCENT, (bar_x, bar_y, int(bar_w * progress), bar_h), border_radius=12)
        pygame.draw.rect(screen, LIGHT, (bar_x, bar_y, bar_w, bar_h), 2, border_radius=12)

        draw_center_text(screen, "Initializing racing surface...", height // 2 + 130, fonts["subtitle"], width, LIGHT)
        draw_checkered_flag(screen, width // 2 - 22, height // 2 - 170, cell=11, rows=4, cols=4)

        pygame.display.flip()
        clock.tick(60)


def draw_invalid_popup(screen, fonts, width, height):
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    overlay.fill(OVERLAY)
    screen.blit(overlay, (0, 0))

    popup_w, popup_h = 420, 210
    popup_x = width // 2 - popup_w // 2
    popup_y = height // 2 - popup_h // 2
    popup_rect = pygame.Rect(popup_x, popup_y, popup_w, popup_h)

    pygame.draw.rect(screen, PANEL_2, popup_rect, border_radius=18)
    pygame.draw.rect(screen, ACCENT, popup_rect, 3, border_radius=18)

    draw_text(screen, "Invalid Path", popup_x + 30, popup_y + 28, fonts["subtitle"], WHITE)
    draw_text(screen, "Draw without self-intersection.", popup_x + 30, popup_y + 72, fonts["font"], LIGHT)
    draw_text(screen, "Clear the track and try again.", popup_x + 30, popup_y + 104, fonts["font"], LIGHT)

    clear_rect = pygame.Rect(popup_x + 110, popup_y + 150, 200, 40)
    draw_button(screen, clear_rect, "Clear Track", fonts["font"], enabled=True, icon="clear")
    return clear_rect