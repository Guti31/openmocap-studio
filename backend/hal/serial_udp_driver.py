from __future__ import annotations

import asyncio
import json
import math
import struct
import threading
import time
from typing import Any

import serial
import serial.tools.list_ports

from backend.hal.base import BaseIMUDriver, PacketCallback, SensorPacket
from backend.kinematics.quaternions import q_normalize


def parse_imu_text_payload(
    raw_text: str,
    default_id: str,
    protocol: str,
    now_ms: float | None = None,
) -> SensorPacket | None:
    """
    Decodifica tramas de texto de IMUs de terceros (ESP32, BNO085, ICM-20948, Arduino):
    1) JSON: {"id":"ESP_01","brand":"esp32_bno085","quat":[w,x,y,z],"gyro":[...],"free_accel":[...],"mag":[...],"battery":95}
       o bien con datos crudos {"id":"ESP_02","accel":[ax,ay,az],"gyro":[gx,gy,gz],"mag":[mx,my,mz]} -> raw_only=True
    2) CSV Cuaternión: ID,w,x,y,z[,gx,gy,gz,ax,ay,az]
    3) CSV Crudo: RAW,ID,ax,ay,az,gx,gy,gz[,mx,my,mz] -> raw_only=True
    """
    line = raw_text.strip()
    if not line:
        return None
    ts = now_ms if now_ms is not None else time.monotonic() * 1000.0

    # Formato JSON
    if line.startswith("{"):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None
        sid = str(obj.get("sensor_id") or obj.get("id") or default_id).strip()
        brand = str(obj.get("brand") or "generic_imu")
        quat = obj.get("quaternion") or obj.get("quat") or obj.get("q")
        gyro = [float(v) for v in (obj.get("gyro") or [0.0, 0.0, 0.0])[:3]]
        mag = [float(v) for v in (obj.get("mag") or [0.0, 0.0, 1.0])[:3]]
        battery = float(obj.get("battery", -1.0))
        rssi = int(obj.get("rssi", 0))

        if quat and len(quat) == 4:
            qn = q_normalize([float(v) for v in quat]).tolist()
            fa = [float(v) for v in (obj.get("free_accel") or obj.get("accel") or [0.0, 0.0, 0.0])[:3]]
            return SensorPacket(
                sensor_id=sid,
                brand=brand,
                protocol=protocol,
                segment=str(obj.get("segment") or "UNASSIGNED"),
                quaternion=qn,
                free_accel=fa,
                gyro=gyro,
                mag=mag,
                battery=battery,
                rssi=rssi,
                hz=100.0,
                timestamp_ms=ts,
                raw_only=False,
            )

        accel = obj.get("accel") or obj.get("acc")
        if accel and len(accel) >= 3:
            return SensorPacket(
                sensor_id=sid,
                brand=brand,
                protocol=protocol,
                segment=str(obj.get("segment") or "UNASSIGNED"),
                quaternion=[1.0, 0.0, 0.0, 0.0],
                free_accel=[float(v) for v in accel[:3]],
                gyro=gyro,
                mag=mag,
                battery=battery,
                rssi=rssi,
                hz=100.0,
                timestamp_ms=ts,
                raw_only=True,
            )
        return None

    # Formato CSV
    parts = [p.strip() for p in line.split(",")]
    if len(parts) >= 8 and parts[0].upper() == "RAW":
        try:
            sid = parts[1] or default_id
            ax, ay, az = float(parts[2]), float(parts[3]), float(parts[4])
            gx, gy, gz = float(parts[5]), float(parts[6]), float(parts[7])
            mx, my, mz = (
                (float(parts[8]), float(parts[9]), float(parts[10]))
                if len(parts) >= 11
                else (0.0, 0.0, 1.0)
            )
            return SensorPacket(
                sensor_id=sid,
                brand="esp32_raw_imu",
                protocol=protocol,
                segment="UNASSIGNED",
                quaternion=[1.0, 0.0, 0.0, 0.0],
                free_accel=[ax, ay, az],
                gyro=[gx, gy, gz],
                mag=[mx, my, mz],
                battery=-1.0,
                rssi=0,
                hz=100.0,
                timestamp_ms=ts,
                raw_only=True,
            )
        except ValueError:
            return None

    if len(parts) >= 5:
        try:
            sid = parts[0] or default_id
            qw, qx, qy, qz = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
            gyro = (
                [float(parts[5]), float(parts[6]), float(parts[7])]
                if len(parts) >= 8
                else [0.0, 0.0, 0.0]
            )
            fa = (
                [float(parts[8]), float(parts[9]), float(parts[10])]
                if len(parts) >= 11
                else [0.0, 0.0, 0.0]
            )
            qn = q_normalize([qw, qx, qy, qz]).tolist()
            return SensorPacket(
                sensor_id=sid,
                brand="generic_csv_imu",
                protocol=protocol,
                segment="UNASSIGNED",
                quaternion=qn,
                free_accel=fa,
                gyro=gyro,
                mag=[0.0, 0.0, 1.0],
                battery=-1.0,
                rssi=0,
                hz=100.0,
                timestamp_ms=ts,
                raw_only=False,
            )
        except ValueError:
            return None
    return None


