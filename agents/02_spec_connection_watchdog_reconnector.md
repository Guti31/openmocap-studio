# Nivel 2 — Agente Especialista #05: Watchdog de Conexión y Anti-Jitter Inalámbrico (`spec_connection_watchdog_reconnector`)

- **Orquestador Padre**: `01_orch_hardware_hal`
- **Skill Especialista Asociada**: `.agent/skills/spec-connection-watchdog-reconnector/SKILL.md`

## Responsabilidad Principal
Garantizar continuidad de movimiento ante microcortes inalámbricos, calcular Hz efectivos por sensor, suavizar jitter de alta frecuencia y gestionar reconexión.

## Archivos Bajo Propiedad
- `backend/hal/watchdog.py`

## Diseño Técnico y Contrato Operativo
Mantiene ventana deslizante de timestamps por sensor, clasifica estado (online, degraded, interpolating, lost), aplica extrapolación por gyro cuando el silencio está entre 25 ms y 250 ms y suavizado SLERP configurable anti-jitter.

## Criterios de Verificación
Interpolación continua sin NaN durante pérdidas breves y recuperación automática al llegar nuevos paquetes.
