import math
from typing import List, Tuple

Point2D = Tuple[float, float]
OFFSET = 1.5


def distance(p1: Point2D, p2: Point2D) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def get_normal(p1: Point2D, p2: Point2D) -> Point2D:
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return (0.0, 0.0)
    return (-dy / length, dx / length)


def generate_cones(track: List[Point2D]):
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


def generate_start_cones(track: List[Point2D]):
    if len(track) < 2:
        return []
    p = track[0]
    n = get_normal(track[0], track[1])

    return [
        (p[0] + 2.0 * n[0], p[1] + 2.0 * n[1]),
        (p[0] - 2.0 * n[0], p[1] - 2.0 * n[1]),
    ]