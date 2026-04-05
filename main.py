import pygame
import numpy as np
from cone_generation import generate_cones, generate_start_cones
from validate import validate_track, is_closed
from csv_writer import export_csv
from scipy.interpolate import splprep, splev

pygame.init()

WIDTH, HEIGHT = 1000, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Track Designer")

clock = pygame.time.Clock()

points = []
drawing = False
valid = False
message = ""

SCALE = 0.05  # pixel → meter


def smooth_path(points):
    if len(points) < 3:
        return points

    pts = np.array(points)
    mask = np.any(np.diff(pts, axis=0) != 0, axis=1)
    pts = np.concatenate(([pts[0]], pts[1:][mask]))
    x = pts[:, 0]
    y = pts[:, 1]
    tck, _ = splprep([x, y], s=5, per=True)
    u_new = np.linspace(0, 1, 200)
    x_new, y_new = splev(u_new, tck)

    return list(zip(x_new, y_new))


def to_meters(points):
    return [(x * SCALE, y * SCALE) for x, y in points]


def draw_text(text, x, y):
    font = pygame.font.SysFont(None, 24)
    img = font.render(text, True, (255, 255, 255))
    screen.blit(img, (x, y))


running = True
while running:
    screen.fill((0, 0, 0))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN:
            drawing = True
            points = []
            valid = False

        elif event.type == pygame.MOUSEBUTTONUP:
            drawing = False

            if is_closed(points):
                points.append(points[0])
                valid, message = validate_track(points)
            else:
                message = "Loop not closed"
                valid = False

        elif event.type == pygame.MOUSEMOTION and drawing:
            points.append(pygame.mouse.get_pos())

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c:
                points = []
                valid = False

            elif event.key == pygame.K_s and valid:
                smooth = smooth_path(points)
                track = to_meters(smooth)

                blue, yellow = generate_cones(track)
                orange = generate_start_cones(track)

                export_csv("track.csv", blue, yellow, orange)

    # draw track
    if len(points) > 1:
        color = (0, 255, 0) if valid else (255, 0, 0)
        pygame.draw.lines(screen, color, False, points, 3)

    # preview cones
    if valid:
        smooth = smooth_path(points)
        track = to_meters(smooth)

        blue, yellow = generate_cones(track)
        orange = generate_start_cones(track)

        # convert back to pixels for display
        def to_pixels(pt):
            return (int(pt[0] / SCALE), int(pt[1] / SCALE))

        for p in blue:
            pygame.draw.circle(screen, (0, 0, 255), to_pixels(p), 4)

        for p in yellow:
            pygame.draw.circle(screen, (255, 255, 0), to_pixels(p), 4)

        for p in orange:
            pygame.draw.circle(screen, (255, 165, 0), to_pixels(p), 6)

    draw_text("Draw with mouse", 10, 10)
    draw_text("Press S to save CSV", 10, 30)
    draw_text("Press C to clear", 10, 50)
    draw_text(message, 10, 70)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()