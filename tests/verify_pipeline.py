from __future__ import annotations

import argparse
import asyncio
import json
import math
import py_compile
import socket
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
import uvicorn
import websockets

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.export.bvh_exporter import validate_bvh
from backend.engine import MocapEngine
from backend.hal import xda_bridge_worker
from backend.hal.base import SensorPacket
from backend.hal.sensor_mapper import DynamicSensorMapper
from backend.hal.serial_udp_driver import WitMotionFrameDecoder, parse_imu_text_payload, parse_osc_imu_datagram
from backend.hal.watchdog import ConnectionWatchdog
from backend.hal.xsens_awinda_driver import (
    SWEEP_CHANNELS,
    XbusStreamParser,
    XsensAwindaDriver,
    build_channel_sweep_order,
    build_xbus_frame,
    cmd_disable_radio,
    cmd_enable_radio,
    cmd_goto_config,
    cmd_goto_measurement,
    cmd_goto_operational,
    cmd_req_radio_channel,
    cmd_set_output_configuration,
    cmd_set_update_rate,
    cmd_wakeup,
    parse_mtdata2_payload,
)
from backend.kinematics.anthropometry import AnthropometricProfile, SkeletonModel, ProfileManager
from backend.kinematics.biomechanics import JointAngleCalculator
from backend.kinematics.calibration import CalibrationEngine
from backend.kinematics.fk_solver import HierarchicalFKSolver
from backend.kinematics.quaternions import euler_zxy_to_q, q_angle_deg, q_from_axis_angle, q_mul, q_normalize, q_rotate_vec, q_to_euler_zxy
from backend.kinematics.sensor_fusion import MadgwickFilter
from backend.main import app, engine
from backend.recording.recorder import TakeRecorder

EXPECTED_AWINDA_17 = {
    "PELVIS": "00B4D904",
    "STERNUM": "00B4D8B2",
    "HEAD": "00B4D902",
    "SHOULDER_L": "00B4D8F1",
    "UPPER_ARM_L": "00B4D8F2",
    "FOREARM_L": "00B4D903",
    "HAND_L": "00B4D905",
    "SHOULDER_R": "00B4D901",
    "UPPER_ARM_R": "00B4D8FF",
    "FOREARM_R": "00B4D8FC",
    "HAND_R": "00B4D8FB",
    "THIGH_L": "00B4D8F6",
    "SHIN_L": "00B4D8F9",
    "FOOT_L": "00B4581A",
    "THIGH_R": "00B4D900",
    "SHIN_R": "00B4D8FE",
    "FOOT_R": "00B4D8FD",
}


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_quaternion_and_fusion_math() -> None:
    print("[1/6] Verificando álgebra de cuaterniones Euler ZXY y filtro Madgwick...")
    rng = np.random.default_rng(123)
    for _ in range(50):
        q = q_normalize(rng.normal(size=4))
        ez, ex, ey = q_to_euler_zxy(q)
        if abs(ex) < 89.0:
            q_rec = euler_zxy_to_q(ez, ex, ey)
            err = q_angle_deg(q, q_rec)
            assert err < 1e-3, f"Error Euler ZXY->Q demasiado alto: {err}"

    # Filtro Madgwick: convergencia bajo gravedad Y-up [0, 9.81, 0] tras perturbación inicial
    flt = MadgwickFilter(beta=0.15)
    flt.reset([0.92, 0.25, 0.20, -0.20])
    for _ in range(400):
        q_est = flt.update([0.0, 0.0, 0.0], [0.0, 9.81, 0.0], mag=None, dt=1.0 / 120.0)
    up_tilt = abs(float(q_est[1])) + abs(float(q_est[3]))
    assert up_tilt < 0.03, f"Madgwick no convergió al eje vertical +Y: q={q_est}"
    print("   -> OK: Euler ZXY (<1e-3 deg) y Madgwick Y-up convergieron correctamente.")


def test_multi_brand_parsers() -> None:
    print("[2/6] Verificando parsers Serial/UDP/OSC/WitMotion y mapeo de 17 IDs Awinda...")
    cfg = json.loads((ROOT / "backend" / "config" / "default_awinda_17.json").read_text(encoding="utf-8"))
    assert cfg["mappings"] == EXPECTED_AWINDA_17, "El archivo default_awinda_17.json no coincide con los 17 IDs exactos."

    p_json = parse_imu_text_payload(
        '{"id":"ESP_ARM","brand":"esp32_bno085","quat":[1,0,0,0],"gyro":[0.1,0.2,0.3],"battery":88}',
        default_id="X",
        protocol="udp",
    )
    assert p_json is not None and p_json.sensor_id == "ESP_ARM" and not p_json.raw_only

    p_raw = parse_imu_text_payload("RAW,ESP_RAW1,0.0,9.81,0.0,0.01,-0.02,0.03", default_id="X", protocol="serial")
    assert p_raw is not None and p_raw.raw_only and p_raw.sensor_id == "ESP_RAW1"

    # OSC /imu/TEST_OSC
    addr = b"/imu/TEST_OSC\x00\x00\x00"
    tags = b",ffff\x00\x00\x00"
    vals = struct.pack(">ffff", 1.0, 0.0, 0.0, 0.0)
    p_osc = parse_osc_imu_datagram(addr + tags + vals, default_id="X")
    assert p_osc is not None and p_osc.sensor_id == "TEST_OSC" and p_osc.protocol == "osc"

    # WitMotion 0x59 quaternion packet
    body = bytes([0x55, 0x59]) + struct.pack("<hhhh", 32767, 0, 0, 0)
    chk = sum(body) & 0xFF
    wit = WitMotionFrameDecoder("WIT_1")
    pkts = wit.feed(body + bytes([chk]), now_ms=100.0)
    assert len(pkts) == 1 and pkts[0].brand == "witmotion"
    print("   -> OK: Todos los parsers multi-marca y los 17 IDs Awinda verificados.")


def test_xbus_awinda_protocol() -> None:
    print("[2b/6] Verificando tramas TDMA Xbus Awinda2 (WakeUp, SetUpdateRate 60Hz, SetOutCfg, EnableMaster, Sweep)...")
    assert cmd_wakeup() == bytes.fromhex("FA FF 3E 00 C3"), "WakeUp Xbus inválido."
    assert cmd_goto_config() == bytes.fromhex("FA FF 30 00 D1"), "GotoConfig Xbus inválido."
    assert cmd_goto_measurement() == bytes.fromhex("FA FF 10 00 F1"), "GotoMeasurement Xbus inválido."
    assert cmd_enable_radio(11) == bytes.fromhex("FA FF B2 01 0B 43"), "EnableMaster ch11 inválido."
    assert cmd_goto_operational() == bytes.fromhex("FA FF C0 00 41"), "GotoOperational inválido."
    assert cmd_disable_radio() == bytes.fromhex("FA FF B4 00 4D"), "DisableMaster inválido."
    assert cmd_req_radio_channel() == bytes.fromhex("FA FF B6 00 4B"), "ReqRadioChannel inválido."

    rate60 = cmd_set_update_rate(60)
    assert rate60 == bytes.fromhex("FA FF A4 02 00 3C 1F"), f"SetUpdateRate(60) inválido: {rate60.hex()}"
    out_cfg = cmd_set_output_configuration(60)
    assert out_cfg[0] == 0xFA and out_cfg[1] == 0xFF and out_cfg[2] == 0xC0 and (sum(out_cfg[1:]) & 0xFF) == 0
    sweep = build_channel_sweep_order(15)
    assert sweep[0] == 15 and set(sweep) == set(range(11, 26)) and len(SWEEP_CHANNELS) == 15

    # Validar persistencia del canal ganador en JSON temporal (awinda_radio.json)
    with tempfile.TemporaryDirectory(prefix="awinda_cfg_") as cfg_tmp:
        tmp_radio = Path(cfg_tmp) / "awinda_radio.json"
        drv = XsensAwindaDriver(lambda _pkts: None, settings_dir=Path(cfg_tmp))
        saved_path = drv.save_radio_channel_config(20, target_path=tmp_radio)
        saved_json = json.loads(saved_path.read_text(encoding="utf-8"))
        assert saved_json["channel"] == 20 and saved_json["rate_hz"] == 60

    # Construir trama MTData2 (MID=0x36) con DeviceId=00B4D904, Quat, FreeAccel y Gyro
    tlv_did = struct.pack(">HBI", 0x0010, 4, 0x00B4D904)
    tlv_quat = struct.pack(">HBffff", 0x2010, 16, 1.0, 0.0, 0.0, 0.0)
    tlv_acc = struct.pack(">HBfff", 0x4030, 12, 0.5, 1.2, -0.3)
    tlv_gyr = struct.pack(">HBfff", 0x8020, 12, 0.1, -0.2, 0.3)
    mt_frame = build_xbus_frame(0x36, tlv_did + tlv_quat + tlv_acc + tlv_gyr, bid=0x01)

    parser = XbusStreamParser()
    parsed = parser.feed(b"\x00\xff" + mt_frame)
    assert len(parsed) == 1 and parsed[0][0] == 0x01 and parsed[0][1] == 0x36
    pkt = parse_mtdata2_payload(parsed[0][0], parsed[0][2], bus_id_map={}, default_hz=120.0, now_ms=10.0)
    assert pkt is not None
    assert pkt.sensor_id == "00B4D904"
    assert pkt.protocol == "xbus_serial"
    assert abs(pkt.free_accel[1] - (-0.3)) < 1e-5 and abs(pkt.free_accel[2] - (-1.2)) < 1e-5
    print("   -> OK: Tramas Xbus EnableRadio/GotoConfig/GotoMeasurement y decodificador MTData2 verificados.")


