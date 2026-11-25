# Nivel 2 — Agente Especialista #04: Simulador Biomecánico Sintético de 17 Sensores (`spec_17sensor_synthetic_simulator`)

- **Orquestador Padre**: `01_orch_hardware_hal`
- **Skill Especialista Asociada**: `.agent/skills/spec-17sensor-synthetic-simulator/SKILL.md`

## Responsabilidad Principal
Generar en tiempo real a 60/120 Hz un flujo completo de 17 sensores (con los IDs exactos de Awinda y cualquier sensor custom) para pruebas integrales sin hardware físico.

## Archivos Bajo Propiedad
- `backend/hal/synthetic_simulator.py`

## Diseño Técnico y Contrato Operativo
Modela ciclos biomecánicos suaves (walk, jog, squat, tpose, npose, wave), calcula gyro local exacto por derivada de cuaternión (q_prev^-1 * q_curr)/dt, emite free_accel consistente con la aceleración de propulsión/frenado en el marco del sensor, permite inyectar offsets de montaje arbitrarios, deriva magnética en yaw por sensor, ruido gaussiano y ráfagas trigger_shake(sensor_id).

## Criterios de Verificación
Verificación en verify_pipeline.py de tasa >= 60 Hz y coherencia exacta entre datos simulados y get_ground_truth_world_quats().
