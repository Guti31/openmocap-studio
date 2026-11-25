from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any, Literal

import numpy as np

from backend.hal.base import BaseIMUDriver, PacketCallback, SensorPacket
from backend.kinematics.quaternions import (
    q_from_axis_angle,
    q_identity,
    q_inv,
    q_mul,
    q_normalize,
    q_rotate_vec,
    q_to_axis_angle,
)
from backend.paths import get_config_dir

MotionPreset = Literal["walk", "jog", "squat", "tpose", "npose", "wave"]


class Synthetic17SensorSimulator(BaseIMUDriver):
    """
    Simulador biomecánico sintético de 17 sensores a 60/120 Hz con los IDs exactos de Xsens Awinda.
    Permite inyectar desalineación de montaje en correas, deriva magnética interior por sensor,
    ruido realista y pulsos de agitación para pruebas integrales sin hardware físico.
    """

    driver_name = "synthetic_simulator"

    def __init__(self, on_packets: PacketCallback) -> None:
        super().__init__(on_packets)
        self.preset: MotionPreset = "walk"
        self.target_hz = 120
        self.sensor_map: dict[str, str] = self._load_default_ids()
        self.custom_segments: list[str] = []

        self.mount_offsets: dict[str, np.ndarray] = {}
        self.yaw_drifts_rad: dict[str, float] = {}
        self.noise_std_rad: float = 0.0
        self._rng = np.random.default_rng(42)

        self._prev_world_quats: dict[str, np.ndarray] = {}
        self._prev_time_s: float | None = None
        self._shake_until: dict[str, float] = {}

        self._task: asyncio.Task[None] | None = None
        self._start_ts = time.monotonic()
        self._sim_clock_s: float = 0.0
        self.status_message_es = "Simulador de 17 sensores en reposo."

    @staticmethod
    def _load_default_ids() -> dict[str, str]:
        cfg_file = get_config_dir() / "default_awinda_17.json"
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        # Mapeo segment -> sensor_id
        return {str(k): str(v) for k, v in data["mappings"].items()}

    def configure_imperfections(
        self,
        mount_offsets: dict[str, list[float]] | None = None,
        yaw_drifts_deg: dict[str, float] | None = None,
        noise_std_rad: float = 0.0,
        randomize: bool = False,
        seed: int = 2026,
    ) -> dict[str, Any]:
        """Configura offsets de correas y derivas magnéticas para validar la calibración."""
        self.noise_std_rad = max(0.0, float(noise_std_rad))
        if randomize:
            rng = np.random.default_rng(seed)
            self.mount_offsets.clear()
            self.yaw_drifts_rad.clear()
            for seg in self.sensor_map.keys():
                axis = rng.normal(size=3)
                angle_deg = float(rng.uniform(25.0, 130.0))
                self.mount_offsets[seg] = q_from_axis_angle(axis, math.radians(angle_deg))
                drift_deg = float(rng.uniform(-40.0, 40.0))
                self.yaw_drifts_rad[seg] = math.radians(drift_deg)
        else:
            if mount_offsets is not None:
                self.mount_offsets = {k: q_normalize(v) for k, v in mount_offsets.items()}
            if yaw_drifts_deg is not None:
                self.yaw_drifts_rad = {k: math.radians(float(v)) for k, v in yaw_drifts_deg.items()}

        return {
            "randomized": randomize,
            "mount_offset_count": len(self.mount_offsets),
            "yaw_drifts_deg": {k: round(math.degrees(v), 2) for k, v in self.yaw_drifts_rad.items()},
            "noise_std_rad": self.noise_std_rad,
        }

    def clear_imperfections(self) -> None:
        self.mount_offsets.clear()
        self.yaw_drifts_rad.clear()
        self.noise_std_rad = 0.0

    def trigger_shake(self, sensor_id: str, duration_s: float = 0.6) -> None:
        self._shake_until[sensor_id.upper()] = time.monotonic() + duration_s

    def compute_biomechanical_pose(self, t: float, preset: MotionPreset | None = None) -> tuple[dict[str, np.ndarray], np.ndarray]:
        """
        Calcula orientaciones mundiales anatómicas ground-truth (convención Y-up)
        y aceleración lineal mundial del tronco [ax, ay, az] en m/s^2.
        """
        mode = preset or self.preset
        quats: dict[str, np.ndarray] = {}
        ident = q_identity()

        def rx(deg: float) -> np.ndarray:
            return q_from_axis_angle([1.0, 0.0, 0.0], math.radians(deg))

        def ry(deg: float) -> np.ndarray:
            return q_from_axis_angle([0.0, 1.0, 0.0], math.radians(deg))

        def rz(deg: float) -> np.ndarray:
            return q_from_axis_angle([0.0, 0.0, 1.0], math.radians(deg))

        world_accel = np.array([0.0, 0.0, 0.0], dtype=np.float64)

        if mode == "tpose":
            for seg in self.sensor_map:
                quats[seg] = ident.copy()
            # Ritmo escapulohumeral anatómico (~14° elevación escapular con brazos horizontales a 90°)
            quats["SHOULDER_L"] = rz(14.0)
            quats["SHOULDER_R"] = rz(-14.0)
            return quats, world_accel

        if mode == "npose":
            for seg in self.sensor_map:
                quats[seg] = ident.copy()
            for seg in ("UPPER_ARM_L", "FOREARM_L", "HAND_L"):
                quats[seg] = rz(-90.0)
            for seg in ("UPPER_ARM_R", "FOREARM_R", "HAND_R"):
                quats[seg] = rz(90.0)
            return quats, world_accel

        if mode in ("walk", "jog"):
            freq = 1.05 if mode == "walk" else 1.65
            w = 2.0 * math.pi * freq
            phase = w * t
            stride_amp = 32.0 if mode == "walk" else 48.0
            knee_amp = 54.0 if mode == "walk" else 75.0
            arm_amp = 24.0 if mode == "walk" else 42.0

            # Pelvis y torso con ligero balanceo natural; aceleración longitudinal fuerte en +Z
            pelvis_yaw = 4.0 * math.sin(phase)
            pelvis_pitch = 3.0 + 1.5 * math.cos(2.0 * phase)
            quats["PELVIS"] = q_normalize(q_mul(ry(pelvis_yaw), rx(pelvis_pitch)))
            quats["STERNUM"] = q_normalize(q_mul(ry(-2.5 * math.sin(phase)), rx(4.0)))
            quats["HEAD"] = q_normalize(q_mul(ry(1.0 * math.sin(phase)), rx(1.5)))

            # Hombros y brazos en contrafase con piernas (brazos abajo ~72° desde horizontal + balanceo sagital)
            quats["SHOULDER_L"] = rz(-3.0)
            quats["SHOULDER_R"] = rz(3.0)

            arm_l_swing = -arm_amp * math.sin(phase)
            arm_r_swing = arm_amp * math.sin(phase)
            quats["UPPER_ARM_L"] = q_normalize(q_mul(rx(arm_l_swing), rz(-74.0)))
            quats["FOREARM_L"] = q_normalize(q_mul(rx(arm_l_swing - 18.0 - 10.0 * max(0.0, -math.sin(phase))), rz(-70.0)))
            quats["HAND_L"] = quats["FOREARM_L"].copy()

            quats["UPPER_ARM_R"] = q_normalize(q_mul(rx(arm_r_swing), rz(74.0)))
            quats["FOREARM_R"] = q_normalize(q_mul(rx(arm_r_swing - 18.0 - 10.0 * max(0.0, math.sin(phase))), rz(70.0)))
            quats["HAND_R"] = quats["FOREARM_R"].copy()

            # Piernas (rotación sagital pura en +X: negativo = pierna hacia delante en +Z, positivo en rodilla = flexión hacia atrás)
            hip_l = -stride_amp * math.sin(phase)
            hip_r = stride_amp * math.sin(phase)
            knee_l = max(2.0, knee_amp * (0.5 - 0.5 * math.cos(phase - 0.55)))
            knee_r = max(2.0, knee_amp * (0.5 + 0.5 * math.cos(phase - 0.55)))
            ankle_l = 12.0 * math.sin(phase + 0.4)
            ankle_r = -12.0 * math.sin(phase + 0.4)

            quats["THIGH_L"] = rx(hip_l)
            quats["SHIN_L"] = rx(hip_l + knee_l)
            quats["FOOT_L"] = rx(hip_l + knee_l + ankle_l - 6.0)

            quats["THIGH_R"] = rx(hip_r)
            quats["SHIN_R"] = rx(hip_r + knee_r)
            quats["FOOT_R"] = rx(hip_r + knee_r + ankle_r - 6.0)

            # Aceleración libre mundial coherente con marcha en dirección +Z (frenado/propulsión en 2*w)
            accel_z = (2.8 if mode == "walk" else 4.2) * math.sin(2.0 * phase) + 0.9 * math.cos(phase)
            accel_y = (1.6 if mode == "walk" else 3.2) * math.cos(2.0 * phase)
            accel_x = 0.04 * math.sin(phase)
            world_accel = np.array([accel_x, accel_y, accel_z], dtype=np.float64)

        elif mode == "squat":
            w = 2.0 * math.pi * 0.45
            depth = 0.5 - 0.5 * math.cos(w * t)  # 0..1
            quats["PELVIS"] = rx(18.0 * depth)
            quats["STERNUM"] = rx(28.0 * depth)
            quats["HEAD"] = rx(10.0 * depth)
            quats["SHOULDER_L"] = ident.copy()
            quats["SHOULDER_R"] = ident.copy()
            # Brazos adelante al hacer sentadilla
            arm_fwd = q_mul(ry(80.0 * depth), rz(-70.0 * (1.0 - 0.85 * depth)))
            arm_fwd_r = q_mul(ry(-80.0 * depth), rz(70.0 * (1.0 - 0.85 * depth)))
            for seg in ("UPPER_ARM_L", "FOREARM_L", "HAND_L"):
                quats[seg] = arm_fwd
            for seg in ("UPPER_ARM_R", "FOREARM_R", "HAND_R"):
                quats[seg] = arm_fwd_r
            thigh_ang = -72.0 * depth
            shin_ang = 54.0 * depth
            quats["THIGH_L"] = rx(thigh_ang)
            quats["SHIN_L"] = rx(shin_ang)
            quats["FOOT_L"] = ident.copy()
            quats["THIGH_R"] = rx(thigh_ang)
            quats["SHIN_R"] = rx(shin_ang)
            quats["FOOT_R"] = ident.copy()
            world_accel = np.array([0.0, 2.2 * math.cos(w * t), -0.4 * math.cos(w * t)], dtype=np.float64)

        else:  # wave
            w = 2.0 * math.pi * 0.9
            for seg in self.sensor_map:
                quats[seg] = ident.copy()
            for seg in ("UPPER_ARM_L", "FOREARM_L", "HAND_L"):
                quats[seg] = rz(-80.0)
            quats["SHOULDER_R"] = rz(10.0)
            quats["UPPER_ARM_R"] = rz(-25.0)
            quats["FOREARM_R"] = rz(-75.0 + 28.0 * math.sin(w * t))
            quats["HAND_R"] = rz(-75.0 + 38.0 * math.sin(w * t - 0.3))
            world_accel = np.array([0.3 * math.sin(w * t), 0.1, 0.0], dtype=np.float64)

        for cname in self.custom_segments:
            quats.setdefault(cname, quats["PELVIS"].copy())

        return quats, world_accel

    def generate_step_packets(self, dt: float) -> list[SensorPacket]:
        """Genera un paso determinístico completo (útil tanto en streaming como en QA)."""
        self._sim_clock_s += dt
        return self.sample_at_time(self._sim_clock_s, dt=dt)

    def sample_at_time(self, t_s: float, dt: float = 1.0 / 120.0) -> list[SensorPacket]:
        world_quats, world_accel = self.compute_biomechanical_pose(t_s)
        now_ms = time.monotonic() * 1000.0
        now_mono = time.monotonic()
        packets: list[SensorPacket] = []

        for idx, (seg, sid) in enumerate(self.sensor_map.items()):
            q_true = world_quats.get(seg, q_identity())
            q_mount = self.mount_offsets.get(seg, q_identity())
            yaw_err = self.yaw_drifts_rad.get(seg, 0.0)
            q_yaw = q_from_axis_angle([0.0, 1.0, 0.0], yaw_err)

            # Orientación medida por el sensor: q_sensor = q_yaw_err * q_true * q_mount
            q_sensor = q_normalize(q_mul(q_yaw, q_mul(q_true, q_mount)))
            if self.noise_std_rad > 0.0:
                nvec = self._rng.normal(0.0, self.noise_std_rad, size=3)
                q_noise = q_from_axis_angle(nvec, float(np.linalg.norm(nvec)))
                q_sensor = q_normalize(q_mul(q_sensor, q_noise))

            # Velocidad angular local exacta del sensor mediante derivada en SO(3)
            q_prev = self._prev_world_quats.get(seg)
            if q_prev is not None and dt > 1e-6:
                dq = q_mul(q_inv(q_prev), q_sensor)
                axis, ang = q_to_axis_angle(dq)
                gyro_local = axis * (ang / dt)
            else:
                gyro_local = np.zeros(3, dtype=np.float64)
            self._prev_world_quats[seg] = q_sensor.copy()

            # Ráfaga simulada de agitación para Shake-to-Identify
            if now_mono < self._shake_until.get(sid.upper(), 0.0):
                gyro_local = gyro_local + np.array([9.5 * math.sin(45.0 * t_s), 5.5, -6.5], dtype=np.float64)

            # Aceleración libre expresada en el marco mundo provisional del sensor (rotada por q_yaw)
            fa_sensor_world = q_rotate_vec(q_yaw, world_accel)
            # Campo magnético de referencia en el marco local del sensor
            mag_local = q_rotate_vec(q_inv(q_sensor), np.array([0.0, -0.45, 0.89], dtype=np.float64))

            battery = max(18.0, 96.0 - (idx * 1.4) - (t_s * 0.01))
            rssi = -44 - (idx % 6) * 3

            packets.append(
                SensorPacket(
                    sensor_id=sid,
                    brand="xsens_awinda_sim",
                    protocol="synthetic",
                    segment=seg,
                    quaternion=[float(v) for v in q_sensor],
                    free_accel=[float(v) for v in fa_sensor_world],
                    gyro=[float(v) for v in gyro_local],
                    mag=[float(v) for v in mag_local],
                    battery=round(battery, 1),
                    rssi=rssi,
                    hz=float(self.target_hz),
                    timestamp_ms=now_ms,
                    raw_only=False,
                )
            )
        return packets

    def get_ground_truth_world_quats(self) -> dict[str, np.ndarray]:
        quats, _ = self.compute_biomechanical_pose(self._sim_clock_s)
        return quats

    async def start(
        self,
        preset: MotionPreset = "walk",
        rate_hz: int = 120,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.preset = preset
        self.target_hz = max(30, min(200, int(rate_hz)))
        if self.running and self._task and not self._task.done():
            self.status_message_es = f"Simulador activo ({self.preset}, {self.target_hz} Hz)."
            return self.get_status()

        self._prev_world_quats.clear()
        self._start_ts = time.monotonic()
        self.running = True
        self._task = asyncio.create_task(self._loop(), name="Synthetic17Sim")
        self.status_message_es = f"Simulador 17-IMU activo ({self.preset} a {self.target_hz} Hz)."
        return self.get_status()

    async def _loop(self) -> None:
        dt = 1.0 / float(self.target_hz)
        next_tick = time.perf_counter()
        while self.running:
            pkts = self.generate_step_packets(dt)
            self.emit(pkts)
            next_tick += dt
            delay = next_tick - time.perf_counter()
            if delay > 0.001:
                await asyncio.sleep(delay)
            else:
                if delay < -0.1:
                    next_tick = time.perf_counter()
                await asyncio.sleep(0)

    async def stop(self) -> dict[str, Any]:
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self.status_message_es = "Simulador de 17 sensores detenido."
        return self.get_status()

    def get_status(self) -> dict[str, Any]:
        return {
            "driver": self.driver_name,
            "running": self.running,
            "preset": self.preset,
            "rate_hz": self.target_hz,
            "sensor_count": len(self.sensor_map),
            "has_mount_offsets": len(self.mount_offsets) > 0,
            "has_yaw_drift": len(self.yaw_drifts_rad) > 0,
            "message_es": self.status_message_es,
        }