def parse_osc_imu_datagram(data: bytes, default_id: str, now_ms: float | None = None) -> SensorPacket | None:
    """Decodifica paquetes OSC binarios estándar tipo /imu/<sensor_id> con floats big-endian."""
    if not data.startswith(b"/"):
        return None
    try:
        null_idx = data.index(b"\x00")
        address = data[:null_idx].decode("utf-8", errors="ignore")
        cursor = (null_idx + 4) & ~3
        if cursor >= len(data) or data[cursor : cursor + 1] != b",":
            return None
        tag_end = data.index(b"\x00", cursor)
        tags = data[cursor + 1 : tag_end].decode("ascii", errors="ignore")
        payload_start = (tag_end + 4) & ~3
        floats: list[float] = []
        offset = payload_start
        for tag in tags:
            if tag == "f" and offset + 4 <= len(data):
                floats.append(struct.unpack(">f", data[offset : offset + 4])[0])
                offset += 4
            elif tag == "i" and offset + 4 <= len(data):
                floats.append(float(struct.unpack(">i", data[offset : offset + 4])[0]))
                offset += 4
        if len(floats) < 4:
            return None
        sid = address.strip("/").split("/")[-1] or default_id
        ts = now_ms if now_ms is not None else time.monotonic() * 1000.0
        qn = q_normalize(floats[:4]).tolist()
        gyro = floats[4:7] if len(floats) >= 7 else [0.0, 0.0, 0.0]
        fa = floats[7:10] if len(floats) >= 10 else [0.0, 0.0, 0.0]
        return SensorPacket(
            sensor_id=sid,
            brand="osc_imu",
            protocol="osc",
            segment="UNASSIGNED",
            quaternion=qn,
            free_accel=fa,
            gyro=gyro,
            mag=[0.0, 0.0, 1.0],
            battery=-1.0,
            rssi=0,
            hz=100.0,
            timestamp_ms=ts,
            raw_only=False,
        )
    except Exception:
        return None


class WitMotionFrameDecoder:
    """Decodificador de paquetes binarios WitMotion 0x55 (0x51 Accel, 0x52 Gyro, 0x59 Quat)."""

    VALID_TYPES = (0x51, 0x52, 0x53, 0x59)

    def __init__(self, sensor_id: str) -> None:
        self.sensor_id = sensor_id
        self.buf = bytearray()
        self.last_accel = [0.0, 9.81, 0.0]
        self.last_gyro = [0.0, 0.0, 0.0]

    @classmethod
    def has_valid_frame(cls, chunk: bytes) -> bool:
        """Verifica si chunk contiene al menos una trama WitMotion de 11 bytes con checksum válido."""
        n = len(chunk)
        for i in range(0, n - 10):
            if chunk[i] == 0x55 and chunk[i + 1] in cls.VALID_TYPES:
                if (sum(chunk[i : i + 10]) & 0xFF) == chunk[i + 10]:
                    return True
        return False

    def feed(self, chunk: bytes, now_ms: float) -> list[SensorPacket]:
        self.buf.extend(chunk)
        packets: list[SensorPacket] = []
        while len(self.buf) >= 11:
            if self.buf[0] != 0x55:
                del self.buf[0]
                continue
            frame = bytes(self.buf[:11])
            checksum = sum(frame[:10]) & 0xFF
            if checksum != frame[10]:
                del self.buf[0]
                continue
            del self.buf[:11]
            ftype = frame[1]
            vals = struct.unpack("<hhhh", frame[2:10])
            if ftype == 0x51:  # Aceleración (g -> m/s^2)
                self.last_accel = [v / 32768.0 * 16.0 * 9.80665 for v in vals[:3]]
            elif ftype == 0x52:  # Velocidad angular (deg/s -> rad/s)
                self.last_gyro = [math.radians(v / 32768.0 * 2000.0) for v in vals[:3]]
            elif ftype == 0x59:  # Cuaternión directo
                q = q_normalize([v / 32768.0 for v in vals]).tolist()
                packets.append(
                    SensorPacket(
                        sensor_id=self.sensor_id,
                        brand="witmotion",
                        protocol="serial",
                        segment="UNASSIGNED",
                        quaternion=q,
                        free_accel=list(self.last_accel),
                        gyro=list(self.last_gyro),
                        mag=[0.0, 0.0, 1.0],
                        battery=-1.0,
                        rssi=0,
                        hz=100.0,
                        timestamp_ms=now_ms,
                        raw_only=False,
                    )
                )
        return packets


