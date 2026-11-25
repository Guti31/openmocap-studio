from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SensorPacket:
    """Esquema canónico universal HAL para cualquier sensor IMU físico o simulado."""

    sensor_id: str
    brand: str
    protocol: str
    segment: str
    quaternion: list[float]  # Hamilton [w, x, y, z]
    free_accel: list[float]  # m/s^2 en marco mundo provisional del sensor (Y-up)
    gyro: list[float]        # rad/s en marco local del sensor
    mag: list[float]         # normalizado o uT en marco local del sensor
    battery: float           # 0.0 - 100.0, o -1.0 si no aplica
    rssi: int                # dBm, o 0 si es cableado/simulado
    hz: float
    timestamp_ms: float
    raw_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "brand": self.brand,
            "protocol": self.protocol,
            "segment": self.segment,
            "quaternion": [float(v) for v in self.quaternion],
            "free_accel": [float(v) for v in self.free_accel],
            "gyro": [float(v) for v in self.gyro],
            "mag": [float(v) for v in self.mag],
            "battery": float(self.battery),
            "rssi": int(self.rssi),
            "hz": round(float(self.hz), 1),
            "timestamp_ms": float(self.timestamp_ms),
            "raw_only": bool(self.raw_only),
        }


PacketCallback = Callable[[list[SensorPacket]], None]


class BaseIMUDriver(ABC):
    """Interfaz base asíncrona obligatoria para todos los drivers de hardware IMU."""

    driver_name: str = "base"

    def __init__(self, on_packets: PacketCallback) -> None:
        self._on_packets = on_packets
        self.running: bool = False
        self.status_message_es: str = "Inactivo"
        self.target_hz: int = 120

    @abstractmethod
    async def start(self, **kwargs: Any) -> dict[str, Any]:
        """Inicia la adquisición del driver."""

    @abstractmethod
    async def stop(self) -> dict[str, Any]:
        """Detiene limpiamente el driver y libera recursos."""

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Devuelve el estado diagnóstico en tiempo real."""

    async def set_rate(self, hz: int) -> None:
        self.target_hz = max(10, min(240, int(hz)))

    def emit(self, packets: list[SensorPacket]) -> None:
        if packets and self._on_packets:
            self._on_packets(packets)


class HALManager:
    """Multiplexor central de drivers IMU multi-marca con registro unificado."""

    def __init__(self) -> None:
        self.drivers: dict[str, BaseIMUDriver] = {}
        self._listeners: list[PacketCallback] = []
        self.last_activity_ms: float = 0.0

    def register_listener(self, cb: PacketCallback) -> None:
        self._listeners.append(cb)

    def register_driver(self, key: str, driver: BaseIMUDriver) -> None:
        self.drivers[key] = driver

    def dispatch_packets(self, packets: list[SensorPacket]) -> None:
        if not packets:
            return
        self.last_activity_ms = time.monotonic() * 1000.0
        for listener in self._listeners:
            listener(packets)

    def get_all_statuses(self) -> dict[str, Any]:
        return {k: drv.get_status() for k, drv in self.drivers.items()}

    async def stop_all(self) -> None:
        for drv in self.drivers.values():
            if drv.running:
                await drv.stop()

