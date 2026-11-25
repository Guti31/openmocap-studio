---
name: global-high-freq-ipc
description: Canal IPC y streaming WebSocket de baja latencia a 60-120 Hz entre el backend Python FastAPI y el visor 3D React/Three.js en Electron.
---

# Skill Global: Comunicación IPC y Streaming WebSocket de Alta Frecuencia

## Propósito
Transmitir poses del esqueleto, telemetría de sensores y ángulos articulares a 60–120 Hz sin saturar la interfaz React ni generar tirones de garbage collection en el visor 3D.

## Contrato del Protocolo
- **Backend (`backend/main.py` + `backend/engine.py`)**:
  - WebSocket `/ws/stream`: emite JSON compacto por cuadro con `seq`, `timestamp_ms`, `rate_hz`, `mode` (`live`/`playback`), `calibration`, `segments` (`{pos, quat, end_pos, accel}`), `sensors` (estado resumido, batería, RSSI, Hz), `angles` (ángulos anatómicos), `recording` y `playback`.
  - Si un cliente lento tiene cola acumulada, descartar el paquete antiguo en favor del más reciente para mantener latencia `< 16 ms`.
- **Frontend (`frontend/src/store/useStudioStore.ts` + `useMocapStream.ts`)**:
  - **Ruta rápida 3D (60 FPS)**: `liveFrameRef` (objeto mutable fuera del árbol de renders de React) leído directamente dentro de `useFrame()` de `@react-three/fiber`.
  - **Ruta UI (~15 Hz)**: Actualización regulada (`throttle ~66 ms`) hacia Zustand para gráficas Recharts, indicadores de batería, RSSI y línea de tiempo.
- **Supervisión Electron (`frontend/electron/main.cjs`)**:
  - Lanza `openmocap-backend.exe` (o `python backend/main.py` en desarrollo), sondea `/api/health` antes de mostrar contenido listo y termina el árbol de procesos al cerrar.
