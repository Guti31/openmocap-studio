from __future__ import annotations

import gzip
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.kinematics.anthropometry import SkeletonModel


@dataclass
class TakeFrame:
    timestamp_s: float
    world_pos: dict[str, list[float]]
    world_quat: dict[str, list[float]]
    local_quat: dict[str, list[float]]
    end_pos: dict[str, list[float]]
    angles: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": round(self.timestamp_s, 5),
            "world_pos": self.world_pos,
            "world_quat": self.world_quat,
            "local_quat": self.local_quat,
            "end_pos": self.end_pos,
            "angles": self.angles,
        }


class TakeRecorder:
    """
    Grabador y reproductor de tomas cuadro por cuadro a 120 Hz en formato .omocap (JSON gzip).
    Soporta recorte (trim_in / trim_out), velocidad variable (0.25x - 2.0x) y bucle.
    """

    def __init__(self, takes_dir: Path) -> None:
        self.takes_dir = takes_dir
        self.takes_dir.mkdir(parents=True, exist_ok=True)

        self.is_recording: bool = False
        self.recording_name: str = ""
        self._rec_start_mono: float = 0.0
        self.frames: list[dict[str, Any]] = []
        self.skeleton_snapshot: dict[str, Any] = {}
        self.fps: float = 120.0
        self.active_take_id: str | None = None

        # Estado de reproducción
        self.mode: str = "live"  # "live" | "playback"
        self.playing: bool = False
        self.loop: bool = True
        self.speed: float = 1.0
        self.current_frame_idx: int = 0
        self.trim_in: int = 0
        self.trim_out: int = 0
        self._play_acc_s: float = 0.0
        self._last_play_tick: float = time.monotonic()

    @staticmethod
    def _safe_filename(name: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_\-\s]", "_", name).strip().replace(" ", "_")
        return clean or f"toma_{int(time.time())}"

    def start_recording(self, name: str | None, skeleton: SkeletonModel, fps: float = 120.0) -> dict[str, Any]:
        self.mode = "live"
        self.playing = False
        self.is_recording = True
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.recording_name = (name or f"Captura_{stamp}").strip()
        self.fps = float(max(30.0, min(200.0, fps)))
        self.frames = []
        self.skeleton_snapshot = skeleton.to_summary()
        self._rec_start_mono = time.monotonic()
        self.trim_in = 0
        self.trim_out = 0
        self.current_frame_idx = 0
        return self.get_status()

    def record_frame(
        self,
        world_pos: dict[str, list[float]],
        world_quat: dict[str, list[float]],
        local_quat: dict[str, list[float]],
        end_pos: dict[str, list[float]],
        angles: dict[str, dict[str, float]],
    ) -> None:
        if not self.is_recording:
            return
        t_s = time.monotonic() - self._rec_start_mono
        self.frames.append(
            {
                "t": round(t_s, 5),
                "world_pos": world_pos,
                "world_quat": world_quat,
                "local_quat": local_quat,
                "end_pos": end_pos,
                "angles": angles,
            }
        )

    def stop_recording(self, save_to_disk: bool = True) -> dict[str, Any]:
        if not self.is_recording:
            return self.get_status()
        self.is_recording = False
        if self.frames:
            self.trim_in = 0
            self.trim_out = len(self.frames) - 1
            self.current_frame_idx = 0
            duration = float(self.frames[-1]["t"]) if len(self.frames) > 1 else (len(self.frames) / self.fps)
            if duration > 0.05 and len(self.frames) > 2:
                self.fps = round((len(self.frames) - 1) / duration, 2)
            if save_to_disk:
                self.save_current_take()
        return self.get_status()

    @staticmethod
    def _meta_path(omocap_path: Path) -> Path:
        return omocap_path.with_name(f"{omocap_path.name}.meta.json")

    def save_current_take(self) -> str:
        if not self.frames:
            raise ValueError("No hay fotogramas capturados para guardar.")
        safe = self._safe_filename(self.recording_name)
        file_name = f"{safe}.omocap"
        target = self.takes_dir / file_name
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        fc = len(self.frames)
        payload = {
            "format": "openmocap-take-v1",
            "name": self.recording_name,
            "created_at": created_at,
            "fps": self.fps,
            "frame_count": fc,
            "trim_in": self.trim_in,
            "trim_out": self.trim_out,
            "skeleton": self.skeleton_snapshot,
            "frames": self.frames,
        }
        with gzip.open(target, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)

        meta = {
            "take_id": file_name,
            "name": self.recording_name,
            "created_at": created_at,
            "fps": float(self.fps),
            "frame_count": fc,
            "duration_s": round(fc / max(1.0, float(self.fps)), 2),
            "size_kb": round(target.stat().st_size / 1024.0, 1),
        }
        try:
            self._meta_path(target).write_text(
                json.dumps(meta, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

        self.active_take_id = file_name
        return file_name

    def list_takes(self) -> list[dict[str, Any]]:
        takes: list[dict[str, Any]] = []
        for fpath in sorted(self.takes_dir.glob("*.omocap"), key=lambda p: p.stat().st_mtime, reverse=True):
            meta_file = self._meta_path(fpath)
            if meta_file.exists():
                try:
                    mdata = json.loads(meta_file.read_text(encoding="utf-8"))
                    if isinstance(mdata, dict) and "frame_count" in mdata:
                        takes.append(mdata)
                        continue
                except Exception:
                    pass
            try:
                with gzip.open(fpath, "rt", encoding="utf-8") as fh:
                    data = json.load(fh)
                fc = int(data.get("frame_count") or len(data.get("frames", [])))
                fps = float(data.get("fps") or 120.0)
                meta = {
                    "take_id": fpath.name,
                    "name": str(data.get("name") or fpath.stem),
                    "created_at": str(data.get("created_at") or ""),
                    "fps": fps,
                    "frame_count": fc,
                    "duration_s": round(fc / max(1.0, fps), 2),
                    "size_kb": round(fpath.stat().st_size / 1024.0, 1),
                }
                takes.append(meta)
                try:
                    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
                except OSError:
                    pass
            except Exception:
                continue
        return takes

    def load_take(self, take_id: str) -> dict[str, Any]:
        safe_name = Path(take_id).name
        if not safe_name or safe_name != take_id or "/" in take_id or "\\" in take_id or ".." in take_id:
            raise ValueError("Nombre de toma inválido.")
        base_dir = self.takes_dir.resolve()
        target = (base_dir / safe_name).resolve()
        if target.parent != base_dir:
            raise ValueError("Ruta de toma no permitida.")
        if not target.exists():
            raise FileNotFoundError(f"Toma no encontrada: {safe_name}")
        with gzip.open(target, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
        self.is_recording = False
        self.recording_name = str(data.get("name") or target.stem)
        self.fps = float(data.get("fps") or 120.0)
        self.frames = list(data.get("frames") or [])
        self.skeleton_snapshot = dict(data.get("skeleton") or {})
        self.trim_in = max(0, min(len(self.frames) - 1, int(data.get("trim_in", 0))))
        self.trim_out = max(self.trim_in, min(len(self.frames) - 1, int(data.get("trim_out", max(0, len(self.frames) - 1)))))
        self.current_frame_idx = self.trim_in
        self.active_take_id = safe_name
        self.mode = "playback"
        self.playing = False
        return self.get_status()

    def set_mode(self, mode: str) -> dict[str, Any]:
        if mode == "live":
            self.mode = "live"
            self.playing = False
        elif mode == "playback":
            if not self.frames:
                raise ValueError("No hay ninguna toma cargada o grabada para reproducir.")
            self.mode = "playback"
        return self.get_status()

    def control_playback(
        self,
        action: str | None = None,
        frame_idx: int | None = None,
        speed: float | None = None,
        loop: bool | None = None,
        trim_in: int | None = None,
        trim_out: int | None = None,
    ) -> dict[str, Any]:
        if speed is not None:
            self.speed = max(0.1, min(4.0, float(speed)))
        if loop is not None:
            self.loop = bool(loop)
        max_idx = max(0, len(self.frames) - 1)
        if trim_in is not None:
            self.trim_in = max(0, min(max_idx, int(trim_in)))
            if self.trim_out < self.trim_in:
                self.trim_out = self.trim_in
        if trim_out is not None:
            self.trim_out = max(self.trim_in, min(max_idx, int(trim_out)))
        if frame_idx is not None and self.frames:
            self.current_frame_idx = max(0, min(max_idx, int(frame_idx)))
            self.mode = "playback"

        if action == "play" and self.frames:
            self.mode = "playback"
            if self.current_frame_idx < self.trim_in or self.current_frame_idx >= self.trim_out:
                self.current_frame_idx = self.trim_in
            self.playing = True
            self._last_play_tick = time.monotonic()
            self._play_acc_s = 0.0
        elif action == "pause":
            self.playing = False
        elif action == "stop":
            self.playing = False
            self.current_frame_idx = self.trim_in
        elif action == "live":
            self.playing = False
            self.mode = "live"
        elif action == "step_next" and self.frames:
            self.mode = "playback"
            self.playing = False
            self.current_frame_idx = min(max_idx, self.current_frame_idx + 1)
        elif action == "step_prev" and self.frames:
            self.mode = "playback"
            self.playing = False
            self.current_frame_idx = max(0, self.current_frame_idx - 1)

        return self.get_status()

    def step_playback(self) -> dict[str, Any] | None:
        """Avanza el cursor de reproducción según velocidad y devuelve el fotograma actual."""
        if self.mode != "playback" or not self.frames:
            return None
        now = time.monotonic()
        dt = now - self._last_play_tick
        self._last_play_tick = now

        if self.playing:
            frame_dur = 1.0 / max(1.0, self.fps)
            self._play_acc_s += dt * self.speed
            steps = int(self._play_acc_s / frame_dur)
            if steps > 0:
                self._play_acc_s -= steps * frame_dur
                nxt = self.current_frame_idx + steps
                if nxt > self.trim_out:
                    if self.loop:
                        span = max(1, (self.trim_out - self.trim_in + 1))
                        self.current_frame_idx = self.trim_in + ((nxt - self.trim_in) % span)
                    else:
                        self.current_frame_idx = self.trim_out
                        self.playing = False
                else:
                    self.current_frame_idx = nxt

        idx = max(0, min(len(self.frames) - 1, self.current_frame_idx))
        return self.frames[idx]

    def get_trimmed_frames(self, respect_trim: bool = True) -> list[dict[str, Any]]:
        if not self.frames:
            return []
        if not respect_trim:
            return list(self.frames)
        start = max(0, min(len(self.frames) - 1, self.trim_in))
        end = max(start, min(len(self.frames) - 1, self.trim_out))
        return self.frames[start : end + 1]

    def get_status(self) -> dict[str, Any]:
        fc = len(self.frames)
        dur = round(fc / max(1.0, self.fps), 2) if fc else 0.0
        return {
            "mode": self.mode,
            "is_recording": self.is_recording,
            "recording_name": self.recording_name,
            "active_take_id": self.active_take_id,
            "fps": self.fps,
            "frame_count": fc,
            "duration_s": dur,
            "playing": self.playing,
            "loop": self.loop,
            "speed": self.speed,
            "current_frame": self.current_frame_idx,
            "trim_in": self.trim_in,
            "trim_out": self.trim_out,
        }

