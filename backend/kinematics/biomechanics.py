from __future__ import annotations

from typing import Sequence

import numpy as np

from backend.kinematics.quaternions import q_inv, q_mul, q_normalize, q_to_euler_xyz, q_to_euler_yzx

JOINT_PAIRS: dict[str, tuple[str, str, int, str]] = {
    # clave: (segmento_padre, segmento_hijo, signo_lateralidad, etiqueta_es)
    "hip_l": ("PELVIS", "THIGH_L", 1, "Cadera Izq."),
    "hip_r": ("PELVIS", "THIGH_R", -1, "Cadera Der."),
    "knee_l": ("THIGH_L", "SHIN_L", 1, "Rodilla Izq."),
    "knee_r": ("THIGH_R", "SHIN_R", -1, "Rodilla Der."),
    "ankle_l": ("SHIN_L", "FOOT_L", 1, "Tobillo Izq."),
    "ankle_r": ("SHIN_R", "FOOT_R", -1, "Tobillo Der."),
    "shoulder_l": ("SHOULDER_L", "UPPER_ARM_L", 1, "Hombro Izq."),
    "shoulder_r": ("SHOULDER_R", "UPPER_ARM_R", -1, "Hombro Der."),
    "elbow_l": ("UPPER_ARM_L", "FOREARM_L", 1, "Codo Izq."),
    "elbow_r": ("UPPER_ARM_R", "FOREARM_R", -1, "Codo Der."),
    "spine": ("PELVIS", "STERNUM", 1, "Columna Lumbar/Torácica"),
    "neck": ("STERNUM", "HEAD", 1, "Cuello"),
}


class JointAngleCalculator:
    """
    Calcula ángulos anatómicos en grados:
    - flexion: Flexión (+) / Extensión (-) alrededor del eje medio-lateral +X
    - abduction: Abducción (+) / Aducción (-) alrededor del eje sagital +Z ajustado por lateralidad
    - rotation: Rotación Interna / Externa alrededor del eje longitudinal +Y
    """

    def compute(self, world_quats: dict[str, Sequence[float] | np.ndarray]) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for joint_key, (parent, child, side, _label) in JOINT_PAIRS.items():
            if parent not in world_quats or child not in world_quats:
                continue
            qp = q_normalize(world_quats[parent])
            qc = q_normalize(world_quats[child])
            q_rel = q_normalize(q_mul(q_inv(qp), qc))

            if joint_key in ("elbow_l", "elbow_r", "shoulder_l", "shoulder_r"):
                # En T-Pose los brazos siguen ±X: descomposición Y-Z-X evita gimbal lock
                # y separa flexión horizontal (+Y) de pronosupinación/rotación axial (+X).
                y_deg, z_deg, x_deg = q_to_euler_yzx(q_rel)
                flexion = side * y_deg
                abduction = side * z_deg
                rotation = side * x_deg
            else:
                x_deg, y_deg, z_deg = q_to_euler_xyz(q_rel)
                if joint_key in ("knee_l", "knee_r"):
                    flexion = x_deg
                elif joint_key in ("hip_l", "hip_r"):
                    flexion = -x_deg
                else:
                    flexion = -x_deg
                abduction = side * z_deg
                rotation = side * y_deg

            result[joint_key] = {
                "flexion": round(float(flexion), 2),
                "abduction": round(float(abduction), 2),
                "rotation": round(float(rotation), 2),
            }
        return result

