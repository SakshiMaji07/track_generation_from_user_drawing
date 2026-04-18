import math
from typing import List, Tuple

import numpy as np

Point2D = Tuple[float, float]

PIXEL_RADIUS = 15
METERS_PER_PIXEL = 0.1
MIN_CONE_SPACING = PIXEL_RADIUS * METERS_PER_PIXEL

TRACK_WIDTH = 5.0
HALF_TRACK_WIDTH = TRACK_WIDTH / 2.0
CONE_STEP = 2.0

START_GATE_BACK_OFFSET = 1.5
START_GATE_FORWARD_OFFSET = 1.5
START_CLEAR_RADIUS = 3.0


def distance(a: Point2D, b: Point2D) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def as_tuple(pt) -> Point2D:
    return float(pt[0]), float(pt[1])


def remove_duplicate_points(points, eps=1e-9):
    if not points:
        return []
    cleaned = [as_tuple(points[0])]
    for pt in points[1:]:
        pt = as_tuple(pt)
        if distance(pt, cleaned[-1]) > eps:
            cleaned.append(pt)
    return cleaned


def ensure_closed(points, eps=1e-9):
    pts = remove_duplicate_points(points, eps=eps)
    if len(pts) < 3:
        return pts
    if distance(pts[0], pts[-1]) > eps:
        pts.append(pts[0])
    return pts


def cumulative_lengths(points):
    lengths = [0.0]
    for i in range(1, len(points)):
        seg_len = distance(points[i - 1], points[i])
        lengths.append(lengths[-1] + seg_len)
    return lengths


def interpolate_on_polyline(points, s):
    pts = ensure_closed(points)
    if len(pts) < 2:
        raise ValueError("Need at least 2 points")

    cum = cumulative_lengths(pts)
    total = cum[-1]
    if total <= 0:
        raise ValueError("Track length is zero")

    s = s % total

    for i in range(1, len(cum)):
        if s <= cum[i]:
            p0 = np.array(pts[i - 1], dtype=float)
            p1 = np.array(pts[i], dtype=float)

            seg_len = cum[i] - cum[i - 1]
            if seg_len <= 1e-9:
                tangent = np.array([1.0, 0.0], dtype=float)
                return as_tuple(p0), tangent

            t = (s - cum[i - 1]) / seg_len
            pos = p0 + t * (p1 - p0)

            tangent = p1 - p0
            tangent_norm = np.linalg.norm(tangent)
            if tangent_norm <= 1e-9:
                tangent = np.array([1.0, 0.0], dtype=float)
            else:
                tangent = tangent / tangent_norm

            return as_tuple(pos), tangent

    p0 = np.array(pts[-2], dtype=float)
    p1 = np.array(pts[-1], dtype=float)
    tangent = p1 - p0
    tangent_norm = np.linalg.norm(tangent)
    tangent = np.array([1.0, 0.0], dtype=float) if tangent_norm <= 1e-9 else tangent / tangent_norm
    return as_tuple(p1), tangent


def offset_point(center, tangent, offset):
    tx, ty = tangent
    normal = np.array([-ty, tx], dtype=float)

    normal_norm = np.linalg.norm(normal)
    normal = np.array([0.0, 1.0], dtype=float) if normal_norm <= 1e-9 else normal / normal_norm

    c = np.array(center, dtype=float)
    p = c + offset * normal
    return as_tuple(p)


def filter_spacing(points, min_dist):
    kept = []
    for p in points:
        if all(distance(p, q) >= min_dist for q in kept):
            kept.append(p)
    return kept


def sample_centerline(points, step):
    pts = ensure_closed(points)
    if len(pts) < 4:
        return []

    total = cumulative_lengths(pts)[-1]
    if total <= 0:
        return []

    count = max(8, int(total / step))
    s_values = np.linspace(0.0, total, count, endpoint=False)

    samples = []
    tangents = []

    for s in s_values:
        pos, tangent = interpolate_on_polyline(pts, s)
        samples.append(pos)
        tangents.append(tangent)

    return samples, tangents, total


def get_start_reference(track_points_m):
    pts = ensure_closed(track_points_m)
    if len(pts) < 4:
        return None, None

    sampled = sample_centerline(pts, CONE_STEP)
    if not sampled:
        return None, None

    centers, tangents, _ = sampled
    start_center = np.array(centers[0], dtype=float)
    start_tangent = np.array(tangents[0], dtype=float)

    tangent_norm = np.linalg.norm(start_tangent)
    start_tangent = np.array([1.0, 0.0], dtype=float) if tangent_norm <= 1e-9 else start_tangent / tangent_norm
    return start_center, start_tangent


def clear_points_near_reference(points, references, clear_radius):
    kept = []
    for p in points:
        if all(distance(p, ref) >= clear_radius for ref in references):
            kept.append(p)
    return kept


def generate_start_cones(track_points_m):
    start_center, start_tangent = get_start_reference(track_points_m)
    if start_center is None:
        return []

    back_center = start_center - START_GATE_BACK_OFFSET * start_tangent
    front_center = start_center + START_GATE_FORWARD_OFFSET * start_tangent

    orange_raw = [
        offset_point(back_center, start_tangent, +HALF_TRACK_WIDTH),
        offset_point(back_center, start_tangent, -HALF_TRACK_WIDTH),
        offset_point(front_center, start_tangent, +HALF_TRACK_WIDTH),
        offset_point(front_center, start_tangent, -HALF_TRACK_WIDTH),
    ]
    return filter_spacing(orange_raw, MIN_CONE_SPACING)


def generate_cones(track_points_m):
    pts = ensure_closed(track_points_m)
    if len(pts) < 4:
        return [], []

    sampled = sample_centerline(pts, CONE_STEP)
    if not sampled:
        return [], []

    centers, tangents, _ = sampled
    left_side = []
    right_side = []

    for c, t in zip(centers, tangents):
        left_side.append(offset_point(c, t, +HALF_TRACK_WIDTH))
        right_side.append(offset_point(c, t, -HALF_TRACK_WIDTH))

    blue = filter_spacing(left_side, MIN_CONE_SPACING)
    yellow = filter_spacing(right_side, MIN_CONE_SPACING)

    blue_final = []
    yellow_final = []

    for b in blue:
        if all(distance(b, y) >= MIN_CONE_SPACING for y in yellow_final):
            blue_final.append(b)

    for y in yellow:
        if all(distance(y, b) >= MIN_CONE_SPACING for b in blue_final):
            yellow_final.append(y)

    return blue_final, yellow_final


def generate_all_cones(track_points_m):
    blue, yellow = generate_cones(track_points_m)
    orange = generate_start_cones(track_points_m)

    start_center, _ = get_start_reference(track_points_m)

    if start_center is not None:
        blue = clear_points_near_reference(blue, [start_center], START_CLEAR_RADIUS)
        yellow = clear_points_near_reference(yellow, [start_center], START_CLEAR_RADIUS)

    if orange:
        blue = clear_points_near_reference(blue, orange, MIN_CONE_SPACING)
        yellow = clear_points_near_reference(yellow, orange, MIN_CONE_SPACING)

    return blue, yellow, orange