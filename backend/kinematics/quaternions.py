from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np


def q_identity() -> np.ndarray:
    """Devuelve el cuaternión identidad en convención Hamilton [w, x, y, z]."""
    return np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)


def q_normalize(q: Sequence[float] | np.ndarray) -> np.ndarray:
    """Normaliza un cuaternión [w, x, y, z] protegiendo contra norma nula."""
    arr = np.asarray(q, dtype=np.float64)
    if arr.shape != (4,):
        arr = arr.reshape((4,))
    norm = float(np.linalg.norm(arr))
    if not math.isfinite(norm) or norm < 1e-12:
        return q_identity()
    out = arr / norm
    if out[0] < 0.0:
        out = -out
    return out


def q_normalize_raw(q: Sequence[float] | np.ndarray) -> np.ndarray:
    """Normaliza sin invertir signo del hemisferio (útil en SLERP continuo)."""
    arr = np.asarray(q, dtype=np.float64).reshape((4,))
    norm = float(np.linalg.norm(arr))
    if not math.isfinite(norm) or norm < 1e-12:
        return q_identity()
    return arr / norm


def q_conj(q: Sequence[float] | np.ndarray) -> np.ndarray:
    """Devuelve el conjugado [w, -x, -y, -z]."""
    arr = np.asarray(q, dtype=np.float64)
    return np.array([arr[0], -arr[1], -arr[2], -arr[3]], dtype=np.float64)


def q_inv(q: Sequence[float] | np.ndarray) -> np.ndarray:
    """Devuelve el inverso multiplicativo de un cuaternión."""
    arr = np.asarray(q, dtype=np.float64)
    n2 = float(np.dot(arr, arr))
    if not math.isfinite(n2) or n2 < 1e-12:
        return q_identity()
    return q_conj(arr) / n2


def q_mul(q1: Sequence[float] | np.ndarray, q2: Sequence[float] | np.ndarray) -> np.ndarray:
    """Producto de Hamilton q1 * q2 para cuaterniones [w, x, y, z]."""
    w1, x1, y1, z1 = float(q1[0]), float(q1[1]), float(q1[2]), float(q1[3])
    w2, x2, y2, z2 = float(q2[0]), float(q2[1]), float(q2[2]), float(q2[3])
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ],
        dtype=np.float64,
    )


def q_rotate_vec(q: Sequence[float] | np.ndarray, v: Sequence[float] | np.ndarray) -> np.ndarray:
    """Rota un vector 3D v mediante el cuaternión unitario q."""
    qn = q_normalize_raw(q)
    w = float(qn[0])
    q_vec = qn[1:4]
    vec = np.asarray(v, dtype=np.float64)
    t = 2.0 * np.cross(q_vec, vec)
    return vec + w * t + np.cross(q_vec, t)


def q_from_axis_angle(axis: Sequence[float] | np.ndarray, angle_rad: float) -> np.ndarray:
    """Construye un cuaternión [w, x, y, z] desde eje 3D y ángulo en radianes."""
    ax = np.asarray(axis, dtype=np.float64)
    norm = float(np.linalg.norm(ax))
    if norm < 1e-12 or abs(angle_rad) < 1e-15:
        return q_identity()
    ax = ax / norm
    half = 0.5 * float(angle_rad)
    s = math.sin(half)
    return np.array([math.cos(half), ax[0] * s, ax[1] * s, ax[2] * s], dtype=np.float64)


def q_to_axis_angle(q: Sequence[float] | np.ndarray) -> tuple[np.ndarray, float]:
    """Extrae (eje_unitario, ángulo_rad) en el rango [0, pi]."""
    qn = q_normalize(q)
    angle = 2.0 * math.acos(max(-1.0, min(1.0, float(qn[0]))))
    s = math.sqrt(max(0.0, 1.0 - float(qn[0]) * float(qn[0])))
    if s < 1e-8:
        return np.array([1.0, 0.0, 0.0], dtype=np.float64), 0.0
    return qn[1:4] / s, angle