class SerialIMUDriver(BaseIMUDriver):
    """Driver para sensores IMU por puerto COM/USB con autodetección de baudios."""

    driver_name = "serial_imu"
    CANDIDATE_BAUDS = [115200, 921600, 57600, 230400, 38400]

    def __init__(self, on_packets: PacketCallback) -> None:
        super().__init__(on_packets)
        self.port: str | None = None
        self.baudrate: int = 115200
        self._serial: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.status_message_es = "Driver Serial/UART inactivo."

    @staticmethod
    def _is_xsens_port_info(p: Any) -> bool:
        hwid_up = (getattr(p, "hwid", "") or "").upper()
        desc_up = (getattr(p, "description", "") or "").upper()
        mfg_up = (getattr(p, "manufacturer", "") or "").upper()
        return (
            getattr(p, "vid", None) == 0x2639
            or "VID_2639" in hwid_up
            or "2639:" in hwid_up
            or "XSENS" in desc_up
            or "AWINDA" in desc_up
            or "MOVELLA" in desc_up
            or "XSENS" in mfg_up
        )

    @classmethod
    def list_ports(cls) -> list[dict[str, str]]:
        return [
            {
                "port": p.device,
                "description": p.description or "Puerto Serial",
                "hwid": p.hwid or "",
                "is_xsens": "1" if cls._is_xsens_port_info(p) else "0",
            }
            for p in serial.tools.list_ports.comports()
        ]

    def _detect_baud(self, port: str) -> int:
        for baud in self.CANDIDATE_BAUDS:
            try:
                with serial.Serial(port, baudrate=baud, timeout=0.2, write_timeout=0.2) as ser:
                    sample = ser.read(160)
                    if not sample:
                        continue
                    if WitMotionFrameDecoder.has_valid_frame(sample):
                        return baud
                    text = sample.decode("utf-8", errors="ignore")
                    if "{" in text or "," in text:
                        return baud
            except serial.SerialException:
                continue
        return 115200

    async def start(
        self,
        port: str = "",
        baudrate: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if self.running:
            await self.stop()
        if not port:
            ports = [p for p in self.list_ports() if p.get("is_xsens") != "1"]
            if not ports:
                self.status_message_es = "No hay puertos COM de terceros disponibles (puertos Xsens excluidos)."
                return self.get_status()
            port = ports[0]["port"]

        chosen_baud = int(baudrate) if int(baudrate) > 0 else self._detect_baud(port)
        try:
            self._serial = serial.Serial(port, baudrate=chosen_baud, timeout=0.2, write_timeout=0.2)
            self.port = port
            self.baudrate = chosen_baud
            self._stop_event.clear()
            self.running = True
            self._thread = threading.Thread(target=self._read_loop, name="SerialIMULoop", daemon=True)
            self._thread.start()
            self.status_message_es = f"Puerto Serial {port} conectado a {chosen_baud} baudios."
        except serial.SerialException as exc:
            self.running = False
            self.status_message_es = f"Error abriendo puerto {port}: {exc}"
        return self.get_status()

    def _read_loop(self) -> None:
        if not self._serial:
            return
        wit_decoder = WitMotionFrameDecoder(sensor_id=f"WIT_{self.port or 'COM'}")
        text_buf = ""
        last_ts_map: dict[str, float] = {}
        while not self._stop_event.is_set() and self._serial and self._serial.is_open:
            try:
                chunk = self._serial.read(256)
                if not chunk:
                    continue
                now_ms = time.monotonic() * 1000.0
                if WitMotionFrameDecoder.has_valid_frame(chunk) or len(wit_decoder.buf) > 0:
                    pkts = wit_decoder.feed(chunk, now_ms)
                    if pkts:
                        self.emit(pkts)
                        continue
                    # Si el buffer acumulado aún no forma trama válida y parece texto, limpiar y procesar texto
                    if any(b in chunk for b in (b"{", b"\n", b",")):
                        wit_decoder.buf.clear()
                    else:
                        continue

                text_buf += chunk.decode("utf-8", errors="ignore")
                while "\n" in text_buf:
                    line, text_buf = text_buf.split("\n", 1)
                    pkt = parse_imu_text_payload(line, default_id=f"SER_{self.port}", protocol="serial", now_ms=now_ms)
                    if pkt:
                        prev = last_ts_map.get(pkt.sensor_id)
                        if prev and (now_ms - prev) > 0.5:
                            pkt.hz = 1000.0 / (now_ms - prev)
                        last_ts_map[pkt.sensor_id] = now_ms
                        self.emit([pkt])
            except Exception:
                time.sleep(0.02)

    async def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        self.running = False
        ser = self._serial
        self._serial = None
        if ser is not None:
            try:
                if hasattr(ser, "cancel_read"):
                    ser.cancel_read()
            except Exception:
                pass
            try:
                if ser.is_open:
                    ser.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self.status_message_es = "Puerto Serial desconectado."
        return self.get_status()

    def get_status(self) -> dict[str, Any]:
        return {
            "driver": self.driver_name,
            "running": self.running,
            "port": self.port,
            "baudrate": self.baudrate,
            "available_ports": self.list_ports(),
            "message_es": self.status_message_es,
        }


class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, driver: UDPOSCDriver) -> None:
        self.driver = driver

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.driver._handle_datagram(data, addr)


