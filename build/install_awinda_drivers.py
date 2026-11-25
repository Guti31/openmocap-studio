"""
Instalador unificado de 1 clic para controladores USB Xsens Awinda (VID_2639)
y Serie Virtual FTDI (ftdibus/ftdiport + CDM212364_Setup.exe WHQL).
"""

from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
from pathlib import Path

VALID_PNPUTIL_CODES = {0, 259, 3010}


def configure_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def resolve_usb_drivers_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "usb_drivers"
    return Path(__file__).resolve().parent / "usb_drivers"


def resolve_pnputil() -> str:
    sys_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidate = sys_root / "System32" / "pnputil.exe"
    if candidate.is_file():
        return str(candidate)
    return "pnputil.exe"


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_self_test(drivers_dir: Path) -> int:
    xsens_dir = drivers_dir / "xsens"
    ftdi_dir = drivers_dir / "ftdi"

    xsens_infs = sorted(xsens_dir.rglob("*.inf")) if xsens_dir.is_dir() else []
    xsens_cats = sorted(xsens_dir.rglob("*.cat")) if xsens_dir.is_dir() else []
    ftdi_infs = sorted(ftdi_dir.rglob("*.inf")) if ftdi_dir.is_dir() else []
    ftdi_cats = sorted(ftdi_dir.rglob("*.cat")) if ftdi_dir.is_dir() else []
    cdm_exe = ftdi_dir / "CDM212364_Setup.exe"

    print(f"[SELF-TEST] Directorio de drivers: {drivers_dir}")
    print(f"[SELF-TEST] Xsens -> {len(xsens_infs)} .inf, {len(xsens_cats)} .cat")
    for p in xsens_infs:
        print(f"  - {p.relative_to(drivers_dir)}")
    print(f"[SELF-TEST] FTDI  -> {len(ftdi_infs)} .inf, {len(ftdi_cats)} .cat, CDM212364_Setup.exe={cdm_exe.is_file()}")
    for p in ftdi_infs:
        print(f"  - {p.relative_to(drivers_dir)}")

    ok = bool(xsens_infs and xsens_cats and ftdi_infs and ftdi_cats)
    if not ok:
        print("[ERROR] Faltan archivos .inf o .cat requeridos en usb_drivers/xsens o usb_drivers/ftdi.", file=sys.stderr)
        return 1
    print("[OK] Paquete unificado de drivers verificado correctamente.")
    return 0


def install_inf_folder(pnputil_exe: str, folder: Path, label: str) -> tuple[bool, bool, int]:
    """Instala todos los paquetes .inf dentro de `folder` mediante pnputil."""
    infs = sorted(folder.rglob("*.inf")) if folder.is_dir() else []
    if not infs:
        print(f"[ERROR] No se encontraron archivos .inf en {folder}")
        return False, False, 1

    print(f"  Paquetes .inf encontrados: {len(infs)}")
    pattern = str(folder / "*.inf")
    cmd = [pnputil_exe, "/add-driver", pattern, "/subdirs", "/install"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)

    if proc.returncode in VALID_PNPUTIL_CODES:
        return True, (proc.returncode == 3010), proc.returncode

    print(f"  [AVISO] pnputil con comodín devolvió código {proc.returncode}; intentando instalación individual...")
    ok_count = 0
    needs_reboot = False
    last_code = proc.returncode
    for inf in infs:
        sub_proc = subprocess.run(
            [pnputil_exe, "/add-driver", str(inf), "/install"],
            capture_output=True,
            text=True,
            check=False,
        )
        last_code = sub_proc.returncode
        if sub_proc.returncode in VALID_PNPUTIL_CODES:
            ok_count += 1
            if sub_proc.returncode == 3010:
                needs_reboot = True
            print(f"    [OK] {inf.parent.name}/{inf.name} (código {sub_proc.returncode})")
        else:
            print(f"    [AVISO] {inf.parent.name}/{inf.name} devolvió código {sub_proc.returncode}")
            if sub_proc.stdout:
                print(f"      {sub_proc.stdout.strip()}")

    success = ok_count > 0
    if not success:
        print(f"[ERROR] No se pudo instalar ningún paquete .inf de {label}.")
    return success, needs_reboot, (0 if success else last_code)


