---
name: spec-joint-angle-biomechanics
description: Calcular en tiempo real los ángulos anatómicos clínicos (Flexión/Extensión, Abducción/Aducción, Rotación Interna/Externa) para 12 articulaciones clave.
---

# Skill Especialista: Analizador Biomecánico de Ángulos Articulares

- **Agente Propietario**: `agents/02_spec_joint_angle_biomechanics.md`
- **Orquestador de Dominio**: `02_orch_kinematics_calibration`

## Archivos Objetivo
- `backend/kinematics/biomechanics.py`

## Especificación Algorítmica y Contratos
Descompone la rotación relativa q_rel = q_inv(q_parent_world) * q_child_world mediante Euler anatómico alineado a los planos sagital, frontal y transversal, respetando lateralidad izquierda/derecha.

## Criterios de Aceptación y Pruebas
Flexión de rodilla positiva en caminata y valores cercanos a 0° en postura neutra T-Pose.
