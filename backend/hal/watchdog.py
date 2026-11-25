from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.hal.base import SensorPacket
from backend.kinematics.quaternions import q_from_axis_angle, q_mul, q_normalize, q_slerp


@dataclass
class TrackedSensorState:
    last_packet: SensorPacket
    smoothed_quat: np.ndarray
    last_seen_mono: float
    timestamps_ms: deque[float] = field(default_factory=lambda: deque(maxlen=40))
    status: str = "online"  # online | degraded | interpolating | lost
    dropped_frames: int = 0
    measured_hz: float = 0.0
    last_interp_drop_mono: float = 0.0


class ConnectionWatchdog:
    """
    Supervisa la salud inalámbrica por sensor, suaviza jitter mediante SLERP adaptativo
    e interpola orientaciones por velocidad angular ante cortes inalámbricos breves (< 250 ms).
    """

    def __init__(self, smoothing_alpha: float = 1.0, max_interp_ms: float = 250.0, lost_ms: float = 1500.0) -> None:
        self.smoothing_alpha = max(0.1, min(1.0, float(smoothing_alpha)))
        self.max_interp_ms = float(max_interp_ms)
        self.lost_ms = float(lost_ms)
        self._sensors: dict[str, TrackedSensorState] = {}
        self._lock = threading.RLock()

    def ingest(self, packet: SensorPacket) -> SensorPacket:
        now = time.monotonic()
        q_in = q_normalize(packet.quaternion)
        with self._lock:
            state = self._sensors.get(packet.sensor_id)

            if state is None:
                state = TrackedSensorState(
                    last_packet=packet,
                    smoothed_quat=q_in,
                    last_seen_mono=now,
                    status="online",
                    measured_hz=packet.hz,
                )
                state.timestamps_ms.append(packet.timestamp_ms)
                self._sensors[packet.sensor_id] = state
                return packet

            # Detectar saltos reales de paquetes respecto al periodo esperado del sensor
            if len(state.timestamps_ms) >= 2 and state.measured_hz > 1.0:
                expected_period_ms = 1000.0 / max(10.0, state.measured_hz)
                gap_ms = packet.timestamp_ms - state.timestamps_ms[-1]
                if gap_ms > expected_period_ms * 1.75:
                    missed = max(1, int(round(gap_ms / expected_period_ms)) - 1)
                    if state.status != "interpolating":
                        state.dropped_frames += missed

            # Filtro SLERP anti-jitter: paso directo si alpha=1.0, con transición suave al volver de interpolación
            effective_alpha = 0.45 if state.status == "interpolating" else self.smoothing_alpha
            if effective_alpha < 0.999:
                q_smooth = q_slerp(state.smoothed_quat, q_in, effective_alpha)
            else:
                q_smooth = q_in

            state.timestamps_ms.append(packet.timestamp_ms)
            if len(state.timestamps_ms) >= 3:
                span = state.timestamps_ms[-1] - state.timestamps_ms[0]
                if span > 1.0:
                    state.measured_hz = ((len(state.timestamps_ms) - 1) * 1000.0) / span
            else:
                state.measured_hz = packet.hz

            state.last_seen_mono = now
            state.last_interp_drop_mono = 0.0
            state.smoothed_quat = q_smooth
            packet.quaternion = [float(v) for v in q_smooth]
            packet.hz = round(float(state.measured_hz), 1)
            state.last_packet = packet
            state.status = "degraded" if state.measured_hz < 20.0 else "online"
            return packet

    def is_fresh_online(self, sensor_id: str, max_age_ms: float = 120.0) -> bool:
        """Indica si el sensor recibió un paquete real reciente dentro de la ventana temporal."""
        with self._lock:
            state = self._sensors.get(sensor_id)
            if state is None:
                return False
            age_ms = (time.monotonic() - state.last_seen_mono) * 1000.0
            return age_ms <= max_age_ms and state.status in ("online", "degraded")

    def get_active_snapshot(self) -> dict[str, SensorPacket]:
        """Devuelve todos los sensores vivos, extrapolando por gyro durante cortes cortos."""
        now = time.monotonic()
        snapshot: dict[str, SensorPacket] = {}
        with self._lock:
            items = list(self._sensors.items())
            for sid, state in items:
                elapsed_ms = (now - state.last_seen_mono) * 1000.0
                pkt = state.last_packet
                if elapsed_ms <= 35.0:
                    snapshot[sid] = pkt
                elif elapsed_ms <= self.max_interp_ms:
                    dt_s = elapsed_ms / 1000.0
                    gyro = np.asarray(pkt.gyro, dtype=np.float64)
                    speed = float(np.linalg.norm(gyro))
                    if speed > 1e-4:
                        q_pred = q_normalize(
                            q_mul(state.smoothed_quat, q_from_axis_angle(gyro, speed * dt_s))
                        )
                    else:
                        q_pred = state.smoothed_quat
                    sample_period_s = 1.0 / max(20.0, state.measured_hz or pkt.hz or 60.0)
                    if state.status != "interpolating":
                        state.dropped_frames += 1
                        state.last_interp_drop_mono = now
                    elif (now - state.last_interp_drop_mono) >= sample_period_s:
                        state.dropped_frames += 1
                        state.last_interp_drop_mono = now
                    state.status = "interpolating"
                    snapshot[sid] = SensorPacket(
                        sensor_id=pkt.sensor_id,
                        brand=pkt.brand,
                        protocol=pkt.protocol,
                        segment=pkt.segment,
                        quaternion=[float(v) for v in q_pred],
                        free_accel=list(pkt.free_accel),
                        gyro=list(pkt.gyro),
                        mag=list(pkt.mag),
                        battery=pkt.battery,
                        rssi=pkt.rssi,
                        hz=pkt.hz,
                        timestamp_ms=pkt.timestamp_ms + elapsed_ms,
                        raw_only=pkt.raw_only,
                    )
                elif elapsed_ms <= self.lost_ms:
                    state.status = "degraded"
                    snapshot[sid] = pkt
                else:
                    state.status = "lost"
        return snapshot

    def get_diagnostics(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        out: dict[str, dict[str, Any]] = {}
        with self._lock:
            items = list(self._sensors.items())
            for sid, state in items:
                pkt = state.last_packet
                age_ms = (now - state.last_seen_mono) * 1000.0
                status = state.status
                if age_ms > self.lost_ms:
                    status = "lost"
                out[sid] = {
                    "sensor_id": sid,
                    "brand": pkt.brand,
                    "protocol": pkt.protocol,
                    "segment": pkt.segment,
                    "battery": pkt.battery,
                    "rssi": pkt.rssi,
                    "hz": round(state.measured_hz, 1),
                    "status": status,
                    "age_ms": round(age_ms, 1),
                    "dropped_frames": state.dropped_frames,
                }
        return out