class UDPOSCDriver(BaseIMUDriver):
    """Servidor UDP/OSC asyncio para recibir IMUs inalámbricos por Wi-Fi (ESP32/OSC)."""

    driver_name = "udp_osc"

    def __init__(self, on_packets: PacketCallback) -> None:
        super().__init__(on_packets)
        self.host: str = "0.0.0.0"
        self.port: int = 9000
        self._transport: asyncio.DatagramTransport | None = None
        self._last_ts: dict[str, float] = {}
        self.packets_received: int = 0
        self.status_message_es = "Receptor Wi-Fi UDP/OSC inactivo."

    async def start(self, host: str = "0.0.0.0", port: int = 9000, **kwargs: Any) -> dict[str, Any]:
        if self.running:
            await self.stop()
        self.host = host
        self.port = int(port)
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _UDPProtocol(self),
                local_addr=(self.host, self.port),
            )
            self._transport = transport
            self.running = True
            self.status_message_es = f"Escuchando IMUs Wi-Fi UDP/OSC en {self.host}:{self.port}."
        except OSError as exc:
            self.running = False
            self.status_message_es = f"No se pudo abrir socket UDP {self.port}: {exc}"
        return self.get_status()

    def _handle_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        now_ms = time.monotonic() * 1000.0
        default_id = f"UDP_{addr[0].replace('.', '_')}"
        pkt = parse_osc_imu_datagram(data, default_id=default_id, now_ms=now_ms)
        if pkt is None:
            text = data.decode("utf-8", errors="ignore")
            # Permite múltiples líneas en un datagrama
            batch: list[SensorPacket] = []
            for line in text.splitlines():
                p = parse_imu_text_payload(line, default_id=default_id, protocol="udp", now_ms=now_ms)
                if p:
                    prev = self._last_ts.get(p.sensor_id)
                    if prev and (now_ms - prev) > 0.5:
                        p.hz = 1000.0 / (now_ms - prev)
                    self._last_ts[p.sensor_id] = now_ms
                    batch.append(p)
            if batch:
                self.packets_received += len(batch)
                self.emit(batch)
            return

        prev = self._last_ts.get(pkt.sensor_id)
        if prev and (now_ms - prev) > 0.5:
            pkt.hz = 1000.0 / (now_ms - prev)
        self._last_ts[pkt.sensor_id] = now_ms
        self.packets_received += 1
        self.emit([pkt])

    async def stop(self) -> dict[str, Any]:
        self.running = False
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self.status_message_es = "Receptor Wi-Fi UDP/OSC detenido."
        return self.get_status()

    def get_status(self) -> dict[str, Any]:
        return {
            "driver": self.driver_name,
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "packets_received": self.packets_received,
            "message_es": self.status_message_es,
        }

