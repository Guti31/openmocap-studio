# Nivel 2 — Agente Especialista #10: Solver Jerárquico de Cinemática Directa (FK) a 120 Hz (`spec_hierarchical_fk_solver`)

- **Orquestador Padre**: `02_orch_kinematics_calibration`
- **Skill Especialista Asociada**: `.agent/skills/spec-hierarchical-fk-solver/SKILL.md`

## Responsabilidad Principal
Propagar rotaciones calibradas a lo largo del árbol esquelético completo a 120 Hz calculando posiciones mundiales de articulaciones, rotaciones locales y contacto con el suelo.

## Archivos Bajo Propiedad
- `backend/kinematics/fk_solver.py`

## Diseño Técnico y Contrato Operativo
Recorre el árbol en orden topológico desde PELVIS, deriva q_local = q_inv(q_world_parent) * q_world, calcula posiciones globales de articulación y extremo distal, detecta el punto plantar más bajo de FOOT_L/FOOT_R y ajusta pelvis.y para impedir penetración del piso Y=0.

## Criterios de Verificación
Comprobación de min_foot_y >= -0.005 m durante toda la caminata y propagación sin discontinuidades para segmentos estándar y custom.
