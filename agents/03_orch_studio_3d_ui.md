# Nivel 1: Orquestador de Estudio 3D e Interfaz (`03_orch_studio_3d_ui`)

## Dominio de Responsabilidad
Construir la aplicación de escritorio multiplataforma Electron + React + Three.js con estándar **UX Ultra-Simple en Español por defecto** guiado en 4 pasos lineales (`1. Antena y Traje` -> `2. Calibrar Traje` -> `3. Grabar Movimiento` -> `4. Exportar`), ocultando las herramientas técnicas de ingeniería detrás de un interruptor opcional **`Modo Avanzado`** (apagado por defecto).

## Agentes Especialistas Bajo Supervisión (6)
13. `spec_desktop_shell_architect`
14. `spec_threejs_mannequin_renderer`
15. `spec_dockable_studio_panels`
16. `spec_calibration_wizard_ui`
17. `spec_anthropometric_profile_manager`
18. `spec_take_recorder_timeline`

## Estándar UX Ultra-Simple vs Modo Avanzado
- **Modo Simple (Por Defecto)**:
  - Barra superior lineal de 4 pasos claros en español + toggle discreto `Modo Avanzado`.
  - Panel izquierdo limpio: tarjeta grande `Estado de la Antena Awinda` con botón `Encender / Reconectar Antena`, campo rápido de `Estatura del Usuario (cm)` con `Aplicar Medidas`, silueta corporal con 17 nodos verde/amarillo/gris y botón discreto de demostración virtual.
  - Visor 3D central maximizado con solo 3 botones (`Centrar Cámara`, `Vista Frontal`, `Ver Esqueleto / Maniquí`) y sin panel derecho técnico.
  - Barra inferior minimalista con Reproducir/Pausar, barra de progreso y grabaciones recientes.
- **Modo Avanzado (Opcional)**:
  - Restaura todos los controles técnicos (Serial COM, UDP/OSC, BLE, canal RF manual, simulador con deriva/agitación, sensores custom 21/32+, gráficas Recharts en vivo, ejes locales y vectores de aceleración).

## Entregables en Código
- `frontend/electron/main.cjs`, `preload.cjs`
- `frontend/src/components/*`, `frontend/src/store/*`, `frontend/src/hooks/*`, `backend/recording/recorder.py`, `backend/engine.py`, `backend/main.py`
