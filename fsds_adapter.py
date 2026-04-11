import os
import sys
import time
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class TelemetryFrame:
    sim_time_s: float
    car_position_xy_m: Tuple[float, float]
    cone_hits: int
    lap_timer_running: bool


class FSDSClientAdapter:
    """
    Python-only FSDS adapter.
    No ROS.

    Human mode:
    - telemetry only
    - keyboard/manual control remains usable

    RAMS-e mode:
    - API control enabled
    """

    def __init__(
        self,
        fsds_python_path: str,
        simulator_exe_path: str,
        settings_json_path: Optional[str] = None,
        custom_map_cli_template: Optional[str] = None,
        startup_timeout_s: float = 25.0,
    ):
        self.fsds_python_path = fsds_python_path
        self.simulator_exe_path = simulator_exe_path
        self.settings_json_path = settings_json_path
        self.custom_map_cli_template = custom_map_cli_template
        self.startup_timeout_s = startup_timeout_s

        self.client = None
        self.process = None
        self.connected = False
        self.api_control_enabled = False

        self._cone_hits = 0
        self._last_collision_stamp = None
        self._last_collision_name = None

        self._ensure_fsds_import()

    def _ensure_fsds_import(self):
        if self.fsds_python_path and self.fsds_python_path not in sys.path:
            sys.path.insert(0, self.fsds_python_path)
        import fsds
        self.fsds = fsds

    def _build_launch_cmd(self, csv_path: str):
        cmd = [self.simulator_exe_path]

        if self.settings_json_path:
            cmd += ["-settings", self.settings_json_path]

        if self.custom_map_cli_template:
            extra = self.custom_map_cli_template.format(csv_path=csv_path)
            cmd += extra.split()

        print("FSDS launch command:", cmd)
        return cmd

    def start_run(self, csv_path: str, enable_api_control: bool = False):
        if self.process is None or self.process.poll() is not None:
            cmd = self._build_launch_cmd(csv_path)
            self.process = subprocess.Popen(cmd)

        self._connect_client(enable_api_control=enable_api_control)
        self._cone_hits = 0
        self._last_collision_stamp = None
        self._last_collision_name = None

    def _connect_client(self, enable_api_control: bool):
        start = time.time()
        while time.time() - start < self.startup_timeout_s:
            try:
                client = self.fsds.FSDSClient()
                client.confirmConnection()

                # Human mode should not steal keyboard/manual control
                if enable_api_control:
                    client.enableApiControl(True)
                    self.api_control_enabled = True
                else:
                    try:
                        client.enableApiControl(False)
                    except Exception:
                        pass
                    self.api_control_enabled = False

                self.client = client
                self.connected = True
                return
            except Exception:
                time.sleep(0.5)

        raise RuntimeError("Could not connect to FSDS Python API within timeout.")

    def _update_cone_hits(self):
        if self.client is None:
            return

        try:
            collision = self.client.simGetCollisionInfo()
        except Exception:
            return

        if not getattr(collision, "has_collided", False):
            return

        obj_name = str(getattr(collision, "object_name", "") or "").lower()
        stamp = getattr(collision, "time_stamp", None)

        looks_like_cone = (
            ("cone" in obj_name)
            or ("yellow" in obj_name)
            or ("blue" in obj_name)
            or ("orange" in obj_name)
        )

        if not looks_like_cone:
            return

        if stamp != self._last_collision_stamp or obj_name != self._last_collision_name:
            self._cone_hits += 1
            self._last_collision_stamp = stamp
            self._last_collision_name = obj_name

    def poll(self) -> Optional[TelemetryFrame]:
        if self.client is None:
            return None

        try:
            state = self.client.getCarState()
            pos = state.kinematics_estimated.position
            sim_time_s = float(state.timestamp) / 1e9
        except Exception:
            return None

        self._update_cone_hits()

        return TelemetryFrame(
            sim_time_s=sim_time_s,
            car_position_xy_m=(float(pos.x_val), float(pos.y_val)),
            cone_hits=self._cone_hits,
            lap_timer_running=True,
        )

    def is_connected(self):
        return self.connected

    def stop(self):
        if self.client is not None:
            try:
                self.client.enableApiControl(False)
            except Exception:
                pass

        self.api_control_enabled = False
        self.connected = False