import csv
import math


def compute_center(points):
    if not points:
        return 0.0, 0.0
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    return sx / len(points), sy / len(points)


def shift_points(points, dx, dy):
    return [(x - dx, y - dy) for x, y in points]


def rotate_points(points, angle_rad):
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    rotated = []
    for x, y in points:
        xr = x * cos_a - y * sin_a
        yr = x * sin_a + y * cos_a
        rotated.append((xr, yr))
    return rotated


def get_start_direction_from_orange(orange):
    """
    Infer the start-line travel direction from the 4 orange cones.

    Assumes:
    - 4 big orange cones
    - two are 'back' gate cones
    - two are 'front' gate cones
    - travel direction is from back pair center -> front pair center

    Strategy:
    Sort orange cones by projection along their principal axis.
    The two lower projected cones form one gate pair, the two higher
    projected cones form the other gate pair.
    """
    if len(orange) < 4:
        return 0.0, 1.0

    # Compute centroid
    cx, cy = compute_center(orange)

    # Centered coordinates
    centered = [(x - cx, y - cy) for x, y in orange]

    # PCA-ish major axis from covariance
    sxx = sum(x * x for x, y in centered)
    syy = sum(y * y for x, y in centered)
    sxy = sum(x * y for x, y in centered)

    # Principal axis angle
    if abs(sxy) < 1e-12 and abs(sxx - syy) < 1e-12:
        axis_angle = 0.0
    else:
        axis_angle = 0.5 * math.atan2(2.0 * sxy, sxx - syy)

    ux = math.cos(axis_angle)
    uy = math.sin(axis_angle)

    # Project points onto axis
    projected = []
    for pt in orange:
        px = pt[0] - cx
        py = pt[1] - cy
        proj = px * ux + py * uy
        projected.append((proj, pt))

    projected.sort(key=lambda t: t[0])

    back_pair = [projected[0][1], projected[1][1]]
    front_pair = [projected[2][1], projected[3][1]]

    back_center = compute_center(back_pair)
    front_center = compute_center(front_pair)

    dx = front_center[0] - back_center[0]
    dy = front_center[1] - back_center[1]

    norm = math.hypot(dx, dy)
    if norm < 1e-12:
        return 0.0, 1.0

    return dx / norm, dy / norm


def angle_to_positive_y(direction):
    """
    Returns angle needed to rotate 'direction' onto +Y axis.
    """
    dx, dy = direction

    # Current direction angle from +X
    current_angle = math.atan2(dx, dy)

    # Target is +Y => angle pi/2 from +X
    target_angle = math.pi / 2.0

    return target_angle - current_angle


def export_csv(filename, blue, yellow, orange):
    # Step 1: translate so start gate center goes to origin
    if orange:
        origin_x, origin_y = compute_center(orange)
    else:
        all_points = blue + yellow + orange
        origin_x, origin_y = compute_center(all_points)

    blue_shifted = shift_points(blue, origin_x, origin_y)
    yellow_shifted = shift_points(yellow, origin_x, origin_y)
    orange_shifted = shift_points(orange, origin_x, origin_y)

    # Step 2: rotate so initial line of cones points toward +Y
    if orange_shifted and len(orange_shifted) >= 4:
        start_dir = get_start_direction_from_orange(orange_shifted)
        rotation_angle = angle_to_positive_y(start_dir)

        blue_final = rotate_points(blue_shifted, rotation_angle)
        yellow_final = rotate_points(yellow_shifted, rotation_angle)
        orange_final = rotate_points(orange_shifted, rotation_angle)
    else:
        blue_final = blue_shifted
        yellow_final = yellow_shifted
        orange_final = orange_shifted

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)

        # FSDS custom map format:
        # tag,x,y,direction,x_variance,y_variance,xy_covariance
        for x, y in blue_final:
            writer.writerow(["blue", x, y, 0.0, 0.0, 0.0, 0.0])

        for x, y in yellow_final:
            writer.writerow(["yellow", x, y, 0.0, 0.0, 0.0, 0.0])

        for x, y in orange_final:
            writer.writerow(["big_orange", x, y, 0.0, 0.0, 0.0, 0.0])

    print(f"Saved FSDS map CSV to {filename} with start gate centered at origin and aligned to +Y")