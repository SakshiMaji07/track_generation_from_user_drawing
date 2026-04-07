import csv


X_FORWARD_OFFSET = 4.0  # meters; increase/decrease as needed


def compute_center(points):
    if not points:
        return 0.0, 0.0
    sx = sum(x for x, _ in points)
    sy = sum(y for _, y in points)
    return sx / len(points), sy / len(points)


def shift_points(points, dx, dy, extra_x=0.0, extra_y=0.0):
    return [(x - dx + extra_x, y - dy + extra_y) for x, y in points]


def export_csv(filename, blue, yellow, orange):
    # Translate so orange gate center goes near origin,
    # then push the whole map ahead of the car in +X.
    if orange:
        origin_x, origin_y = compute_center(orange)
    else:
        all_points = blue + yellow + orange
        origin_x, origin_y = compute_center(all_points)

    blue_final = shift_points(blue, origin_x, origin_y, extra_x=X_FORWARD_OFFSET)
    yellow_final = shift_points(yellow, origin_x, origin_y, extra_x=X_FORWARD_OFFSET)
    orange_final = shift_points(orange, origin_x, origin_y, extra_x=X_FORWARD_OFFSET)

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

    print(f"Saved FSDS map CSV to {filename} with start gate centered and shifted +X by {X_FORWARD_OFFSET} m")