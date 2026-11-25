from __future__ import annotations

import os
import sys
from pathlib import Path


def get_app_root() -> Path:
    """Devuelve la raíz del proyecto en desarrollo o del paquete compilado."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_resource_root() -> Path:
    """Devuelve la raíz donde residen recursos empaquetados (config, blender_tools)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_user_data_root() -> Path:
    """Devuelve el directorio escribible para perfiles, tomas y exportaciones."""
    override = os.environ.get("OPENMOCAP_DATA_DIR")
    if override:
        root = Path(override).expanduser().resolve()
    elif getattr(sys, "frozen", False):
        local_app = os.environ.get("LOCALAPPDATA")
        base = Path(local_app) if local_app else Path.home()
        root = base / "OpenMocapStudio"
    else:
        root = Path(__file__).resolve().parent.parent
    return root


def get_config_dir() -> Path:
    res_cfg = get_resource_root() / "backend" / "config"
    if res_cfg.exists():
        return res_cfg
    direct_cfg = get_resource_root() / "config"
    if direct_cfg.exists():
        return direct_cfg
    return Path(__file__).resolve().parent / "config"


def get_blender_script_path() -> Path:
    candidates = [
        get_resource_root() / "blender_tools" / "convertir_a_fbx.py",
        get_app_root() / "blender_tools" / "convertir_a_fbx.py",
        get_app_root().parent / "blender_tools" / "convertir_a_fbx.py",
        Path(__file__).resolve().parent.parent / "blender_tools" / "convertir_a_fbx.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def ensure_runtime_dirs() -> dict[str, Path]:
    data_root = get_user_data_root()
    if not getattr(sys, "frozen", False):
        backend_data = data_root / "backend" / "data"
        exports_root = data_root / "exports"
    else:
        backend_data = data_root / "data"
        exports_root = data_root / "exports"

    dirs = {
        "data": backend_data,
        "profiles": backend_data / "profiles",
        "takes": backend_data / "takes",
        "settings": backend_data / "settings",
        "exports": exports_root,
        "bvh": exports_root / "bvh",
        "fbx": exports_root / "fbx",
        "videos": exports_root / "videos",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def get_settings_dir() -> Path:
    """Devuelve el directorio escribible de configuración persistente de usuario."""
    data_root = get_user_data_root()
    settings_dir = (data_root / "data" / "settings") if getattr(sys, "frozen", False) else (data_root / "backend" / "data" / "settings")
    settings_dir.mkdir(parents=True, exist_ok=True)
    return settings_dir

