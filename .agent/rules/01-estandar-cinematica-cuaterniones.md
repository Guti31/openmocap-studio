# Regla Global 01: Estándar de Cinemática, Cuaterniones y Coordenadas

## Convención de Cuaterniones
- Todo cuaternión interno y transmitido en el sistema usa la **convención de Hamilton `[w, x, y, z]`**, donde `w` es la parte escalar y `(x, y, z)` la parte vectorial.
- Todo cuaternión almacenado o propagado debe mantenerse normalizado (`||q|| = 1.0`, tolerancia `1e-9`). Si `||q|| < 1e-12`, se sustituye por el cuaternión identidad `[1.0, 0.0, 0.0, 0.0]`.
- El producto de rotación sigue la composición `q_total = q_outer * q_inner`, equivalente en matrices de rotación 3x3 a `R(q_total) = R(q_outer) @ R(q_inner)`.
- La interpolación esférica (SLERP) debe comprobar siempre `dot(q1, q2) < 0` e invertir `-q2` para garantizar el arco geodésico más corto (evitando saltos de 360 grados).
- El promediado estático de cuaterniones durante calibración debe usar el método propio de **Markley** (autovector dominante de la matriz `M = sum(q_i @ q_i^T)`), nunca promedio aritmético ingenuo sin normalización espectral.

## Sistemas de Coordenadas
- **Estudio / OpenMocap / Three.js / BVH interno**: Mano derecha **Y-Up**:
  - `+Y`: Arriba (vertical opuesta a la gravedad).
  - `+Z`: Frente anatómico (dirección de marcha tras calibración).
  - `+X`: Izquierda anatómica del sujeto (siguiendo regla de mano derecha: `X x Y = Z`).
- **Blender**: Mano derecha **Z-Up** (`+Z` arriba, `-Y` frente en vista frontal estándar).
  - Al importar `.bvh` en Blender (`bpy.ops.import_anim.bvh`), usar `axis_forward='Z'`, `axis_up='Y'`.
  - Al exportar `.fbx` desde Blender (`bpy.ops.export_scene.fbx`), usar `axis_forward='-Z'`, `axis_up='Y'` y `add_leaf_bones=False`.

## Descomposición Euler y Bloqueo de Cardán
- Toda la matemática de rotación interna, fusión, calibración y solver FK se ejecuta exclusivamente en cuaterniones o matrices SO(3), **100 % libre de gimbal lock**.
- Únicamente la capa final de exportación `.bvh` y el reporte de ángulos anatómicos convierten a ángulos de Euler (`Zrotation Xrotation Yrotation` intrínseco en BVH, con `unwrap_euler_sequence` para continuidad temporal).