async def run_live_server_tests(no_hardware: bool = True) -> None:
    orig_start_monitor = engine.xsens.start_auto_monitor
    if no_hardware:
        async def _noop_monitor(*_args, **_kwargs) -> None:
            return None

        engine.xsens.start_auto_monitor = _noop_monitor  # type: ignore[method-assign]

    port = find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    ws_url = f"ws://127.0.0.1:{port}/ws/stream"

    # Esperar arranque del servidor
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        ready = False
        for _ in range(50):
            try:
                r = await client.get("/api/health")
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                await asyncio.sleep(0.1)
        assert ready, "El servidor FastAPI no arrancó a tiempo."

        try:
            aw_st = (await client.get("/api/hardware/awinda/status")).json()
            assert "handshake_log" in aw_st and "antenna_state" in aw_st
            if not no_hardware:
                assert aw_st["auto_monitor_running"] is True, f"Auto-monitor Awinda inactivo: {aw_st}"
                scan_res = (await client.post("/api/hardware/awinda/scan")).json()
                assert "all_com_ports" in scan_res and "awinda_status" in scan_res
                print(f"   -> OK: Escaneo USB completado ({len(scan_res['all_com_ports'])} puertos COM; estado antena={scan_res['awinda_status']['antenna_state']}).")
            else:
                print("   -> OK: Modo --no-hardware activo (cero contacto con COM6 / XsScanner).")

            # Pausar auto-monitor y driver físico durante las pruebas deterministas del simulador sintético
            engine.xsens._auto_monitor_running = False
            await client.post("/api/hardware/driver/stop", json={"driver": "xsens_awinda"})

            # [3/6] Streaming WebSocket >= 60 Hz con los 17 IDs exactos
            print("[3/6] Verificando streaming WebSocket >= 60 Hz y 17 sensores mapeados...")
            await client.post("/api/hardware/driver/start", json={"driver": "simulator", "preset": "walk", "rate_hz": 120})
            await client.post("/api/hardware/simulator/config", json={"preset": "walk", "rate_hz": 120, "clear_imperfections": True})
            await asyncio.sleep(0.25)

            frames_rx = 0
            last_frame: dict | None = None
            t0 = time.perf_counter()
            async with websockets.connect(ws_url) as ws:
                while (time.perf_counter() - t0) < 2.2:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    msg = json.loads(raw)
                    if "segments" in msg:
                        frames_rx += 1
                        last_frame = msg
            elapsed = time.perf_counter() - t0
            ws_hz = frames_rx / elapsed
            assert last_frame is not None, "No se recibieron cuadros por WebSocket."
            assert ws_hz >= 60.0, f"Tasa WebSocket insuficiente: {ws_hz:.1f} Hz (< 60.0 Hz)"

            mapped_pairs = {s["segment"]: s["sensor_id"] for s in last_frame["sensors"]}
            assert mapped_pairs == EXPECTED_AWINDA_17, f"Mapeo incompleto: {mapped_pairs}"
            print(f"   -> OK: WebSocket recibiendo {ws_hz:.1f} Hz ({frames_rx} cuadros en {elapsed:.2f} s) con 17 IDs exactos.")

            # [4/6] Calibración T-Pose + Caminata con correas aleatorias + deriva magnética -> error < 0.5°
            print("[4/6] Verificando calibración T-Pose + Caminata (correas aleatorias + deriva magnética)...")
            await client.post(
                "/api/hardware/simulator/config",
                json={"preset": "tpose", "rate_hz": 120, "randomize_imperfections": True, "noise_std_rad": 0.0, "seed": 2026},
            )
            await asyncio.sleep(0.15)

            # Fase estática 1.2 s
            r = await client.post("/api/calibration/start-static", json={"pose_type": "tpose", "duration_s": 1.0})
            assert r.status_code == 200
            for _ in range(40):
                await asyncio.sleep(0.08)
                st = (await client.get("/api/calibration/status")).json()
                if st["state"] == "static_done":
                    break
            assert st["state"] == "static_done", f"No completó fase estática: {st}"

            # Verificar error en T-Pose con calibración estática
            # Cambiar a caminata y capturar fase dinámica 2.0 s
            await client.post("/api/hardware/simulator/config", json={"preset": "walk", "rate_hz": 120})
            await asyncio.sleep(0.15)
            r = await client.post("/api/calibration/start-walk", json={"duration_s": 2.2})
            assert r.status_code == 200
            for _ in range(50):
                await asyncio.sleep(0.1)
                st = (await client.get("/api/calibration/status")).json()
                if st["state"] == "calibrated":
                    break
            assert st["state"] == "calibrated", f"No completó calibración dinámica: {st}"

            # Evaluar error exacto determinista paso a paso durante un ciclo completo de caminata (y en T-Pose)
            errors_deg: list[float] = []
            max_err = 0.0
            worst_seg = ""
            # Evaluar 24 instantes en walk
            for step_idx in range(24):
                t_eval = 0.1 * step_idx
                pkts = engine.simulator.sample_at_time(t_eval, dt=1.0 / 120.0)
                gt_quats, _ = engine.simulator.compute_biomechanical_pose(t_eval, preset="walk")
                for pkt in pkts:
                    q_cal = engine.calibration.apply(pkt.segment, np.asarray(pkt.quaternion))
                    err = q_angle_deg(q_cal, gt_quats[pkt.segment])
                    errors_deg.append(err)
                    if err > max_err:
                        max_err = err
                        worst_seg = pkt.segment

            mean_err = sum(errors_deg) / len(errors_deg)
            assert mean_err < 0.5 and max_err < 0.5, (
                f"Error de calibración excede 0.5°: medio={mean_err:.3f}°, máximo={max_err:.3f}° ({worst_seg})"
            )
            print(f"   -> OK: Calibración verificada (error medio={mean_err:.3f}°, máximo={max_err:.3f}° en {worst_seg}).")

            # [5/6] Contacto con el piso, biomecánica y Shake-to-Identify
            print("[5/6] Verificando contacto con el suelo, biomecánica y Shake-to-Identify...")
            min_y_vals: list[float] = []
            knee_flex_vals: list[float] = []
            async with websockets.connect(ws_url) as ws:
                for _ in range(60):
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))
                    if "min_foot_y" in msg:
                        min_y_vals.append(float(msg["min_foot_y"]))
                    if "angles" in msg and "knee_l" in msg["angles"]:
                        knee_flex_vals.append(float(msg["angles"]["knee_l"]["flexion"]))
            assert min(min_y_vals) >= -0.005, f"Penetración de piso detectada: {min(min_y_vals)}"
            assert (max(knee_flex_vals) - min(knee_flex_vals)) > 20.0, "Rango de flexión de rodilla insuficiente."

            await client.post("/api/hardware/simulator/shake", json={"sensor_id": "00B4D904", "duration_s": 0.4})
            await asyncio.sleep(0.28)
            map_state = (await client.get("/api/mapping")).json()
            assert map_state["mapping"]["last_shake_event"] is not None, "No se detectó agitación de sensor."
            assert map_state["mapping"]["last_shake_event"]["sensor_id"] == "00B4D904"
            print("   -> OK: Piso Y>=0, flexión rodilla realista y Shake-to-Identify verificados.")

            # [6/6] Grabación y exportación BVH válida de 23 huesos con Pose T inicio/fin
            print("[6/6] Verificando grabación 120 Hz y exportación .BVH 23 huesos con Pose T inicio/fin...")
            await client.post("/api/recording/start", json={"name": "qa_walk_test"})
            await asyncio.sleep(1.1)
            rec_stop = (await client.post("/api/recording/stop")).json()
            assert rec_stop["frame_count"] >= 60, f"Pocos cuadros grabados: {rec_stop['frame_count']}"

            expected_23_openmocap = {
                "Pelvis", "Spine", "Spine1", "Spine2", "Spine3", "Neck", "Head",
                "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
                "RightShoulder", "RightArm", "RightForeArm", "RightHand",
                "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
                "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase",
            }
            for preset_name in ("openmocap", "mixamo", "rigify"):
                exp_res = (
                    await client.post(
                        "/api/export/bvh",
                        json={
                            "file_name": f"qa_verify_{preset_name}.bvh",
                            "scale": 1.0,
                            "naming": preset_name,
                            "include_tpose_frame0": True,
                            "tpose_lead_in_out": True,
                            "respect_trim": True,
                        },
                    )
                ).json()
                bvh_path = Path(exp_res["file_path"])
                val = validate_bvh(bvh_path)
                assert val["valid"] and val["joint_count"] == 23 and val["expected_channels"] == 72, val
                assert val["end_site_count"] == 5, f"End Sites inesperados: {val['end_site_count']}"
                assert val["frame_count"] == rec_stop["frame_count"] + 90
                if preset_name == "openmocap":
                    assert set(val["joints"]) == expected_23_openmocap
                    for deg in val["first_frame_rotations"]:
                        assert abs(deg) < 1e-3, f"Frame 0 fuera de Pose T: {deg}"
                    for deg in val["last_frame_rotations"]:
                        wrapped = ((deg + 180.0) % 360.0) - 180.0
                        assert abs(wrapped) < 1e-3, f"Último frame fuera de Pose T: {deg}"
            print("   -> OK: Archivos .BVH validados (23 huesos, 72 canales, 5 End Sites y Pose T inicio/fin).")

        finally:
            engine.xsens.start_auto_monitor = orig_start_monitor  # type: ignore[method-assign]
            server.should_exit = True
            await asyncio.sleep(0.2)


