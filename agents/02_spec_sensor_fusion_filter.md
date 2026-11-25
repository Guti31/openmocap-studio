# Nivel 2 — Agente Especialista #12: Filtro de Fusión Sensorial Madgwick / Mahony (`spec_sensor_fusion_filter`)

- **Orquestador Padre**: `02_orch_kinematics_calibration`
- **Skill Especialista Asociada**: `.agent/skills/spec-sensor-fusion-filter/SKILL.md`

## Responsabilidad Principal
Estimar cuaterniones en tiempo real cuando sensores de terceros (ESP32/Arduino/MPU/ICM) envían únicamente acelerómetro, giroscopio y/o magnetómetro crudos.

## Archivos Bajo Propiedad
- `backend/kinematics/sensor_fusion.py`

## Diseño Técnico y Contrato Operativo
Implementa gradiente descendente analítico de Madgwick (6-DOF IMU y 9-DOF MARG) y filtro complementario PI de Mahony, manteniendo un estado independiente por sensor_id en SensorFusionBank con dt adaptativo.

## Criterios de Verificación
Convergencia estable hacia cuaternión unitario bajo gravedad simulada + rotación conocida en pruebas automatizadas.