def q_angle_deg(q1: Sequence[float] | np.ndarray, q2: Sequence[float] | np.ndarray) -> float:
    """Calcula la distancia angular geodésica mínima en grados entre dos cuaterniones."""
    a = q_normalize_raw(q1)
    b = q_normalize_raw(q2)
    dot = abs(float(np.dot(a, b)))
    dot = max(0.0, min(1.0, dot))
    return math.degrees(2.0 * math.acos(dot))


def q_slerp(q1: Sequence[float] | np.ndarray, q2: Sequence[float] | np.ndarray, t: float) -> np.ndarray:
    """Interpolación esférica lineal por el arco más corto."""
    t_clamped = max(0.0, min(1.0, float(t)))
    a = q_normalize_raw(q1)
    b = q_normalize_raw(q2)
    dot = float(np.dot(a, b))
    if dot < 0.0:
        b = -b
        dot = -dot
    if dot > 0.9995:
        return q_normalize_raw(a + t_clamped * (b - a))
    dot = max(-1.0, min(1.0, dot))
    theta_0 = math.acos(dot)
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * t_clamped
    s0 = math.cos(theta) - dot * math.sin(theta) / sin_theta_0
    s1 = math.sin(theta) / sin_theta_0
    return q_normalize_raw(s0 * a + s1 * b)


def q_average_markley(quats: Iterable[Sequence[float] | np.ndarray]) -> np.ndarray:
    """Calcula el promedio óptimo de cuaterniones mediante el método propio de Markley."""
    mat = np.zeros((4, 4), dtype=np.float64)
    count = 0
    for q in quats:
        qn = q_normalize_raw(q)
        mat += np.outer(qn, qn)
        count += 1
    if count == 0:
        return q_identity()
    eigvals, eigvecs = np.linalg.eigh(mat)
    best = eigvecs[:, int(np.argmax(eigvals))]
    return q_normalize(best)


