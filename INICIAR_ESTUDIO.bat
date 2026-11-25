@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   OpenMocap Studio - APLICACION_TRAJE
echo ============================================================

echo [1/4] Verificando entorno Python y dependencias...
if not exist "backend\.venv\Scripts\python.exe" (
    echo [INFO] Creando entorno virtual Python en backend\.venv...
    python -m venv backend\.venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual Python.
        pause
        exit /b 1
    )
    backend\.venv\Scripts\pip.exe install -r backend\requirements.txt
    if errorlevel 1 (
        echo [ERROR] Fallo la instalacion de dependencias Python.
        pause
        exit /b 1
    )
)

if not exist "frontend\node_modules" (
    echo [INFO] Instalando dependencias de interfaz en frontend\...
    pushd frontend
    call npm.cmd install
    if errorlevel 1 (
        popd
        echo [ERROR] Fallo npm install en frontend\.
        pause
        exit /b 1
    )
    popd
)

echo [2/4] Liberando puertos previos (5173 / 8000) si estuvieran ocupados...
powershell -NoProfile -Command "$pids = Get-NetTCPConnection -LocalPort 5173,8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($p in $pids) { if ($p -and $p -gt 0) { $proc = Get-Process -Id $p -ErrorAction SilentlyContinue; if ($proc -and $proc.ProcessName -match '^(node|electron|python|python3)$') { Write-Host ('Deteniendo proceso previo ' + $proc.ProcessName + ' (PID ' + $p + ')'); Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } } }"
timeout /t 1 /nobreak >nul

echo [3/4] Iniciando backend FastAPI (120 Hz + Auto-escaneo Awinda USB) en puerto 8000...
start "OpenMocap Backend" /B cmd /c "backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

powershell -NoProfile -Command "$ok=$false; for ($i=0; $i -lt 40; $i++) { Start-Sleep -Milliseconds 500; try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { $ok=$true; break } } catch {} }; if (-not $ok) { Write-Host '[ERROR] El backend Python no respondio en http://127.0.0.1:8000/api/health' -ForegroundColor Red; exit 1 }"
if errorlevel 1 (
    echo [ERROR] No se pudo iniciar el servidor backend en el puerto 8000.
    pause
    exit /b 1
)

echo [4/4] Abriendo interfaz de escritorio OpenMocap Studio...
pushd frontend
call npm.cmd run electron:dev
set "APP_EXIT=%errorlevel%"
popd

powershell -NoProfile -Command "$pids = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($p in $pids) { if ($p -and $p -gt 0) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } }"

if not "%APP_EXIT%"=="0" (
    echo.
    echo [ERROR] La aplicacion se cerro con codigo de error %APP_EXIT%.
    pause
    exit /b %APP_EXIT%
)

endlocal
