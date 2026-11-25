from __future__ import annotations

import asyncio
import importlib
import json
import os
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import serial
import serial.tools.list_ports

from backend.hal.base import BaseIMUDriver, PacketCallback, SensorPacket
from backend.kinematics.quaternions import q_normalize
from backend.paths import get_config_dir, get_settings_dir

# Mantener vivos los handles de os.add_dll_directory() durante todo el ciclo de vida del proceso
_DLL_DIR_HANDLES: list[Any] = []

XSENS_USB_VID = 0x2639
FTDI_USB_VID = 0x0403

# Constantes del protocolo binario Xsens Xbus (verificadas en AW-DNG2-ANT FW 4.6.0)
XBUS_PREAMBLE = 0xFA
XBUS_BID_MASTER = 0xFF
MID_REQ_DID = 0x00
MID_DEVICE_ID = 0x01
MID_GOTO_MEASUREMENT = 0x10
MID_GOTO_MEASUREMENT_ACK = 0x11
MID_REQ_FW_REV = 0x12
MID_FW_REV = 0x13
MID_GOTO_CONFIG = 0x30
MID_GOTO_CONFIG_ACK = 0x31
MID_MTDATA2 = 0x36
MID_WAKEUP = 0x3E
MID_WAKEUP_ACK = 0x3F
MID_ERROR = 0x42
MID_NOTIFICATION = 0x46
MID_BOOTLOADER_FINISHED = 0xF2
MID_REQ_STATION_OPTIONS = 0x7C
MID_REQ_STATION_OPTIONS_ACK = 0x7D
MID_SET_UPDATE_RATE = 0xA4
MID_SET_UPDATE_RATE_ACK = 0xA5
MID_SET_OUTPUT_CONFIGURATION = 0xC0

# Control de radio inalámbrica y sincronización TDMA Awinda2 (principal) + respaldo heredado 0xAC
MID_ENABLE_MASTER = 0xB2
MID_ENABLE_MASTER_ACK = 0xB3
MID_DISABLE_MASTER = 0xB4
MID_DISABLE_MASTER_ACK = 0xB5
MID_REQ_RADIO_CHANNEL = 0xB6
MID_REQ_RADIO_CHANNEL_ACK = 0xB7
MID_SET_WIRELESS_CONFIG = 0xBA
MID_SET_WIRELESS_CONFIG_ACK = 0xBB
MID_GOTO_OPERATIONAL = 0xC0
MID_GOTO_OPERATIONAL_ACK = 0xC1
MID_ACCEPT_MTW = 0xC4
MID_ACCEPT_MTW_ACK = 0xC5
MID_REQ_FRAME_RATES = 0xCA
MID_REQ_FRAME_RATES_ACK = 0xCB
MID_ENABLE_RADIO_LEGACY = 0xAC
MID_ENABLE_RADIO_LEGACY_ACK = 0xAD

# Alias principales para compatibilidad clara
MID_ENABLE_RADIO = MID_ENABLE_MASTER
MID_ENABLE_RADIO_ACK = MID_ENABLE_MASTER_ACK

SWEEP_CHANNELS: list[int] = [11, 15, 20, 25, 12, 13, 14, 16, 17, 18, 19, 21, 22, 23, 24]
DEFAULT_AWINDA_TDMA_HZ: int = 60
CHANNEL_DWELL_SECONDS: float = 3.5


def build_channel_sweep_order(initial_channel: int = 11) -> list[int]:
    """Devuelve el orden prioritario de barrido RF [11..25] iniciando en initial_channel."""
    ch = max(11, min(25, int(initial_channel)))
    return [ch] + [c for c in SWEEP_CHANNELS if c != ch]


def xbus_checksum(body_after_fa: bytes) -> int:
    """Calcula el byte de comprobación Xbus tal que sum(bytes desde BID hasta checksum) & 0xFF == 0."""
    return (-sum(body_after_fa)) & 0xFF


def build_xbus_frame(mid: int, data: bytes = b"", bid: int = XBUS_BID_MASTER) -> bytes:
    """Construye una trama binaria Xbus válida con preámbulo 0xFA y checksum."""
    length = len(data)
    if length < 255:
        body = bytes([bid & 0xFF, mid & 0xFF, length]) + data
    else:
        body = bytes([bid & 0xFF, mid & 0xFF, 0xFF]) + struct.pack(">H", length) + data
    return bytes([XBUS_PREAMBLE]) + body + bytes([xbus_checksum(body)])


def cmd_wakeup(bid: int = XBUS_BID_MASTER) -> bytes:
    """Trama Xbus WakeUp: FA FF 3E 00 C3."""
    return build_xbus_frame(MID_WAKEUP, b"", bid=bid)


def cmd_wakeup_ack(bid: int = XBUS_BID_MASTER) -> bytes:
    """Trama Xbus WakeUpAck: FA FF 3F 00 C2."""
    return build_xbus_frame(MID_WAKEUP_ACK, b"", bid=bid)


def cmd_goto_config(bid: int = XBUS_BID_MASTER) -> bytes:
    """Trama Xbus GotoConfig: FA FF 30 00 D1."""
    return build_xbus_frame(MID_GOTO_CONFIG, b"", bid=bid)


def cmd_goto_measurement(bid: int = XBUS_BID_MASTER) -> bytes:
    """Trama Xbus GotoMeasurement: FA FF 10 00 F1."""
    return build_xbus_frame(MID_GOTO_MEASUREMENT, b"", bid=bid)


def cmd_req_did(bid: int = XBUS_BID_MASTER) -> bytes:
    """Solicita el identificador único de la estación/dongle Awinda: FA FF 00 00 01."""
    return build_xbus_frame(MID_REQ_DID, b"", bid=bid)


def cmd_req_fw_rev(bid: int = XBUS_BID_MASTER) -> bytes:
    """Solicita la revisión de firmware de la estación/dongle: FA FF 12 00 EF."""
    return build_xbus_frame(MID_REQ_FW_REV, b"", bid=bid)


def cmd_bootloader_finished() -> bytes:
    """Saca al dongle del estado bootloader hacia el firmware operacional: FA FF F2 01 46 C8."""
    return bytes.fromhex("FA FF F2 01 46 C8")


def cmd_set_update_rate(rate_hz: int = DEFAULT_AWINDA_TDMA_HZ) -> bytes:
    """Configura la tasa TDMA inalámbrica en Hz (MID = 0xA4, 0x00 0x3C = 60 Hz)."""
    hz = max(40, min(120, int(rate_hz)))
    return build_xbus_frame(MID_SET_UPDATE_RATE, struct.pack(">H", hz), bid=XBUS_BID_MASTER)


def cmd_set_output_configuration(rate_hz: int = DEFAULT_AWINDA_TDMA_HZ) -> bytes:
    """Configura salida inalámbrica XDI (DeviceId, Quaternion, FreeAccel, StatusWord) a rate_hz."""
    hz = max(40, min(120, int(rate_hz)))
    blocks = (
        struct.pack(">HH", 0x0010, 0xFFFF)
        + struct.pack(">HH", 0x1070, 0xFFFF)
        + struct.pack(">HH", 0x2010, hz)
        + struct.pack(">HH", 0x4030, hz)
        + struct.pack(">HH", 0xE020, hz)
    )
    return build_xbus_frame(MID_SET_OUTPUT_CONFIGURATION, blocks, bid=XBUS_BID_MASTER)


def cmd_set_wireless_config(rate_hz: int = DEFAULT_AWINDA_TDMA_HZ) -> bytes:
    """Configura parámetros inalámbricos TDMA (MID = 0xBA)."""
    hz = max(40, min(120, int(rate_hz)))
    return build_xbus_frame(MID_SET_WIRELESS_CONFIG, struct.pack(">H", hz), bid=XBUS_BID_MASTER)


def cmd_accept_mtw(device_id: int) -> bytes:
    """Acepta explícitamente un sensor MTw por su DeviceID de 32 bits (MID = 0xC4)."""
    return build_xbus_frame(MID_ACCEPT_MTW, struct.pack(">I", int(device_id) & 0xFFFFFFFF), bid=XBUS_BID_MASTER)


def cmd_enable_radio(channel: int = 11) -> bytes:
    """Enciende la radio maestra Awinda2 en el canal indicado [11..25] (MID = 0xB2, ack = 0xB3)."""
    ch = max(11, min(25, int(channel)))
    return build_xbus_frame(MID_ENABLE_MASTER, bytes([ch]), bid=XBUS_BID_MASTER)


def cmd_goto_operational() -> bytes:
    """Completa la transición operacional tras EnableMaster (MID = 0xC0, len = 0, FA FF C0 00 41)."""
    return build_xbus_frame(MID_GOTO_OPERATIONAL, b"", bid=XBUS_BID_MASTER)


def cmd_disable_radio() -> bytes:
    """Apaga la radio inalámbrica de la estación Awinda2 (MID = 0xB4 DisableMaster, FA FF B4 00 4D)."""
    return build_xbus_frame(MID_DISABLE_MASTER, b"", bid=XBUS_BID_MASTER)


def cmd_req_radio_channel() -> bytes:
    """Consulta el canal RF activo en la estación Awinda2 (MID = 0xB6, FA FF B6 00 4B)."""
    return build_xbus_frame(MID_REQ_RADIO_CHANNEL, b"", bid=XBUS_BID_MASTER)


def cmd_enable_radio_legacy_u16(channel: int = 11) -> bytes:
    """Respaldo heredado Awinda1/MTw [0x00, channel] (MID = 0xAC)."""
    ch = max(11, min(25, int(channel)))
    return build_xbus_frame(MID_ENABLE_RADIO_LEGACY, bytes([0x00, ch]), bid=XBUS_BID_MASTER)