def test_realistic_mtw_calibration() -> None:
    """
    [EXTRA-CAL] Prueba calibración con ruido realista de sensores físicos MTw:
      - Caso A: Traje parcial (5 de 17 sensores), micro-balanceo +-1.5 deg y gyro < 0.35 rad/s,
                transición atómica idle -> static_tpose -> dynamic_walk -> calibrated vía HALManager.
      - Caso B: Calibración rápida (Solo T-Pose) con 1 único sensor sin PELVIS.
      - Caso C: Cero paquetes recibidos -> error explícito ok=False (nunca regreso silencioso a idle).
    """
    print("[2c/6] Verificando calibración MTw realista (micro-balanceo +-1.5°, traje parcial y modo rápido)...")
    eng = MocapEngine()
    partial_segs = ["PELVIS", "STERNUM", "THIGH_L", "SHIN_L", "HAND_R"]
    strap_offsets = {
        "PELVIS": q_from_axis_angle([0.2, 1.0, 0.1], math.radians(38.0)),
        "STERNUM": q_from_axis_angle([0.0, 0.9, 0.4], math.radians(-52.0)),
        "THIGH_L": q_from_axis_angle([1.0, 0.2, -0.3], math.radians(74.0)),
        "SHIN_L": q_from_axis_angle([-0.3, 0.9, 0.2], math.radians(-115.0)),
        "HAND_R": q_from_axis_angle([0.4, -0.5, 0.8], math.radians(95.0)),
    }
    mag_drifts_deg = {
        "PELVIS": 18.0,
        "STERNUM": -27.0,
        "THIGH_L": 33.0,
        "SHIN_L": -22.0,
        "HAND_R": 41.0,
    }

    st0 = eng.calibration.get_status()
    assert st0["stage"] == "idle" and st0["state"] == "uncalibrated"

    st1 = eng.start_calibration_static(pose_type="tpose", duration_s=0.55, mode="full")
    assert st1["state"] == "capturing_static" and st1["stage"] == "static_tpose"
    assert st1["transition_seq"] > st0["transition_seq"]

    # Caso A1: fase estática 4s simulada comprimida (~30 muestras a 60 Hz) con micro-balanceo ±1.5 deg
    t_mono0 = time.monotonic()
    for i in range(32):
        t_s = i / 60.0
        batch: list[SensorPacket] = []
        for idx, seg in enumerate(partial_segs):
            q_ref = np.asarray(eng.skeleton.segments[seg].tpose_quat, dtype=np.float64)
            sway_rad = math.radians(1.5) * math.sin(2.0 * math.pi * 1.4 * t_s + idx * 0.7)
            gyro_sway = math.radians(1.5) * (2.0 * math.pi * 1.4) * math.cos(2.0 * math.pi * 1.4 * t_s + idx * 0.7)
            assert abs(gyro_sway) < 0.25
            q_sway = q_from_axis_angle([0.7, 0.2, 0.7], sway_rad)
            q_true = q_normalize(q_mul(q_sway, q_ref))
            q_drift = q_from_axis_angle([0.0, 1.0, 0.0], math.radians(mag_drifts_deg[seg]))
            q_raw = q_normalize(q_mul(q_drift, q_mul(q_true, strap_offsets[seg])))
            batch.append(
                SensorPacket(
                    sensor_id=EXPECTED_AWINDA_17[seg],
                    brand="xsens_awinda",
                    protocol="xda",
                    segment="UNASSIGNED",
                    quaternion=q_raw.tolist(),
                    free_accel=[0.01, 0.02, -0.01],
                    gyro=[gyro_sway * 0.7, gyro_sway * 0.2, gyro_sway * 0.7],
                    mag=[0.0, 0.0, 1.0],
                    battery=88.0,
                    rssi=-48,
                    hz=60.0,
                    timestamp_ms=(t_mono0 + t_s) * 1000.0,
                    raw_only=False,
                )
            )
        eng.hal.dispatch_packets(batch)

    time.sleep(0.60)
    eng.step_once()
    st2 = eng.calibration.get_status()
    assert st2["state"] == "static_done", f"Se reinició en estático: {st2}"
    assert st2["stage"] == "static_straight"
    assert st2["ok"] is True and st2["error_es"] is None
    assert st2["calibrated_segments"] == 5
    assert st2["active_stream_count"] == 5 and st2["live_packet_count"] >= 30
    assert st2["max_static_std_deg"] <= 6.0
    assert st2["mean_static_gyro_rad_s"] < 0.35
    assert st2["transition_seq"] > st1["transition_seq"]

    # Caso A2: fase caminata con excitación sagital/propulsión y transición atómica a calibrated
    st3 = eng.start_calibration_walk(duration_s=0.85)
    assert st3["state"] == "capturing_walk" and st3["stage"] == "dynamic_walk"
    assert st3["transition_seq"] > st2["transition_seq"]

    for i in range(45):
        t_s = i / 60.0
        batch = []
        swing_vel = 1.6 * math.sin(2.0 * math.pi * 1.1 * t_s)
        prop_acc = 1.8 * math.sin(2.0 * math.pi * 2.2 * t_s)
        for seg in partial_segs:
            q_ref = np.asarray(eng.skeleton.segments[seg].tpose_quat, dtype=np.float64)
            q_drift = q_from_axis_angle([0.0, 1.0, 0.0], math.radians(mag_drifts_deg[seg]))
            q_raw = q_normalize(q_mul(q_drift, q_mul(q_ref, strap_offsets[seg])))
            if seg in ("THIGH_L", "SHIN_L"):
                omega_world = np.array([swing_vel, 0.0, 0.0], dtype=np.float64)
                omega_world_drifted = q_rotate_vec(q_drift, omega_world)
                from backend.kinematics.quaternions import q_inv

                gyro_local = q_rotate_vec(q_inv(q_raw), omega_world_drifted)
                fa = [0.0, 0.0, 0.0]
            else:
                gyro_local = [0.02, 0.05, 0.01]
                acc_world = q_rotate_vec(q_drift, np.array([0.0, 0.0, prop_acc], dtype=np.float64))
                fa = [float(acc_world[0]), float(acc_world[1]), float(acc_world[2])]
            batch.append(
                SensorPacket(
                    sensor_id=EXPECTED_AWINDA_17[seg],
                    brand="xsens_awinda",
                    protocol="xda",
                    segment="UNASSIGNED",
                    quaternion=q_raw.tolist(),
                    free_accel=fa,
                    gyro=[float(v) for v in gyro_local],
                    mag=[0.0, 0.0, 1.0],
                    battery=87.0,
                    rssi=-48,
                    hz=60.0,
                    timestamp_ms=(t_mono0 + 1.0 + t_s) * 1000.0,
                    raw_only=False,
                )
            )
        eng.hal.dispatch_packets(batch)

    time.sleep(0.90)
    frame_after = eng.step_once()
    st4 = frame_after["calibration"]
    assert st4["state"] == "calibrated" and st4["stage"] == "calibrated"
    assert st4["ok"] is True and st4["error_es"] is None
    assert st4["calibrated_segments"] == 5
    assert st4["transition_seq"] > st3["transition_seq"]
    assert len(frame_after["segments"]) == 23, "El esqueleto parcial debe completar los 23 huesos con respaldo neutro."

    # Caso B: Calibración rápida con 1 solo sensor sin PELVIS
    eng_quick = MocapEngine()
    st_q0 = eng_quick.start_calibration_static(pose_type="tpose", duration_s=0.5, mode="quick")
    assert st_q0["mode"] == "quick"
    for i in range(15):
        sw = math.radians(1.2) * math.sin(i * 0.4)
        q_hand = q_normalize(q_mul(q_from_axis_angle([0.0, 0.0, 1.0], sw), np.asarray(eng_quick.skeleton.segments["HAND_R"].tpose_quat)))
        eng_quick.hal.dispatch_packets([
            SensorPacket(
                sensor_id=EXPECTED_AWINDA_17["HAND_R"],
                brand="xsens_awinda",
                protocol="xda",
                segment="UNASSIGNED",
                quaternion=q_hand.tolist(),
                free_accel=[0.0, 0.0, 0.0],
                gyro=[0.05, 0.02, 0.04],
                mag=[0.0, 0.0, 1.0],
                battery=90.0,
                rssi=-45,
                hz=60.0,
                timestamp_ms=float(i) * 16.0,
                raw_only=False,
            )
        ])
    time.sleep(0.55)
    eng_quick.step_once()
    st_q1 = eng_quick.calibration.get_status()
    assert st_q1["state"] == "calibrated" and st_q1["stage"] == "calibrated"
    assert st_q1["mode"] == "quick" and st_q1["ok"] is True and st_q1["calibrated_segments"] == 1
    assert st_q1["active_stream_count"] == 1 and st_q1["live_packet_count"] >= 10

    # Caso C: Cero paquetes recibidos -> error explícito en español, jamás regreso silencioso a idle
    eng_err = MocapEngine()
    eng_err.start_calibration_static(pose_type="tpose", duration_s=0.5, mode="full")
    time.sleep(0.55)
    eng_err.step_once()
    st_err = eng_err.calibration.get_status()
    assert st_err["ok"] is False
    assert st_err["state"] == "error" and st_err["stage"] == "error"
    assert st_err["active_stream_count"] == 0 and st_err["live_packet_count"] == 0
    assert st_err["error_es"] and len(st_err["error_es"]) > 10
    print("   -> OK: Calibración MTw realista (5 sensores ±1.5°, modo rápido 1 sensor y error explícito 0 paquetes) verificada.")


