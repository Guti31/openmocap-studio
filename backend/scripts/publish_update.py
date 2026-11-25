"""
Script autónomo para publicar nuevas versiones de OpenMocap Studio hacia GitHub Releases (Guti31/openmocap-studio).
Flujo:
  1. Incrementa o fija la versión en frontend/package.json (y actualiza package-lock.json si aplica).
  2. Compila backend, worker XDA, frontend y NSIS + latest.yml + .blockmap vía GENERAR_INSTALADOR.bat.
  3. Ejecuta git add / commit / push hacia origin main.
  4. Publica el Release v<VERSION> en GitHub adjuntando el instalador .exe, latest.yml y .blockmap.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PKG_JSON = ROOT / "frontend" / "package.json"
PKG_LOCK = ROOT / "frontend" / "package-lock.json"
DIST_INSTALLER = ROOT / "dist_installer"


def resolve_tool(name: str, extra_candidates: list[Path]) -> str:
    found = shutil.which(name)
    if found:
        return found
    for cand in extra_candidates:
        if cand.is_file():
            return str(cand)
    raise FileNotFoundError(
        f"No se encontró '{name}'. Instálalo o agrégalo al PATH antes de publicar actualizaciones."
    )


def bump_semver(current: str, mode: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", current.strip())
    if not m:
        raise ValueError(f"Versión actual inválida en package.json: '{current}'")
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if mode == "major":
        return f"{major + 1}.0.0"
    if mode == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def run_step(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"\n> {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(cwd or ROOT), text=True, check=False)
    if check and proc.returncode != 0:
        raise RuntimeError(f"El comando falló con código {proc.returncode}: {' '.join(cmd)}")
    return proc


def main() -> int:
    parser = argparse.ArgumentParser(description="Publicador en 1 clic de OpenMocap Studio (GitHub Releases)")
    parser.add_argument("--version", type=str, default="", help="Versión explícita X.Y.Z (ej. 1.0.1)")
    parser.add_argument("--bump", choices=["patch", "minor", "major"], default="patch", help="Tipo de incremento")
    parser.add_argument("--notes", type=str, default="", help="Notas de la versión para GitHub Release")
    parser.add_argument("--skip-build", action="store_true", help="Omite GENERAR_INSTALADOR.bat si ya compilaste")
    args = parser.parse_args()

    git_exe = resolve_tool(
        "git",
        [
            Path(r"C:\Program Files\Git\cmd\git.exe"),
            Path(r"C:\Program Files\Git\bin\git.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "git.exe",
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Microsoft"
            / "WinGet"
            / "Packages"
            / "Git.MinGit_Microsoft.Winget.Source_8wekyb3d8bbwe"
            / "cmd"
            / "git.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "cmd" / "git.exe",
        ],
    )
    gh_exe = resolve_tool(
        "gh",
        [
            Path(r"C:\Program Files\GitHub CLI\gh.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHub CLI" / "gh.exe",
        ],
    )

    pkg_data = json.loads(PKG_JSON.read_text(encoding="utf-8"))
    old_version = str(pkg_data["version"]).strip()

    if args.version.strip():
        new_version = args.version.strip().lstrip("vV")
        if not re.match(r"^\d+\.\d+\.\d+$", new_version):
            raise ValueError(f"Formato de versión inválido: '{new_version}' (usa X.Y.Z)")
    else:
        new_version = bump_semver(old_version, args.bump)

    print(f"[INFO] Versión actual: {old_version} -> Nueva versión a publicar: {new_version}")

    pkg_data["version"] = new_version
    PKG_JSON.write_text(json.dumps(pkg_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if PKG_LOCK.exists():
        try:
            lock_data = json.loads(PKG_LOCK.read_text(encoding="utf-8"))
            lock_data["version"] = new_version
            if isinstance(lock_data.get("packages"), dict) and "" in lock_data["packages"]:
                lock_data["packages"][""]["version"] = new_version
            PKG_LOCK.write_text(json.dumps(lock_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass

    if not args.skip_build:
        run_step(["cmd", "/c", str(ROOT / "GENERAR_INSTALADOR.bat")], cwd=ROOT)

    exe_path = DIST_INSTALLER / f"OpenMocap Studio Setup {new_version}.exe"
    yml_path = DIST_INSTALLER / "latest.yml"
    blockmap_path = DIST_INSTALLER / f"OpenMocap Studio Setup {new_version}.exe.blockmap"

    for artifact in (exe_path, yml_path, blockmap_path):
        if not artifact.is_file():
            raise FileNotFoundError(f"No se encontró el artefacto requerido para auto-updater: {artifact}")

    notes = args.notes.strip() or (
        f"Actualización OpenMocap Studio v{new_version}: mejoras de estabilidad, cinemática y exportación."
    )

    run_step([git_exe, "add", "-A"], cwd=ROOT)
    status_res = subprocess.run([git_exe, "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True)
    if status_res.stdout.strip():
        run_step([git_exe, "commit", "-m", f"chore(release): v{new_version}"], cwd=ROOT)

    run_step([git_exe, "push", "origin", "main"], cwd=ROOT)

    tag = f"v{new_version}"
    run_step(
        [
            gh_exe,
            "release",
            "create",
            tag,
            str(exe_path),
            str(yml_path),
            str(blockmap_path),
            "--repo",
            "Guti31/openmocap-studio",
            "--title",
            f"OpenMocap Studio {tag}",
            "--notes",
            notes,
        ],
        cwd=ROOT,
    )

    print(f"\n[OK] Release {tag} publicado en https://github.com/Guti31/openmocap-studio/releases/tag/{tag}")
    print("[OK] Tanto GutApp como electron-updater detectarán esta versión automáticamente.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
