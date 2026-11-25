from __future__ import annotations

import os
import struct
import sys
import threading
import time
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.hal.xsens_awinda_driver import (
    DEFAULT_AWINDA_TDMA_HZ,
    MID_DEVICE_ID,
    MID_FW_REV,
    MID_GOTO_CONFIG_ACK,
    MID_MTDATA2,
    MID_NOTIFICATION,
    MID_WAKEUP,
    MID_WAKEUP_ACK,
    XbusStreamParser,
    activate_awinda_tdma_channel_sync,
    build_channel_sweep_order,
    cmd_bootloader_finished,
    cmd_disable_radio,
    cmd_goto_config,
    cmd_req_did,
    cmd_req_fw_rev,
    cmd_wakeup,
    cmd_wakeup_ack,
    list_all_com_ports_prioritized,
    read_xbus_frames_sync,
)


def fmt_hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data) if data else "<vacío>"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    watchdog = threading.Timer(8.0, lambda: os._exit(0))
    watchdog.daemon = True
    watchdog.start()

    opened_ser: serial.Serial | None = None
    try:
        ports = list_all_com_ports_prioritized()
        print("=== PUERTOS COM DETECTADOS ===")
        for p in ports:
            print(f"  [P{p['priority']}] {p['port']} | {p['description']} | vid={p['vid']} pid={p['pid']}")

        xsens_ports = [p for p in ports if p["priority"] <= 2]
        if not xsens_ports:
            print("[ERROR] No se encontró ningún puerto Xsens/FTDI conectado.")
            return 1

        target_port = xsens_ports[0]["port"]
        print(f"\n=== PROBANDO ANTENA FÍSICA EN {target_port} ===")

        active_baud = 0
        active_stopbits = "8N2"
        config_ack = False
        active_parser = XbusStreamParser()

        for baud in (921600, 2000000, 115200, 460800):
            port_locked = False
            for sb_val, sb_label in ((serial.STOPBITS_TWO, "8N2"), (serial.STOPBITS_ONE, "8N1")):
                ser: serial.Serial | None = None
                parser = XbusStreamParser()
                try:
                    ser = serial.Serial(
                        target_port,
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
                    time.sleep(0.03)
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()

                    tx_wu = cmd_wakeup()
                    tx_cfg = cmd_goto_config()
                    ser.write(tx_wu)
                    time.sleep(0.02)
                    ser.write(tx_cfg)

                    frames, raw_rx = read_xbus_frames_sync(
                        ser,
                        parser,
                        timeout_s=0.18,
                        target_mids={MID_GOTO_CONFIG_ACK, MID_WAKEUP_ACK, MID_WAKEUP, MID_DEVICE_ID},
                    )
                    print(f"[PROBE {target_port} @ {baud} {sb_label}] RX={fmt_hex(raw_rx)}")

                    if any(m in (MID_WAKEUP, MID_WAKEUP_ACK, MID_MTDATA2) for _, m, _ in frames) and not any(
                        m == MID_GOTO_CONFIG_ACK for _, m, _ in frames
                    ):
                        if any(m == MID_WAKEUP for _, m, _ in frames):
                            ser.write(cmd_wakeup_ack())
                            time.sleep(0.02)
                        ser.write(tx_cfg)
                        extra_f, _ = read_xbus_frames_sync(
                            ser, parser, timeout_s=0.18, target_mids={MID_GOTO_CONFIG_ACK}
                        )
                        frames.extend(extra_f)

                    if any(m in (MID_GOTO_CONFIG_ACK, MID_WAKEUP_ACK, MID_DEVICE_ID) for _, m, _ in frames):
                        opened_ser = ser
                        active_baud = baud
                        active_stopbits = sb_label
                        active_parser = parser
                        config_ack = True
                        break

                    ser.close()
                    time.sleep(0.03)
                except Exception as exc:
                    print(f"[PROBE {target_port} @ {baud} {sb_label}] Error: {exc}")
                    if ser is not None and ser.is_open:
                        try:
                            ser.close()
                        except Exception:
                            pass
                    if "PermissionError" in str(exc) or "Acceso denegado" in str(exc):
                        port_locked = True
                        break
            if opened_ser is not None or port_locked:
                break

        if opened_ser is None or not config_ack:
            print("\n[RESULTADO] Sin respuesta ACK en ninguna velocidad.")
            return 2

        print(f"\n=== VELOCIDAD CONFIRMADA: {active_baud} bps {active_stopbits} (config_ack=True) ===")

        # 0. Verificar revisión de firmware
        opened_ser.reset_input_buffer()
        opened_ser.write(cmd_req_fw_rev())
        fw_frames, fw_rx = read_xbus_frames_sync(opened_ser, active_parser, timeout_s=0.2, target_mids={MID_FW_REV})
        print(f"[ReqFWRev] RX: {fmt_hex(fw_rx)}")
        if any(m == MID_FW_REV and len(pl) >= 1 and pl[0] == 0xFF for _, m, pl in fw_frames):
            opened_ser.write(cmd_bootloader_finished())
            time.sleep(0.8)
            opened_ser.reset_input_buffer()
            opened_ser.write(cmd_goto_config())
            read_xbus_frames_sync(opened_ser, active_parser, timeout_s=0.25, target_mids={MID_GOTO_CONFIG_ACK})

        # 1. ReqDID
        opened_ser.reset_input_buffer()
        opened_ser.write(cmd_req_did())
        did_frames, did_rx = read_xbus_frames_sync(opened_ser, active_parser, timeout_s=0.2, target_mids={MID_DEVICE_ID})
        station_id = None
        for _, m, pl in did_frames:
            if m == MID_DEVICE_ID and len(pl) >= 4:
                station_id = f"{struct.unpack_from('>I', pl, 0)[0]:08X}"
        print(f"[ReqDID] DeviceID={station_id} RX={fmt_hex(did_rx)}")

        # 2. Activar TDMA 60 Hz en canal 11 (con barrido corto de prueba si no llegan MTw en 1.2s)
        sweep_list = build_channel_sweep_order(11)[:2]  # probar canal 11 y 15 dentro del límite de 8 s
        radio_ack = False
        meas_ack = False
        verified_channel: int | None = None
        mtw_packets = 0

        for ch in sweep_list:
            r_ok, m_ok, ver_ch, logs = activate_awinda_tdma_channel_sync(
                opened_ser, active_parser, ch, DEFAULT_AWINDA_TDMA_HZ
            )
            for entry in logs:
                print(f"  [{ch}] {entry}")
            radio_ack = radio_ack or r_ok
            meas_ack = meas_ack or m_ok
            verified_channel = ver_ch or ch

            # Escuchar hasta 1.2s tramas reales de sensores MTw
            rx_frames, _raw = read_xbus_frames_sync(
                opened_ser,
                active_parser,
                timeout_s=1.2,
                target_mids={MID_MTDATA2},
            )
            sensor_hits = [
                (b, m, pl.hex())
                for b, m, pl in rx_frames
                if m == MID_MTDATA2 or (m == MID_DEVICE_ID and b != 0xFF) or (m == MID_NOTIFICATION and len(pl) >= 4)
            ]
            if sensor_hits:
                mtw_packets += len(sensor_hits)
                print(f"  [Canal {ch}] Sensores MTw detectados: {sensor_hits[:4]}")
                break

        print(f"\n=== RESUMEN HARDWARE EN VIVO ({target_port} @ {active_baud} bps {active_stopbits}) ===")
        print(f"  station_id       = {station_id}")
        print(f"  config_ack       = {config_ack}")
        print(f"  radio_ack        = {radio_ack}")
        print(f"  verified_channel = {verified_channel}")
        print(f"  measurement_ack  = {meas_ack}")
        print(f"  mtw_sensor_hits  = {mtw_packets}")
        return 0 if (config_ack and radio_ack and meas_ack) else 3
    finally:
        if opened_ser is not None:
            try:
                if opened_ser.is_open:
                    opened_ser.write(cmd_goto_config())
                    time.sleep(0.02)
                    opened_ser.write(cmd_disable_radio())
                    time.sleep(0.02)
                    opened_ser.close()
            except Exception:
                pass
        watchdog.cancel()


if __name__ == "__main__":
    raise SystemExit(main())
