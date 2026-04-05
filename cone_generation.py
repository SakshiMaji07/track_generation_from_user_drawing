import numpy as np

OFFSET = 1.5  # meters


def distance(p1, p2):
    return np.linalg.norm(np.array(p1) - np.array(p2))


def get_normal(p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    length = np.sqrt(dx * dx + dy * dy)
    if length == 0:
        return (0, 0)

    nx = -dy / length
    ny = dx / length

    return (nx, ny)


def generate_cones(track):
    blue_cones = []
    yellow_cones = []

    for i in range(len(track) - 1):
        p = track[i]
        n = get_normal(track[i], track[i + 1])

        left = (p[0] + OFFSET * n[0], p[1] + OFFSET * n[1])
        right = (p[0] - OFFSET * n[0], p[1] - OFFSET * n[1])

        blue_cones.append(left)
        yellow_cones.append(right)

    return blue_cones, yellow_cones


def generate_start_cones(track):
    p = track[0]
    n = get_normal(track[0], track[1])

    return [
        (p[0] + 2 * n[0], p[1] + 2 * n[1]),
        (p[0] - 2 * n[0], p[1] - 2 * n[1]),
    ]