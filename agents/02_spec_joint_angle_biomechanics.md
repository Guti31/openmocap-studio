# Nivel 2 — Agente Especialista #11: Analizador Biomecánico de Ángulos Articulares (`spec_joint_angle_biomechanics`)

- **Orquestador Padre**: `02_orch_kinematics_calibration`
- **Skill Especialista Asociada**: `.agent/skills/spec-joint-angle-biomechanics/SKILL.md`

## Responsabilidad Principal
Calcular en tiempo real los ángulos anatómicos clínicos (Flexión/Extensión, Abducción/Aducción, Rotación Interna/Externa) para 12 articulaciones clave.

## Archivos Bajo Propiedad
- `backend/kinematics/biomechanics.py`

## Diseño Técnico y Contrato Operativo
Descompone la rotación relativa q_rel = q_inv(q_parent_world) * q_child_world mediante Euler anatómico alineado a los planos sagital, frontal y transversal, respetando lateralidad izquierda/derecha.

## Criterios de Verificación
Flexión de rodilla positiva en caminata y valores cercanos a 0° en postura neutra T-Pose.
