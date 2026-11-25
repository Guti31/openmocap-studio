from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from typing import Any

from backend.hal.base import SensorPacket
from backend.paths import get_config_dir


class DynamicSensorMapper:
    """
    Mapeador bidireccional sensor_id <-> segmento anatómico.
    Precarga los 17 IDs exactos Xsens Awinda, permite reasignar o añadir sensores ilimitados
    (21, 32+ sensores) y detecta agitación física ("Agitar para identificar").
    """

    def __init__(self, settings_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self.settings_dir = settings_dir
        self.segment_to_sensor: dict[str, str] = {}
        self.sensor_to_segment: dict[str, str] = {}
        self.extended_presets: list[dict[str, Any]] = []

        # Detector de agitación sostenida
        self._shake_start_mono: dict[str, float] = {}
        self._shake_cooldown: dict[str, float] = {}
        self.last_shake_event: dict[str, Any] | None = None
        self.shake_threshold_rad_s: float = 6.5
        self.shake_min_duration_s: float = 0.12

        self._load_defaults()

    def _load_defaults(self) -> None:
        with self._lock:
            cfg_file = get_config_dir() / "default_awinda_17.json"
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            self.extended_presets = list(data.get("extended_segment_presets", []))
            for seg, sid in data.get("mappings", {}).items():
                self.assign(str(sid), str(seg), persist=False)

            if self.settings_dir:
                custom_file = self.settings_dir / "sensor_mapping.json"
                if custom_file.exists():
                    try:
                        saved = json.loads(custom_file.read_text(encoding="utf-8"))
                        if isinstance(saved, dict) and saved:
                            self.segment_to_sensor.clear()
                            self.sensor_to_segment.clear()
                            for seg, sid in saved.items():
                                self.assign(str(sid), str(seg), persist=False)
                    except (OSError, json.JSONDecodeError):
                        pass

    def _persist(self) -> None:
        with self._lock:
            if self.settings_dir:
                self.settings_dir.mkdir(parents=True, exist_ok=True)
                target = self.settings_dir / "sensor_mapping.json"
                target.write_text(
                    json.dumps(self.segment_to_sensor, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

    def reset_to_default_awinda(self) -> dict[str, str]:
        with self._lock:
            if self.settings_dir:
                target = self.settings_dir / "sensor_mapping.json"
                if target.exists():
                    target.unlink()
            self.segment_to_sensor.clear()
            self.sensor_to_segment.clear()
            self._load_defaults()
            return dict(self.segment_to_sensor)

    def assign(self, sensor_id: str, segment: str, persist: bool = True) -> dict[str, str]:
        sid = sensor_id.strip().upper()
        seg = segment.strip().upper()
        if not sid or not seg:
            raise ValueError("sensor_id y segment son obligatorios.")

        with self._lock:
            # Liberar asignaciones previas en conflicto
            old_seg = self.sensor_to_segment.pop(sid, None)
            if old_seg:
                self.segment_to_sensor.pop(old_seg, None)

            old_sid = self.segment_to_sensor.pop(seg, None)
            if old_sid:
                self.sensor_to_segment.pop(old_sid, None)

            self.segment_to_sensor[seg] = sid
            self.sensor_to_segment[sid] = seg
            if persist:
                self._persist()
            return dict(self.segment_to_sensor)

    def unassign_sensor(self, sensor_id: str) -> dict[str, str]:
        sid = sensor_id.strip().upper()
        with self._lock:
            seg = self.sensor_to_segment.pop(sid, None)
            if seg:
                self.segment_to_sensor.pop(seg, None)
            self._persist()
            return dict(self.segment_to_sensor)

    def resolve_and_check_shake(self, packet: SensorPacket) -> str:
        """Asigna segmento al paquete recibido y verifica si el sensor fue agitado."""
        sid = packet.sensor_id.strip().upper()
        packet.sensor_id = sid
        with self._lock:
            seg = self.sensor_to_segment.get(sid)
            if seg:
                packet.segment = seg
            elif packet.segment and packet.segment.upper() != "UNASSIGNED":
                # Auto-registrar si el paquete ya trae segmento explícito libre
                cand = packet.segment.upper()
                if cand not in self.segment_to_sensor:
                    self.assign(sid, cand, persist=True)
                    packet.segment = cand
                else:
                    packet.segment = "UNASSIGNED"
            else:
                packet.segment = "UNASSIGNED"

            # Detección de agitación ("Shake to identify")
            gx, gy, gz = float(packet.gyro[0]), float(packet.gyro[1]), float(packet.gyro[2])
            mag = math.sqrt(gx * gx + gy * gy + gz * gz)
            now = time.monotonic()
            if mag >= self.shake_threshold_rad_s:
                start = self._shake_start_mono.setdefault(sid, now)
                if (now - start) >= self.shake_min_duration_s:
                    if now >= self._shake_cooldown.get(sid, 0.0):
                        self._shake_cooldown[sid] = now + 1.5
                        self.last_shake_event = {
                            "sensor_id": sid,
                            "segment": packet.segment,
                            "brand": packet.brand,
                            "gyro_norm": round(mag, 2),
                            "timestamp_ms": round(packet.timestamp_ms, 1),
                        }
            else:
                self._shake_start_mono.pop(sid, None)

            return packet.segment

    def get_mapping_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "segment_to_sensor": dict(self.segment_to_sensor),
                "sensor_to_segment": dict(self.sensor_to_segment),
                "extended_presets": list(self.extended_presets),
                "last_shake_event": dict(self.last_shake_event) if self.last_shake_event else None,
            }