def q_to_rotmat(q: Sequence[float] | np.ndarray) -> np.ndarray:
    """Convierte cuaternión unitario [w, x, y, z] a matriz de rotación SO(3) 3x3."""
    w, x, y, z = q_normalize_raw(q)
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return np.array(
        [
            [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
            [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
            [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
        ],
        dtype=np.float64,
    )


def rotmat_to_q(R: np.ndarray) -> np.ndarray:
    """Convierte matriz de rotación 3x3 (método Shepperd) a cuaternión [w, x, y, z]."""
    m = np.asarray(R, dtype=np.float64)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    return q_normalize([w, x, y, z])


def q_to_euler_zxy(q: Sequence[float] | np.ndarray) -> tuple[float, float, float]:
    """
    Descompone cuaternión a Euler intrínseco Z-X-Y en grados: (z_deg, x_deg, y_deg).
    Equivale a R = Rz(z) @ Rx(x) @ Ry(y), estándar en exportación BVH Zrotation Xrotation Yrotation.
    """
    R = q_to_rotmat(q)
    # En R = Rz(z) @ Rx(x) @ Ry(y):
    # R[2, 1] = sin(x)
    # R[0, 1] = -sin(z)*cos(x), R[1, 1] = cos(z)*cos(x)
    # R[2, 0] = -cos(x)*sin(y), R[2, 2] = cos(x)*cos(y)
    sin_x = max(-1.0, min(1.0, float(R[2, 1])))
    x = math.asin(sin_x)
    if abs(sin_x) < 0.99999:
        z = math.atan2(-float(R[0, 1]), float(R[1, 1]))
        y = math.atan2(-float(R[2, 0]), float(R[2, 2]))
    else:
        # Bloqueo de cardán (x ≈ ±90°): fijar y = 0 y resolver z
        y = 0.0
        z = math.atan2(float(R[1, 0]), float(R[0, 0]))
    return (math.degrees(z), math.degrees(x), math.degrees(y))


def euler_zxy_to_q(z_deg: float, x_deg: float, y_deg: float) -> np.ndarray:
    """Reconstruye cuaternión desde Euler intrínseco Z-X-Y en grados."""
    qz = q_from_axis_angle([0.0, 0.0, 1.0], math.radians(z_deg))
    qx = q_from_axis_angle([1.0, 0.0, 0.0], math.radians(x_deg))
    qy = q_from_axis_angle([0.0, 1.0, 0.0], math.radians(y_deg))
    return q_normalize(q_mul(qz, q_mul(qx, qy)))


def q_to_euler_xyz(q: Sequence[float] | np.ndarray) -> tuple[float, float, float]:
    """Descompone cuaternión a Euler intrínseco X-Y-Z en grados: (x_deg, y_deg, z_deg)."""
    R = q_to_rotmat(q)
    # En R = Rx(x) @ Ry(y) @ Rz(z):
    # R[0, 2] = sin(y)
    # R[1, 2] = -sin(x)*cos(y), R[2, 2] = cos(x)*cos(y)
    # R[0, 1] = -cos(y)*sin(z), R[0, 0] = cos(y)*cos(z)
    sin_y = max(-1.0, min(1.0, float(R[0, 2])))
    y = math.asin(sin_y)
    if abs(sin_y) < 0.99999:
        x = math.atan2(-float(R[1, 2]), float(R[2, 2]))
        z = math.atan2(-float(R[0, 1]), float(R[0, 0]))
    else:
        z = 0.0
        x = math.atan2(float(R[2, 1]), float(R[1, 1]))
    return (math.degrees(x), math.degrees(y), math.degrees(z))


def q_to_euler_yzx(q: Sequence[float] | np.ndarray) -> tuple[float, float, float]:
    """Descompone cuaternión a Euler intrínseco Y-Z-X en grados: (y_deg, z_deg, x_deg)."""
    R = q_to_rotmat(q)
    # En R = Ry(y) @ Rz(z) @ Rx(x):
    # R[1, 0] = sin(z)
    # R[2, 0] = -sin(y)*cos(z), R[0, 0] = cos(y)*cos(z)
    # R[1, 2] = -cos(z)*sin(x), R[1, 1] = cos(z)*cos(x)
    sin_z = max(-1.0, min(1.0, float(R[1, 0])))
    z = math.asin(sin_z)
    if abs(sin_z) < 0.99999:
        y = math.atan2(-float(R[2, 0]), float(R[0, 0]))
        x = math.atan2(-float(R[1, 2]), float(R[1, 1]))
    else:
        x = 0.0
        y = math.atan2(float(R[0, 2]), float(R[2, 2]))
    return (math.degrees(y), math.degrees(z), math.degrees(x))


def unwrap_euler_sequence(sequence_deg: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    """Elimina saltos de ±360 grados entre fotogramas consecutivos de ángulos Euler."""
    if not sequence_deg:
        return []
    out: list[tuple[float, float, float]] = [sequence_deg[0]]
    for idx in range(1, len(sequence_deg)):
        px, py, pz = out[-1]
        cx, cy, cz = sequence_deg[idx]
        while cx - px > 180.0:
            cx -= 360.0
        while cx - px < -180.0:
            cx += 360.0
        while cy - py > 180.0:
            cy -= 360.0
        while cy - py < -180.0:
            cy += 360.0
        while cz - pz > 180.0:
            cz -= 360.0
        while cz - pz < -180.0:
            cz += 360.0
        out.append((cx, cy, cz))
    return out


def q_extract_yaw_y(q: Sequence[float] | np.ndarray) -> float:
    """Extrae el ángulo de guiñada (yaw) alrededor del eje vertical +Y en radianes."""
    fwd = q_rotate_vec(q, [0.0, 0.0, 1.0])
    if math.hypot(float(fwd[0]), float(fwd[2])) < 1e-6:
        up = q_rotate_vec(q, [1.0, 0.0, 0.0])
        return math.atan2(-float(up[2]), float(up[0]))
    return math.atan2(float(fwd[0]), float(fwd[2]))
