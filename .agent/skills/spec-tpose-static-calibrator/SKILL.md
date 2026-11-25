---
name: spec-tpose-static-calibrator
description: Capturar 4 segundos de postura estática (T-Pose o N-Pose) para neutralizar la orientación arbitraria con que cada sensor fue amarrado a las correas del cuerpo.
---

# Skill Especialista: Calibrador Estático T-Pose / N-Pose

- **Agente Propietario**: `agents/02_spec_tpose_static_calibrator.md`
- **Orquestador de Dominio**: `02_orch_kinematics_calibration`

## Archivos Objetivo
- `backend/kinematics/calibration.py`

## Especificación Algorítmica y Contratos
Acumula cuaterniones válidos por segmento, calcula promedio espectral de Markley q_raw_static y desviación estándar angular para puntuación de calidad (0-100 %), y calcula q_offset = q_inv(q_raw_static) * q_bone_ref junto con reinicio rápido de rumbo (heading reset).

## Criterios de Aceptación y Pruebas
Eliminación de offsets arbitrarios de 25°-135° en todos los segmentos con error residual cercano a 0° en postura estática.
