# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['c:/APLICACION_TRAJE/build/install_awinda_drivers.py'],
    pathex=[],
    binaries=[],
    datas=[('c:/APLICACION_TRAJE/build/usb_drivers', 'usb_drivers')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Drivers_Xsens_Awinda_Win64',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon=['c:/APLICACION_TRAJE/build/icon.ico'],
)
