---
name: global-quaternion-math
description: Estándar transversal de álgebra de cuaterniones Hamilton [w,x,y,z], SLERP geodésico, promedio de Markley, reinicio de rumbo y descomposición Euler ZXY sin gimbal lock.
---

# Skill Global: Matemática de Cuaterniones y Cinemática Espacial

## Propósito
Garantizar consistencia algebraica exacta entre captura IMU, fusión de sensores, calibración estática/dinámica, solver FK y exportación `.bvh`.

## Convenciones y Primitivas Clave
1. **Representación**: Vector NumPy `np.ndarray` de forma `(4,)` con componentes `[w, x, y, z]`.
2. **Operaciones base** en `backend/kinematics/quaternions.py`:
   - `q_normalize(q)`: normaliza y corrige vectores degenerados hacia identidad.
   - `q_conj(q)` / `q_inv(q)`: para cuaterniones unitarios `q^-1 = [w, -x, -y, -z]`.
   - `q_mul(q1, q2)`: producto de Hamilton asociativo.
   - `q_rotate_vec(q, v)`: `v' = v + 2*w*(q_vec x v) + 2*(q_vec x (q_vec x v))`.
   - `q_slerp(q1, q2, t)`: fuerza `dot >= 0` para camino más corto; usa NLERP cuando `dot > 0.9995` para máxima estabilidad numérica.
   - `q_average_markley(quats)`: máximo autovector real simétrico de `sum(q_i q_i^T)`.
   - `q_to_euler_zxy(q)` y `euler_zxy_to_q(z_deg, x_deg, y_deg)`: consistentes con el orden de canales `Zrotation Xrotation Yrotation` de BVH.
   - `unwrap_euler_sequence(angles_deg)`: elimina saltos artificiales de `±360°` entre fotogramas consecutivos antes de escribir `.bvh`.

## Verificación Matemática Obligatoria
- `q_mul(q, q_inv(q))` debe igualar `[1, 0, 0, 0]` con error `< 1e-9`.
- `euler_zxy_to_q(*q_to_euler_zxy(q))` debe igualar `±q` con error angular `< 1e-4°`.
