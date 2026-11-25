# Nivel 0: Orquestador Director Maestro (`00_master_director_orchestrator`)

## Misión
Dirigir la arquitectura completa, coherencia técnica, integración entre backend Python y escritorio Electron/React, y la validación final de **OpenMocap Studio (`APLICACION_TRAJE`)** de forma 100 % autónoma.

## Orquestadores Subordinados (Nivel 1)
1. `01_orch_hardware_hal`: Adquisición multi-marca (Xsens Awinda, Serial, UDP/OSC, BLE, Simulador), estabilidad inalámbrica y mapeo dinámico.
2. `02_orch_kinematics_calibration`: Antropometría de Winter, calibración T-Pose/N-Pose + Caminata dinámica, fusión Madgwick, solver FK y biomecánica.
3. `03_orch_studio_3d_ui`: Shell Electron, visor Three.js 60 FPS, paneles acoplables, asistentes en español, gráficas en vivo y grabador de tomas.
4. `04_orch_export_packaging`: Exportador `.bvh`, puente automatizado Blender `.fbx`, grabador de video `.mp4`, i18n, PyInstaller + Electron Builder y QA integral.

## Reglas Globales Vinculantes
- `00-politica-cero-placeholders.md`
- `01-estandar-cinematica-cuaterniones.md`
- `02-protocolo-hal-universal.md`
