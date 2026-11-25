from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.engine import MocapEngine
from backend.export.video_converter import convert_webm_to_mp4, resolve_ffmpeg_executable

engine = MocapEngine()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await engine.start()
    try:
        yield
    finally:
        await engine.stop()


app = FastAPI(
    title="OpenMocap Studio API",
    version="1.0.0",
    description="Backend HAL, calibración cinemática 120 Hz, exportación Blender y streaming WebSocket.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Modelos de solicitud ---


class DriverStartRequest(BaseModel):
    driver: Literal["simulator", "xsens_awinda", "serial_imu", "udp_osc", "ble_imu"]
    preset: str = "walk"
    rate_hz: int = 120
    channel: int = 11
    port: str = ""
    baudrate: int = 0
    udp_port: int = 9000
    addresses: list[str] = Field(default_factory=list)


class DriverStopRequest(BaseModel):
    driver: Literal["simulator", "xsens_awinda", "serial_imu", "udp_osc", "ble_imu", "all"]


class SimulatorConfigRequest(BaseModel):
    preset: Literal["walk", "jog", "squat", "tpose", "npose", "wave"] | None = None
    rate_hz: int | None = None
    randomize_imperfections: bool | None = None
    clear_imperfections: bool = False
    noise_std_rad: float = 0.0
    seed: int = 2026


class SimulatorShakeRequest(BaseModel):
    sensor_id: str
    duration_s: float = 0.6


class AssignSensorRequest(BaseModel):
    sensor_id: str
    segment: str


class CustomSegmentRequest(BaseModel):
    name: str
    parent: str = "PELVIS"
    offset_m: list[float] = Field(default_factory=lambda: [0.0, 0.1, 0.0])
    end_site_m: list[float] = Field(default_factory=lambda: [0.0, 0.1, 0.0])
    label_es: str | None = None
    sensor_id: str | None = None


class CalibrationStaticRequest(BaseModel):
    pose_type: Literal["tpose", "npose"] = "tpose"
    duration_s: float = 4.0
    mode: Literal["full", "quick"] = "full"


class CalibrationStraightRequest(BaseModel):
    duration_s: float = 3.0
    complete_after: bool = False


class CalibrationWalkRequest(BaseModel):
    duration_s: float = 6.0


class RecordingStartRequest(BaseModel):
    name: str | None = None


class PlaybackControlRequest(BaseModel):
    action: Literal["play", "pause", "stop", "live", "step_next", "step_prev"] | None = None
    frame_idx: int | None = None
    speed: float | None = None
    loop: bool | None = None
    trim_in: int | None = None
    trim_out: int | None = None


class FKModeRequest(BaseModel):
    mode: Literal["in_place", "free_walk"]


class ExportBVHRequest(BaseModel):
    file_name: str | None = None
    scale: float = 1.0
    naming: Literal["openmocap", "mixamo", "rigify"] = "openmocap"
    include_tpose_frame0: bool = True
    respect_trim: bool = True
    tpose_lead_in_out: bool = True


class ExportFBXRequest(BaseModel):
    file_name: str | None = None
    scale: float = 1.0
    naming: Literal["openmocap", "mixamo", "rigify"] = "openmocap"
    include_tpose_frame0: bool = True
    respect_trim: bool = True
    tpose_lead_in_out: bool = True


class BlenderPathRequest(BaseModel):
    blender_path: str


class AwindaReconnectRequest(BaseModel):
    channel: int | None = None
    rate_hz: int | None = None


# --- Endpoints Salud & WebSocket ---


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": "OpenMocap Studio",
        "ffmpeg_available": resolve_ffmpeg_executable() is not None,
        "blender": engine.blender.get_status(),
        "skeleton_segments": len(engine.skeleton.order),
        "rate_hz": round(engine._actual_stream_hz or float(engine._broadcast_hz), 1),
        "awinda": engine.xsens.get_status(),
        "simulator_running": engine.simulator.running,
    }


@app.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    engine.register_ws(websocket)
    try:
        while True:
            # Mantener socket abierto recibiendo comandos keep-alive opcionales
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        engine.unregister_ws(websocket)


