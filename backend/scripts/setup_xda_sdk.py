from __future__ import annotations

import datetime as dt
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.paths import get_settings_dir

CONFIG_OUT = get_settings_dir() / "xda_paths.json" if getattr(sys, "frozen", False) else (ROOT / "backend" / "config" / "xda_paths.json")
XDA_VENV_PYTHON = ROOT / "backend" / ".venv_xda" / "Scripts" / "python.exe"


def _candidate_roots() -> list[Path]:
    home = Path.home()
    roots = [
        ROOT / "backend" / "xda_sdk",
        Path(r"C:\Program Files\Movella"),
        Path(r"C:\Program Files\Xsens"),
        Path(r"C:\Program Files (x86)\Movella"),
        Path(r"C:\Program Files (x86)\Xsens"),
        Path(r"C:\Movella"),
        Path(r"C:\Xsens"),
        home / "Downloads",
        home / "Documents",
        home / "Desktop",
        home / "AppData" / "Local",
        home / "AppData" / "Roaming",
    ]
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        drv = Path(f"{letter}:\\")
        if drv.exists():
            roots.append(drv)
    return [r for r in roots if r.exists()]


def _is_compatible_wheel(whl: Path) -> bool:
    name = whl.name.lower()
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    arch_ok = ("win_amd64" in name) or ("any" in name) or ("win" not in name)
    py_ok = (py_tag in name) or ("py3-none" in name) or ("cp3-" in name)
    return arch_ok and py_ok