def test_blender_bridge_syntax() -> None:
    script = ROOT / "blender_tools" / "convertir_a_fbx.py"
    py_compile.compile(str(script), doraise=True)
    print("[EXTRA] Sintaxis de blender_tools/convertir_a_fbx.py verificada correctamente.")


def test_xda_bridge_worker_swig_mock() -> None:
    """
    [EXTRA-XDA] Valida secuencia oficial Example_mtw con mocks SWIG sin tocar COM6:
      - Cero llamadas a setOutputConfiguration()
      - Secuencia gotoConfig -> setUpdateRate(60) -> enableRadio -> waitForAllDevicesInitialized -> gotoMeasurement
      - Emisión de paquetes vía onLiveDataAvailable
      - Estado 'error' (nunca 'radio_on') cuando gotoMeasurement() falla persistentemente
    """
    print("[EXTRA-XDA] Verificando secuencia oficial XDA con mocks SWIG (sin hardware real)...")

    class _MockDid:
        def __init__(self, hex_id: str, master: bool = False) -> None:
            self._hex = hex_id
            self._master = master

        def toXsString(self) -> str:
            return self._hex

        def isWirelessMaster(self) -> bool:
            return self._master

        def isAwinda2(self) -> bool:
            return self._master

        def isAwinda2Station(self) -> bool:
            return self._master

        def isAwindaX(self) -> bool:
            return False

        def isAwinda2Dongle(self) -> bool:
            return self._master

        def isAwindaXDongle(self) -> bool:
            return False

    class _MockPacket:
        def __init__(self, sid: str) -> None:
            self._sid = sid

        def deviceId(self):
            return _MockDid(self._sid, master=False)

        def containsOrientation(self) -> bool:
            return True

        def containsPacketCounter(self) -> bool:
            return True

        def packetCounter(self) -> int:
            return 1

        def orientationQuaternion(self):
            return [1.0, 0.0, 0.0, 0.0]

        def containsFreeAcceleration(self) -> bool:
            return True

        def freeAcceleration(self):
            return [0.1, 0.2, 0.3]

        def containsCalibratedGyroscopeData(self) -> bool:
            return True

        def calibratedGyroscopeData(self):
            return [0.01, -0.02, 0.03]

        def containsCalibratedMagneticField(self) -> bool:
            return True

        def calibratedMagneticField(self):
            return [0.0, 1.0, 0.0]

        def containsRssi(self) -> bool:
            return True

        def rssi(self) -> int:
            return -44

    def _run_scenario(fail_measurement: bool):
        calls: list[str] = []
        emitted: list[dict] = []
        stop_ev = threading.Event()
        child_did = _MockDid("00B4D904", master=False)
        master_did = _MockDid("01210CE2", master=True)

        class _MockChild:
            def __init__(self) -> None:
                self.cbs = []

            def deviceId(self):
                return child_did

            def addCallbackHandler(self, cb) -> None:
                self.cbs.append(cb)

            def removeCallbackHandler(self, cb) -> None:
                if cb in self.cbs:
                    self.cbs.remove(cb)

            def batteryLevel(self) -> float:
                return 92.0

            def setOutputConfiguration(self, *_a):
                raise AssertionError("setOutputConfiguration NO debe llamarse en hijos MTw Awinda2")

        child_dev = _MockChild()

        class _MockMaster:
            def __init__(self) -> None:
                self._radio = False
                self.cbs = []

            def gotoConfig(self) -> bool:
                calls.append("gotoConfig")
                return True

            def supportedUpdateRates(self):
                return [120, 100, 80, 60]

            def setUpdateRate(self, hz: int) -> None:
                calls.append(f"setUpdateRate({hz})")

            def addCallbackHandler(self, cb) -> None:
                self.cbs.append(cb)

            def removeCallbackHandler(self, cb) -> None:
                if cb in self.cbs:
                    self.cbs.remove(cb)

            def isRadioEnabled(self) -> bool:
                return self._radio

            def enableRadio(self, ch: int) -> bool:
                calls.append(f"enableRadio({ch})")
                self._radio = True
                return True

            def disableRadio(self) -> None:
                self._radio = False

            def childCount(self) -> int:
                return 1 if self._radio else 0

            def children(self):
                return [child_dev] if self._radio else []

            def waitForAllDevicesInitialized(self) -> None:
                calls.append("waitForAllDevicesInitialized")

            def gotoMeasurement(self) -> bool:
                calls.append("gotoMeasurement")
                if fail_measurement:
                    return False
                for cb in child_dev.cbs:
                    cb.onLiveDataAvailable(child_dev, _MockPacket("00B4D904"))
                return True

            def lastResultText(self) -> str:
                return "Mock Error" if fail_measurement else ""

            def setOutputConfiguration(self, *_a):
                raise AssertionError("setOutputConfiguration NO debe llamarse en maestro Awinda2")

        master_dev = _MockMaster()

        class _MockPortInfo:
            def deviceId(self):
                return master_did

            def portName(self) -> str:
                return "COM_MOCK"

            def baudrate(self) -> int:
                return 2000000

        class _MockControl:
            def openPort(self, port_arg) -> bool:
                assert isinstance(port_arg, _MockPortInfo), "Debe llamar openPort(XsPortInfo)"
                calls.append("openPort")
                return True

            def device(self, did):
                if did.toXsString() == "01210CE2":
                    return master_dev
                if did.toXsString() == "00B4D904":
                    return child_dev
                return None

            def closePort(self, _p) -> None:
                pass

            def close(self) -> None:
                pass

            def destruct(self) -> None:
                pass

        class _FakeXda:
            XCS_Wireless = 1
            XCS_PluggedIn = 2
            XCS_Disconnected = 3
            XCS_Rejected = 4
            XCS_WirelessOutOfRange = 5

            class XsCallback:
                pass

            @staticmethod
            def XsControl_construct():
                return _MockControl()

            @staticmethod
            def XsScanner_scanPorts():
                return [_MockPortInfo()]

        with tempfile.TemporaryDirectory(prefix="xda_mock_") as td:
            args = SimpleNamespace(
                channel=11,
                rate_hz=60,
                port="",
                config_dir=td,
                settings_dir=td,
                locked_channel=0,
                max_runtime=0.25,
                dwell_s=0.15,
                settle_wait_s=0.06,
                join_wait_s=0.10,
                meas_retry_delay_s=0.02,
                self_test_import=False,
            )
            rc = xda_bridge_worker.run_worker(args, xda_module=_FakeXda, emit_fn=emitted.append, stop_event_override=stop_ev)
            assert rc == 0, f"Worker mock salió con rc={rc}"
            radio_json = json.loads((Path(td) / "awinda_radio.json").read_text(encoding="utf-8"))
            assert radio_json["locked_channel"] == 11, f"Canal ganador no bloqueado: {radio_json}"
        return calls, emitted

    calls_ok, out_ok = _run_scenario(fail_measurement=False)
    for req_step in ("openPort", "gotoConfig", "setUpdateRate(60)", "enableRadio(11)", "waitForAllDevicesInitialized", "gotoMeasurement"):
        assert req_step in calls_ok, f"Falta paso {req_step} en {calls_ok}"
    assert calls_ok.index("waitForAllDevicesInitialized") < calls_ok.index("gotoMeasurement")
    pkts_ev = [m for m in out_ok if m.get("type") == "packets"]
    assert len(pkts_ev) >= 1 and pkts_ev[0]["packets"][0]["sensor_id"] == "00B4D904"
    meas_statuses = [m for m in out_ok if m.get("type") == "status" and not m.get("sweeping_channels") and m.get("measurement_ack")]
    assert meas_statuses and meas_statuses[-1]["antenna_state"] == "streaming"
    assert meas_statuses[-1]["locked_channel"] == 11

    calls_err, out_err = _run_scenario(fail_measurement=True)
    assert calls_err.count("gotoMeasurement") >= 5
    err_statuses = [m for m in out_err if m.get("type") == "status" and m.get("antenna_state") == "error"]
    assert err_statuses and err_statuses[-1]["measurement_ack"] is False

    # Verificar que si awinda_radio.json tiene locked_channel=15, jamás salta a otros canales aunque channel=11
    with tempfile.TemporaryDirectory(prefix="xda_locked_") as td_lock:
        (Path(td_lock) / "awinda_radio.json").write_text(
            json.dumps({"channel": 15, "locked_channel": 15}), encoding="utf-8"
        )
        locked_calls: list[str] = []
        locked_emitted: list[dict] = []

        class _LockedFakeMaster:
            def __init__(self) -> None:
                self._radio = False

            def gotoConfig(self) -> bool:
                return True

            def supportedUpdateRates(self):
                return [60]

            def setUpdateRate(self, _hz: int) -> None:
                pass

            def addCallbackHandler(self, _cb) -> None:
                pass

            def removeCallbackHandler(self, _cb) -> None:
                pass

            def isRadioEnabled(self) -> bool:
                return self._radio

            def enableRadio(self, ch: int) -> bool:
                locked_calls.append(f"enableRadio({ch})")
                self._radio = True
                return True

            def disableRadio(self) -> None:
                self._radio = False

            def childCount(self) -> int:
                return 0

            def children(self):
                return []

        class _LockedFakeXda:
            XCS_Wireless = 1
            XCS_PluggedIn = 2
            XCS_Disconnected = 3
            XCS_Rejected = 4
            XCS_WirelessOutOfRange = 5

            class XsCallback:
                pass

            @staticmethod
            def XsControl_construct():
                lm = _LockedFakeMaster()

                class _LC:
                    def openPort(self, _p):
                        return True

                    def device(self, _d):
                        return lm

                    def closePort(self, _p):
                        pass

                    def close(self):
                        pass

                    def destruct(self):
                        pass

                return _LC()

            @staticmethod
            def XsScanner_scanPorts():
                class _LP:
                    def deviceId(self):
                        return _MockDid("01210CE2", master=True)

                    def portName(self):
                        return "COM_LOCK"

                    def baudrate(self):
                        return 2000000

                return [_LP()]

        args_lock = SimpleNamespace(
            channel=11,
            rate_hz=60,
            port="",
            config_dir=td_lock,
            settings_dir=td_lock,
            locked_channel=0,
            max_runtime=0.22,
            dwell_s=0.06,
            settle_wait_s=0.05,
            join_wait_s=0.08,
            meas_retry_delay_s=0.02,
            self_test_import=False,
        )
        rc_l = xda_bridge_worker.run_worker(args_lock, xda_module=_LockedFakeXda, emit_fn=locked_emitted.append)
        assert rc_l == 0 and locked_calls == ["enableRadio(15)"], f"Canal bloqueado violado: {locked_calls}"
    print("   -> OK: Secuencia XDA sin setOutputConfiguration, bloqueo permanente RF y error explícito verificados.")


