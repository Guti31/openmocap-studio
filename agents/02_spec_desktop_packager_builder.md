# Nivel 2 — Agente Especialista #23: Empaquetador de Escritorio PyInstaller + Electron Builder (`spec_desktop_packager_builder`)

- **Orquestador Padre**: `04_orch_export_packaging`
- **Skill Especialista Asociada**: `.agent/skills/spec-desktop-packager-builder/SKILL.md`

## Responsabilidad Principal
Configurar la compilación autocontenida del backend Python y el instalador distribuible .exe / multiplataforma para usuarios finales sin dependencias manuales.

## Archivos Bajo Propiedad
- `build/openmocap_backend.spec`
- `frontend/package.json`
- `INICIAR_ESTUDIO.bat`
- `GENERAR_INSTALADOR.bat`

## Diseño Técnico y Contrato Operativo
PyInstaller empaqueta backend/main.py, configuraciones, blender_tools y binario ffmpeg de imageio_ffmpeg; electron-builder empaqueta dist/ de Vite + extraResources en un instalador NSIS Windows (.exe) y scripts .bat UTF-8 listos para lanzar o compilar.

## Criterios de Verificación
Validación de rutas relativas en spec, existencia de scripts .bat ejecutables y compilación limpia de frontend.
