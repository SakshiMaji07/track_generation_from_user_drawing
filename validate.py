from shapely.geometry import LineString


def is_closed(points, threshold=20):
    if len(points) < 3:
        return False
    dx = points[0][0] - points[-1][0]
    dy = points[0][1] - points[-1][1]
    return (dx * dx + dy * dy) ** 0.5 < threshold


def validate_track(points):
    if len(points) < 3:
        return False, "Too few points"

    line = LineString(points)

    if not line.is_ring:
        return False, "Not a closed loop"

    if not line.is_simple:
        return False, "Self-intersecting"

    return True, "Valid track"