def test_pca_walk_360_disambiguation() -> None:
    """[EXTRA-360] Verifica calibración PCA completa sin inversión ±180° caminando hacia +135° y -150°."""
    print("[EXTRA-360] Verificando calibración dinámica PCA en 360° (psi=+135° y psi=-150°)...")
    with tempfile.TemporaryDirectory(prefix="cal360_") as td:
        pm = ProfileManager(Path(td))
        skel = SkeletonModel(pm.get_active_profile())
        from backend.hal.synthetic_simulator import Synthetic17SensorSimulator

        sim = Synthetic17SensorSimulator(lambda _p: None)
        for psi_deg in (135.0, -150.0):
            cal = CalibrationEngine(skel)
            sim.clear_imperfections()
            rng = np.random.default_rng(700 + int(abs(psi_deg)))
            sim.mount_offsets = {
                seg: q_from_axis_angle(rng.normal(size=3), math.radians(float(rng.uniform(35.0, 145.0))))
                for seg in sim.sensor_map
            }
            sim.yaw_drifts_rad = {seg: math.radians(psi_deg) for seg in sim.sensor_map}

            sim.preset = "tpose"
            sim.sample_at_time(0.0, dt=1.0 / 60.0)
            cal.start_static(pose_type="tpose", duration_s=0.2, mode="full")
            for k in range(12):
                for pkt in sim.sample_at_time(k / 60.0, dt=1.0 / 60.0):
                    cal.feed_sample(pkt.segment if pkt.segment != "UNASSIGNED" else _seg_for_sid(sim, pkt.sensor_id), np.asarray(pkt.quaternion), np.asarray(pkt.gyro), np.asarray(pkt.free_accel), sensor_id=pkt.sensor_id, from_hal=True)
            st_s = cal.finalize_static()
            assert st_s["state"] == "static_done"

            sim.preset = "walk"
            sim.sample_at_time(0.0, dt=1.0 / 60.0)
            cal.start_walk(duration_s=0.3)
            for k in range(120):
                for pkt in sim.sample_at_time(k / 60.0, dt=1.0 / 60.0):
                    cal.feed_sample(_seg_for_sid(sim, pkt.sensor_id), np.asarray(pkt.quaternion), np.asarray(pkt.gyro), np.asarray(pkt.free_accel), sensor_id=pkt.sensor_id, from_hal=True)
            st_w = cal.finalize_walk()
            assert st_w["state"] == "calibrated"

            errs = []
            for idx in range(20):
                t_eval = 0.1 * idx
                gt_quats, _ = sim.compute_biomechanical_pose(t_eval, preset="walk")
                for pkt in sim.sample_at_time(t_eval, dt=1.0 / 120.0):
                    seg = _seg_for_sid(sim, pkt.sensor_id)
                    q_cal = cal.apply(seg, np.asarray(pkt.quaternion))
                    errs.append(q_angle_deg(q_cal, gt_quats[seg]))
            assert max(errs) < 0.5, f"Fallo 360° a psi={psi_deg}°: max_err={max(errs):.2f}°"
    print("   -> OK: Calibración PCA 360° verificada (<0.5° a +135° y -150°).")