# --- Endpoints Hardware HAL ---


@app.get("/api/hardware/awinda/status")
async def awinda_status() -> dict[str, Any]:
    return engine.xsens.get_status()


@app.post("/api/hardware/awinda/scan")
async def awinda_scan_all() -> dict[str, Any]:
    return await engine.xsens.scan_all_usb_ports(auto_connect=True)


@app.post("/api/hardware/awinda/reconnect")
async def awinda_reconnect(req: AwindaReconnectRequest | None = None) -> dict[str, Any]:
    channel = req.channel if req else None
    rate_hz = req.rate_hz if req else None
    return await engine.xsens.reconnect(channel=channel, rate_hz=rate_hz)


@app.get("/api/hardware/status")
async def hardware_status() -> dict[str, Any]:
    return {
        "drivers": engine.hal.get_all_statuses(),
        "sensors": list(engine.watchdog.get_diagnostics().values()),
        "mapping": engine.mapper.get_mapping_state(),
        "skeleton": engine.skeleton.to_summary(),
    }


@app.post("/api/hardware/scan")
async def hardware_scan() -> dict[str, Any]:
    awinda_stations = engine.xsens.scan_stations()
    serial_ports = engine.serial.list_ports()
    ble_devices = await engine.ble.scan_devices(timeout_s=2.5)
    return {
        "xsens_stations": awinda_stations,
        "serial_ports": serial_ports,
        "ble_devices": ble_devices,
        "drivers": engine.hal.get_all_statuses(),
    }


@app.post("/api/hardware/driver/start")
async def hardware_start_driver(req: DriverStartRequest) -> dict[str, Any]:
    if req.driver == "simulator":
        return await engine.simulator.start(preset=req.preset, rate_hz=req.rate_hz)  # type: ignore[arg-type]
    if req.driver == "xsens_awinda":
        return await engine.xsens.start(channel=req.channel, rate_hz=req.rate_hz, port_name=req.port or None)
    if req.driver == "serial_imu":
        return await engine.serial.start(port=req.port, baudrate=req.baudrate)
    if req.driver == "udp_osc":
        return await engine.udp.start(port=req.udp_port)
    if req.driver == "ble_imu":
        return await engine.ble.start(addresses=req.addresses or None)
    raise HTTPException(status_code=400, detail="Driver no soportado.")


@app.post("/api/hardware/driver/stop")
async def hardware_stop_driver(req: DriverStopRequest) -> dict[str, Any]:
    if req.driver == "all":
        await engine.hal.stop_all()
        return engine.hal.get_all_statuses()
    drv = engine.hal.drivers.get(req.driver)
    if not drv:
        raise HTTPException(status_code=404, detail="Driver no encontrado.")
    return await drv.stop()


@app.post("/api/hardware/ble/disconnect")
async def ble_disconnect() -> dict[str, Any]:
    return await engine.ble.stop()


@app.post("/api/hardware/simulator/config")
async def simulator_config(req: SimulatorConfigRequest) -> dict[str, Any]:
    if req.clear_imperfections:
        engine.simulator.clear_imperfections()
    if req.randomize_imperfections:
        engine.simulator.configure_imperfections(
            randomize=True,
            noise_std_rad=req.noise_std_rad,
            seed=req.seed,
        )
    if req.preset is not None or req.rate_hz is not None:
        await engine.simulator.start(
            preset=req.preset or engine.simulator.preset,
            rate_hz=req.rate_hz or engine.simulator.target_hz,
        )
    return engine.simulator.get_status()


@app.post("/api/hardware/simulator/shake")
async def simulator_shake(req: SimulatorShakeRequest) -> dict[str, Any]:
    engine.simulator.trigger_shake(req.sensor_id, duration_s=req.duration_s)
    return {"triggered": True, "sensor_id": req.sensor_id.upper()}


# --- Endpoints Mapeo Dinámico ---


@app.get("/api/mapping")
async def get_mapping() -> dict[str, Any]:
    return {
        "mapping": engine.mapper.get_mapping_state(),
        "skeleton": engine.skeleton.to_summary(),
    }