def cmd_enable_radio_legacy_u8(channel: int = 11) -> bytes:
    """Respaldo heredado Awinda1/MTw [channel] (MID = 0xAC)."""
    ch = max(11, min(25, int(channel)))
    return build_xbus_frame(MID_ENABLE_RADIO_LEGACY, bytes([ch]), bid=XBUS_BID_MASTER)


def activate_awinda_tdma_channel_sync(
    ser: serial.Serial,
    parser: XbusStreamParser,
    channel: int,
    tdma_rate_hz: int = DEFAULT_AWINDA_TDMA_HZ,
    stop_event: threading.Event | None = None,
    operational_wait_s: float = 0.0,
    on_operational_frames: Callable[[list[tuple[int, int, bytes]]], None] | None = None,
) -> tuple[bool, bool, int | None, list[str]]:
    """
    Ejecuta el ciclo síncrono completo TDMA Awinda2 sobre el puerto serie ya abierto:
      GotoConfig -> DisableMaster -> SetUpdateRate(60) -> SetOutputConfiguration(60) ->
      EnableMaster(ch) -> GotoOperational -> ReqRadioChannel (con respaldo 0xAC) ->
      [espera opcional en modo Operational para aceptación MTw] -> GotoMeasurement.
    Devuelve (radio_ack, measurement_ack, verified_channel, logs).
    """
    ch = max(11, min(25, int(channel)))
    logs: list[str] = []

    ser.write(cmd_goto_config())
    cfg_f, cfg_rx = read_xbus_frames_sync(
        ser, parser, timeout_s=0.22, target_mids={MID_GOTO_CONFIG_ACK, MID_WAKEUP, MID_DEVICE_ID}
    )
    logs.append(f"GotoConfig(ch={ch}): rx={cfg_rx.hex()} mids={[hex(m) for _, m, _ in cfg_f]}")

    ser.write(cmd_disable_radio())
    dis_f, dis_rx = read_xbus_frames_sync(
        ser, parser, timeout_s=0.18, target_mids={MID_DISABLE_MASTER_ACK, MID_ERROR}
    )
    logs.append(f"DisableMaster(ch={ch}): rx={dis_rx.hex()} mids={[hex(m) for _, m, _ in dis_f]}")

    # Enviar configuración de tasa TDMA (60 Hz) + salida XDI antes de EnableMaster
    ser.write(cmd_set_update_rate(tdma_rate_hz))
    rate_f, _ = read_xbus_frames_sync(
        ser, parser, timeout_s=0.12, target_mids={MID_SET_UPDATE_RATE_ACK, MID_ERROR}
    )
    ser.write(cmd_set_output_configuration(tdma_rate_hz))
    out_f, _ = read_xbus_frames_sync(
        ser, parser, timeout_s=0.12, target_mids={MID_GOTO_OPERATIONAL_ACK, MID_ERROR}
    )
    logs.append(
        f"TDMA60Hz(rate={[hex(m) for _, m, _ in rate_f]}, out={[hex(m) for _, m, _ in out_f]})"
    )

    radio_ack = False
    verified_ch: int | None = None
    op_f: list[tuple[int, int, bytes]] = []
    ch_f: list[tuple[int, int, bytes]] = []

    ser.write(cmd_enable_radio(ch))
    en_f, en_rx = read_xbus_frames_sync(
        ser, parser, timeout_s=0.25, target_mids={MID_ENABLE_MASTER_ACK, MID_ERROR}
    )
    logs.append(f"EnableMaster(ch={ch}): rx={en_rx.hex()} mids={[hex(m) for _, m, _ in en_f]}")

    if any(mid == MID_ENABLE_MASTER_ACK for _b, mid, _p in en_f):
        ser.write(cmd_goto_operational())
        op_f, op_rx = read_xbus_frames_sync(
            ser, parser, timeout_s=0.30, target_mids={MID_GOTO_OPERATIONAL_ACK, MID_ERROR}
        )
        logs.append(f"GotoOperational(ch={ch}): rx={op_rx.hex()} mids={[hex(m) for _, m, _ in op_f]}")

        ser.write(cmd_req_radio_channel())
        ch_f, ch_rx = read_xbus_frames_sync(
            ser, parser, timeout_s=0.20, target_mids={MID_REQ_RADIO_CHANNEL_ACK, MID_ERROR}
        )
        logs.append(f"ReqRadioChannel(ch={ch}): rx={ch_rx.hex()} mids={[hex(m) for _, m, _ in ch_f]}")

        for _b, mid, pl in ch_f:
            if mid == MID_REQ_RADIO_CHANNEL_ACK and len(pl) >= 2:
                val = struct.unpack_from(">h", pl, 0)[0]
                if val >= 11:
                    verified_ch = int(val)

        op_ok = any(mid == MID_GOTO_OPERATIONAL_ACK for _b, mid, _p in op_f)
        if verified_ch == ch or op_ok:
            radio_ack = True
            verified_ch = verified_ch if verified_ch is not None else ch
    else:
        for tag, leg_frame in (
            ("LegacyRadio2B", cmd_enable_radio_legacy_u16(ch)),
            ("LegacyRadio1B", cmd_enable_radio_legacy_u8(ch)),
        ):
            ser.write(leg_frame)
            leg_f, leg_rx = read_xbus_frames_sync(
                ser, parser, timeout_s=0.20, target_mids={MID_ENABLE_RADIO_LEGACY_ACK, MID_ERROR}
            )
            logs.append(f"{tag}(ch={ch}): rx={leg_rx.hex()} mids={[hex(m) for _, m, _ in leg_f]}")
            if any(mid == MID_ENABLE_RADIO_LEGACY_ACK for _b, mid, _p in leg_f):
                radio_ack = True
                verified_ch = ch
                break

    if not radio_ack:
        return False, False, None, logs

    if on_operational_frames is not None and (op_f or ch_f):
        on_operational_frames(op_f + ch_f)

    # Ventana de escucha en modo Operational (hasta 1.2 s en barrido) para detectar MasterIndication (0x46) / DeviceID
    if operational_wait_s > 0.0:
        op_deadline = time.monotonic() + operational_wait_s
        while time.monotonic() < op_deadline:
            if (stop_event is not None and stop_event.is_set()) or not ser.is_open:
                return radio_ack, False, verified_ch, logs
            waiting = ser.in_waiting
            if waiting > 0:
                chunk = ser.read(min(4096, waiting))
                if chunk:
                    extra_frames = parser.feed(chunk)
                    if extra_frames and on_operational_frames is not None:
                        on_operational_frames(extra_frames)
            step = min(0.05, max(0.0, op_deadline - time.monotonic()))
            if step > 0.0:
                if stop_event is not None:
                    if stop_event.wait(step):
                        return radio_ack, False, verified_ch, logs
                else:
                    time.sleep(step)

    if (stop_event is not None and stop_event.is_set()) or not ser.is_open:
        return radio_ack, False, verified_ch, logs

    ser.write(cmd_goto_measurement())
    meas_f, meas_rx = read_xbus_frames_sync(
        ser, parser, timeout_s=0.28, target_mids={MID_GOTO_MEASUREMENT_ACK, MID_MTDATA2, MID_ERROR}
    )
    logs.append(f"GotoMeasurement(ch={ch}): rx={meas_rx.hex()} mids={[hex(m) for _, m, _ in meas_f]}")
    meas_ack = any(mid in (MID_GOTO_MEASUREMENT_ACK, MID_MTDATA2) for _b, mid, _p in meas_f)
    return radio_ack, meas_ack, verified_ch, logs


def read_xbus_frames_sync(
    ser: serial.Serial,
    parser: XbusStreamParser,
    timeout_s: float = 0.35,
    target_mids: set[int] | None = None,
) -> tuple[list[tuple[int, int, bytes]], bytes]:
    """
    Lee respuestas Xbus de forma incremental sin bloqueos hasta timeout_s o hasta recibir
    alguno de los MIDs esperados, devolviendo (tramas_decodificadas, bytes_crudos).
    """
    collected_frames: list[tuple[int, int, bytes]] = []
    raw_chunks = bytearray()
    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting > 0:
            chunk = ser.read(waiting)
            if chunk:
                raw_chunks.extend(chunk)
                new_frames = parser.feed(chunk)
                if new_frames:
                    collected_frames.extend(new_frames)
                    if target_mids and any(mid in target_mids for _bid, mid, _pl in collected_frames):
                        break
        else:
            time.sleep(0.01)

    return collected_frames, bytes(raw_chunks)


