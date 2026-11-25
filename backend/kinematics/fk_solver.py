from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from backend.kinematics.anthropometry import SkeletonModel
from backend.kinematics.quaternions import (
    q_angle_deg,
    q_identity,
    q_inv,
    q_mul,
    q_normalize,
    q_rotate_vec,
    q_slerp,
)

RootMotionMode = Literal["in_place", "free_walk"]

# Pesos progresivos de curvatura vertebral entre Pelvis y Esternón (Spine..Spine3)
SPINE_SLERP_WEIGHTS: dict[str, float] = {
    "SPINE": 0.20,
    "SPINE1": 0.45,
    "SPINE2": 0.75,
}
NECK_SLERP_WEIGHT = 0.45


@dataclass
class FKSolvedPose:
    """Resultado completo de Cinemática Directa para un instante de tiempo."""

    world_pos: dict[str, list[float]]
    world_quat: dict[str, list[float]]
    local_quat: dict[str, list[float]]
    end_pos: dict[str, list[float]]
    min_foot_y: float


class HierarchicalFKSolver:
    """
    Solver de Cinemática Directa jerárquica (FK) a 120 Hz sobre esqueleto de 23 huesos tipo Vicon/MVN.
    Sintetiza columna de 4 segmentos (SLERP), cuello y dedos de los pies desde los 17 sensores Awinda,
    incluye anclaje ZUPT de Root/Pelvis en reposo y contacto exacto con el piso Y = 0.000.
    """

    def __init__(self, skeleton: SkeletonModel) -> None:
        self.skeleton = skeleton
        self.root_mode: RootMotionMode = "in_place"
        self._pelvis_xz = np.array([0.0, 0.0], dtype=np.float64)
        self._prev_foot_pos: dict[str, np.ndarray] = {}
        self._prev_pelvis_quat: np.ndarray | None = None
        self._prev_foot_quats: dict[str, np.ndarray] = {}
        self._zupt_pelvis_y: float | None = None
        self.zupt_active: bool = False

    def update_skeleton(self, skeleton: SkeletonModel) -> None:
        self.skeleton = skeleton

    def reset_root_position(self) -> None:
        self._pelvis_xz = np.array([0.0, 0.0], dtype=np.float64)
        self._prev_foot_pos.clear()
        self._prev_pelvis_quat = None
        self._prev_foot_quats.clear()
        self._zupt_pelvis_y = None
        self.zupt_active = False

    def solve(
        self,
        calibrated_world_quats: dict[str, np.ndarray],
        sensor_gyros: dict[str, np.ndarray] | None = None,
        dt: float = 1.0 / 120.0,
    ) -> FKSolvedPose:
        """
        Resuelve las 23 articulaciones a partir de cuaterniones mundiales de sensores activos.
        Sintetiza vértebras Spine..Spine2, Neck y ToeBase mediante interpolación esférica (SLERP).
        """
        world_quat_arr: dict[str, np.ndarray] = {}
        local_quat_arr: dict[str, np.ndarray] = {}
        world_pos_arr: dict[str, np.ndarray] = {}
        end_pos_arr: dict[str, np.ndarray] = {}

        q_pelvis = (
            q_normalize(calibrated_world_quats["PELVIS"])
            if "PELVIS" in calibrated_world_quats
            else q_identity()
        )
        q_chest = (
            q_normalize(calibrated_world_quats["STERNUM"])
            if "STERNUM" in calibrated_world_quats
            else q_pelvis
        )
        q_head = (
            q_normalize(calibrated_world_quats["HEAD"])
            if "HEAD" in calibrated_world_quats
            else q_chest
        )

        # Paso 1: Propagar e interpolar rotaciones en orden topológico (23 huesos + custom)
        for seg_name in self.skeleton.order:
            seg_def = self.skeleton.segments[seg_name]
            parent_q = world_quat_arr[seg_def.parent] if seg_def.parent else q_identity()

            if seg_name in calibrated_world_quats:
                wq = q_normalize(calibrated_world_quats[seg_name])
            elif seg_name in SPINE_SLERP_WEIGHTS:
                wq = q_normalize(q_slerp(q_pelvis, q_chest, SPINE_SLERP_WEIGHTS[seg_name]))
            elif seg_name == "NECK":
                wq = q_normalize(q_slerp(q_chest, q_head, NECK_SLERP_WEIGHT))
            elif seg_name == "TOE_L":
                wq = world_quat_arr.get("FOOT_L", parent_q)
            elif seg_name == "TOE_R":
                wq = world_quat_arr.get("FOOT_R", parent_q)
            else:
                wq = parent_q

            world_quat_arr[seg_name] = wq
            if seg_def.parent:
                local_quat_arr[seg_name] = q_normalize(q_mul(q_inv(parent_q), wq))
            else:
                local_quat_arr[seg_name] = wq

        # Paso 2: Propagar posiciones desde pelvis provisional
        pelvis_def = self.skeleton.segments["PELVIS"]
        pelvis_base_y = float(pelvis_def.offset_m[1])
        world_pos_arr["PELVIS"] = np.array(
            [float(self._pelvis_xz[0]), pelvis_base_y, float(self._pelvis_xz[1])],
            dtype=np.float64,
        )
        end_pos_arr["PELVIS"] = world_pos_arr["PELVIS"] + q_rotate_vec(
            world_quat_arr["PELVIS"],
            pelvis_def.end_site_m,
        )

        for seg_name in self.skeleton.order[1:]:
            seg_def = self.skeleton.segments[seg_name]
            parent_name = seg_def.parent or "PELVIS"
            p_pos = world_pos_arr[parent_name]
            p_rot = world_quat_arr[parent_name]
            j_pos = p_pos + q_rotate_vec(p_rot, seg_def.offset_m)
            world_pos_arr[seg_name] = j_pos
            end_pos_arr[seg_name] = j_pos + q_rotate_vec(world_quat_arr[seg_name], seg_def.end_site_m)

        # Paso 3: Contacto exacto de plantas de pies (talón, metatarso y punta) con el plano Y = 0.000
        ankle_to_sole = float(self.skeleton.dimensions.get("ankle_to_sole_m", 0.065))
        contact_candidates: list[float] = []
        for foot_name, toe_name in (("FOOT_L", "TOE_L"), ("FOOT_R", "TOE_R")):
            if foot_name in world_pos_arr and foot_name in end_pos_arr:
                heel_sole_pt = world_pos_arr[foot_name] + q_rotate_vec(
                    world_quat_arr[foot_name],
                    [0.0, -ankle_to_sole, 0.0],
                )
                contact_candidates.append(float(heel_sole_pt[1]))
                if toe_name in world_pos_arr and toe_name in end_pos_arr:
                    contact_candidates.append(float(world_pos_arr[toe_name][1]))
                    contact_candidates.append(float(end_pos_arr[toe_name][1]))
                else:
                    contact_candidates.append(float(end_pos_arr[foot_name][1]))

        raw_min_y = min(contact_candidates) if contact_candidates else 0.0
        raw_y_shift = -raw_min_y
        raw_pelvis_y = pelvis_base_y + raw_y_shift

        # Paso 4: Anclaje ZUPT de Root/Pelvis (elimina "brinquitos" y deriva en postura quieta)
        foot_speeds: list[float] = []
        safe_dt = max(1e-3, float(dt))
        for foot_name in ("FOOT_L", "FOOT_R"):
            if sensor_gyros and foot_name in sensor_gyros:
                foot_speeds.append(float(np.linalg.norm(sensor_gyros[foot_name])))
            elif foot_name in world_quat_arr:
                cur_fq = world_quat_arr[foot_name]
                prev_fq = self._prev_foot_quats.get(foot_name)
                if prev_fq is not None:
                    foot_speeds.append(math.radians(q_angle_deg(prev_fq, cur_fq)) / safe_dt)
                else:
                    foot_speeds.append(0.0)
                self._prev_foot_quats[foot_name] = cur_fq.copy()

        pelvis_delta_deg = (
            q_angle_deg(self._prev_pelvis_quat, q_pelvis)
            if self._prev_pelvis_quat is not None
            else 0.0
        )
        self._prev_pelvis_quat = q_pelvis.copy()

        is_stationary = (
            bool(foot_speeds)
            and all(spd < 0.45 for spd in foot_speeds)
            and pelvis_delta_deg < 1.5
        )
        self.zupt_active = is_stationary

        if is_stationary:
            if self._zupt_pelvis_y is None:
                self._zupt_pelvis_y = raw_pelvis_y
            else:
                dy = raw_pelvis_y - self._zupt_pelvis_y
                if abs(dy) <= 0.004:
                    # Banda muerta de 4 mm: altura pélvica completamente estable
                    pass
                elif abs(dy) <= 0.04:
                    self._zupt_pelvis_y += 0.08 * dy
                else:
                    self._zupt_pelvis_y += 0.35 * dy
            y_shift = self._zupt_pelvis_y - pelvis_base_y
        else:
            self._zupt_pelvis_y = raw_pelvis_y
            y_shift = raw_y_shift

        for seg_name in self.skeleton.order:
            world_pos_arr[seg_name][1] += y_shift
            end_pos_arr[seg_name][1] += y_shift

        # Paso 5: Odometría horizontal en free_walk solo cuando el sujeto NO está en ZUPT
        if (
            not is_stationary
            and self.root_mode == "free_walk"
            and "FOOT_L" in end_pos_arr
            and "FOOT_R" in end_pos_arr
        ):
            left_y = float(end_pos_arr.get("TOE_L", end_pos_arr["FOOT_L"])[1])
            right_y = float(end_pos_arr.get("TOE_R", end_pos_arr["FOOT_R"])[1])
            stance = "FOOT_L" if left_y <= right_y else "FOOT_R"
            cur_foot = end_pos_arr[stance]
            if stance in self._prev_foot_pos:
                dx = float(self._prev_foot_pos[stance][0] - cur_foot[0])
                dz = float(self._prev_foot_pos[stance][2] - cur_foot[2])
                if abs(dx) < 0.08 and abs(dz) < 0.08:
                    self._pelvis_xz[0] += dx
                    self._pelvis_xz[1] += dz
                    for seg_name in self.skeleton.order:
                        world_pos_arr[seg_name][0] += dx
                        world_pos_arr[seg_name][2] += dz
                        end_pos_arr[seg_name][0] += dx
                        end_pos_arr[seg_name][2] += dz
            self._prev_foot_pos["FOOT_L"] = end_pos_arr["FOOT_L"].copy()
            self._prev_foot_pos["FOOT_R"] = end_pos_arr["FOOT_R"].copy()
        elif not is_stationary:
            self._prev_foot_pos.clear()

        return FKSolvedPose(
            world_pos={k: [round(float(v), 5) for v in pos] for k, pos in world_pos_arr.items()},
            world_quat={k: [round(float(v), 6) for v in q] for k, q in world_quat_arr.items()},
            local_quat={k: [round(float(v), 6) for v in q] for k, q in local_quat_arr.items()},
            end_pos={k: [round(float(v), 5) for v in pos] for k, pos in end_pos_arr.items()},
            min_foot_y=round(raw_min_y + y_shift, 5),
        )

    @staticmethod
    def compute_joint_distances(pose: FKSolvedPose) -> dict[str, float]:
        """Calcula longitudes euclidianas reales entre centros articulares resueltos por FK."""

        def _dist(seg_a: str, seg_b: str | None = None) -> float:
            if seg_a not in pose.world_pos:
                return 0.0
            p0 = np.asarray(pose.world_pos[seg_a], dtype=np.float64)
            p1 = (
                np.asarray(pose.world_pos[seg_b], dtype=np.float64)
                if (seg_b and seg_b in pose.world_pos)
                else np.asarray(pose.end_pos[seg_a], dtype=np.float64)
            )
            return round(float(np.linalg.norm(p1 - p0)), 5)

        return {
            "clavicle_l": _dist("SHOULDER_L", "UPPER_ARM_L"),
            "clavicle_r": _dist("SHOULDER_R", "UPPER_ARM_R"),
            "upper_arm_l": _dist("UPPER_ARM_L", "FOREARM_L"),
            "upper_arm_r": _dist("UPPER_ARM_R", "FOREARM_R"),
            "forearm_l": _dist("FOREARM_L", "HAND_L"),
            "forearm_r": _dist("FOREARM_R", "HAND_R"),
            "hand_l": _dist("HAND_L"),
            "hand_r": _dist("HAND_R"),
            "toe_l": _dist("TOE_L"),
            "toe_r": _dist("TOE_R"),
        }
