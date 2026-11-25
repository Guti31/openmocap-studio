from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def resolve_ffmpeg_executable() -> str | None:
    """Localiza ffmpeg en el PATH del sistema o mediante el binario integrado de imageio-ffmpeg."""
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass
    return None


def convert_webm_to_mp4(webm_bytes: bytes, output_mp4_path: Path, fps: int = 60) -> dict[str, Any]:
    """Convierte un flujo WebM grabado del visor 3D hacia MP4 H.264 compatible universalmente."""
    ffmpeg = resolve_ffmpeg_executable()
    output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
    temp_webm = output_mp4_path.with_suffix(".webm")
    temp_webm.write_bytes(webm_bytes)

    if not ffmpeg:
        return {
            "converted_mp4": False,
            "file_path": str(temp_webm),
            "file_name": temp_webm.name,
            "message_es": "FFmpeg no disponible; se guardó la grabación en formato WebM.",
        }

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(temp_webm),
        "-r",
        str(max(24, min(120, int(fps)))),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_mp4_path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if proc.returncode != 0 or not output_mp4_path.exists():
        return {
            "converted_mp4": False,
            "file_path": str(temp_webm),
            "file_name": temp_webm.name,
            "message_es": f"Fallo al transcodificar a MP4 ({proc.stderr[-250:]}); se conservó WebM.",
        }

    try:
        temp_webm.unlink()
    except OSError:
        pass

    return {
        "converted_mp4": True,
        "file_path": str(output_mp4_path),
        "file_name": output_mp4_path.name,
        "ffmpeg_path": ffmpeg,
        "message_es": f"Video MP4 guardado correctamente: {output_mp4_path.name}",
    }

