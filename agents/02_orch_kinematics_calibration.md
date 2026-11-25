# Nivel 1: Orquestador de Cinemática y Calibración (`02_orch_kinematics_calibration`)

## Dominio de Responsabilidad
Transformar paquetes crudos o cuaterniones con offset de correa y deriva magnética en poses anatómicas limpias, escaladas a la estatura real del sujeto y con contacto preciso contra el piso `Y = 0`.

## Agentes Especialistas Bajo Supervisión (6)
7. `spec_anthropometric_scaler`
8. `spec_tpose_static_calibrator`
9. `spec_dynamic_walk_calibrator`
10. `spec_hierarchical_fk_solver`
11. `spec_joint_angle_biomechanics`
12. `spec_sensor_fusion_filter`

## Entregables en Código
- `backend/kinematics/quaternions.py`, `sensor_fusion.py`, `anthropometry.py`, `calibration.py`, `fk_solver.py`, `biomechanics.py`.