class XbusStreamParser:
    """Parser incremental para flujos binarios Xbus (preámbulo 0xFA + verificación de checksum)."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[tuple[int, int, bytes]]:
        self._buf.extend(chunk)
        frames: list[tuple[int, int, bytes]] = []
        while len(self._buf) >= 5:
            if self._buf[0] != XBUS_PREAMBLE:
                del self._buf[0]
                continue
            bid = self._buf[1]
            mid = self._buf[2]
            len_byte = self._buf[3]
            if len_byte == 0xFF:
                if len(self._buf) < 7:
                    break
                data_len = struct.unpack(">H", bytes(self._buf[4:6]))[0]
                hdr_len = 6
            else:
                data_len = len_byte
                hdr_len = 4
            total_len = hdr_len + data_len + 1
            if total_len > 4096:
                del self._buf[0]
                continue
            if len(self._buf) < total_len:
                break
            raw_frame = bytes(self._buf[:total_len])
            if (sum(raw_frame[1:]) & 0xFF) != 0:
                del self._buf[0]
                continue
            del self._buf[:total_len]
            payload = raw_frame[hdr_len : hdr_len + data_len]
            frames.append((bid, mid, payload))
        return frames


def parse_mtdata2_payload(
    bid: int,
    payload: bytes,
    bus_id_map: dict[int, str],
    default_hz: float = 120.0,
    now_ms: float | None = None,
) -> SensorPacket | None:
    """
    Decodifica un paquete MTData2 (MID = 0x36) en bloques TLV (XDI uint16, Len uint8, Valor)
    y normaliza ejes desde ENU Z-up (Xsens) hacia Estudio Y-up (+Y arriba, +Z frente).
    """
    ts = now_ms if now_ms is not None else time.monotonic() * 1000.0
    pos = 0
    n = len(payload)

    q_out: list[float] | None = None
    free_accel = [0.0, 0.0, 0.0]
    accel_raw: list[float] | None = None
    gyro = [0.0, 0.0, 0.0]
    mag = [0.0, 0.0, 1.0]
    sensor_id = bus_id_map.get(bid)
    battery = 85.0
    rssi = -52

    while pos + 3 <= n:
        xdi = struct.unpack_from(">H", payload, pos)[0]
        dlen = payload[pos + 2]
        pos += 3
        if pos + dlen > n:
            break
        val = payload[pos : pos + dlen]
        pos += dlen

        xdi_group = xdi & 0xFFF0
        # Cuaternión (XDI 0x2010..0x2013)
        if xdi_group == 0x2010 and dlen >= 16:
            qw, qx, qy, qz = struct.unpack_from(">ffff", val, 0)
            q_out = q_normalize([qw, qx, qz, -qy]).tolist()
        # Aceleración libre (XDI 0x4030)
        elif xdi_group == 0x4030 and dlen >= 12:
            ax, ay, az = struct.unpack_from(">fff", val, 0)
            free_accel = [float(ax), float(az), -float(ay)]
        # Aceleración calibrada respaldo (XDI 0x4020)
        elif xdi_group == 0x4020 and dlen >= 12:
            ax, ay, az = struct.unpack_from(">fff", val, 0)
            accel_raw = [float(ax), float(az), -float(ay)]
        # Velocidad angular (XDI 0x8020)
        elif xdi_group == 0x8020 and dlen >= 12:
            gx, gy, gz = struct.unpack_from(">fff", val, 0)
            gyro = [float(gx), float(gz), -float(gy)]
        # Campo magnético (XDI 0xC020)
        elif xdi_group == 0xC020 and dlen >= 12:
            mx, my, mz = struct.unpack_from(">fff", val, 0)
            mag = [float(mx), float(mz), -float(my)]
        # Identificador de dispositivo MTw (XDI 0x0010, 0x1070 o 0xE080)
        elif xdi in (0x0010, 0x1070, 0xE080) and dlen >= 4:
            dev_num = struct.unpack_from(">I", val, 0)[0]
            sensor_id = f"{dev_num:08X}"
            bus_id_map[bid] = sensor_id
        # Estado extendido (batería/RSSI si viene adjunto)
        elif xdi == 0xE030 and dlen >= 1:
            battery = float(val[0])
        elif xdi == 0xE040 and dlen >= 1:
            rssi = int(struct.unpack_from(">b", val, 0)[0])

    if q_out is None:
        return None

    if free_accel == [0.0, 0.0, 0.0] and accel_raw is not None:
        free_accel = accel_raw

    sid = (sensor_id or f"AWINDA_MTW_{bid:02d}").upper()
    return SensorPacket(
        sensor_id=sid,
        brand="xsens_awinda",
        protocol="xbus_serial",
        segment="UNASSIGNED",
        quaternion=q_out,
        free_accel=free_accel,
        gyro=gyro,
        mag=mag,
        battery=battery,
        rssi=rssi,
        hz=default_hz,
        timestamp_ms=ts,
        raw_only=False,
    )


def _load_xda_paths_config() -> dict[str, Any]:
    for base_dir in (get_settings_dir(), get_config_dir()):
        cfg_file = base_dir / "xda_paths.json"
        if cfg_file.exists():
            try:
                return json.loads(cfg_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
    return {}


def _is_awinda_device_id(did: Any) -> bool:
    if did is None:
        return False
    for attr in (
        "isWirelessMaster",
        "isAwinda2",
        "isAwinda2Station",
        "isAwindaX",
        "isAwinda2Dongle",
        "isAwindaXDongle",
    ):
        fn = getattr(did, attr, None)
        if callable(fn):
            try:
                if fn():
                    return True
            except Exception:
                pass
    return False


def _try_import_xda() -> Any | None:
    """Registra rutas DLL de Movella/Xsens mediante os.add_dll_directory() e importa xsensdeviceapi."""
    cfg = _load_xda_paths_config()
    dll_dirs: list[str] = list(cfg.get("dll_dirs") or [])
    python_dirs: list[str] = list(cfg.get("python_dirs") or [])

    candidate_dirs = [
        Path(r"C:\Program Files\Movella"),
        Path(r"C:\Program Files\Xsens"),
        Path(r"C:\Program Files (x86)\Movella"),
        Path(r"C:\Program Files (x86)\Xsens"),
    ]
    for base in candidate_dirs:
        if not base.exists():
            continue
        for hit in base.rglob("xsensdeviceapi"):
            if hit.is_dir():
                python_dirs.append(str(hit.parent))
                dll_dirs.append(str(hit))
        for dll in base.rglob("xsensdeviceapi64.dll"):
            dll_dirs.append(str(dll.parent))

    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        for ddir in dict.fromkeys(dll_dirs):
            p = Path(ddir)
            if p.exists():
                try:
                    _DLL_DIR_HANDLES.append(os.add_dll_directory(str(p)))
                except OSError:
                    pass

    for pdir in dict.fromkeys(python_dirs):
        if Path(pdir).exists() and pdir not in sys.path:
            sys.path.insert(0, pdir)

    try:
        return importlib.import_module("xsensdeviceapi")
    except ImportError:
        return None


def _normalize_awinda_id(raw_id: Any) -> str:
    txt = str(raw_id or "").strip().upper()
    if txt.startswith("0X"):
        txt = txt[2:]
    if txt and len(txt) < 8 and all(ch in "0123456789ABCDEF" for ch in txt):
        txt = txt.zfill(8)
    return txt


def _resolve_xda_bridge_command() -> list[str] | None:
    """Localiza el worker oficial XDA congelado (.exe) o el puente Python 3.10 (.venv_xda)."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        frozen_candidates = [
            exe_dir / "xda-bridge-worker.exe",
            exe_dir / "xda_bridge" / "xda-bridge-worker.exe",
        ]
        for cand in frozen_candidates:
            if cand.is_file():
                return [str(cand)]
        return None

    worker_script = Path(__file__).resolve().parent / "xda_bridge_worker.py"
    if not worker_script.is_file():
        return None

    cfg = _load_xda_paths_config()
    candidates: list[Path] = []
    cfg_exe = cfg.get("xda_python_exe")
    if cfg_exe:
        candidates.append(Path(str(cfg_exe)))
    candidates.append(Path(__file__).resolve().parent.parent / ".venv_xda" / "Scripts" / "python.exe")

    seen: set[str] = set()
    for cand in candidates:
        key = str(cand).lower()
        if key in seen:
            continue
        seen.add(key)
        if not cand.is_file():
            continue
        site_xda = cand.parent.parent / "Lib" / "site-packages" / "xsensdeviceapi"
        if cfg.get("xda_bridge_ready") or cfg.get("sdk_installed") or site_xda.is_dir():
            return [str(cand), "-u", str(worker_script)]
    return None


def list_all_com_ports_prioritized() -> list[dict[str, Any]]:
    """
    Escanea TODOS los puertos serie/USB de Windows ordenados por prioridad:
      1: Xsens/Movella VID 0x2639 o descripción 'Xsens'/'Awinda'/'Movella'
      2: FTDI VID 0x0403 o descripción 'FTDI'/'USB Serial Port'
      3: Cualquier otro puerto COM del sistema
    """
    ports_info: list[dict[str, Any]] = []
    for p in serial.tools.list_ports.comports():
        hwid_up = (p.hwid or "").upper()
        desc_up = (p.description or "").upper()
        mfg_up = (p.manufacturer or "").upper()

        is_xsens = (
            p.vid == XSENS_USB_VID
            or "VID_2639" in hwid_up
            or "2639:" in hwid_up
            or "XSENS" in desc_up
            or "AWINDA" in desc_up
            or "MOVELLA" in desc_up
            or "XSENS" in mfg_up
        )
        is_ftdi = (
            p.vid == FTDI_USB_VID
            or "VID_0403" in hwid_up
            or "FTDI" in desc_up
            or "FTDI" in mfg_up
            or "USB SERIAL PORT" in desc_up
        )
        priority = 1 if is_xsens else (2 if is_ftdi else 3)
        ports_info.append(
            {
                "port": p.device,
                "description": p.description or "Puerto Serie",
                "manufacturer": p.manufacturer or "",
                "hwid": p.hwid or "",
                "vid": hex(p.vid) if p.vid else None,
                "pid": hex(p.pid) if p.pid else None,
                "priority": priority,
                "is_xsens": is_xsens,
                "is_ftdi_candidate": is_ftdi,
            }
        )
    ports_info.sort(key=lambda item: (item["priority"], item["port"]))
    return ports_info


def detect_usb_awinda_ports() -> list[dict[str, Any]]:
    """Devuelve puertos COM prioritarios pertenecientes a Xsens Awinda (P1) o adaptadores FTDI/USB Serial (P2)."""
    return [p for p in list_all_com_ports_prioritized() if p["priority"] <= 2]


