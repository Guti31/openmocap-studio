# Nivel 2 — Agente Especialista #13: Arquitecto del Shell de Escritorio Electron + FastAPI (`spec_desktop_shell_architect`)

- **Orquestador Padre**: `03_orch_studio_3d_ui`
- **Skill Especialista Asociada**: `.agent/skills/spec-desktop-shell-architect/SKILL.md`

## Responsabilidad Principal
Orquestar el ciclo de vida de la ventana de escritorio Electron, arranque automático del servidor Python, salud IPC y cierre limpio sin procesos huérfanos.

## Archivos Bajo Propiedad
- `frontend/electron/main.cjs`
- `frontend/electron/preload.cjs`
- `backend/main.py`
- `backend/engine.py`

## Diseño Técnico y Contrato Operativo
En producción ejecuta resources/backend/openmocap-backend.exe; en desarrollo lanza backend/.venv/Scripts/python.exe backend/main.py. Verifica /api/health antes de habilitar UI, expone diálogos nativos vía contextBridge y termina el proceso hijo en will-quit.

## Criterios de Verificación
Validación de sintaxis Node (node --check) y arranque coordinado de backend + ventana de escritorio.
