---
name: spec-sensor-fusion-filter
description: Estimar cuaterniones en tiempo real cuando sensores de terceros (ESP32/Arduino/MPU/ICM) envían únicamente acelerómetro, giroscopio y/o magnetómetro crudos.
---

# Skill Especialista: Filtro de Fusión Sensorial Madgwick / Mahony

- **Agente Propietario**: `agents/02_spec_sensor_fusion_filter.md`
- **Orquestador de Dominio**: `02_orch_kinematics_calibration`

## Archivos Objetivo
- `backend/kinematics/sensor_fusion.py`

## Especificación Algorítmica y Contratos
Implementa gradiente descendente analítico de Madgwick (6-DOF IMU y 9-DOF MARG) y filtro complementario PI de Mahony, manteniendo un estado independiente por sensor_id en SensorFusionBank con dt adaptativo.

## Criterios de Aceptación y Pruebas
Convergencia estable hacia cuaternión unitario bajo gravedad simulada + rotación conocida en pruebas automatizadas.
