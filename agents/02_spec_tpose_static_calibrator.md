# Nivel 2 — Agente Especialista #08: Calibrador Estático T-Pose / N-Pose (`spec_tpose_static_calibrator`)

- **Orquestador Padre**: `02_orch_kinematics_calibration`
- **Skill Especialista Asociada**: `.agent/skills/spec-tpose-static-calibrator/SKILL.md`

## Responsabilidad Principal
Capturar 4 segundos de postura estática (T-Pose o N-Pose) para neutralizar la orientación arbitraria con que cada sensor fue amarrado a las correas del cuerpo.

## Archivos Bajo Propiedad
- `backend/kinematics/calibration.py`

## Diseño Técnico y Contrato Operativo
Acumula cuaterniones válidos por segmento, calcula promedio espectral de Markley q_raw_static y desviación estándar angular para puntuación de calidad (0-100 %), y calcula q_offset = q_inv(q_raw_static) * q_bone_ref junto con reinicio rápido de rumbo (heading reset).

## Criterios de Verificación
Eliminación de offsets arbitrarios de 25°-135° en todos los segmentos con error residual cercano a 0° en postura estática.
