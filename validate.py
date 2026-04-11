import math
from dataclasses import dataclass
from typing import List, Tuple, Optional

from shapely.geometry import LineString, Polygon

Point2D = Tuple[float, float]


def dist(a: Point2D, b: Point2D) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_in_circle(p: Point2D, c: Point2D, r: float) -> bool:
    return dist(p, c) <= r


def validate_track(points: List[Point2D]):
    if len(points) < 4:
        return False, "Too few points"

    if dist(points[0], points[-1]) > 30:
        return False, "Track is not closed enough"

    line = LineString(points)
    if not line.is_simple:
        return False, "Track self-intersects"

    try:
        poly = Polygon(points)
        if not poly.is_valid:
            return False, "Invalid polygon geometry"
        if poly.area < 1200:
            return False, "Track area too small"
    except Exception:
        return False, "Failed to build valid track"

    return True, "Valid track"


def cumulative_lengths(points: List[Point2D]) -> List[float]:
    out = [0.0]
    for i in range(1, len(points)):
        out.append(out[-1] + dist(points[i - 1], points[i]))
    return out


def interpolate_polyline(points: List[Point2D], s: float):
    cum = cumulative_lengths(points)
    total = cum[-1]
    if total <= 1e-9:
        raise ValueError("Zero-length polyline")

    s = max(0.0, min(s, total))
    for i in range(1, len(cum)):
        if s <= cum[i]:
            p0 = points[i - 1]
            p1 = points[i]
            seg = cum[i] - cum[i - 1]
            if seg <= 1e-9:
                return p0, (1.0, 0.0)
            t = (s - cum[i - 1]) / seg
            x = p0[0] + t * (p1[0] - p0[0])
            y = p0[1] + t * (p1[1] - p0[1])
            tx = p1[0] - p0[0]
            ty = p1[1] - p0[1]
            n = math.hypot(tx, ty)
            return (x, y), ((tx / n), (ty / n)) if n > 1e-9 else (1.0, 0.0)
    p0, p1 = points[-2], points[-1]
    tx, ty = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(tx, ty)
    return p1, ((tx / n), (ty / n)) if n > 1e-9 else (1.0, 0.0)


def generate_checkpoints(points: List[Point2D], checkpoint_count=10):
    total = cumulative_lengths(points)[-1]
    if total <= 0:
        return []

    checkpoints = []
    for i in range(checkpoint_count):
        s = (i / checkpoint_count) * total
        pos, tangent = interpolate_polyline(points, s)
        checkpoints.append({
            "index": i,
            "position": pos,
            "tangent": tangent,
            "radius": 7.5,
        })
    return checkpoints


@dataclass
class LapState:
    started: bool = False
    finished: bool = False
    next_checkpoint_index: int = 1
    checkpoints_passed: int = 0
    distance_travelled: float = 0.0
    last_position: Optional[Point2D] = None
    cone_hits: int = 0
    start_time_s: Optional[float] = None
    finish_time_s: Optional[float] = None


class LapValidator:
    def __init__(self, track_points: List[Point2D], checkpoint_count=10):
        ok, msg = validate_track(track_points)
        if not ok:
            raise ValueError(msg)

        self.track_points = track_points[:] if track_points[0] == track_points[-1] else track_points + [track_points[0]]
        self.checkpoints = generate_checkpoints(self.track_points, checkpoint_count)
        self.state = LapState()
        self.track_length = cumulative_lengths(self.track_points)[-1]

    @staticmethod
    def _dot(a, b):
        return a[0] * b[0] + a[1] * b[1]

    @staticmethod
    def _sub(a, b):
        return (a[0] - b[0], a[1] - b[1])

    def _crossed_forward(self, car_pos: Point2D, checkpoint: dict) -> bool:
        cp = checkpoint["position"]
        tangent = checkpoint["tangent"]
        radius = checkpoint["radius"]

        if dist(car_pos, cp) > radius:
            return False

        if self.state.last_position is None:
            return False

        rel_prev = self._sub(self.state.last_position, cp)
        rel_curr = self._sub(car_pos, cp)

        normal = (-tangent[1], tangent[0])
        prev_side = self._dot(rel_prev, normal)
        curr_side = self._dot(rel_curr, normal)

        motion = self._dot(self._sub(car_pos, self.state.last_position), tangent)
        return (prev_side * curr_side <= 0.0) and (motion > -0.05)

    def update(self, car_pos: Point2D, sim_time_s: float, cone_hits: int = 0):
        events = {
            "lap_started": False,
            "checkpoint_passed": None,
            "lap_finished": False,
            "lap_invalid": False,
            "reason": None,
        }

        if self.state.last_position is not None:
            self.state.distance_travelled += dist(self.state.last_position, car_pos)
        self.state.last_position = car_pos
        self.state.cone_hits = max(self.state.cone_hits, cone_hits)

        if not self.state.started:
            if self._crossed_forward(car_pos, self.checkpoints[0]):
                self.state.started = True
                self.state.start_time_s = sim_time_s
                events["lap_started"] = True
            return events

        if self.state.next_checkpoint_index < len(self.checkpoints):
            target = self.checkpoints[self.state.next_checkpoint_index]
            if self._crossed_forward(car_pos, target):
                self.state.checkpoints_passed += 1
                events["checkpoint_passed"] = self.state.next_checkpoint_index
                self.state.next_checkpoint_index += 1

        if self.state.next_checkpoint_index >= len(self.checkpoints):
            if self._crossed_forward(car_pos, self.checkpoints[0]):
                progress_ratio = self.state.checkpoints_passed / max(1, len(self.checkpoints) - 1)
                min_required_distance = 0.70 * self.track_length

                if progress_ratio < 0.95:
                    events["lap_invalid"] = True
                    events["reason"] = "Track not followed sufficiently"
                    return events

                if self.state.distance_travelled < min_required_distance:
                    events["lap_invalid"] = True
                    events["reason"] = "Distance too short; reverse exploit blocked"
                    return events

                self.state.finished = True
                self.state.finish_time_s = sim_time_s
                events["lap_finished"] = True

        return events

    def get_lap_time(self):
        if self.state.start_time_s is None or self.state.finish_time_s is None:
            return None
        return self.state.finish_time_s - self.state.start_time_s

    def get_summary(self):
        return {
            "started": self.state.started,
            "finished": self.state.finished,
            "checkpoints_passed": self.state.checkpoints_passed,
            "total_checkpoints": len(self.checkpoints) - 1,
            "distance_travelled": self.state.distance_travelled,
            "cone_hits": self.state.cone_hits,
            "lap_time_s": self.get_lap_time(),
        }