def check_windows_pnp_driver_status() -> dict[str, Any]:
    """
    Consulta dispositivos Plug & Play presentes en Windows para detectar si un dongle físico
    Xsens/FTDI está conectado por USB pero carece de controlador o puerto COM operativo.
    """
    if sys.platform != "win32":
        return {"present": False, "driver_missing": False, "devices": []}

    ps_script = (
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $_.InstanceId -match '2639|0403' -or $_.FriendlyName -match 'Xsens|Movella|Awinda|FTDI' } | "
        "Select-Object Status, Class, FriendlyName, InstanceId, Problem | ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3.5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = proc.stdout.strip()
        if not raw:
            return {"present": False, "driver_missing": False, "devices": []}
        parsed = json.loads(raw)
        devices = parsed if isinstance(parsed, list) else [parsed]
        xsens_or_usb_devices = [
            d
            for d in devices
            if "2639" in str(d.get("InstanceId", "")).upper()
            or any(
                kw in str(d.get("FriendlyName", "")).upper()
                for kw in ("XSENS", "AWINDA", "MOVELLA")
            )
        ]
        target_list = xsens_or_usb_devices if xsens_or_usb_devices else devices
        has_ok_port = any(
            str(d.get("Status", "")).upper() == "OK" and str(d.get("Class", "")).upper() == "PORTS"
            for d in target_list
        )
        has_broken = any(str(d.get("Status", "")).upper() != "OK" for d in target_list)
        return {
            "present": len(target_list) > 0,
            "driver_missing": len(target_list) > 0 and (has_broken or not has_ok_port),
            "devices": devices,
        }
    except Exception:
        return {"present": False, "driver_missing": False, "devices": []}


