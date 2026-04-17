import csv
import hashlib
import json
from typing import List, Tuple, Optional

Point2D = Tuple[float, float]

X_FORWARD_OFFSET = 2.0


def compute_center(points: List[Point2D]):
    if not points:
        return 0.0, 0.0
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    return sx / len(points), sy / len(points)


def shift_points(points, dx, dy, extra_x=0.0, extra_y=0.0):
    return [(x - dx + extra_x, y - dy + extra_y) for x, y in points]


def map_fingerprint(track_points, blue, yellow, orange):
    payload = {
        "track_points": track_points,
        "blue": blue,
        "yellow": yellow,
        "orange": orange,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def export_csv(filename, blue, yellow, orange, origin: Optional[Point2D] = None):
    if origin is not None:
        origin_x, origin_y = origin
    elif orange:
        origin_x, origin_y = compute_center(orange)
    else:
        all_points = blue + yellow + orange
        origin_x, origin_y = compute_center(all_points)

    blue_final = shift_points(blue, origin_x, origin_y, extra_x=X_FORWARD_OFFSET)
    yellow_final = shift_points(yellow, origin_x, origin_y, extra_x=X_FORWARD_OFFSET)
    orange_final = shift_points(orange, origin_x, origin_y, extra_x=X_FORWARD_OFFSET)

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        for x, y in blue_final:
            writer.writerow(["blue", x, y, 0.0, 0.0, 0.0, 0.0])

        for x, y in yellow_final:
            writer.writerow(["yellow", x, y, 0.0, 0.0, 0.0, 0.0])

        for x, y in orange_final:
            writer.writerow(["big_orange", x, y, 0.0, 0.0, 0.0, 0.0])

    print(f"Saved FSDS map CSV to {filename}")
    return {
        "filename": filename,
        "blue_count": len(blue_final),
        "yellow_count": len(yellow_final),
        "orange_count": len(orange_final),
        "origin": (origin_x, origin_y),
        "blue_local": blue_final,
        "yellow_local": yellow_final,
        "orange_local": orange_final,
    }
