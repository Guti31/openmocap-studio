---
name: spec-dynamic-sensor-mapper
description: Auto-asignar los 17 IDs Xsens Awinda precargados, soportar expansión dinámica ilimitada (21, 32+ sensores o props) e identificar sensores físicamente al agitarlos.
---

# Skill Especialista: Mapeador Dinámico de Sensores y Detección por Agitación

- **Agente Propietario**: `agents/02_spec_dynamic_sensor_mapper.md`
- **Orquestador de Dominio**: `01_orch_hardware_hal`

## Archivos Objetivo
- `backend/hal/sensor_mapper.py`
- `backend/config/default_awinda_17.json`

## Especificación Algorítmica y Contratos
Carga default_awinda_17.json, persiste asignaciones activas, permite registrar segmentos personalizados sobre cualquier hueso padre y detecta agitación sostenida ||gyro|| > 3.5 rad/s durante >= 120 ms con ventana de cooldown para emitir eventos shake_detected al frontend.

## Criterios de Aceptación y Pruebas
Confirmación automática de los 17 IDs Awinda exactos y disparo de evento shake_detected en pruebas automatizadas.
