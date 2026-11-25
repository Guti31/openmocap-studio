---
name: spec-hierarchical-fk-solver
description: Propagar rotaciones calibradas a lo largo del árbol esquelético completo a 120 Hz calculando posiciones mundiales de articulaciones, rotaciones locales y contacto con el suelo.
---

# Skill Especialista: Solver Jerárquico de Cinemática Directa (FK) a 120 Hz

- **Agente Propietario**: `agents/02_spec_hierarchical_fk_solver.md`
- **Orquestador de Dominio**: `02_orch_kinematics_calibration`

## Archivos Objetivo
- `backend/kinematics/fk_solver.py`

## Especificación Algorítmica y Contratos
Recorre el árbol en orden topológico desde PELVIS, deriva q_local = q_inv(q_world_parent) * q_world, calcula posiciones globales de articulación y extremo distal, detecta el punto plantar más bajo de FOOT_L/FOOT_R y ajusta pelvis.y para impedir penetración del piso Y=0.

## Criterios de Aceptación y Pruebas
Comprobación de min_foot_y >= -0.005 m durante toda la caminata y propagación sin discontinuidades para segmentos estándar y custom.
