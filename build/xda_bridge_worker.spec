# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).resolve().parent
DLL_DIR = ROOT / "backend" / "xda_sdk" / "dll64"

binaries = []
if DLL_DIR.is_dir():
    for dll in sorted(DLL_DIR.glob("*.dll")):
        binaries.append((str(dll), "xda_dll64"))

binaries += collect_dynamic_libs("xsensdeviceapi")
datas = collect_data_files("xsensdeviceapi")

hiddenimports = [
    "numpy",
    "xsensdeviceapi",
    "xsensdeviceapi.xsensdeviceapi_py310_64",
    "xsensdeviceapi._xsensdeviceapi_py310_64",
]

a = Analysis(
    [str(ROOT / "backend" / "hal" / "xda_bridge_worker.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "scipy", "fastapi", "uvicorn", "bleak"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="xda-bridge-worker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
)
