import csv


def export_csv(filename, blue, yellow, orange):
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["x", "y", "type"])

        for x, y in blue:
            writer.writerow([x, y, "blue"])

        for x, y in yellow:
            writer.writerow([x, y, "yellow"])

        for x, y in orange:
            writer.writerow([x, y, "orange"])

    print(f"Saved to {filename}")