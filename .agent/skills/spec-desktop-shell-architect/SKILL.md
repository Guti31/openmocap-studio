---
name: spec-desktop-shell-architect
description: Orquestar el ciclo de vida de la ventana de escritorio Electron, arranque automático del servidor Python, salud IPC y cierre limpio sin procesos huérfanos.
---

# Skill Especialista: Arquitecto del Shell de Escritorio Electron + FastAPI

- **Agente Propietario**: `agents/02_spec_desktop_shell_architect.md`
- **Orquestador de Dominio**: `03_orch_studio_3d_ui`

## Archivos Objetivo
- `frontend/electron/main.cjs`
- `frontend/electron/preload.cjs`
- `backend/main.py`
- `backend/engine.py`

## Especificación Algorítmica y Contratos
En producción ejecuta resources/backend/openmocap-backend.exe; en desarrollo lanza backend/.venv/Scripts/python.exe backend/main.py. Verifica /api/health antes de habilitar UI, expone diálogos nativos vía contextBridge y termina el proceso hijo en will-quit.

## Criterios de Aceptación y Pruebas
Validación de sintaxis Node (node --check) y arranque coordinado de backend + ventana de escritorio.