def _seg_for_sid(sim, sid: str) -> str:
    for seg, s in sim.sensor_map.items():
        if s == sid:
            return seg
    return "UNASSIGNED"


def test_elbow_biomechanics_independent() -> None:
    """[EXTRA-BIO] Verifica separación real entre flexión de codo y pronosupinación axial."""
    print("[EXTRA-BIO] Verificando independencia de flexión vs rotación en codos...")
    calc = JointAngleCalculator()
    q_ident = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)
    # Flexión 90° alrededor de Y + pronosupinación 45° alrededor de X (en lado L y R)
    q_l = q_normalize(q_mul(q_from_axis_angle([0.0, 1.0, 0.0], math.radians(90.0)), q_from_axis_angle([1.0, 0.0, 0.0], math.radians(45.0))))
    q_r = q_normalize(q_mul(q_from_axis_angle([0.0, 1.0, 0.0], math.radians(-90.0)), q_from_axis_angle([1.0, 0.0, 0.0], math.radians(-45.0))))
    angles = calc.compute({"UPPER_ARM_L": q_ident, "FOREARM_L": q_l, "UPPER_ARM_R": q_ident, "FOREARM_R": q_r})
    for key in ("elbow_l", "elbow_r"):
        assert abs(angles[key]["flexion"] - 90.0) < 0.5, f"{key} flexion inesperada: {angles[key]}"
        assert abs(angles[key]["rotation"] - 45.0) < 0.5, f"{key} rotation inesperada: {angles[key]}"
    print("   -> OK: Codos miden flexión (90°) y rotación/pronosupinación (45°) de forma independiente.")


