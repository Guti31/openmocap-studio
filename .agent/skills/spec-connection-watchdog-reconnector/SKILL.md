---
name: spec-connection-watchdog-reconnector
description: Garantizar continuidad de movimiento ante microcortes inalámbricos, calcular Hz efectivos por sensor, suavizar jitter de alta frecuencia y gestionar reconexión.
---

# Skill Especialista: Watchdog de Conexión y Anti-Jitter Inalámbrico

- **Agente Propietario**: `agents/02_spec_connection_watchdog_reconnector.md`
- **Orquestador de Dominio**: `01_orch_hardware_hal`

## Archivos Objetivo
- `backend/hal/watchdog.py`

## Especificación Algorítmica y Contratos
Mantiene ventana deslizante de timestamps por sensor, clasifica estado (online, degraded, interpolating, lost), aplica extrapolación por gyro cuando el silencio está entre 25 ms y 250 ms y suavizado SLERP configurable anti-jitter.

## Criterios de Aceptación y Pruebas
Interpolación continua sin NaN durante pérdidas breves y recuperación automática al llegar nuevos paquetes.
