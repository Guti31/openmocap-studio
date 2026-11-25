# Nivel 2 — Agente Especialista #09: Calibrador Dinámico de Caminata y Ejes Funcionales (`spec_dynamic_walk_calibrator`)

- **Orquestador Padre**: `02_orch_kinematics_calibration`
- **Skill Especialista Asociada**: `.agent/skills/spec-dynamic-walk-calibrator/SKILL.md`

## Responsabilidad Principal
Capturar 6 segundos de caminata natural para identificar el eje funcional de flexión sagital de cada extremidad y eliminar la deriva magnética de interiores por sensor.

## Archivos Bajo Propiedad
- `backend/kinematics/calibration.py`

## Diseño Técnico y Contrato Operativo
Proyecta gyro local al marco provisional del sensor (omega_mag = q_raw * gyro) y evalúa PCA 2D sobre (omega_x, omega_z) para extremidades (eje medio-lateral +X) o aceleración horizontal de propulsión (a_x, a_z) para tronco/cabeza (eje frontal +Z). Extrae psi por sensor, construye q_heading = rotY(-psi) y recalcula la calibración bilateral q_heading * q_raw * q_offset_final.

## Criterios de Verificación
Validación en verify_pipeline.py con deriva magnética distinta por sensor (-40° a +40°) logrando error medio y máximo < 0.5° frente al ground truth.
