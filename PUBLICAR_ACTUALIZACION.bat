@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Publicador 1-Clic - OpenMocap Studio (GitHub + GutApp)
echo ============================================================
echo.

if "%~1"=="" (
    set /p USER_VER="Nueva version X.Y.Z (deja vacio para auto-incrementar patch): "
) else (
    set "USER_VER=%~1"
)

if "%~2"=="" (
    set /p USER_NOTES="Notas de cambios de esta version (Enter para texto por defecto): "
) else (
    set "USER_NOTES=%~2"
)

if "%USER_VER%"=="" (
    backend\.venv\Scripts\python.exe backend\scripts\publish_update.py --bump patch --notes "%USER_NOTES%"
) else (
    backend\.venv\Scripts\python.exe backend\scripts\publish_update.py --version "%USER_VER%" --notes "%USER_NOTES%"
)

if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo completar la publicacion de la actualizacion.
    exit /b 1
)

echo.
echo [OK] Actualizacion publicada correctamente en GitHub Releases y GutApp.
endlocal