def test_security_and_hardening() -> None:
    """[EXTRA-SEC] Path traversal, .meta.json, ROOT OFFSET BVH, filtro WitMotion 'U', y concurrencia."""
    print("[EXTRA-SEC] Verificando seguridad de rutas, WitMotion sin colisión 'U' y concurrencia...")
    with tempfile.TemporaryDirectory(prefix="sec_qa_") as td:
        rec = TakeRecorder(Path(td) / "takes")
        pm = ProfileManager(Path(td) / "profiles")
        skel = SkeletonModel(pm.get_active_profile())
        rec.start_recording("seguridad", skel, fps=120.0)
        rec.record_frame({"PELVIS": [0.0, 0.93, 0.0]}, {"PELVIS": [1.0, 0.0, 0.0, 0.0]}, {"PELVIS": [1.0, 0.0, 0.0, 0.0]}, {"PELVIS": [0.0, 1.0, 0.0]}, {})
        rec.stop_recording(save_to_disk=True)

        assert (Path(td) / "takes" / f"{rec.active_take_id}.meta.json").exists()
        assert len(rec.list_takes()) == 1

        for bad_id in ("../secreto.omocap", "..\\secreto.omocap", "sub/toma.omocap"):
            try:
                rec.load_take(bad_id)
                raise AssertionError(f"Debió rechazar path traversal: {bad_id}")
            except ValueError:
                pass

    bvh_text = (ROOT / "backend" / "export" / "bvh_exporter.py").read_text(encoding="utf-8")
    assert "OFFSET 0.000000 0.000000 0.000000" in bvh_text

    assert WitMotionFrameDecoder.has_valid_frame(b'{"id":"UPPER_ARM_U","quat":[1,0,0,0]}\n') is False
    body = bytes([0x55, 0x59]) + struct.pack("<hhhh", 32767, 0, 0, 0)
    assert WitMotionFrameDecoder.has_valid_frame(body + bytes([sum(body) & 0xFF])) is True

    # Estrés concurrente de hilos en Watchdog y DynamicSensorMapper
    wd = ConnectionWatchdog()
    mapper = DynamicSensorMapper()
    errs: list[BaseException] = []

    def _writer():
        try:
            for i in range(150):
                p = SensorPacket(f"SENS_{i % 20:02d}", "test", "udp", "UNASSIGNED", [1, 0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 1], 90.0, -50, 60.0, float(i) * 16.0)
                mapper.resolve_and_check_shake(p)
                wd.ingest(p)
        except BaseException as exc:
            errs.append(exc)

    def _reader():
        try:
            for _ in range(150):
                wd.get_active_snapshot()
                wd.get_diagnostics()
                mapper.get_mapping_state()
        except BaseException as exc:
            errs.append(exc)

    threads = [threading.Thread(target=_writer), threading.Thread(target=_writer), threading.Thread(target=_reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errs, f"Error de concurrencia: {errs}"
    print("   -> OK: Path traversal bloqueado, WitMotion validado y concurrencia libre de errores.")


def test_scapula_anatomy_and_straight_check() -> None:
    """
    [EXTRA-SCAPULA] Verifica exactitud anatómica escapular y anclaje de Postura Recta (3 s):
      1) Separación entre sitio de montaje del sensor escapular (~6 cm medial, ~5 cm inferior) y
         centro glenohumeral/distancias exactas hombro-codo-muñeca-mano según estatura.
      2) Tras calibrar Posición T (con +14° elevación escapular + desplazamiento de correas al bajar brazos)
         -> Postura Recta (3 s) -> Caminata, la inclinación residual en torso, escápulas y brazos en N-Pose es < 1.0°.
      3) Flujo Solo Rápido (T-Pose + Postura Recta sin caminar) también logra inclinación residual < 1.0°.
    """
    print("[EXTRA-SCAPULA] Verificando anatomía escapular, distancias articulares y Postura Recta (<1.0°)...")
    prof = AnthropometricProfile(id="qa_180", name="Sujeto 180", height_cm=180.0)
    skel = SkeletonModel(prof)
    dims = skel.dimensions

    # 1. Validar separación de montaje escapular y distancias reales en FK
    sh_l_def = skel.segments["SHOULDER_L"]
    sh_r_def = skel.segments["SHOULDER_R"]
    assert sh_l_def.sensor_mount_offset_m[0] < -0.05 and sh_l_def.sensor_mount_offset_m[1] < -0.04
    assert sh_r_def.sensor_mount_offset_m[0] > 0.05 and sh_r_def.sensor_mount_offset_m[1] < -0.04
    assert dims["clavicle_length_m"] > 0.14

    fk = HierarchicalFKSolver(skel)
    from backend.hal.synthetic_simulator import Synthetic17SensorSimulator

    sim = Synthetic17SensorSimulator(lambda _p: None)
    npose_gt, _ = sim.compute_biomechanical_pose(0.0, preset="npose")
    npose_fk = fk.solve(npose_gt)
    dists = fk.compute_joint_distances(npose_fk)
    assert abs(dists["clavicle_l"] - dims["clavicle_length_m"]) < 0.001
    assert abs(dists["clavicle_r"] - dims["clavicle_length_m"]) < 0.001
    assert abs(dists["upper_arm_l"] - dims["upper_arm_length_m"]) < 0.001
    assert abs(dists["upper_arm_r"] - dims["upper_arm_length_m"]) < 0.001
    assert abs(dists["forearm_l"] - dims["forearm_length_m"]) < 0.001
    assert abs(dists["forearm_r"] - dims["forearm_length_m"]) < 0.001
    assert abs(dists["hand_l"] - dims["hand_length_m"]) < 0.001

    # Vector brazo izquierdo en N-Pose apunta hacia abajo -Y dentro de < 0.5°
    ua_dir = np.asarray(npose_fk.world_pos["FOREARM_L"]) - np.asarray(npose_fk.world_pos["UPPER_ARM_L"])
    ua_dir /= max(1e-9, float(np.linalg.norm(ua_dir)))
    arm_down_deg = math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(ua_dir, np.array([0.0, -1.0, 0.0])))))))
    assert arm_down_deg < 0.5, f"Brazo en N-Pose no apunta verticalmente: {arm_down_deg:.2f}°"

    # 2. Simular calibración completa T-Pose -> Posición Recta -> Caminata con desplazamiento real de arnés
    cal = CalibrationEngine(skel)
    rng = np.random.default_rng(909)
    sim.clear_imperfections()
    base_mounts = {
        seg: q_from_axis_angle(rng.normal(size=3), math.radians(float(rng.uniform(25.0, 120.0))))
        for seg in sim.sensor_map
    }
    sim.mount_offsets = dict(base_mounts)
    sim.yaw_drifts_rad = {seg: math.radians(float(rng.uniform(-45.0, 45.0))) for seg in sim.sensor_map}

    # Desplazamiento adicional del sensor escapular/brazo únicamente durante T-Pose (brazos arriba)
    tpose_harness_pull = q_from_axis_angle([0.3, 0.2, 1.0], math.radians(4.0))
    sim.preset = "tpose"
    sim.sample_at_time(0.0, dt=1.0 / 60.0)
    cal.start_static(pose_type="tpose", duration_s=0.2, mode="full")
    for k in range(15):
        pkts = sim.sample_at_time(k / 60.0, dt=1.0 / 60.0)
        for pkt in pkts:
            seg = _seg_for_sid(sim, pkt.sensor_id)
            q_in = np.asarray(pkt.quaternion, dtype=np.float64)
            if seg in ("SHOULDER_L", "SHOULDER_R", "UPPER_ARM_L", "UPPER_ARM_R"):
                q_in = q_normalize(q_mul(q_in, tpose_harness_pull))
            cal.feed_sample(seg, q_in, np.asarray(pkt.gyro), np.asarray(pkt.free_accel), sensor_id=pkt.sensor_id, from_hal=True)
    st_t = cal.finalize_static()
    assert st_t["state"] == "static_done"

    # Bajar brazos a Posición Recta (sin tirón de T-Pose): capturar 3 s (simulado)
    sim.mount_offsets = dict(base_mounts)
    sim.preset = "npose"
    sim.sample_at_time(0.0, dt=1.0 / 60.0)
    cal.start_straight(duration_s=0.2, complete_after=False)
    for k in range(15):
        for pkt in sim.sample_at_time(k / 60.0, dt=1.0 / 60.0):
            seg = _seg_for_sid(sim, pkt.sensor_id)
            cal.feed_sample(seg, np.asarray(pkt.quaternion), np.asarray(pkt.gyro), np.asarray(pkt.free_accel), sensor_id=pkt.sensor_id, from_hal=True)
    st_r = cal.finalize_straight()
    assert st_r["state"] == "straight_done" and st_r["straight_anchored"] is True

    # Fase Caminata
    sim.preset = "walk"
    sim.sample_at_time(0.0, dt=1.0 / 60.0)
    cal.start_walk(duration_s=0.3)
    for k in range(90):
        for pkt in sim.sample_at_time(k / 60.0, dt=1.0 / 60.0):
            seg = _seg_for_sid(sim, pkt.sensor_id)
            cal.feed_sample(seg, np.asarray(pkt.quaternion), np.asarray(pkt.gyro), np.asarray(pkt.free_accel), sensor_id=pkt.sensor_id, from_hal=True)
    st_w = cal.finalize_walk()
    assert st_w["state"] == "calibrated" and st_w["straight_anchored"] is True

    # Evaluar postura N-Pose final en torso, escápulas y brazos
    sim.preset = "npose"
    sim.sample_at_time(0.0, dt=1.0 / 60.0)
    check_segs = ("PELVIS", "STERNUM", "HEAD", "SHOULDER_L", "SHOULDER_R", "UPPER_ARM_L", "UPPER_ARM_R", "FOREARM_L", "FOREARM_R", "HAND_L", "HAND_R")
    npose_pkts = sim.sample_at_time(0.0, dt=1.0 / 60.0)
    max_npose_err = 0.0
    for pkt in npose_pkts:
        seg = _seg_for_sid(sim, pkt.sensor_id)
        if seg in check_segs:
            q_cal = cal.apply(seg, np.asarray(pkt.quaternion))
            err = q_angle_deg(q_cal, npose_gt[seg])
            max_npose_err = max(max_npose_err, err)
            assert err < 1.0, f"Inclinación residual excesiva en {seg} tras Postura Recta: {err:.3f}°"

    # 3. Validar flujo Solo Rápido (T-Pose + Postura Recta sin caminar -> complete_after=True)
    cal_q = CalibrationEngine(skel)
    sim.preset = "tpose"
    sim.yaw_drifts_rad = {seg: 0.0 for seg in sim.sensor_map}
    sim.sample_at_time(0.0, dt=1.0 / 60.0)
    cal_q.start_static(pose_type="tpose", duration_s=0.2, mode="quick")
    for k in range(12):
        for pkt in sim.sample_at_time(k / 60.0, dt=1.0 / 60.0):
            seg = _seg_for_sid(sim, pkt.sensor_id)
            q_in = np.asarray(pkt.quaternion, dtype=np.float64)
            if seg in ("SHOULDER_L", "SHOULDER_R", "UPPER_ARM_L", "UPPER_ARM_R"):
                q_in = q_normalize(q_mul(q_in, tpose_harness_pull))
            cal_q.feed_sample(seg, q_in, np.asarray(pkt.gyro), np.asarray(pkt.free_accel), sensor_id=pkt.sensor_id, from_hal=True)
    cal_q.finalize_static()
    sim.preset = "npose"
    sim.sample_at_time(0.0, dt=1.0 / 60.0)
    cal_q.start_straight(duration_s=0.2, complete_after=True)
    for k in range(12):
        for pkt in sim.sample_at_time(k / 60.0, dt=1.0 / 60.0):
            seg = _seg_for_sid(sim, pkt.sensor_id)
            cal_q.feed_sample(seg, np.asarray(pkt.quaternion), np.asarray(pkt.gyro), np.asarray(pkt.free_accel), sensor_id=pkt.sensor_id, from_hal=True)
    st_quick_done = cal_q.finalize_straight()
    assert st_quick_done["state"] == "calibrated" and st_quick_done["mode"] == "quick" and st_quick_done["straight_anchored"] is True
    for pkt in sim.sample_at_time(0.0, dt=1.0 / 60.0):
        seg = _seg_for_sid(sim, pkt.sensor_id)
        if seg in check_segs:
            err_q = q_angle_deg(cal_q.apply(seg, np.asarray(pkt.quaternion)), npose_gt[seg])
            assert err_q < 1.0, f"Error en flujo Rápido Solo para {seg}: {err_q:.3f}°"

    print(f"   -> OK: Distancias escapulares exactas (clavícula={dists['clavicle_l']:.3f}m, brazo={dists['upper_arm_l']:.3f}m) e inclinación recta máx={max_npose_err:.3f}° (<1.0°).")