@app.post("/api/mapping/assign")
async def assign_mapping(req: AssignSensorRequest) -> dict[str, Any]:
    seg = req.segment.strip().upper()
    if seg not in engine.skeleton.segments:
        raise HTTPException(status_code=400, detail=f"Segmento desconocido: {seg}")
    mapping = engine.mapper.assign(req.sensor_id, seg, persist=True)
    engine.simulator.sensor_map = dict(mapping)
    return {"segment_to_sensor": mapping, "mapping": engine.mapper.get_mapping_state()}


@app.post("/api/mapping/unassign")
async def unassign_mapping(sensor_id: str) -> dict[str, Any]:
    mapping = engine.mapper.unassign_sensor(sensor_id)
    engine.simulator.sensor_map = dict(mapping)
    return {"segment_to_sensor": mapping}


@app.post("/api/mapping/add-custom")
async def add_custom_segment(req: CustomSegmentRequest) -> dict[str, Any]:
    try:
        prof = engine.profile_manager.add_custom_segment(
            name=req.name,
            parent=req.parent,
            offset_m=req.offset_m,
            end_site_m=req.end_site_m,
            label_es=req.label_es,
        )
        skel = engine.reload_skeleton()
        if req.sensor_id:
            clean_seg = req.name.strip().upper().replace(" ", "_")
            mapping = engine.mapper.assign(req.sensor_id, clean_seg, persist=True)
            engine.simulator.sensor_map = dict(mapping)
        return {"profile": prof.to_dict(), "skeleton": skel, "mapping": engine.mapper.get_mapping_state()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mapping/reset-default")
async def reset_mapping_default() -> dict[str, Any]:
    mapping = engine.mapper.reset_to_default_awinda()
    engine.simulator.sensor_map = dict(mapping)
    return {"segment_to_sensor": mapping}


# --- Endpoints Perfiles Antropométricos ---


@app.get("/api/profiles")
async def list_profiles() -> dict[str, Any]:
    return {
        "profiles": engine.profile_manager.list_profiles(),
        "active_skeleton": engine.skeleton.to_summary(),
    }


@app.post("/api/profiles")
async def upsert_profile(payload: dict[str, Any]) -> dict[str, Any]:
    prof = engine.profile_manager.upsert_profile(payload)
    skel = engine.reload_skeleton()
    return {"profile": prof.to_dict(), "profiles": engine.profile_manager.list_profiles(), "skeleton": skel}


@app.post("/api/profiles/{profile_id}/activate")
async def activate_profile(profile_id: str) -> dict[str, Any]:
    try:
        prof = engine.profile_manager.set_active_profile(profile_id)
        skel = engine.reload_skeleton()
        return {"profile": prof.to_dict(), "profiles": engine.profile_manager.list_profiles(), "skeleton": skel}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> dict[str, Any]:
    try:
        engine.profile_manager.delete_profile(profile_id)
        skel = engine.reload_skeleton()
        return {"profiles": engine.profile_manager.list_profiles(), "skeleton": skel}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- Endpoints Calibración ---


@app.get("/api/calibration/status")
async def calibration_status() -> dict[str, Any]:
    return engine.calibration.get_status()


@app.post("/api/calibration/start-static")
async def calibration_start_static(req: CalibrationStaticRequest) -> dict[str, Any]:
    return engine.start_calibration_static(pose_type=req.pose_type, duration_s=req.duration_s, mode=req.mode)


@app.post("/api/calibration/start-straight")
async def calibration_start_straight(req: CalibrationStraightRequest) -> dict[str, Any]:
    try:
        return engine.start_calibration_straight(duration_s=req.duration_s, complete_after=req.complete_after)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/calibration/complete-quick")
async def calibration_complete_quick() -> dict[str, Any]:
    return engine.complete_calibration_quick()


@app.post("/api/calibration/start-walk")
async def calibration_start_walk(req: CalibrationWalkRequest) -> dict[str, Any]:
    try:
        return engine.start_calibration_walk(duration_s=req.duration_s)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/calibration/reset")
async def calibration_reset() -> dict[str, Any]:
    return engine.reset_calibration()


@app.post("/api/calibration/heading-reset")
async def calibration_heading_reset() -> dict[str, Any]:
    return engine.heading_reset()


# --- Endpoints Grabación, Reproducción y FK ---


@app.post("/api/recording/start")
async def recording_start(req: RecordingStartRequest) -> dict[str, Any]:
    return engine.recorder.start_recording(req.name, engine.skeleton, fps=float(engine._internal_hz))


@app.post("/api/recording/stop")
async def recording_stop() -> dict[str, Any]:
    return engine.recorder.stop_recording(save_to_disk=True)


@app.get("/api/recording/takes")
async def recording_takes() -> dict[str, Any]:
    return {
        "takes": engine.recorder.list_takes(),
        "status": engine.recorder.get_status(),
    }


@app.post("/api/recording/load/{take_id}")
async def recording_load(take_id: str) -> dict[str, Any]:
    try:
        return engine.recorder.load_take(take_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/playback/control")
async def playback_control(req: PlaybackControlRequest) -> dict[str, Any]:
    try:
        return engine.recorder.control_playback(
            action=req.action,
            frame_idx=req.frame_idx,
            speed=req.speed,
            loop=req.loop,
            trim_in=req.trim_in,
            trim_out=req.trim_out,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/fk/mode")
async def set_fk_mode(req: FKModeRequest) -> dict[str, Any]:
    return engine.set_root_mode(req.mode)


# --- Endpoints Exportación Blender BVH / FBX y Video MP4 ---


@app.get("/api/export/blender-status")
async def blender_status() -> dict[str, Any]:
    return engine.blender.get_status()


@app.post("/api/export/blender-path")
async def set_blender_path(req: BlenderPathRequest) -> dict[str, Any]:
    try:
        path = engine.blender.set_custom_blender_path(req.blender_path)
        return {"blender_path": path, "status": engine.blender.get_status()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/export/bvh")
async def export_bvh_endpoint(req: ExportBVHRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            engine.export_bvh,
            file_name=req.file_name,
            scale=req.scale,
            naming=req.naming,
            include_tpose_frame0=req.include_tpose_frame0,
            respect_trim=req.respect_trim,
            tpose_lead_in_out=req.tpose_lead_in_out,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/export/fbx")
async def export_fbx_endpoint(req: ExportFBXRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            engine.export_fbx,
            file_name=req.file_name,
            scale=req.scale,
            naming=req.naming,
            include_tpose_frame0=req.include_tpose_frame0,
            respect_trim=req.respect_trim,
            tpose_lead_in_out=req.tpose_lead_in_out,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/video/convert-mp4")
async def video_convert_mp4(
    file: UploadFile = File(...),
    filename: str = Form(default=""),
    fps: int = Form(default=60),
) -> dict[str, Any]:
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="El archivo de video enviado está vacío.")
    base = Path(filename or file.filename or "captura_3d").stem
    out_mp4 = engine.dirs["videos"] / f"{base}.mp4"
    return await asyncio.to_thread(convert_webm_to_mp4, raw_bytes, out_mp4, fps=fps)


@app.get("/api/export/files")
async def list_export_files() -> dict[str, Any]:
    def scan(folder: Path) -> list[dict[str, Any]]:
        out = []
        for f in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file():
                out.append(
                    {
                        "name": f.name,
                        "path": str(f),
                        "size_kb": round(f.stat().st_size / 1024.0, 1),
                    }
                )
        return out

    return {
        "dirs": {k: str(v) for k, v in engine.dirs.items()},
        "bvh": scan(engine.dirs["bvh"]),
        "fbx": scan(engine.dirs["fbx"]),
        "videos": scan(engine.dirs["videos"]),
    }


@app.get("/api/export/download/{folder}/{filename}")
async def download_export(folder: Literal["bvh", "fbx", "videos"], filename: str):
    safe_name = Path(filename).name
    target = engine.dirs[folder] / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    return FileResponse(path=str(target), filename=safe_name)


def parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenMocap Studio Backend Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


if __name__ == "__main__":
    cli = parse_cli()
    uvicorn.run(app, host=cli.host, port=cli.port, log_level="info")

