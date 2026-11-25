---
name: spec-desktop-packager-builder
description: Configurar la compilación autocontenida del backend Python y el instalador distribuible .exe / multiplataforma para usuarios finales sin dependencias manuales.
---

# Skill Especialista: Empaquetador de Escritorio PyInstaller + Electron Builder

- **Agente Propietario**: `agents/02_spec_desktop_packager_builder.md`
- **Orquestador de Dominio**: `04_orch_export_packaging`

## Archivos Objetivo
- `build/openmocap_backend.spec`
- `frontend/package.json`
- `INICIAR_ESTUDIO.bat`
- `GENERAR_INSTALADOR.bat`

## Especificación Algorítmica y Contratos
PyInstaller empaqueta backend/main.py, configuraciones, blender_tools y binario ffmpeg de imageio_ffmpeg; electron-builder empaqueta dist/ de Vite + extraResources en un instalador NSIS Windows (.exe) y scripts .bat UTF-8 listos para lanzar o compilar.

## Criterios de Aceptación y Pruebas
Validación de rutas relativas en spec, existencia de scripts .bat ejecutables y compilación limpia de frontend.