def test_zupt_pelvis_and_floor_contact() -> None:
    """
    [EXTRA-ZUPT] Verifica:
      1) Estabilidad ZUPT del Root/Pelvis en postura quieta con micro-ruido (variación vertical < 2 mm, XZ fijo).
      2) Contacto exacto de plantas de pies con el plano Y = 0.000 ([-0.005, 0.005] m).
      3) Interpolación progresiva SLERP de los 4 segmentos de columna (Spine..Spine3) y cuello (Neck).
    """
    print("[EXTRA-ZUPT] Verificando ZUPT de Pelvis (<2 mm), piso Y=0 y columna 4 segmentos + cuello...")
    prof = AnthropometricProfile(id="qa_zupt", name="Sujeto 175", height_cm=175.0)
    skel = SkeletonModel(prof)
    fk = HierarchicalFKSolver(skel)
    fk.root_mode = "free_walk"

    from backend.hal.synthetic_simulator import Synthetic17SensorSimulator

    sim = Synthetic17SensorSimulator(lambda _p: None)
    base_npose, _ = sim.compute_biomechanical_pose(0.0, preset="npose")

    rng = np.random.default_rng(1234)
    pelvis_y_vals: list[float] = []
    pelvis_xz_vals: list[tuple[float, float]] = []
    min_foot_ys: list[float] = []

    for i in range(60):
        noisy_quats = {}
        for seg, q in base_npose.items():
            # Micro-vibración realista de IMU en reposo (±0.7°) sin velocidad angular > 0.45 rad/s
            delta = rng.normal(0.0, math.radians(0.18), size=3)
            noisy_quats[seg] = q_normalize(q_mul(q, q_from_axis_angle(delta, float(np.linalg.norm(delta)))))
        gyros = {
            "FOOT_L": np.array([0.08, 0.05, 0.04], dtype=np.float64),
            "FOOT_R": np.array([0.06, -0.07, 0.05], dtype=np.float64),
        }
        pose = fk.solve(noisy_quats, sensor_gyros=gyros, dt=1.0 / 120.0)
        assert fk.zupt_active is True, f"ZUPT debería estar activo en cuadro {i}"
        p_pos = pose.world_pos["PELVIS"]
        pelvis_y_vals.append(float(p_pos[1]))
        pelvis_xz_vals.append((float(p_pos[0]), float(p_pos[2])))
        min_foot_ys.append(float(pose.min_foot_y))

    vert_span = max(pelvis_y_vals) - min(pelvis_y_vals)
    assert vert_span < 0.002, f"Saltos verticales excesivos en Pelvis bajo ZUPT: {vert_span*1000:.2f} mm"
    assert all(xz == (0.0, 0.0) for xz in pelvis_xz_vals), f"Deriva XZ detectada bajo ZUPT: {pelvis_xz_vals[:5]}"
    assert all(-0.005 <= fy <= 0.005 for fy in min_foot_ys), f"Contacto fuera de piso Y=0: {min(min_foot_ys)}..{max(min_foot_ys)}"

    # Verificar curva SLERP progresiva en columna (Pelvis=0°, Chest=40°, Head=60°)
    fk_curve = HierarchicalFKSolver(skel)
    curved = dict(base_npose)
    curved["PELVIS"] = q_from_axis_angle([1.0, 0.0, 0.0], 0.0)
    curved["STERNUM"] = q_from_axis_angle([1.0, 0.0, 0.0], math.radians(40.0))
    curved["HEAD"] = q_from_axis_angle([1.0, 0.0, 0.0], math.radians(60.0))
    cpose = fk_curve.solve(curved)
    assert abs(q_angle_deg(cpose.world_quat["SPINE"], curved["PELVIS"]) - 8.0) < 0.2
    assert abs(q_angle_deg(cpose.world_quat["SPINE1"], curved["PELVIS"]) - 18.0) < 0.2
    assert abs(q_angle_deg(cpose.world_quat["SPINE2"], curved["PELVIS"]) - 30.0) < 0.2
    assert abs(q_angle_deg(cpose.world_quat["STERNUM"], curved["PELVIS"]) - 40.0) < 0.2
    assert abs(q_angle_deg(cpose.world_quat["NECK"], curved["PELVIS"]) - 49.0) < 0.2
    print(f"   -> OK: ZUPT Pelvis estable (variación={vert_span*1000:.2f} mm < 2 mm), piso Y∈[{min(min_foot_ys):.4f}, {max(min_foot_ys):.4f}] m y SLERP 4-segmentos verificado.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoría integral OpenMocap Studio")
    parser.add_argument("--no-hardware", action="store_true", help="Evita abrir puertos COM físicos o XsScanner (predeterminado)")
    parser.add_argument("--with-hardware", action="store_true", help="Habilita escaneo real sobre puertos COM/USB")
    args = parser.parse_args()
    no_hardware = True if (args.no_hardware or not args.with_hardware) else False

    with tempfile.TemporaryDirectory(prefix="openmocap_qa_") as tmpdir:
        import os

        os.environ["OPENMOCAP_DATA_DIR"] = tmpdir
        test_quaternion_and_fusion_math()
        test_multi_brand_parsers()
        test_xbus_awinda_protocol()
        test_xda_bridge_worker_swig_mock()
        test_realistic_mtw_calibration()
        test_pca_walk_360_disambiguation()
        test_scapula_anatomy_and_straight_check()
        test_zupt_pelvis_and_floor_contact()
        test_elbow_biomechanics_independent()
        test_security_and_hardening()
        asyncio.run(run_live_server_tests(no_hardware=no_hardware))
        test_blender_bridge_syntax()
    print("\n=== VERIFICACIÓN INTEGRAL EXITOSA: TODAS LAS PRUEBAS PASARON ===")


if __name__ == "__main__":
    main()