def _probe_xda_python(py_exe: Path, dll_dirs: list[str], python_dirs: list[str]) -> tuple[bool, str | None, str | None]:
    """Verifica mediante subproceso si un intérprete Python (ej. .venv_xda) importa xsensdeviceapi."""
    if not py_exe.exists():
        return False, None, None
    probe_code = (
        "import json, os, sys\n"
        f"dll_dirs = {json.dumps(dll_dirs)}\n"
        f"py_dirs = {json.dumps(python_dirs)}\n"
        "handles = []\n"
        "if sys.platform == 'win32' and hasattr(os, 'add_dll_directory'):\n"
        "    for d in dll_dirs:\n"
        "        if os.path.isdir(d):\n"
        "            try:\n"
        "                handles.append(os.add_dll_directory(d))\n"
        "            except OSError:\n"
        "                pass\n"
        "for p in py_dirs:\n"
        "    if os.path.isdir(p) and p not in sys.path:\n"
        "        sys.path.insert(0, p)\n"
        "import xsensdeviceapi as xda\n"
        "ver = ''\n"
        "try:\n"
        "    v = xda.XsVersion()\n"
        "    xda.xdaVersion(v)\n"
        "    ver = v.toXsString()\n"
        "except Exception:\n"
        "    ver = getattr(xda, '__version__', '') or 'unknown'\n"
        "print(json.dumps({'ok': True, 'version': ver, 'file': getattr(xda, '__file__', '')}))\n"
    )
    proc = subprocess.run(
        [str(py_exe), "-c", probe_code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if proc.returncode != 0:
        return False, None, None
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                if data.get("ok"):
                    return True, str(data.get("version") or ""), str(data.get("file") or "")
            except json.JSONDecodeError:
                pass
    return False, None, None


def discover_and_setup_xda() -> dict[str, Any]:
    """
    Escanea rutas estándar de Windows, backend/xda_sdk y backend/.venv_xda en busca de wheels
    xsensdeviceapi*.whl, DLLs nativas (xsensdeviceapi64.dll / xstypes64.dll) y puente Python 3.10.
    Guarda el resultado en backend/config/xda_paths.json.
    """
    wheels_found: list[Path] = []
    dll_dirs: set[str] = set()
    python_dirs: set[str] = set()
    installed_wheel: str | None = None

    for base in _candidate_roots():
        base_depth = len(base.parts)
        for root_dir, dirs, files in os.walk(base):
            rpath = Path(root_dir)
            depth = len(rpath.parts) - base_depth
            low_dir = root_dir.lower()
            # Evitar recorrer carpetas enormes ajenas dentro de AppData o discos completos
            if depth >= 1 and any(
                skip in low_dir
                for skip in (
                    "\\google\\",
                    "\\microsoft\\",
                    "\\packages\\",
                    "\\temp\\",
                    "\\cache\\",
                    "\\node_modules",
                    "\\windowsapps",
                    "\\.venv",
                )
            ):
                dirs[:] = []
                continue
            if depth >= 4 and not any(k in low_dir for k in ("xsens", "movella", "awinda", "xda_sdk")):
                dirs[:] = []
                continue
            for fname in files:
                low = fname.lower()
                if low.startswith("xsensdeviceapi") and low.endswith(".whl"):
                    wheels_found.append(rpath / fname)
                elif low in ("xsensdeviceapi64.dll", "xstypes64.dll", "xsensdeviceapi32.dll", "xstypes32.dll"):
                    dll_dirs.add(str(rpath))
                elif low == "__init__.py" and rpath.name.lower() == "xsensdeviceapi":
                    python_dirs.add(str(rpath.parent))
                    dll_dirs.add(str(rpath))

    # Detectar también DLLs incluidas dentro de backend/.venv_xda/Lib/site-packages/xsensdeviceapi
    xda_site_pkg = ROOT / "backend" / ".venv_xda" / "Lib" / "site-packages" / "xsensdeviceapi"
    if xda_site_pkg.is_dir():
        dll_dirs.add(str(xda_site_pkg))

    sorted_dlls = sorted(dll_dirs)
    sorted_py_dirs = sorted(python_dirs)

    # Intentar importar o instalar wheel compatible en el intérprete actual
    inproc_ok = False
    xda_version: str | None = None
    try:
        mod = importlib.import_module("xsensdeviceapi")
        inproc_ok = True
        try:
            v = mod.XsVersion()
            mod.xdaVersion(v)
            xda_version = v.toXsString()
        except Exception:
            xda_version = None
    except ImportError:
        compat_wheels = [w for w in wheels_found if _is_compatible_wheel(w)]
        for whl in compat_wheels:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-deps", str(whl)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode == 0:
                installed_wheel = str(whl)
                break

        for ddir in sorted_dlls:
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(ddir)
                except OSError:
                    pass
        for pdir in sorted_py_dirs:
            if pdir not in sys.path:
                sys.path.insert(0, pdir)
        try:
            mod = importlib.import_module("xsensdeviceapi")
            inproc_ok = True
            try:
                v = mod.XsVersion()
                mod.xdaVersion(v)
                xda_version = v.toXsString()
            except Exception:
                xda_version = None
        except ImportError:
            inproc_ok = False

    # Verificar el intérprete puente dedicado Python 3.10 (.venv_xda)
    bridge_ready = False
    bridge_ver: str | None = None
    if XDA_VENV_PYTHON.exists():
        bridge_ready, bridge_ver, _ = _probe_xda_python(XDA_VENV_PYTHON, sorted_dlls, sorted_py_dirs)
        if not bridge_ready:
            cp310_wheels = [w for w in wheels_found if "cp310" in w.name.lower() and "win_amd64" in w.name.lower()]
            for whl in cp310_wheels:
                proc = subprocess.run(
                    [str(XDA_VENV_PYTHON), "-m", "pip", "install", "--no-deps", str(whl)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if proc.returncode == 0:
                    installed_wheel = str(whl)
                    bridge_ready, bridge_ver, _ = _probe_xda_python(XDA_VENV_PYTHON, sorted_dlls, sorted_py_dirs)
                    if bridge_ready:
                        break
        elif not installed_wheel:
            cp310_wheels = [w for w in wheels_found if "cp310" in w.name.lower() and "win_amd64" in w.name.lower()]
            if cp310_wheels:
                installed_wheel = str(cp310_wheels[0])

    if not xda_version and bridge_ver:
        xda_version = bridge_ver

    sdk_installed = inproc_ok or bridge_ready

    if inproc_ok:
        msg = "SDK oficial Xsens Device API (xsensdeviceapi) activo en el intérprete principal."
    elif bridge_ready:
        msg = (
            f"SDK oficial Xsens Device API ({xda_version or 'XDA'}) listo vía puente dedicado "
            "Python 3.10 (backend/.venv_xda)."
        )
    elif wheels_found:
        msg = (
            f"Se encontraron wheels XDA ({wheels_found[0].name}), pero falta entorno compatible; "
            "se usará el motor nativo Xbus USB Serial."
        )
    else:
        msg = (
            "No se encontró Movella/Xsens MT Software Suite instalado localmente; "
            "se habilitará automáticamente el protocolo nativo Xbus USB Serial."
        )

    payload = {
        "sdk_installed": sdk_installed,
        "xda_bridge_ready": bridge_ready,
        "xda_python_exe": str(XDA_VENV_PYTHON) if bridge_ready else None,
        "xda_version": xda_version,
        "installed_wheel": installed_wheel,
        "wheels_discovered": [str(w) for w in wheels_found],
        "dll_dirs": sorted_dlls,
        "python_dirs": sorted_py_dirs,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "message_es": msg,
    }
    CONFIG_OUT.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = discover_and_setup_xda()
    print(json.dumps(result, indent=2, ensure_ascii=False))

