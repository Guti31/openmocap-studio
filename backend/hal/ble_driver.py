from __future__ import annotations

import asyncio
import struct
import time
from typing import Any

from bleak import BleakClient, BleakScanner

from backend.hal.base import BaseIMUDriver, PacketCallback, SensorPacket
from backend.kinematics.quaternions import q_normalize

# UUIDs estándar Movella/Xsens DOT y servicio estándar de batería
DOT_CONTROL_CHAR_UUID = "15172001-4947-11e9-8646-d663bd873d93"
DOT_MEDIUM_PAYLOAD_UUID = "15172003-4947-11e9-8646-d663bd873d93"
DOT_SHORT_PAYLOAD_UUID = "15172004-4947-11e9-8646-d663bd873d93"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"


class BLEIMUDriver(BaseIMUDriver):
    """
    Driver Bluetooth Low Energy (BLE) mediante bleak.
    Compatible con sensores Movella/Xsens DOT y servicios GATT genéricos de cuaterniones IMU.
    """

    driver_name = "ble_imu"

    def __init__(self, on_packets: PacketCallback) -> None:
        super().__init__(on_packets)
        self.discovered_devices: list[dict[str, Any]] = []
        self.connected_addresses: list[str] = []
        self._clients: dict[str, BleakClient] = {}
        self._last_ts: dict[str, float] = {}
        self._battery_cache: dict[str, float] = {}
        self.status_message_es = "Escáner Bluetooth BLE listo."

    async def scan_devices(self, timeout_s: float = 3.0) -> list[dict[str, Any]]:
        try:
            devices = await BleakScanner.discover(timeout=timeout_s, return_adv=True)
            found: list[dict[str, Any]] = []
            for addr, (dev, adv) in devices.items():
                name = dev.name or adv.local_name or "Dispositivo BLE"
                uuids = [u.lower() for u in (adv.service_uuids or [])]
                is_imu = (
                    "xsens" in name.lower()
                    or "movella" in name.lower()
                    or "dot" in name.lower()
                    or "imu" in name.lower()
                    or any(u.startswith("1517") for u in uuids)
                )
                found.append(
                    {
                        "address": addr,
                        "name": name,
                        "rssi": int(adv.rssi) if adv.rssi is not None else -75,
                        "is_imu_candidate": is_imu,
                        "service_uuids": uuids,
                    }
                )
            found.sort(key=lambda d: (not d["is_imu_candidate"], -d["rssi"]))
            self.discovered_devices = found
            self.status_message_es = f"Escaneo BLE completado: {len(found)} dispositivos encontrados."
            return found
        except Exception as exc:
            self.status_message_es = f"Adaptador Bluetooth BLE no disponible o desactivado: {exc}"
            return []

    def _make_notification_handler(self, sensor_id: str, brand: str):
        def handler(_sender: Any, data: bytearray) -> None:
            now_ms = time.monotonic() * 1000.0
            prev = self._last_ts.get(sensor_id)
            hz = 1000.0 / max(1.0, now_ms - prev) if prev else 60.0
            self._last_ts[sensor_id] = now_ms

            # Movella DOT Medium Payload: 4 bytes ts + 16 bytes quat (w,x,y,z float32 LE) + 12 bytes free_accel
            if len(data) >= 20:
                qw, qx, qy, qz = struct.unpack_from("<ffff", data, 4)
                qn = q_normalize([qw, qx, qz, -qy]).tolist()
                if len(data) >= 32:
                    ax, ay, az = struct.unpack_from("<fff", data, 20)
                    fa = [float(ax), float(az), -float(ay)]
                else:
                    fa = [0.0, 0.0, 0.0]
            elif len(data) >= 16:
                qw, qx, qy, qz = struct.unpack_from("<ffff", data, 0)
                qn = q_normalize([qw, qx, qy, qz]).tolist()
                fa = [0.0, 0.0, 0.0]
            else:
                return

            self.emit(
                [
                    SensorPacket(
                        sensor_id=sensor_id,
                        brand=brand,
                        protocol="ble",
                        segment="UNASSIGNED",
                        quaternion=qn,
                        free_accel=fa,
                        gyro=[0.0, 0.0, 0.0],
                        mag=[0.0, 0.0, 1.0],
                        battery=self._battery_cache.get(sensor_id, 90.0),
                        rssi=-58,
                        hz=hz,
                        timestamp_ms=now_ms,
                        raw_only=False,
                    )
                ]
            )

        return handler

    async def start(self, addresses: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        targets = addresses or [d["address"] for d in self.discovered_devices if d.get("is_imu_candidate")]
        if not targets:
            await self.scan_devices(timeout_s=2.5)
            targets = [d["address"] for d in self.discovered_devices if d.get("is_imu_candidate")]

        if not targets:
            self.status_message_es = "No se detectaron sensores IMU BLE compatibles encendidos."
            return self.get_status()

        connected = 0
        for addr in targets:
            if addr in self._clients:
                continue
            try:
                client = BleakClient(addr, timeout=6.0)
                await client.connect()
                if not client.is_connected:
                    continue
                sid = f"BLE_{addr.replace(':', '')[-6:].upper()}"
                try:
                    bat_bytes = await client.read_gatt_char(BATTERY_LEVEL_UUID)
                    if bat_bytes:
                        self._battery_cache[sid] = float(bat_bytes[0])
                except Exception:
                    pass

                # Habilitar flujo Movella DOT Medium Payload (modo cuaternión + aceleración libre)
                subscribed = False
                for uuid in (DOT_MEDIUM_PAYLOAD_UUID, DOT_SHORT_PAYLOAD_UUID):
                    try:
                        await client.start_notify(uuid, self._make_notification_handler(sid, "movella_dot"))
                        subscribed = True
                        break
                    except Exception:
                        continue

                if subscribed:
                    try:
                        # Comando medición continua Movella DOT: [1, 1, 0x06]
                        await client.write_gatt_char(DOT_CONTROL_CHAR_UUID, bytearray([0x01, 0x01, 0x06]))
                    except Exception:
                        pass
                    self._clients[addr] = client
                    connected += 1
                else:
                    await client.disconnect()
            except Exception:
                continue

        self.connected_addresses = list(self._clients.keys())
        self.running = connected > 0 or len(self._clients) > 0
        self.status_message_es = (
            f"BLE conectado a {len(self._clients)} sensores."
            if self.running
            else "No fue posible suscribir notificaciones GATT en los dispositivos BLE encontrados."
        )
        return self.get_status()

    async def stop(self) -> dict[str, Any]:
        for client in list(self._clients.values()):
            try:
                await client.disconnect()
            except Exception:
                pass
        self._clients.clear()
        self.connected_addresses.clear()
        self.running = False
        self.status_message_es = "Sensores Bluetooth BLE desconectados."
        return self.get_status()

    def get_status(self) -> dict[str, Any]:
        return {
            "driver": self.driver_name,
            "running": self.running,
            "connected_addresses": self.connected_addresses,
            "discovered_devices": self.discovered_devices,
            "message_es": self.status_message_es,
        }