class XsensAwindaDriver(BaseIMUDriver):
    """
    Driver Plug & Play de doble motor para estación/antena USB Xsens Awinda:
      - Modo 1: SDK oficial Xsens Device API (xsensdeviceapi) con os.add_dll_directory().
      - Modo 2: Protocolo binario nativo Xbus sobre USB Serial (VID 0x2639) cuando XDA no está instalado.
    Escanea automáticamente cada 2 s y enciende la radio RF al instante al detectar la antena USB.
    """

    driver_name = "xsens_awinda"

    def __init__(self, on_packets: PacketCallback, settings_dir: Path | None = None) -> None:
        super().__init__(on_packets)
        self.settings_dir = settings_dir
        self._xda = _try_import_xda()
        self._xda_bridge_cmd: list[str] | None = _resolve_xda_bridge_command()
        self._xda_bridge_python: Path | None = Path(self._xda_bridge_cmd[0]) if self._xda_bridge_cmd else None
        self.sdk_available: bool = (self._xda is not None) or (self._xda_bridge_cmd is not None)
        self.locked_channel: int | None = self._load_locked_channel()
        self.channel: int = self.locked_channel if self.locked_channel is not None else self._load_saved_channel()
        self.tdma_rate_hz: int = DEFAULT_AWINDA_TDMA_HZ
        self.target_hz = DEFAULT_AWINDA_TDMA_HZ
        self.sweeping_channels: bool = False
        default_cfg_dir = get_settings_dir() if getattr(sys, "frozen", False) else get_config_dir()
        self.radio_config_path: Path = (self.settings_dir or default_cfg_dir) / "awinda_radio.json"
        self.station_id: str | None = None
        self.port: str | None = None
        self.baudrate: int = 0
        self.stopbits_label: str = ""
        self.active_radio_channel: int | None = None
        self.config_ack: bool = False
        self.radio_ack: bool = False
        self.measurement_ack: bool = False
        self.connection_mode: str = "none"  # "none" | "xda" | "xbus_serial"
        self.antenna_state: str = "disconnected"  # "disconnected" | "driver_missing" | "no_response" | "connecting" | "radio_on" | "streaming"
        self.driver_missing: bool = False
        self.detected_mtws: list[str] = []
        self.dropped_packets: int = 0
        self.all_com_ports: list[dict[str, Any]] = list_all_com_ports_prioritized()
        self.last_handshake_log: list[str] = []

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._control: Any = None
        self._master_device: Any = None
        self._serial: serial.Serial | None = None
        self._bus_id_map: dict[int, str] = {}
        self._seen_mtws: set[str] = set()
        self._winning_channel_saved: bool = False
        self._last_packet_mono: float = 0.0

        self._auto_monitor_task: asyncio.Task[None] | None = None
        self._auto_monitor_running: bool = False
        self._io_lock: asyncio.Lock | None = None
        self._io_lock_loop: asyncio.AbstractEventLoop | None = None
        self._bridge_proc: subprocess.Popen[str] | None = None
        self._bridge_stderr_thread: threading.Thread | None = None
        self._bridge_ready_event = threading.Event()
        self._bridge_start_ok: bool = False
        self._on_connected_cb: Callable[[], None] | None = None
        self._last_pnp_check_ts: float = 0.0
        self._cached_pnp: dict[str, Any] = {"present": False, "driver_missing": False, "devices": []}

        self.status_message_es = "Esperando antena USB Xsens Awinda..."

    def _get_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._io_lock is None or self._io_lock_loop is not loop:
            self._io_lock = asyncio.Lock()
            self._io_lock_loop = loop
        return self._io_lock

    def _radio_cfg_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        if self.settings_dir:
            candidates.append(self.settings_dir / "awinda_radio.json")
            candidates.append(self.settings_dir / "awinda_settings.json")
        candidates.append(get_settings_dir() / "awinda_radio.json")
        candidates.append(get_config_dir() / "awinda_radio.json")
        return candidates

    def _load_locked_channel(self) -> int | None:
        for cfg in self._radio_cfg_candidates():
            if cfg.exists():
                try:
                    data = json.loads(cfg.read_text(encoding="utf-8"))
                    raw = data.get("locked_channel")
                    if raw is not None:
                        ch = int(raw)
                        if 11 <= ch <= 25:
                            return ch
                except Exception:
                    pass
        return None

    def _load_saved_channel(self) -> int:
        for cfg in self._radio_cfg_candidates():
            if cfg.exists():
                try:
                    data = json.loads(cfg.read_text(encoding="utf-8"))
                    raw = data.get("locked_channel") if data.get("locked_channel") is not None else data.get("channel", 11)
                    return max(11, min(25, int(raw)))
                except Exception:
                    pass
        return 11

    def save_radio_channel_config(
        self,
        channel: int,
        target_path: Path | None = None,
        lock_channel: bool = True,
    ) -> Path:
        """Persiste el canal RF ganador (bloqueado) y configuración TDMA en directorio escribible."""
        ch = max(11, min(25, int(channel)))
        if lock_channel:
            self.locked_channel = ch
        payload = {
            "channel": ch,
            "locked_channel": ch if lock_channel else self.locked_channel,
            "rate_hz": int(self.tdma_rate_hz),
            "station_id": self.station_id,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        writable_dir = self.settings_dir or get_settings_dir()
        written_path = target_path or (writable_dir / "awinda_radio.json")

        if target_path is not None:
            targets = [target_path]
        else:
            targets = [writable_dir / "awinda_radio.json"]
            if not getattr(sys, "frozen", False):
                targets.append(get_config_dir() / "awinda_radio.json")

        for out_file in targets:
            try:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(text, encoding="utf-8")
                written_path = out_file
            except OSError:
                pass

        if self.settings_dir and target_path is None:
            try:
                self.settings_dir.mkdir(parents=True, exist_ok=True)
                (self.settings_dir / "awinda_settings.json").write_text(
                    json.dumps({"channel": ch}, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                pass

        self.radio_config_path = written_path
        return written_path

    def _save_channel(self, channel: int) -> None:
        self.save_radio_channel_config(channel)

    def _get_pnp_cached(self, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if force or (now - self._last_pnp_check_ts) > 6.0:
            self._cached_pnp = check_windows_pnp_driver_status()
            self._last_pnp_check_ts = now
        return self._cached_pnp

    def scan_stations(self) -> list[dict[str, Any]]:
        """Escanea estaciones Xsens Awinda vía XDA oficial y todos los puertos COM/USB de Windows."""
        self.all_com_ports = list_all_com_ports_prioritized()
        found: list[dict[str, Any]] = []
        seen_ports: set[str] = set()

        if self.sdk_available and self._xda is not None:
            try:
                ports = self._xda.XsScanner_scanPorts(0, 100, True, True)
                for p in ports:
                    dev_id = p.deviceId()
                    if _is_awinda_device_id(dev_id):
                        pname = p.portName()
                        seen_ports.add(pname)
                        found.append(
                            {
                                "device_id": dev_id.toXsString(),
                                "port": pname,
                                "baudrate": int(p.baudrate()),
                                "is_station": True,
                                "priority": 0,
                                "mode": "xda",
                            }
                        )
            except Exception:
                pass

        for usb_port in self.all_com_ports:
            if usb_port["priority"] <= 2 and usb_port["port"] not in seen_ports:
                found.append(
                    {
                        "device_id": "AWINDA_USB" if usb_port["is_xsens"] else "FTDI_USB",
                        "port": usb_port["port"],
                        "baudrate": 115200,
                        "is_station": True,
                        "priority": usb_port["priority"],
                        "mode": "xbus_serial",
                        "description": usb_port["description"],
                    }
                )
        return found

    async def scan_all_usb_ports(self, auto_connect: bool = True) -> dict[str, Any]:
        """Escaneo manual o bajo demanda de todos los puertos COM y dispositivos PnP USB."""
        stations = self.scan_stations()
        pnp = self._cached_pnp if stations else await asyncio.to_thread(self._get_pnp_cached, True)
        if auto_connect and not self.running:
            if stations:
                await self.start(channel=self.channel, rate_hz=self.target_hz)
                if self.running and self._on_connected_cb:
                    self._on_connected_cb()
            elif pnp.get("driver_missing"):
                self.driver_missing = True
                self.antenna_state = "driver_missing"
                self.status_message_es = (
                    "Antena Xsens detectada sin controlador USB. "
                    "Instala el driver USB de Movella/Xsens MT Software Suite y reconecta el cable"
                )
        return {
            "all_com_ports": self.all_com_ports,
            "xsens_candidates": stations,
            "pnp_status": pnp,
            "awinda_status": self.get_status(),
        }

    async def start(
        self,
        channel: int | None = None,
        rate_hz: int = DEFAULT_AWINDA_TDMA_HZ,
        port_name: str | None = None,
        force_channel: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        async with self._get_lock():
            if self.running:
                return self.get_status()

            if self.locked_channel is not None and not force_channel:
                self.channel = self.locked_channel
            elif channel is not None:
                self.channel = max(11, min(25, int(channel)))
                self._save_channel(self.channel)
            # Sincronización TDMA para hasta 17 MTw requiere 60 Hz (o 40/50/60 según solicitud)
            req_hz = int(rate_hz)
            self.tdma_rate_hz = 60 if req_hz <= 60 or req_hz >= 110 else req_hz
            self.target_hz = self.tdma_rate_hz
            self.sweeping_channels = False
            self._winning_channel_saved = False
            self.antenna_state = "connecting"
            self.driver_missing = False

            # Modo 1a: Puente Oficial XDA (worker congelado o Python 3.10 dedicado)
            if self._xda_bridge_cmd is not None:
                ok_bridge = await self._start_xda_bridge_mode(port_name=port_name)
                if ok_bridge:
                    return self.get_status()

            # Modo 1b: SDK Oficial XDA en proceso (si el intérprete principal lo soporta)
            if self._xda is not None:
                ok_xda = await self._start_xda_mode(port_name=port_name)
                if ok_xda:
                    return self.get_status()

            # Modo 2: Respaldo Nativo Protocolo Binario Xbus Bidireccional sobre USB Serial (VID 0x2639)
            ok_xbus = await self._start_xbus_serial_mode(port_name=port_name)
            if ok_xbus:
                return self.get_status()

            # Si ya hubo puertos COM candidatos pero ninguno respondió ACK real, preservar estado honesto "no_response"
            if self.antenna_state == "no_response":
                return self.get_status()

            # Diagnóstico PnP Windows si el hardware está físicamente presente pero sin driver USB
            pnp = await asyncio.to_thread(self._get_pnp_cached, False)
            if pnp.get("driver_missing"):
                self.driver_missing = True
                self.antenna_state = "driver_missing"
                self.status_message_es = (
                    "Antena Xsens detectada sin controlador USB. "
                    "Instala el driver USB de Movella/Xsens MT Software Suite y reconecta el cable"
                )
            else:
                self.driver_missing = False
                self.antenna_state = "disconnected"
                self.status_message_es = "Conecta tu antena Xsens Awinda por USB para encender el enlace inalámbrico."

            return self.get_status()

    def _shutdown_bridge_proc(self, proc: subprocess.Popen[str] | None) -> None:
        """Envía señal STOP por stdin al puente XDA para liberar radio/COM6 limpiamente."""
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin is not None:
                try:
                    proc.stdin.write("STOP\n")
                    proc.stdin.flush()
                except Exception:
                    pass
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=3.5)
                except subprocess.TimeoutExpired:
                    pass
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=1.0)
                    except Exception:
                        pass
        finally:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass

    def _xda_bridge_stderr_loop(self, proc: subprocess.Popen[str]) -> None:
        if proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                txt = line.strip()
                if txt:
                    self.last_handshake_log = (self.last_handshake_log + [f"XDA stderr: {txt}"])[-40:]
        except Exception:
            pass

    def _xda_bridge_read_loop(self, proc: subprocess.Popen[str]) -> None:
        """Lee mensajes JSONL desde xda_bridge_worker.py (estado, barrido y paquetes MTw)."""
        if proc.stdout is None:
            self._bridge_ready_event.set()
            return
        try:
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                mtype = msg.get("type")
                if mtype == "station_ready":
                    self.station_id = _normalize_awinda_id(msg.get("station_id") or self.station_id or "") or self.station_id
                    self.port = str(msg.get("port") or self.port or "") or self.port
                    self.baudrate = int(msg.get("baudrate") or 2000000)
                    self.stopbits_label = "8N2 (XDA)"
                    self.config_ack = bool(msg.get("config_ack", True))
                    if msg.get("channel") is not None:
                        self.channel = max(11, min(25, int(msg["channel"])))
                    self.last_handshake_log = (
                        self.last_handshake_log + [f"XDA ready: {self.port} id={self.station_id} rate={msg.get('rate_hz')}"]
                    )[-40:]

                elif mtype == "status":
                    if msg.get("station_id"):
                        self.station_id = _normalize_awinda_id(msg["station_id"])
                    if msg.get("port"):
                        self.port = str(msg["port"])
                    if msg.get("baudrate"):
                        self.baudrate = int(msg["baudrate"])
                    self.stopbits_label = "8N2 (XDA)"
                    if msg.get("channel") is not None:
                        self.channel = max(11, min(25, int(msg["channel"])))
                    if msg.get("active_radio_channel") is not None:
                        self.active_radio_channel = int(msg["active_radio_channel"])
                    if msg.get("locked_channel") is not None:
                        lch = max(11, min(25, int(msg["locked_channel"])))
                        if self.locked_channel != lch:
                            self.locked_channel = lch
                            self.save_radio_channel_config(lch, lock_channel=True)
                    self.config_ack = True
                    self.radio_ack = bool(msg.get("radio_ack", self.radio_ack))
                    self.measurement_ack = bool(msg.get("measurement_ack", self.measurement_ack))
                    self.sweeping_channels = bool(msg.get("sweeping_channels", self.sweeping_channels))
                    if "detected_mtws" in msg and isinstance(msg["detected_mtws"], list):
                        live_set = {
                            norm_sid
                            for raw_sid in msg["detected_mtws"]
                            if (norm_sid := _normalize_awinda_id(raw_sid))
                        }
                        self._seen_mtws = live_set
                        self.detected_mtws = sorted(live_set)
                    self.antenna_state = str(msg.get("antenna_state") or "radio_on")
                    self.connection_mode = "xda"
                    self.driver_missing = False
                    self.status_message_es = str(
                        msg.get("message_es")
                        or f"Motor Oficial XDA Activo · Canal RF {self.channel} · {len(self.detected_mtws)}/17 Sensores"
                    )
                    self.last_handshake_log = (
                        self.last_handshake_log
                        + [
                            f"XDA status: state={self.antenna_state} ch={self.channel} "
                            f"mtw={len(self.detected_mtws)} meas={self.measurement_ack}"
                        ]
                    )[-40:]
                    if (self.radio_ack or self.antenna_state == "error") and not self._bridge_ready_event.is_set():
                        self._bridge_start_ok = True
                        self._bridge_ready_event.set()

                elif mtype == "debug":
                    where = str(msg.get("where") or msg.get("key") or "worker")
                    err_txt = str(msg.get("error") or msg.get("message_es") or "")
                    self.last_handshake_log = (
                        self.last_handshake_log + [f"XDA debug ({where}): {err_txt}"]
                    )[-40:]

                elif mtype == "packets":
                    now_ms = time.monotonic() * 1000.0
                    batch: list[SensorPacket] = []
                    for item in msg.get("packets") or []:
                        sid = _normalize_awinda_id(item.get("sensor_id"))
                        if not sid:
                            continue
                        self._seen_mtws.add(sid)
                        q_raw = item.get("quaternion") or [1.0, 0.0, 0.0, 0.0]
                        batch.append(
                            SensorPacket(
                                sensor_id=sid,
                                brand="xsens_awinda",
                                protocol="xda",
                                segment="UNASSIGNED",
                                quaternion=q_normalize(q_raw).tolist(),
                                free_accel=[float(v) for v in (item.get("free_accel") or [0.0, 0.0, 0.0])],
                                gyro=[float(v) for v in (item.get("gyro") or [0.0, 0.0, 0.0])],
                                mag=[float(v) for v in (item.get("mag") or [0.0, 0.0, 1.0])],
                                battery=float(item.get("battery", 85.0)),
                                rssi=int(item.get("rssi", -52)),
                                hz=float(item.get("hz") or self.tdma_rate_hz),
                                timestamp_ms=float(item.get("timestamp_ms") or now_ms),
                                raw_only=False,
                            )
                        )
                    self.detected_mtws = sorted(self._seen_mtws)
                    if batch:
                        self.connection_mode = "xda"
                        self.antenna_state = "streaming"
                        self._last_packet_mono = time.monotonic()
                        self.status_message_es = (
                            f"Motor Oficial XDA Activo · Canal RF {self.channel} · {len(self.detected_mtws)}/17 Sensores"
                        )
                        self.emit(batch)

                elif mtype == "error":
                    err_msg = str(msg.get("message_es") or "Error desconocido en puente XDA.")
                    self.last_handshake_log = (self.last_handshake_log + [f"XDA error: {err_msg}"])[-40:]
                    if not self._bridge_ready_event.is_set():
                        self._bridge_start_ok = False
                        self._bridge_ready_event.set()

                elif mtype == "stopped":
                    self.last_handshake_log = (self.last_handshake_log + ["XDA worker detenido limpiamente."])[-40:]
                    break
        except Exception as exc:
            self.last_handshake_log = (self.last_handshake_log + [f"XDA bridge read error: {exc}"])[-40:]
        finally:
            if not self._bridge_ready_event.is_set():
                self._bridge_ready_event.set()
            if not self._stop_event.is_set() and self.running and self.connection_mode == "xda":
                self.running = False
                self.connection_mode = "none"
                self.antenna_state = "disconnected"
                self.sweeping_channels = False
                self.status_message_es = "Antena USB Awinda desconectada."

    async def _start_xda_bridge_mode(self, port_name: str | None = None) -> bool:
        base_cmd = self._xda_bridge_cmd or _resolve_xda_bridge_command()
        if not base_cmd:
            return False
        self._xda_bridge_cmd = base_cmd

        self.all_com_ports = list_all_com_ports_prioritized()
        if not port_name and not [p for p in self.all_com_ports if p["priority"] <= 2]:
            return False

        self._stop_event.clear()
        self._bridge_ready_event.clear()
        self._bridge_start_ok = False
        self.config_ack = False
        self.radio_ack = False
        self.measurement_ack = False
        self.last_handshake_log = []
        self._seen_mtws.clear()

        writable_settings = self.settings_dir or get_settings_dir()
        eff_channel = self.locked_channel if self.locked_channel is not None else self.channel
        cmd = [
            *base_cmd,
            "--channel",
            str(eff_channel),
            "--rate-hz",
            str(self.tdma_rate_hz),
            "--config-dir",
            str(get_config_dir()),
            "--settings-dir",
            str(writable_settings),
        ]
        if self.locked_channel is not None:
            cmd.extend(["--locked-channel", str(self.locked_channel)])
        if port_name:
            cmd.extend(["--port", port_name])

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            self.last_handshake_log = [f"Error lanzando puente XDA: {exc}"]
            return False

        self._bridge_proc = proc
        self._bridge_stderr_thread = threading.Thread(
            target=self._xda_bridge_stderr_loop, args=(proc,), name="XsensBridgeStderr", daemon=True
        )
        self._bridge_stderr_thread.start()
        self._thread = threading.Thread(
            target=self._xda_bridge_read_loop, args=(proc,), name="XsensBridgeStdout", daemon=True
        )
        self._thread.start()

        wait_timeout = 12.0 if getattr(sys, "frozen", False) else 6.0
        ready = await asyncio.to_thread(self._bridge_ready_event.wait, wait_timeout)
        if ready and self._bridge_start_ok and not self._stop_event.is_set() and proc.poll() is None:
            self.connection_mode = "xda"
            self.running = True
            self.driver_missing = False
            if self.antenna_state in ("disconnected", "connecting", "no_response"):
                self.antenna_state = "radio_on"
            return True

        await asyncio.to_thread(self._shutdown_bridge_proc, proc)
        self._bridge_proc = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        if self._bridge_stderr_thread and self._bridge_stderr_thread.is_alive():
            self._bridge_stderr_thread.join(timeout=0.5)
        self._bridge_stderr_thread = None
        self.running = False
        self.connection_mode = "none"
        return False

    async def _start_xda_mode(self, port_name: str | None = None) -> bool:
        xda = self._xda
        try:
            ports = xda.XsScanner_scanPorts(0, 100, True, True)
            target_port = None
            for p in ports:
                if port_name and p.portName() != port_name:
                    continue
                if _is_awinda_device_id(p.deviceId()):
                    target_port = p
                    break

            if target_port is None:
                return False

            control = xda.XsControl_construct()
            if not control.openPort(target_port):
                control.destruct()
                return False

            device = control.device(target_port.deviceId())
            if device is None:
                control.close()
                control.destruct()
                return False

            self.station_id = target_port.deviceId().toXsString()
            self.port = target_port.portName()
            self.config_ack = bool(device.gotoConfig())
            device.setUpdateRate(self.tdma_rate_hz)

            # Barrido automático (o canal bloqueado fijo) hasta detectar sensores hijos
            winning_ch = self.channel
            children: list[Any] = []
            cand_channels = [self.locked_channel] if self.locked_channel is not None else build_channel_sweep_order(self.channel)
            self.sweeping_channels = self.locked_channel is None
            for cand_ch in cand_channels:
                try:
                    if hasattr(device, "disableRadio"):
                        device.disableRadio()
                except Exception:
                    pass
                if device.enableRadio(cand_ch):
                    self.radio_ack = True
                    self.active_radio_channel = cand_ch
                    deadline = time.monotonic() + CHANNEL_DWELL_SECONDS
                    while time.monotonic() < deadline:
                        await asyncio.sleep(0.25)
                        children = list(device.children())
                        c_count = int(device.childCount()) if hasattr(device, "childCount") else len(children)
                        if c_count > 0 or len(children) > 0:
                            winning_ch = cand_ch
                            self.channel = cand_ch
                            self._save_channel(cand_ch)
                            self._winning_channel_saved = True
                            break
                    if self._winning_channel_saved:
                        break
            if not self._winning_channel_saved and self.active_radio_channel != self.channel:
                try:
                    device.disableRadio()
                except Exception:
                    pass
                device.enableRadio(self.channel)
                self.active_radio_channel = self.channel
            self.sweeping_channels = bool(len(children) == 0)
            self.detected_mtws = [c.deviceId().toXsString().upper() for c in children]

            if not device.gotoMeasurement():
                device.disableRadio()
                control.close()
                control.destruct()
                return False

            self.measurement_ack = True
            self._control = control
            self._master_device = device
            self.connection_mode = "xda"
            self.antenna_state = "streaming" if self.detected_mtws else "radio_on"
            self._stop_event.clear()
            self.running = True
            self._thread = threading.Thread(target=self._xda_read_loop, name="XsensAwindaXDA", daemon=True)
            self._thread.start()
            self.status_message_es = (
                f"Antena Encendida (XDA · {self.port} · Canal {self.channel} · {self.tdma_rate_hz} Hz · "
                f"{len(self.detected_mtws)} sensores)."
            )
            return True
        except Exception as exc:
            self.status_message_es = f"XDA no pudo abrir la antena ({exc}); intentando protocolo Xbus USB..."
            return False

    async def _start_xbus_serial_mode(self, port_name: str | None = None) -> bool:
        self.all_com_ports = list_all_com_ports_prioritized()
        if port_name:
            candidates = [
                p for p in self.all_com_ports if p["port"] == port_name
            ] or [{"port": port_name, "priority": 1, "is_xsens": True, "description": port_name}]
        else:
            candidates = [p for p in self.all_com_ports if p["priority"] <= 2]

        self.config_ack = False
        self.radio_ack = False
        self.measurement_ack = False
        self.stopbits_label = ""
        self.active_radio_channel = None
        self.last_handshake_log = []

        if not candidates:
            return False

        opened_ser: serial.Serial | None = None
        selected_port: str | None = None
        selected_baud: int = 0
        selected_stopbits: str = ""
        active_parser = XbusStreamParser()

        # Paso 1: Autonegociación estricta de velocidad y framing (8N2 prioritario para Awinda2, respaldo 8N1) con ACK real
        for cand in candidates:
            cport = cand["port"]
            port_locked = False
            for baud in (921600, 2000000, 115200, 460800):
                for sb_val, sb_label in ((serial.STOPBITS_TWO, "8N2"), (serial.STOPBITS_ONE, "8N1")):
                    ser: serial.Serial | None = None
                    parser = XbusStreamParser()
                    try:
                        ser = serial.Serial(
                            cport,
                            baudrate=baud,
                            bytesize=serial.EIGHTBITS,
                            parity=serial.PARITY_NONE,
                            stopbits=sb_val,
                            timeout=0.2,
                            write_timeout=0.2,
                            rtscts=False,
                            dsrdtr=False,
                            xonxoff=False,
                        )
                        ser.dtr = True
                        ser.rts = True
                        await asyncio.sleep(0.05)
                        ser.reset_input_buffer()
                        ser.reset_output_buffer()

                        # Enviar WakeUp (FA FF 3E 00 C3) + GotoConfig (FA FF 30 00 D1)
                        ser.write(cmd_wakeup())
                        await asyncio.sleep(0.03)
                        ser.write(cmd_goto_config())

                        frames, raw_rx = await asyncio.to_thread(
                            read_xbus_frames_sync,
                            ser,
                            parser,
                            0.35,
                            {MID_GOTO_CONFIG_ACK, MID_WAKEUP_ACK, MID_WAKEUP, MID_DEVICE_ID},
                        )
                        self.last_handshake_log.append(
                            f"{cport}@{baud} {sb_label}: rx={len(raw_rx)}B mids={[hex(m) for _, m, _ in frames]}"
                        )

                        # Si el dongle despertó (WakeUp 0x3E) o estaba transmitiendo MTData2 (0x36), confirmar GotoConfigAck (0x31)
                        if any(mid in (MID_WAKEUP, MID_WAKEUP_ACK, MID_MTDATA2) for _b, mid, _pl in frames) and not any(
                            mid == MID_GOTO_CONFIG_ACK for _b, mid, _pl in frames
                        ):
                            if any(mid == MID_WAKEUP for _b, mid, _pl in frames):
                                ser.write(cmd_wakeup_ack())
                                await asyncio.sleep(0.02)
                            ser.write(cmd_goto_config())
                            extra_frames, extra_rx = await asyncio.to_thread(
                                read_xbus_frames_sync,
                                ser,
                                parser,
                                0.25,
                                {MID_GOTO_CONFIG_ACK},
                            )
                            frames.extend(extra_frames)
                            if extra_rx:
                                self.last_handshake_log.append(
                                    f"{cport}@{baud} {sb_label} retry: rx={len(extra_rx)}B mids={[hex(m) for _, m, _ in extra_frames]}"
                                )

                        if any(mid in (MID_GOTO_CONFIG_ACK, MID_WAKEUP_ACK, MID_DEVICE_ID) for _b, mid, _pl in frames):
                            opened_ser = ser
                            selected_port = cport
                            selected_baud = baud
                            selected_stopbits = sb_label
                            active_parser = parser
                            self.config_ack = True
                            break

                        ser.close()
                        await asyncio.sleep(0.03)
                    except serial.SerialException as exc:
                        self.last_handshake_log.append(f"{cport}@{baud} {sb_label}: error={exc}")
                        if ser is not None and ser.is_open:
                            try:
                                ser.close()
                            except Exception:
                                pass
                        msg_err = str(exc)
                        if "PermissionError" in msg_err or "Acceso denegado" in msg_err or "Access is denied" in msg_err:
                            port_locked = True
                            break
                        continue

                if opened_ser is not None or port_locked:
                    break

            if opened_ser is not None:
                break

        if opened_ser is None or selected_port is None or not self.config_ack:
            self.running = False
            self.connection_mode = "none"
            self.port = candidates[0]["port"]
            self.baudrate = 0
            self.stopbits_label = ""
            self.active_radio_channel = None
            self.antenna_state = "no_response"
            self.status_message_es = (
                "Puerto COM detectado sin respuesta de la antena. Desconecta y vuelve a conectar el USB"
            )
            return False

        # Paso 2: Secuencia completa de encendido físico de radio RF con confirmación ACK real
        try:
            self._serial = opened_ser
            self.port = selected_port
            self.baudrate = selected_baud
            self.stopbits_label = selected_stopbits
            self._bus_id_map.clear()
            self._seen_mtws.clear()

            # 2.0 Verificar versión de firmware (0x12 -> 0x13); recuperar si el dongle quedó en bootloader (0xFF)
            opened_ser.reset_input_buffer()
            opened_ser.write(cmd_req_fw_rev())
            fw_frames, fw_raw = await asyncio.to_thread(
                read_xbus_frames_sync, opened_ser, active_parser, 0.25, {MID_FW_REV, MID_ERROR}
            )
            self.last_handshake_log.append(
                f"ReqFWRev: rx={fw_raw.hex()} mids={[hex(m) for _, m, _ in fw_frames]}"
            )
            if any(mid == MID_FW_REV and len(pl) >= 1 and pl[0] == 0xFF for _b, mid, pl in fw_frames):
                opened_ser.write(cmd_bootloader_finished())
                await asyncio.sleep(0.9)
                opened_ser.reset_input_buffer()
                opened_ser.write(cmd_goto_config())
                bl_cfg, _ = await asyncio.to_thread(
                    read_xbus_frames_sync, opened_ser, active_parser, 0.30, {MID_GOTO_CONFIG_ACK}
                )
                self.last_handshake_log.append(
                    f"BootloaderExit->GotoConfig: mids={[hex(m) for _, m, _ in bl_cfg]}"
                )

            # 2.1 ReqDID (FA FF 00 00 01) -> leer DeviceID (0x01)
            opened_ser.reset_input_buffer()
            opened_ser.write(cmd_req_did())
            did_frames, _ = await asyncio.to_thread(
                read_xbus_frames_sync, opened_ser, active_parser, 0.25, {MID_DEVICE_ID}
            )
            for _bid, mid, pl in did_frames:
                if mid == MID_DEVICE_ID and len(pl) >= 4:
                    self.station_id = f"{struct.unpack_from('>I', pl, 0)[0]:08X}"

            # 2.2 Secuencia completa TDMA 60 Hz + EnableMaster/EnableRadio + GotoOperational + ReqRadioChannel + GotoMeasurement
            radio_ok, meas_ok, verified_ch, cycle_logs = await asyncio.to_thread(
                activate_awinda_tdma_channel_sync,
                opened_ser,
                active_parser,
                self.channel,
                self.tdma_rate_hz,
            )
            self.last_handshake_log.extend(cycle_logs)
            self.radio_ack = radio_ok
            self.active_radio_channel = verified_ch
            self.measurement_ack = meas_ok

            # 2.3 Cero falsos positivos: nunca marcar encendido si la radio no confirmó ACK real
            if not self.radio_ack:
                opened_ser.close()
                self._serial = None
                self.running = False
                self.connection_mode = "none"
                self.active_radio_channel = None
                self.antenna_state = "no_response"
                self.status_message_es = (
                    f"Antena respondió en {selected_port} ({selected_baud} bps {selected_stopbits}) "
                    "pero no confirmó el encendido de radio RF. Desconecta y vuelve a conectar el USB"
                )
                return False

            # 2.4 Activar lector en vivo y barrido RF automático de canales 11..25 si aún no hay MTw vinculados
            self.connection_mode = "xbus_serial"
            self.antenna_state = "radio_on"
            self.driver_missing = False
            self.sweeping_channels = True
            self._stop_event.clear()
            self.running = True
            self._thread = threading.Thread(target=self._xbus_serial_read_loop, name="XsensAwindaXbus", daemon=True)
            self._thread.start()
            self.status_message_es = (
                f"Antena Encendida en {self.port} ({self.baudrate} bps {self.stopbits_label} · "
                f"ID {self.station_id or 'Awinda'} · Canal RF {self.channel} · TDMA {self.tdma_rate_hz} Hz). "
                "Buscando sensores MTw del traje..."
            )
            return True
        except Exception as exc:
            try:
                opened_ser.close()
            except Exception:
                pass
            self._serial = None
            self.running = False
            self.connection_mode = "none"
            self.antenna_state = "no_response"
            self.status_message_es = f"Error encendiendo radio Awinda en {selected_port}: {exc}"
            return False

    def _xda_read_loop(self) -> None:
        """Hilo lector para paquetes XDA oficiales normalizados a Estudio Y-up."""
        last_pkt_ts: dict[str, float] = {}
        while not self._stop_event.is_set() and self._master_device is not None:
            try:
                children = self._master_device.children()
                self.detected_mtws = [c.deviceId().toXsString().upper() for c in children]
                batch: list[SensorPacket] = []
                now_ms = time.monotonic() * 1000.0
                for child in children:
                    if not child.isOperational():
                        continue
                    pkt = child.peekDataPacket()
                    if pkt is None or pkt.empty():
                        continue
                    sid = child.deviceId().toXsString().upper()
                    if pkt.containsOrientation():
                        xq = pkt.orientationQuaternion()
                        q_raw = q_normalize([xq[0], xq[1], xq[3], -xq[2]])
                    else:
                        q_raw = [1.0, 0.0, 0.0, 0.0]

                    if pkt.containsFreeAcceleration():
                        fa = pkt.freeAcceleration()
                        free_accel = [float(fa[0]), float(fa[2]), -float(fa[1])]
                    else:
                        free_accel = [0.0, 0.0, 0.0]

                    if pkt.containsCalibratedGyroscopeData():
                        gy = pkt.calibratedGyroscopeData()
                        gyro = [float(gy[0]), float(gy[2]), -float(gy[1])]
                    else:
                        gyro = [0.0, 0.0, 0.0]

                    if pkt.containsCalibratedMagneticField():
                        mg = pkt.calibratedMagneticField()
                        mag = [float(mg[0]), float(mg[2]), -float(mg[1])]
                    else:
                        mag = [0.0, 0.0, 1.0]

                    battery = float(child.batteryLevel()) if hasattr(child, "batteryLevel") else 85.0
                    rssi = int(pkt.rssi()) if hasattr(pkt, "rssi") else -52
                    prev = last_pkt_ts.get(sid)
                    hz = 1000.0 / max(1.0, now_ms - prev) if prev else float(self.target_hz)
                    last_pkt_ts[sid] = now_ms

                    batch.append(
                        SensorPacket(
                            sensor_id=sid,
                            brand="xsens_awinda",
                            protocol="xda",
                            segment="UNASSIGNED",
                            quaternion=[float(v) for v in q_raw],
                            free_accel=free_accel,
                            gyro=gyro,
                            mag=mag,
                            battery=battery,
                            rssi=rssi,
                            hz=hz,
                            timestamp_ms=now_ms,
                            raw_only=False,
                        )
                    )
                if batch:
                    self.antenna_state = "streaming"
                    self._last_packet_mono = time.monotonic()
                    self.emit(batch)
                time.sleep(max(0.002, 0.5 / float(self.target_hz)))
            except Exception:
                self.dropped_packets += 1
                time.sleep(0.01)

    def _handle_control_frames(self, ser: serial.Serial, frames: list[tuple[int, int, bytes]]) -> None:
        """Procesa tramas de control/descubrimiento (DeviceID, MasterIndication 0x46, EnableMaster) sin duplicar lógica."""
        for bid, mid, payload in frames:
            if mid == MID_DEVICE_ID and len(payload) >= 4:
                dev_hex = f"{struct.unpack_from('>I', payload, 0)[0]:08X}"
                if bid == XBUS_BID_MASTER:
                    self.station_id = dev_hex
                else:
                    self._bus_id_map[bid] = dev_hex
                    self._seen_mtws.add(dev_hex)
            elif mid == MID_NOTIFICATION and len(payload) >= 4:
                dev_num = struct.unpack_from(">I", payload, 0)[0]
                if dev_num > 0:
                    dev_hex = f"{dev_num:08X}"
                    self._seen_mtws.add(dev_hex)
                    try:
                        ser.write(cmd_accept_mtw(dev_num))
                    except Exception:
                        pass
            elif mid in (MID_ENABLE_MASTER, MID_ENABLE_MASTER_ACK) and bid != XBUS_BID_MASTER:
                if len(payload) >= 4:
                    dev_hex = f"{struct.unpack_from('>I', payload, 0)[0]:08X}"
                    self._seen_mtws.add(dev_hex)

    def _sync_detected_mtws_state(self, persist_channel: int | None = None) -> None:
        self.detected_mtws = sorted(self._seen_mtws)
        if self._seen_mtws and not self._winning_channel_saved:
            self._winning_channel_saved = True
            self.sweeping_channels = False
            target_ch = persist_channel if persist_channel is not None else self.channel
            self._save_channel(target_ch)
            self.status_message_es = (
                f"Antena Encendida en {self.port} ({self.baudrate} bps · Canal RF {target_ch} fijado · "
                f"{len(self.detected_mtws)} sensores MTw vinculados)."
            )

    def _xbus_serial_read_loop(self) -> None:
        """
        Hilo lector no bloqueante para tramas binarias Xbus (MTData2 0x36, DeviceID, MasterIndication 0x46).
        Si tras 3.5 s en el canal actual no se detectan sensores MTw, ejecuta barrido automático por [11..25]
        esperando 1.2 s en Operational y 2.3 s en Measurement por canal (3.5 s totales) hasta vincular un sensor.
        """
        parser = XbusStreamParser()
        last_pkt_ts: dict[str, float] = {}
        sweep_order = build_channel_sweep_order(self.channel)
        sweep_idx = 0
        last_switch_mono = time.monotonic()
        operational_wait_s = 1.2
        meas_dwell_target = CHANNEL_DWELL_SECONDS

        while not self._stop_event.is_set():
            ser = self._serial
            if ser is None or not ser.is_open:
                break
            try:
                waiting = ser.in_waiting
                if waiting <= 0:
                    # Barrido inteligente solo si el canal NO está bloqueado y no hay MTw vinculados
                    if (
                        self.locked_channel is None
                        and not self._winning_channel_saved
                        and len(self._seen_mtws) == 0
                        and (time.monotonic() - last_switch_mono) >= meas_dwell_target
                        and not self._stop_event.is_set()
                    ):
                        sweep_idx = (sweep_idx + 1) % len(sweep_order)
                        next_ch = sweep_order[sweep_idx]
                        self.sweeping_channels = True
                        radio_ok, meas_ok, ver_ch, _logs = activate_awinda_tdma_channel_sync(
                            ser,
                            parser,
                            next_ch,
                            self.tdma_rate_hz,
                            stop_event=self._stop_event,
                            operational_wait_s=operational_wait_s,
                            on_operational_frames=lambda f: self._handle_control_frames(ser, f),
                        )
                        if self._stop_event.is_set() or not ser.is_open:
                            break
                        if radio_ok:
                            self.channel = next_ch
                            self.active_radio_channel = ver_ch or next_ch
                            self.radio_ack = True
                            self.measurement_ack = meas_ok
                            self._sync_detected_mtws_state(persist_channel=next_ch)
                            if not self._seen_mtws:
                                self.status_message_es = (
                                    f"Antena Encendida en {self.port} ({self.baudrate} bps {self.stopbits_label} · "
                                    f"Canal RF {next_ch} · Barrido TDMA {self.tdma_rate_hz} Hz). Buscando sensores MTw..."
                                )
                        meas_dwell_target = max(0.5, CHANNEL_DWELL_SECONDS - operational_wait_s)
                        last_switch_mono = time.monotonic()
                    else:
                        self._stop_event.wait(0.01)
                    continue

                chunk = ser.read(min(4096, waiting))
                if not chunk:
                    continue
                now_ms = time.monotonic() * 1000.0
                frames = parser.feed(chunk)
                self._handle_control_frames(ser, frames)
                batch: list[SensorPacket] = []
                for bid, mid, payload in frames:
                    if mid == MID_MTDATA2:
                        pkt = parse_mtdata2_payload(
                            bid=bid,
                            payload=payload,
                            bus_id_map=self._bus_id_map,
                            default_hz=float(self.tdma_rate_hz),
                            now_ms=now_ms,
                        )
                        if pkt is not None:
                            prev = last_pkt_ts.get(pkt.sensor_id)
                            if prev and (now_ms - prev) > 0.5:
                                pkt.hz = 1000.0 / (now_ms - prev)
                            last_pkt_ts[pkt.sensor_id] = now_ms
                            self._seen_mtws.add(pkt.sensor_id)
                            batch.append(pkt)

                self._sync_detected_mtws_state()
                if batch:
                    self.antenna_state = "streaming"
                    self._last_packet_mono = time.monotonic()
                    self.emit(batch)
            except (serial.SerialException, OSError, AttributeError):
                if self._stop_event.is_set():
                    break
                # Cable desconectado físicamente: salir para permitir reconexión Plug & Play
                self.running = False
                self.connection_mode = "none"
                self.antenna_state = "disconnected"
                self.sweeping_channels = False
                self.status_message_es = "Antena USB Awinda desconectada."
                break
            except Exception:
                self.dropped_packets += 1
                time.sleep(0.005)

    async def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        self._bridge_ready_event.set()
        async with self._get_lock():
            self._stop_event.set()
            self._bridge_ready_event.set()
            self.running = False

            bridge_proc = self._bridge_proc
            self._bridge_proc = None
            if bridge_proc is not None:
                await asyncio.to_thread(self._shutdown_bridge_proc, bridge_proc)

            # Cerrar puerto serial ANTES de esperar el hilo lector para evitar cualquier deadlock en Windows
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
                        ser.write(cmd_goto_config())
                        time.sleep(0.03)
                        ser.write(cmd_disable_radio())
                        time.sleep(0.02)
                except Exception:
                    pass
                try:
                    if ser.is_open:
                        ser.close()
                except Exception:
                    pass

            thread = self._thread
            self._thread = None
            if thread and thread.is_alive():
                thread.join(timeout=1.5)

            err_thread = self._bridge_stderr_thread
            self._bridge_stderr_thread = None
            if err_thread and err_thread.is_alive():
                err_thread.join(timeout=0.5)

            try:
                if self._master_device is not None:
                    self._master_device.gotoConfig()
                    self._master_device.disableRadio()
                if self._control is not None:
                    self._control.close()
                    self._control.destruct()
            except Exception:
                pass
            self._master_device = None
            self._control = None

            self.connection_mode = "none"
            self.antenna_state = "disconnected"
            self.sweeping_channels = False
            self._winning_channel_saved = False
            self.baudrate = 0
            self.stopbits_label = ""
            self.active_radio_channel = None
            self.config_ack = False
            self.radio_ack = False
            self.measurement_ack = False
            self.port = None
            self.status_message_es = "Estación Xsens Awinda detenida."
            return self.get_status()

    async def reconnect(self, channel: int | None = None, rate_hz: int | None = None) -> dict[str, Any]:
        await self.stop()
        await asyncio.sleep(0.15)
        force = channel is not None
        res = await self.start(
            channel=channel or self.locked_channel or self.channel,
            rate_hz=rate_hz or self.target_hz,
            force_channel=force,
        )
        if self.running and self._on_connected_cb:
            self._on_connected_cb()
        return res

    async def start_auto_monitor(self, on_connected: Callable[[], None] | None = None) -> None:
        """Inicia escaneo automático Plug & Play cada 2 segundos al arrancar la aplicación."""
        self._on_connected_cb = on_connected
        if self._auto_monitor_running and self._auto_monitor_task and not self._auto_monitor_task.done():
            return
        self._auto_monitor_running = True
        self._auto_monitor_task = asyncio.create_task(self._auto_monitor_loop(), name="AwindaAutoPlugPlay")

    async def stop_auto_monitor(self) -> None:
        self._auto_monitor_running = False
        if self._auto_monitor_task and not self._auto_monitor_task.done():
            self._auto_monitor_task.cancel()
            try:
                await self._auto_monitor_task
            except asyncio.CancelledError:
                pass
        self._auto_monitor_task = None

    async def _auto_monitor_loop(self) -> None:
        while self._auto_monitor_running:
            try:
                if self.running:
                    # Comprobar si el puerto COM desapareció o el subproceso puente XDA cerró tras desconectar el USB
                    if self.connection_mode == "xbus_serial":
                        ports_now = {p["port"] for p in detect_usb_awinda_ports()}
                        if self.port and self.port not in ports_now:
                            await self.stop()
                    elif self.connection_mode == "xda" and self._bridge_proc is not None:
                        if self._bridge_proc.poll() is not None:
                            await self.stop()
                    # Actualizar estado radio_on vs streaming si pasaron >2s sin paquetes MTw
                    if self.running and self.antenna_state == "streaming":
                        if (time.monotonic() - self._last_packet_mono) > 2.5:
                            self.antenna_state = "radio_on"
                else:
                    # Intentar auto-detección y encendido inmediato de radio RF
                    stations = self.scan_stations()
                    if stations:
                        await self.start(channel=self.channel, rate_hz=self.target_hz)
                        if self._auto_monitor_running and self.running and self.radio_ack and self._on_connected_cb:
                            self._on_connected_cb()
                    else:
                        pnp = await asyncio.to_thread(self._get_pnp_cached, False)
                        if pnp.get("driver_missing"):
                            self.driver_missing = True
                            self.antenna_state = "driver_missing"
                            self.status_message_es = (
                                "Antena Xsens detectada sin controlador USB. "
                                "Instala el driver USB de Movella/Xsens MT Software Suite y reconecta el cable"
                            )
                        else:
                            self.driver_missing = False
                            self.antenna_state = "disconnected"
                            self.status_message_es = "Conecta tu antena Xsens Awinda por USB o prueba la demostración virtual."
            except Exception:
                pass
            await asyncio.sleep(2.0)

    def get_status(self) -> dict[str, Any]:
        return {
            "driver": self.driver_name,
            "sdk_available": self.sdk_available,
            "running": self.running,
            "connection_mode": self.connection_mode,
            "antenna_state": self.antenna_state,
            "driver_missing": self.driver_missing,
            "auto_monitor_running": self._auto_monitor_running,
            "port": self.port,
            "baudrate": self.baudrate,
            "stopbits_label": self.stopbits_label,
            "active_radio_channel": self.active_radio_channel,
            "config_ack": self.config_ack,
            "radio_ack": self.radio_ack,
            "measurement_ack": self.measurement_ack,
            "channel": self.channel,
            "locked_channel": self.locked_channel,
            "rate_hz": self.target_hz,
            "tdma_rate_hz": self.tdma_rate_hz,
            "sweeping_channels": self.sweeping_channels,
            "radio_config_path": str(self.radio_config_path),
            "station_id": self.station_id,
            "detected_mtws": self.detected_mtws,
            "connected_sensor_count": len(self.detected_mtws),
            "target_sensor_count": 17,
            "dropped_packets": self.dropped_packets,
            "all_com_ports": self.all_com_ports,
            "handshake_log": self.last_handshake_log,
            "message_es": self.status_message_es,
        }
