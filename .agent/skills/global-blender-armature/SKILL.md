---
name: global-blender-armature
description: Estándar de jerarquía anatómica escalada de 17+ huesos, exportación BVH limpia y puente automatizado hacia FBX compatible con Rigify y Mixamo en Blender.
---

# Skill Global: Armadura Compatible con Blender (BVH / FBX)

## Jerarquía Canónica (17 Segmentos Base + Extensible)
Raíz en `PELVIS` (caderas):
- Tronco y cabeza: `PELVIS -> STERNUM -> HEAD` (+ `End Site`).
- Brazo izquierdo (`+X` en T-Pose): `STERNUM -> SHOULDER_L -> UPPER_ARM_L -> FOREARM_L -> HAND_L`.
- Brazo derecho (`-X` en T-Pose): `STERNUM -> SHOULDER_R -> UPPER_ARM_R -> FOREARM_R -> HAND_R`.
- Pierna izquierda (`+X` lateral, `-Y` abajo): `PELVIS -> THIGH_L -> SHIN_L -> FOOT_L`.
- Pierna derecha (`-X` lateral, `-Y` abajo): `PELVIS -> THIGH_R -> SHIN_R -> FOOT_R`.
- Segmentos personalizados adicionales (`21`, `32+` sensores) se anexan dinámicamente bajo el padre elegido y se incluyen en la jerarquía BVH exportada.

## Reglas de Exportación Limpia
1. **`.bvh` (`backend/export/bvh_exporter.py`)**:
   - En pose de reposo (`OFFSET`), todos los vectores corresponden exactamente a las longitudes escaladas antropométricamente en T-Pose.
   - `ROOT Pelvis` con 6 canales (`Xposition Yposition Zposition Zrotation Xrotation Yrotation`); cada `JOINT` con 3 canales (`Zrotation Xrotation Yrotation`).
   - Desempaquetado continuo de ángulos Euler ZXY para evitar volteretas de interpolación en Blender.
   - Soporte de mapeo de nombres: `openmocap`, `mixamo` (`mixamorig:Hips`, etc.) y `rigify` (`hips`, `spine.002`, `upper_arm.L`, etc.).
2. **`.fbx` (`blender_tools/convertir_a_fbx.py`)**:
   - Invoca `blender --background --python convertir_a_fbx.py` sin interfaz gráfica, aplica `axis_forward='-Z', axis_up='Y'`, elimina leaf bones innecesarios y hornea fotogramas clave a la tasa de la toma.
