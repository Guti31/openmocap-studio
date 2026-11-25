# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "backend" / "config" / "default_awinda_17.json"), "backend/config"),
    (str(ROOT / "blender_tools"), "blender_tools"),
]
datas += collect_data_files("imageio_ffmpeg")

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("websockets")
    + collect_submodules("serial")
    + collect_submodules("bleak")
    + [
        "scipy.linalg",
        "scipy.spatial.transform",
        "multipart",
        "python_multipart",
        "imageio_ffmpeg",
    ]
)

a = Analysis(
    [str(ROOT / "backend" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "pluggy", "watchfiles", "httpx"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="openmocap-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="backend",
)

