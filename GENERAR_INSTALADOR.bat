@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Compilador de Instalador - OpenMocap Studio (.exe)
echo ============================================================

echo [1/4] Compilando backend principal (Python 3.12) con PyInstaller...
backend\.venv\Scripts\pyinstaller.exe --clean --noconfirm --distpath dist --workpath build\pyinstaller_work build\openmocap_backend.spec
if errorlevel 1 (
    echo [ERROR] Fallo la compilacion del backend principal.
    exit /b 1
)

echo [2/4] Verificando PyInstaller y compilando Worker XDA Oficial (Python 3.10 + DLLs)...
if not exist "backend\.venv_xda\Scripts\pyinstaller.exe" (
    echo [INFO] Instalando pyinstaller en backend\.venv_xda...
    backend\.venv_xda\Scripts\pip.exe install pyinstaller
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar PyInstaller en backend\.venv_xda.
        exit /b 1
    )
)
backend\.venv_xda\Scripts\pyinstaller.exe --clean --noconfirm --distpath dist\backend --workpath build\pyinstaller_work_xda build\xda_bridge_worker.spec
if errorlevel 1 (
    echo [ERROR] Fallo la compilacion de xda-bridge-worker.exe.
    exit /b 1
)

echo [3/4] Compilando frontend TypeScript + Vite...
pushd frontend
call npm.cmd run build
if errorlevel 1 (
    popd
    echo [ERROR] Fallo la compilacion del frontend.
    exit /b 1
)

echo [4/4] Generando instalador distribuible con Electron Builder...
call npx.cmd electron-builder --win --publish never
if errorlevel 1 (
    popd
    echo [ERROR] Fallo electron-builder.
    exit /b 1
)
popd

echo.
echo [OK] Binarios en dist\backend y setup en %cd%\dist_installer
endlocal