def run_cdm_setup_silent(cdm_exe: Path) -> None:
    """Ejecuta el instalador oficial WHQL de FTDI de forma silenciosa como respaldo."""
    if not cdm_exe.is_file():
        print("[INFO] CDM212364_Setup.exe no está presente; se usan paquetes FTDI firmados.")
        return
    print("  Ejecutando respaldo oficial FTDI WHQL (CDM212364_Setup.exe /S)...")
    try:
        proc = subprocess.run(
            [str(cdm_exe), "/S"],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if proc.returncode == 0:
            print("  [OK] CDM212364_Setup.exe completado correctamente.")
        else:
            print(
                f"  [AVISO] CDM212364_Setup.exe finalizó con código {proc.returncode}; "
                "los drivers FTDI firmados ya fueron registrados vía pnputil."
            )
    except subprocess.TimeoutExpired:
        print(
            "  [AVISO] CDM212364_Setup.exe excedió 90 s esperando cierre; "
            "los drivers FTDI firmados ya quedaron registrados vía pnputil."
        )
    except Exception as exc:
        print(f"  [AVISO] No se pudo ejecutar CDM212364_Setup.exe ({exc}).")


def pause_before_exit(no_pause: bool) -> None:
    if no_pause:
        return
    try:
        input("\nPresiona ENTER para cerrar esta ventana...")
    except EOFError:
        pass


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(
        description="Instalador unificado de drivers Xsens Awinda (VID_2639) + FTDI Virtual COM (COMx)."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Verifica la integridad de los paquetes de drivers incluidos sin modificar Windows.",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Finaliza sin esperar confirmación con Enter.",
    )
    args = parser.parse_args()

    drivers_dir = resolve_usb_drivers_dir()
    if args.self_test:
        return run_self_test(drivers_dir)

    print("======================================================================")
    print("  OpenMocap Studio · Instalador de Drivers Xsens Awinda + FTDI Serial ")
    print("======================================================================")

    if not is_admin():
        print(
            "[AVISO] Este instalador requiere permisos de Administrador para registrar controladores.\n"
            "        Si falla el registro, haz clic derecho -> 'Ejecutar como administrador'."
        )

    pnputil_exe = resolve_pnputil()
    xsens_dir = drivers_dir / "xsens"
    ftdi_dir = drivers_dir / "ftdi"

    print("\n[Paso 1/2] Instalación de Driver USB Xsens (VID_2639)...")
    xsens_ok, xsens_reboot, _ = install_inf_folder(pnputil_exe, xsens_dir, "Driver USB Xsens (VID_2639)")

    print("\n[Paso 2/2] Instalación de Driver Serie Virtual FTDI (COMx)...")
    ftdi_ok, ftdi_reboot, _ = install_inf_folder(pnputil_exe, ftdi_dir, "Driver Serie Virtual FTDI (COMx)")
    run_cdm_setup_silent(ftdi_dir / "CDM212364_Setup.exe")

    print("\n======================================================================")
    print("  RESUMEN DE INSTALACIÓN DE CONTROLADORES")
    print("======================================================================")
    print(f"  [{'OK' if xsens_ok else 'ERROR'}] Driver USB Xsens (VID_2639)")
    print(f"  [{'OK' if ftdi_ok else 'ERROR'}] Driver Serie Virtual FTDI (COMx)")

    if xsens_reboot or ftdi_reboot:
        print("\n[IMPORTANTE] Windows recomendó reiniciar el equipo para completar la activación.")

    if xsens_ok and ftdi_ok:
        print("\nListo. Ya puedes conectar la estación/dongle USB Xsens Awinda y abrir OpenMocap Studio.")
        pause_before_exit(args.no_pause)
        return 0

    print("\n[ATENCIÓN] Revisa los mensajes anteriores y vuelve a ejecutar como Administrador.")
    pause_before_exit(args.no_pause)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
