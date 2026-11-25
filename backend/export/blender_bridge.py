from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.paths import get_blender_script_path


class BlenderFBXBridge:
    """
    Detecta instalaciones de Blender en Windows/Linux/macOS y ejecuta la conversión
    automatizada en segundo plano (.bvh -> .fbx compatible con Rigify y Mixamo).
    """

    def __init__(self, settings_dir: Path | None = None) -> None:
        self.settings_dir = settings_dir
        self.custom_blender_path: str | None = self._load_saved_path()

    def _load_saved_path(self) -> str | None:
        if not self.settings_dir:
            return None
        cfg = self.settings_dir / "blender_path.json"
        if cfg.exists():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                val = data.get("blender_path")
                if val and Path(val).exists():
                    return str(val)
            except Exception:
                pass
        return None

    def set_custom_blender_path(self, path_str: str) -> str:
        p = Path(path_str).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"No existe el ejecutable de Blender en: {p}")
        self.custom_blender_path = str(p)
        if self.settings_dir:
            self.settings_dir.mkdir(parents=True, exist_ok=True)
            (self.settings_dir / "blender_path.json").write_text(
                json.dumps({"blender_path": self.custom_blender_path}, indent=2),
                encoding="utf-8",
            )
        return self.custom_blender_path

    def detect_blender(self) -> str | None:
        if self.custom_blender_path and Path(self.custom_blender_path).exists():
            return self.custom_blender_path

        env_path = os.environ.get("BLENDER_EXE")
        if env_path and Path(env_path).exists():
            return env_path

        which_hit = shutil.which("blender")
        if which_hit:
            return which_hit

        win_bases = [
            Path(r"C:\Program Files\Blender Foundation"),
            Path(r"C:\Program Files (x86)\Blender Foundation"),
            Path.home() / "AppData" / "Local" / "Programs" / "Blender Foundation",
        ]
        candidates: list[Path] = []
        for base in win_bases:
            if base.exists():
                candidates.extend(base.glob("Blender*/blender.exe"))
        if candidates:
            candidates.sort(reverse=True)
            return str(candidates[0])
        return None

    def get_status(self) -> dict[str, Any]:
        exe = self.detect_blender()
        script = get_blender_script_path()
        return {
            "blender_found": exe is not None,
            "blender_path": exe,
            "script_path": str(script),
            "script_exists": script.exists(),
        }

    def convert_bvh_to_fbx(
        self,
        bvh_path: Path,
        fbx_path: Path,
        rig_preset: str = "openmocap",
        fps: float = 120.0,
        scale: float = 1.0,
    ) -> dict[str, Any]:
        blender_exe = self.detect_blender()
        if not blender_exe:
            raise FileNotFoundError(
                "No se encontró Blender instalado en el equipo. "
                "Instale Blender o seleccione manualmente blender.exe en la ventana de exportación."
            )
        script_path = get_blender_script_path()
        if not script_path.exists():
            raise FileNotFoundError(f"Falta el script puente de Blender: {script_path}")

        fbx_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            blender_exe,
            "--background",
            "--factory-startup",
            "--python",
            str(script_path),
            "--",
            "--input",
            str(bvh_path),
            "--output",
            str(fbx_path),
            "--rig-preset",
            rig_preset,
            "--fps",
            str(int(round(fps))),
            "--scale",
            str(float(scale)),
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if proc.returncode != 0 or not fbx_path.exists():
            raise RuntimeError(
                f"Error convirtiendo BVH a FBX en Blender (código {proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return {
            "file_path": str(fbx_path),
            "file_name": fbx_path.name,
            "blender_path": blender_exe,
            "rig_preset": rig_preset,
            "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
        }

