from __future__ import annotations

import asyncio
import ctypes
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import WebSocket

from backend.export.blender_bridge import BlenderFBXBridge
from backend.export.bvh_exporter import RigNamingPreset, export_take_to_bvh
from backend.hal.base import HALManager, SensorPacket
from backend.hal.ble_driver import BLEIMUDriver
from backend.hal.sensor_mapper import DynamicSensorMapper
from backend.hal.serial_udp_driver import SerialIMUDriver, UDPOSCDriver
from backend.hal.synthetic_simulator import MotionPreset, Synthetic17SensorSimulator
from backend.hal.watchdog import ConnectionWatchdog
from backend.hal.xsens_awinda_driver import XsensAwindaDriver
from backend.kinematics.anthropometry import AnthropometricProfile, ProfileManager, SkeletonModel
from backend.kinematics.biomechanics import JointAngleCalculator
from backend.kinematics.calibration import CalibrationEngine, CalibrationMode, PoseType
from backend.kinematics.fk_solver import HierarchicalFKSolver, RootMotionMode
from backend.kinematics.quaternions import q_identity, q_normalize
from backend.kinematics.sensor_fusion import SensorFusionBank
from backend.paths import ensure_runtime_dirs
from backend.recording.recorder import TakeRecorder


class MocapEngine:
    """
    Motor central en tiempo real de OpenMocap Studio (120 Hz interno, 60-120 Hz WebSocket).
    Coordina HAL -> Watchdog -> Fusión -> Mapeo -> Calibración -> Solver FK -> Biomecánica -> Grabación.
    """

    def __init__(self) -> None:
        self.dirs = ensure_runtime_dirs()

        # Antropometría y esqueleto
        self.profile_manager = ProfileManager(self.dirs["profiles"])
        self.skeleton = SkeletonModel(self.profile_manager.get_active_profile())

        # Cinemática y calibración
        self.fusion_bank = SensorFusionBank(algorithm="madgwick", beta=0.08)
        self.calibration = CalibrationEngine(self.skeleton)
        self.fk_solver = HierarchicalFKSolver(self.skeleton)
        self.biomechanics = JointAngleCalculator()

        # Capa HAL y drivers
        self.hal = HALManager()
        self.mapper = DynamicSensorMapper(settings_dir=self.dirs["settings"])
        self.watchdog = ConnectionWatchdog(smoothing_alpha=1.0)

        self.simulator = Synthetic17SensorSimulator(self.hal.dispatch_packets)
        self.xsens = XsensAwindaDriver(self.hal.dispatch_packets, settings_dir=self.dirs["settings"])
        self.serial = SerialIMUDriver(self.hal.dispatch_packets)
        self.udp = UDPOSCDriver(self.hal.dispatch_packets)
        self.ble = BLEIMUDriver(self.hal.dispatch_packets)

        self.hal.register_driver("simulator", self.simulator)
        self.hal.register_driver("xsens_awinda", self.xsens)
        self.hal.register_driver("serial_imu", self.serial)
        self.hal.register_driver("udp_osc", self.udp)
        self.hal.register_driver("ble_imu", self.ble)
        self.hal.register_listener(self._on_hal_packets)

        # Grabación y exportación
        self.recorder = TakeRecorder(self.dirs["takes"])
        self.blender = BlenderFBXBridge(settings_dir=self.dirs["settings"])

        # Estado en vivo
        self._latest_raw_quats: dict[str, np.ndarray] = {}
        self._latest_accels: dict[str, list[float]] = {}
        self._last_frame_payload: dict[str, Any] = {}
        self._seq: int = 0
        self._broadcast_hz: int = 120
        self._internal_hz: int = 120
        self._ws_clients: set[WebSocket] = set()
        self._engine_task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._actual_stream_hz: float = 0.0
        self._last_broadcast_ts: float = time.perf_counter()
        self._last_shake_sent_ts: float = 0.0

    async def start(self) -> None:
        if self._running:
            return
        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeBeginPeriod(1)
            except Exception:
                pass
        self._running = True
        # Arrancar monitoreo Plug & Play de antena Xsens Awinda cada 2 segundos
        await self.xsens.start_auto_monitor(on_connected=self._on_real_antenna_connected)
        self._engine_task = asyncio.create_task(self._main_loop(), name="MocapEngineLoop")

    def _on_real_antenna_connected(self) -> None:
        """Si la antena física Awinda se conecta por USB, detener demo virtual para usar sensores reales."""
        if self.simulator.running:
            asyncio.create_task(self.simulator.stop())

    async def stop(self) -> None:
        self._running = False
        await self.xsens.stop_auto_monitor()
        if self._engine_task and not self._engine_task.done():
            self._engine_task.cancel()
            try:
                await self._engine_task
            except asyncio.CancelledError:
                pass
        await self.hal.stop_all()
        if sys.platform == "win32":
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass

    def _on_hal_packets(self, packets: list[SensorPacket]) -> None:
        for pkt in packets:
            if pkt.raw_only:
                q_est = self.fusion_bank.update_sensor(
                    sensor_id=pkt.sensor_id,
                    gyro_rad=pkt.gyro,
                    accel_ms2=pkt.free_accel,
                    mag=pkt.mag,
                    timestamp_ms=pkt.timestamp_ms,
                )
                pkt.quaternion = [float(v) for v in q_est]
                pkt.raw_only = False

            self.mapper.resolve_and_check_shake(pkt)
            clean_pkt = self.watchdog.ingest(pkt)
            if self.calibration.is_capturing() and self.recorder.mode != "playback":
                self.calibration.feed_sample(
                    segment=clean_pkt.segment,
                    q_raw=q_normalize(clean_pkt.quaternion),
                    gyro=np.asarray(clean_pkt.gyro, dtype=np.float64),
                    free_accel=np.asarray(clean_pkt.free_accel, dtype=np.float64),
                    sensor_id=clean_pkt.sensor_id,
                    from_hal=True,
                )

    def step_once(self) -> dict[str, Any]:
        """Ejecuta un paso completo de calibración -> FK -> biomecánica -> grabación/reproducción."""
        self.calibration.tick()
        snapshot = self.watchdog.get_active_snapshot()

        if self.recorder.mode == "playback" and self.recorder.frames:
            pb_frame = self.recorder.step_playback()
            if pb_frame is not None:
                world_pos = pb_frame["world_pos"]
                world_quat = pb_frame["world_quat"]
                local_quat = pb_frame["local_quat"]
                end_pos = pb_frame["end_pos"]
                angles = pb_frame["angles"]
            else:
                world_pos, world_quat, local_quat, end_pos, angles = {}, {}, {}, {}, {}
            accels_by_seg: dict[str, list[float]] = {}
            min_foot_y = 0.0
        else:
            raw_by_seg: dict[str, np.ndarray] = {}
            calibrated_by_seg: dict[str, np.ndarray] = {}
            gyro_by_seg: dict[str, np.ndarray] = {}
            accels_by_seg = {}

            for pkt in snapshot.values():
                seg = pkt.segment
                if not seg or seg == "UNASSIGNED" or seg not in self.skeleton.segments:
                    continue
                q_raw = q_normalize(pkt.quaternion)
                raw_by_seg[seg] = q_raw
                gyro = np.asarray(pkt.gyro, dtype=np.float64)
                gyro_by_seg[seg] = gyro
                fa = np.asarray(pkt.free_accel, dtype=np.float64)
                if (
                    self.calibration.is_capturing()
                    and not self.calibration.has_recent_hal_samples(0.25)
                    and self.watchdog.is_fresh_online(pkt.sensor_id, max_age_ms=120.0)
                ):
                    self.calibration.feed_sample(seg, q_raw, gyro, fa, sensor_id=pkt.sensor_id, from_hal=False)
                calibrated_by_seg[seg] = self.calibration.apply(seg, q_raw)
                accels_by_seg[seg] = [round(float(v), 3) for v in pkt.free_accel]

            self._latest_raw_quats = raw_by_seg
            self._latest_accels = accels_by_seg
            pose = self.fk_solver.solve(
                calibrated_by_seg,
                sensor_gyros=gyro_by_seg,
                dt=1.0 / float(self._internal_hz),
            )
            world_pos = pose.world_pos
            world_quat = pose.world_quat
            local_quat = pose.local_quat
            end_pos = pose.end_pos
            min_foot_y = pose.min_foot_y
            angles = self.biomechanics.compute(world_quat)

            if self.recorder.is_recording:
                self.recorder.record_frame(world_pos, world_quat, local_quat, end_pos, angles)

        segments_payload: dict[str, Any] = {}
        for seg_name in self.skeleton.order:
            if seg_name in world_pos:
                segments_payload[seg_name] = {
                    "pos": world_pos[seg_name],
                    "quat": world_quat[seg_name],
                    "local_quat": local_quat.get(seg_name, [1.0, 0.0, 0.0, 0.0]),
                    "end_pos": end_pos[seg_name],
                    "accel": accels_by_seg.get(seg_name, [0.0, 0.0, 0.0]),
                }

        sensors_diag = self.watchdog.get_diagnostics()
        shake_ev = self.mapper.last_shake_event
        emit_shake = None
        if shake_ev and float(shake_ev["timestamp_ms"]) > self._last_shake_sent_ts:
            self._last_shake_sent_ts = float(shake_ev["timestamp_ms"])
            emit_shake = shake_ev

        self._seq += 1
        payload = {
            "seq": self._seq,
            "timestamp_ms": round(time.monotonic() * 1000.0, 2),
            "rate_hz": round(self._actual_stream_hz or float(self._broadcast_hz), 1),
            "mode": self.recorder.mode,
            "root_mode": self.fk_solver.root_mode,
            "min_foot_y": min_foot_y,
            "skeleton_order": self.skeleton.order,
            "segments": segments_payload,
            "angles": angles,
            "sensors": list(sensors_diag.values()),
            "calibration": self.calibration.get_status(),
            "recording": self.recorder.get_status(),
            "awinda": self.xsens.get_status(),
            "simulator_active": self.simulator.running,
            "shake_detected": emit_shake,
        }
        self._last_frame_payload = payload
        return payload

    async def _main_loop(self) -> None:
        dt = 1.0 / float(self._internal_hz)
        broadcast_interval = 1.0 / float(self._broadcast_hz)
        next_step = time.perf_counter()
        last_bcast = next_step

        while self._running:
            now = time.perf_counter()
            payload = self.step_once()

            if self._ws_clients and (now - last_bcast) >= (broadcast_interval * 0.9):
                delta = now - self._last_broadcast_ts
                if delta > 0.0005:
                    inst_hz = 1.0 / delta
                    self._actual_stream_hz = (
                        inst_hz
                        if self._actual_stream_hz == 0.0
                        else (0.85 * self._actual_stream_hz + 0.15 * inst_hz)
                    )
                self._last_broadcast_ts = now
                last_bcast = now
                payload["rate_hz"] = round(self._actual_stream_hz, 1)
                await self._broadcast(payload)

            next_step += dt
            sleep_s = next_step - time.perf_counter()
            if sleep_s > 0.001:
                await asyncio.sleep(sleep_s)
            else:
                if sleep_s < -0.1:
                    next_step = time.perf_counter()
                await asyncio.sleep(0)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        if not self._ws_clients:
            return
        raw_text = json.dumps(payload, separators=(",", ":"))
        dead: list[WebSocket] = []
        for ws in list(self._ws_clients):
            try:
                await asyncio.wait_for(ws.send_text(raw_text), timeout=0.05)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    def register_ws(self, ws: WebSocket) -> None:
        self._ws_clients.add(ws)

    def unregister_ws(self, ws: WebSocket) -> None:
        self._ws_clients.discard(ws)

    # --- Operaciones de dominio invocadas por REST API y tests ---

    def reload_skeleton(self) -> dict[str, Any]:
        prof = self.profile_manager.get_active_profile()
        self.skeleton = SkeletonModel(prof)
        self.calibration.update_skeleton(self.skeleton)
        self.fk_solver.update_skeleton(self.skeleton)
        self.simulator.custom_segments = [s for s in self.skeleton.order if self.skeleton.segments[s].is_custom]
        return self.skeleton.to_summary()

    def start_calibration_static(
        self,
        pose_type: PoseType = "tpose",
        duration_s: float = 4.0,
        mode: CalibrationMode = "full",
    ) -> dict[str, Any]:
        return self.calibration.start_static(pose_type=pose_type, duration_s=duration_s, mode=mode)

    def start_calibration_straight(self, duration_s: float = 3.0, complete_after: bool = False) -> dict[str, Any]:
        return self.calibration.start_straight(duration_s=duration_s, complete_after=complete_after)

    def complete_calibration_quick(self) -> dict[str, Any]:
        return self.calibration.complete_quick_from_static()

    def start_calibration_walk(self, duration_s: float = 6.0) -> dict[str, Any]:
        return self.calibration.start_walk(duration_s=duration_s)

    def reset_calibration(self) -> dict[str, Any]:
        return self.calibration.reset()

    def heading_reset(self) -> dict[str, Any]:
        return self.calibration.quick_heading_reset(self._latest_raw_quats)

    def set_root_mode(self, mode: RootMotionMode) -> dict[str, Any]:
        self.fk_solver.root_mode = mode
        if mode == "in_place":
            self.fk_solver.reset_root_position()
        return {"root_mode": self.fk_solver.root_mode}

    def export_bvh(
        self,
        file_name: str | None = None,
        scale: float = 1.0,
        naming: RigNamingPreset = "openmocap",
        include_tpose_frame0: bool = True,
        respect_trim: bool = True,
        tpose_lead_in_out: bool = True,
    ) -> dict[str, Any]:
        frames = self.recorder.get_trimmed_frames(respect_trim=respect_trim)
        if not frames:
            raise ValueError("No hay fotogramas grabados o cargados para exportar.")
        raw_base = (file_name or self.recorder.recording_name or f"mocap_{int(time.time())}").strip()
        base = Path(raw_base).name
        if not base or base in (".", ".."):
            base = f"mocap_{int(time.time())}"
        if not base.lower().endswith(".bvh"):
            base += ".bvh"
        out_path = self.dirs["bvh"] / base

        export_skeleton = self.skeleton
        snap = self.recorder.skeleton_snapshot
        if isinstance(snap, dict) and isinstance(snap.get("profile"), dict):
            try:
                export_skeleton = SkeletonModel(AnthropometricProfile.from_dict(snap["profile"]))
            except Exception:
                export_skeleton = self.skeleton

        return export_take_to_bvh(
            output_path=out_path,
            frames=frames,
            skeleton=export_skeleton,
            fps=self.recorder.fps or 120.0,
            scale=scale,
            naming=naming,
            include_tpose_frame0=include_tpose_frame0,
            tpose_lead_in_out=tpose_lead_in_out,
        )

    def export_fbx(
        self,
        file_name: str | None = None,
        scale: float = 1.0,
        naming: RigNamingPreset = "openmocap",
        include_tpose_frame0: bool = True,
        respect_trim: bool = True,
        tpose_lead_in_out: bool = True,
    ) -> dict[str, Any]:
        bvh_info = self.export_bvh(
            file_name=file_name,
            scale=scale,
            naming="openmocap",
            include_tpose_frame0=include_tpose_frame0,
            respect_trim=respect_trim,
            tpose_lead_in_out=tpose_lead_in_out,
        )
        bvh_path = Path(bvh_info["file_path"])
        fbx_name = bvh_path.with_suffix(".fbx").name
        fbx_path = self.dirs["fbx"] / fbx_name
        fbx_res = self.blender.convert_bvh_to_fbx(
            bvh_path=bvh_path,
            fbx_path=fbx_path,
            rig_preset=naming,
            fps=self.recorder.fps or 120.0,
            scale=1.0,
        )
        return {"bvh": bvh_info, "fbx": fbx_res}
