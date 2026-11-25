# Nivel 2 — Agente Especialista #06: Mapeador Dinámico de Sensores y Detección por Agitación (`spec_dynamic_sensor_mapper`)

- **Orquestador Padre**: `01_orch_hardware_hal`
- **Skill Especialista Asociada**: `.agent/skills/spec-dynamic-sensor-mapper/SKILL.md`

## Responsabilidad Principal
Auto-asignar los 17 IDs Xsens Awinda precargados, soportar expansión dinámica ilimitada (21, 32+ sensores o props) e identificar sensores físicamente al agitarlos.

## Archivos Bajo Propiedad
- `backend/hal/sensor_mapper.py`
- `backend/config/default_awinda_17.json`

## Diseño Técnico y Contrato Operativo
Carga default_awinda_17.json, persiste asignaciones activas, permite registrar segmentos personalizados sobre cualquier hueso padre y detecta agitación sostenida ||gyro|| > 3.5 rad/s durante >= 120 ms con ventana de cooldown para emitir eventos shake_detected al frontend.

## Criterios de Verificación
Confirmación automática de los 17 IDs Awinda exactos y disparo de evento shake_detected en pruebas automatizadas.
