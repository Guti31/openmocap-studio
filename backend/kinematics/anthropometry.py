from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.kinematics.quaternions import q_from_axis_angle, q_identity

# Elevación escapular natural promedio durante la abducción horizontal a 90° (T-Pose)
SCAPULA_TPOSE_ELEVATION_DEG = 14.0


@dataclass
class SegmentDef:
    """Definición anatómica de un segmento en la jerarquía del estudio (mano derecha Y-up)."""

    name: str
    parent: str | None
    offset_m: list[float]
    end_site_m: list[float]
    tpose_quat: list[float]
    npose_quat: list[float]
    mixamo_name: str
    rigify_name: str
    label_es: str
    is_custom: bool = False
    sensor_mount_offset_m: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    bvh_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parent": self.parent,
            "offset_m": [round(float(v), 5) for v in self.offset_m],
            "end_site_m": [round(float(v), 5) for v in self.end_site_m],
            "tpose_quat": [round(float(v), 6) for v in self.tpose_quat],
            "npose_quat": [round(float(v), 6) for v in self.npose_quat],
            "bvh_name": self.bvh_name or self.name,
            "mixamo_name": self.mixamo_name,
            "rigify_name": self.rigify_name,
            "label_es": self.label_es,
            "is_custom": self.is_custom,
            "sensor_mount_offset_m": [round(float(v), 5) for v in self.sensor_mount_offset_m],
        }


@dataclass
class AnthropometricProfile:
    """Perfil antropométrico de sujeto basado en proporciones de Winter y medidas opcionales."""

    id: str
    name: str
    height_cm: float
    arm_span_cm: float | None = None
    hip_height_cm: float | None = None
    knee_height_cm: float | None = None
    ankle_height_cm: float | None = None
    shoulder_width_cm: float | None = None
    foot_length_cm: float | None = None
    hip_width_cm: float | None = None
    shoulder_height_cm: float | None = None
    custom_segments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "height_cm": float(self.height_cm),
            "arm_span_cm": self.arm_span_cm,
            "hip_height_cm": self.hip_height_cm,
            "knee_height_cm": self.knee_height_cm,
            "ankle_height_cm": self.ankle_height_cm,
            "shoulder_width_cm": self.shoulder_width_cm,
            "foot_length_cm": self.foot_length_cm,
            "hip_width_cm": self.hip_width_cm,
            "shoulder_height_cm": self.shoulder_height_cm,
            "custom_segments": list(self.custom_segments),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnthropometricProfile:
        return cls(
            id=str(data.get("id") or str(uuid.uuid4())[:8]),
            name=str(data.get("name") or "Sujeto Estándar"),
            height_cm=max(80.0, min(250.0, float(data.get("height_cm", 175.0)))),
            arm_span_cm=data.get("arm_span_cm"),
            hip_height_cm=data.get("hip_height_cm"),
            knee_height_cm=data.get("knee_height_cm"),
            ankle_height_cm=data.get("ankle_height_cm"),
            shoulder_width_cm=data.get("shoulder_width_cm"),
            foot_length_cm=data.get("foot_length_cm"),
            hip_width_cm=data.get("hip_width_cm"),
            shoulder_height_cm=data.get("shoulder_height_cm"),
            custom_segments=list(data.get("custom_segments") or []),
        )


def compute_winter_dimensions(profile: AnthropometricProfile) -> dict[str, float]:
    """
    Calcula dimensiones óseas en metros usando tablas antropométricas de Winter (1990)
    ajustadas suavemente por cualquier medida directa opcional provista por el usuario.
    """
    H = profile.height_cm / 100.0

    # Alturas verticales desde el piso (Y = 0.0)
    ankle_h = (profile.ankle_height_cm / 100.0) if profile.ankle_height_cm else 0.039 * H
    knee_h = (profile.knee_height_cm / 100.0) if profile.knee_height_cm else 0.285 * H
    hip_h = (profile.hip_height_cm / 100.0) if profile.hip_height_cm else 0.530 * H
    shoulder_h = (profile.shoulder_height_cm / 100.0) if profile.shoulder_height_cm else 0.818 * H

    # Asegurar monotonicidad anatómica
    ankle_h = max(0.03, min(0.15, ankle_h))
    knee_h = max(ankle_h + 0.15, min(0.70, knee_h))
    hip_h = max(knee_h + 0.15, min(1.30, hip_h))
    shoulder_h = max(hip_h + 0.18, min(1.90, shoulder_h))

    thigh_len = hip_h - knee_h
    shin_len = knee_h - ankle_h
    foot_len = (profile.foot_length_cm / 100.0) if profile.foot_length_cm else 0.152 * H

    # Tronco articulado en 4 vértebras (Spine..Spine3) + cuello + cabeza
    torso_total = shoulder_h - hip_h
    pelvis_sacrum_y = 0.08 * torso_total
    spine_total = torso_total - pelvis_sacrum_y
    spine_l0 = 0.22 * spine_total
    spine_l1 = 0.24 * spine_total
    spine_l2 = 0.27 * spine_total
    spine_l3 = 0.27 * spine_total

    sternum_y = 0.52 * torso_total
    shoulder_from_sternum_y = torso_total - sternum_y
    neck_len = max(0.065, 0.0485 * H)
    head_offset_y = neck_len
    head_len = max(0.14, H - shoulder_h - neck_len)

    # Suela real del pie y segmento de dedos (ToeBase)
    ankle_to_sole = ankle_h
    foot_ball_z = foot_len * 0.62
    toe_len = max(0.06, foot_len * 0.34)

    # Anchos y centros articulares anatómicos reales (separando montaje escapular del sensor)
    hip_half_w = ((profile.hip_width_cm / 100.0) * 0.5) if profile.hip_width_cm else 0.0955 * H
    biacromial_w = (profile.shoulder_width_cm / 100.0) if profile.shoulder_width_cm else 0.258 * H
    acromion_half_w = 0.5 * biacromial_w
    # Articulación esternoclavicular (SC) ~2.6 cm lateral al esternón a 1.75 m
    sternoclavicular_x = max(0.018, 0.015 * H)
    # Centro glenohumeral real (GH) ~2.1 cm medial al borde acromial externo
    glenohumeral_half_w = max(sternoclavicular_x + 0.08, acromion_half_w - 0.012 * H)
    clavicle_len_x = max(0.08, glenohumeral_half_w - sternoclavicular_x)
    glenohumeral_drop_y = 0.015 * H
    sternoclavicular_y = max(0.04, shoulder_from_sternum_y - glenohumeral_drop_y)

    # Desplazamiento físico informativo del sensor escapular (espalda alta: ~6 cm medial, ~5 cm inferior)
    scapula_sensor_medial_m = round(0.060 * (H / 1.75), 4)
    scapula_sensor_inferior_m = round(0.050 * (H / 1.75), 4)
    scapula_sensor_posterior_m = round(0.045 * (H / 1.75), 4)

    # Brazos desde envergadura o Winter medidos exactamente desde el centro glenohumeral
    if profile.arm_span_cm:
        arm_span_m = profile.arm_span_cm / 100.0
        single_arm = max(0.35, (arm_span_m - 2.0 * glenohumeral_half_w) * 0.5)
        total_winter_arm = 0.186 + 0.146 + 0.108
        upper_arm_len = single_arm * (0.186 / total_winter_arm)
        forearm_len = single_arm * (0.146 / total_winter_arm)
        hand_len = single_arm * (0.108 / total_winter_arm)
    else:
        upper_arm_len = 0.186 * H
        forearm_len = 0.146 * H
        hand_len = 0.108 * H

    return {
        "height_m": round(H, 4),
        "pelvis_height_m": round(hip_h, 4),
        "pelvis_sacrum_y_m": round(pelvis_sacrum_y, 4),
        "spine_l0_m": round(spine_l0, 4),
        "spine_l1_m": round(spine_l1, 4),
        "spine_l2_m": round(spine_l2, 4),
        "spine_l3_m": round(spine_l3, 4),
        "thigh_length_m": round(thigh_len, 4),
        "shin_length_m": round(shin_len, 4),
        "ankle_height_m": round(ankle_h, 4),
        "ankle_to_sole_m": round(ankle_to_sole, 4),
        "foot_length_m": round(foot_len, 4),
        "foot_ball_z_m": round(foot_ball_z, 4),
        "toe_length_m": round(toe_len, 4),
        "sternum_offset_y_m": round(sternum_y, 4),
        "shoulder_offset_y_m": round(shoulder_from_sternum_y, 4),
        "sternoclavicular_x_m": round(sternoclavicular_x, 4),
        "sternoclavicular_y_m": round(sternoclavicular_y, 4),
        "clavicle_from_spine3_y_m": round(max(0.02, spine_l3 - glenohumeral_drop_y), 4),
        "glenohumeral_half_width_m": round(glenohumeral_half_w, 4),
        "glenohumeral_drop_y_m": round(glenohumeral_drop_y, 4),
        "scapula_sensor_medial_m": scapula_sensor_medial_m,
        "scapula_sensor_inferior_m": scapula_sensor_inferior_m,
        "scapula_sensor_posterior_m": scapula_sensor_posterior_m,
        "neck_length_m": round(neck_len, 4),
        "head_offset_y_m": round(head_offset_y, 4),
        "head_length_m": round(head_len, 4),
        "hip_half_width_m": round(hip_half_w, 4),
        "clavicle_inner_x_m": round(sternoclavicular_x, 4),
        "clavicle_length_m": round(clavicle_len_x, 4),
        "upper_arm_length_m": round(upper_arm_len, 4),
        "forearm_length_m": round(forearm_len, 4),
        "hand_length_m": round(hand_len, 4),
    }


class SkeletonModel:
    """Modelo jerárquico articulado de 23 huesos tipo Vicon/MVN escalado para FK, 3D y BVH."""

    CANONICAL_ORDER = [
        "PELVIS",
        "SPINE",
        "SPINE1",
        "SPINE2",
        "STERNUM",
        "NECK",
        "HEAD",
        "SHOULDER_L",
        "UPPER_ARM_L",
        "FOREARM_L",
        "HAND_L",
        "SHOULDER_R",
        "UPPER_ARM_R",
        "FOREARM_R",
        "HAND_R",
        "THIGH_L",
        "SHIN_L",
        "FOOT_L",
        "TOE_L",
        "THIGH_R",
        "SHIN_R",
        "FOOT_R",
        "TOE_R",
    ]

    def __init__(self, profile: AnthropometricProfile) -> None:
        self.profile = profile
        self.dimensions = compute_winter_dimensions(profile)
        self.segments: dict[str, SegmentDef] = {}
        self.order: list[str] = []
        self.children: dict[str, list[str]] = {}
        self._build_hierarchy()

    def _build_hierarchy(self) -> None:
        d = self.dimensions
        ident = q_identity().tolist()
        n_left_arm = q_from_axis_angle([0.0, 0.0, 1.0], math.radians(-90.0)).tolist()
        n_right_arm = q_from_axis_angle([0.0, 0.0, 1.0], math.radians(90.0)).tolist()
        t_left_shoulder = q_from_axis_angle([0.0, 0.0, 1.0], math.radians(SCAPULA_TPOSE_ELEVATION_DEG)).tolist()
        t_right_shoulder = q_from_axis_angle([0.0, 0.0, 1.0], math.radians(-SCAPULA_TPOSE_ELEVATION_DEG)).tolist()

        defs = [
            SegmentDef(
                name="PELVIS",
                parent=None,
                offset_m=[0.0, d["pelvis_height_m"], 0.0],
                end_site_m=[0.0, d["pelvis_sacrum_y_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="Pelvis",
                mixamo_name="mixamorig:Hips",
                rigify_name="hips",
                label_es="Pelvis",
            ),
            SegmentDef(
                name="SPINE",
                parent="PELVIS",
                offset_m=[0.0, d["pelvis_sacrum_y_m"], 0.0],
                end_site_m=[0.0, d["spine_l0_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="Spine",
                mixamo_name="mixamorig:Spine",
                rigify_name="spine",
                label_es="Lumbar Baja (L5-L3)",
            ),
            SegmentDef(
                name="SPINE1",
                parent="SPINE",
                offset_m=[0.0, d["spine_l0_m"], 0.0],
                end_site_m=[0.0, d["spine_l1_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="Spine1",
                mixamo_name="mixamorig:Spine1",
                rigify_name="spine.001",
                label_es="Lumbar Alta (L2-T12)",
            ),
            SegmentDef(
                name="SPINE2",
                parent="SPINE1",
                offset_m=[0.0, d["spine_l1_m"], 0.0],
                end_site_m=[0.0, d["spine_l2_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="Spine2",
                mixamo_name="mixamorig:Spine2",
                rigify_name="spine.002",
                label_es="Torácica Baja (T11-T6)",
            ),
            SegmentDef(
                name="STERNUM",
                parent="SPINE2",
                offset_m=[0.0, d["spine_l2_m"], 0.0],
                end_site_m=[0.0, d["spine_l3_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="Spine3",
                mixamo_name="mixamorig:Spine3",
                rigify_name="spine.003",
                label_es="Esternón / Torácica Alta",
            ),
            SegmentDef(
                name="NECK",
                parent="STERNUM",
                offset_m=[0.0, d["spine_l3_m"], 0.0],
                end_site_m=[0.0, d["neck_length_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="Neck",
                mixamo_name="mixamorig:Neck",
                rigify_name="spine.004",
                label_es="Cuello",
            ),
            SegmentDef(
                name="HEAD",
                parent="NECK",
                offset_m=[0.0, d["neck_length_m"], 0.0],
                end_site_m=[0.0, d["head_length_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="Head",
                mixamo_name="mixamorig:Head",
                rigify_name="spine.006",
                label_es="Cabeza",
            ),
            # Brazo izquierdo (+X) desde Articulación Esternoclavicular -> Centro Glenohumeral
            SegmentDef(
                name="SHOULDER_L",
                parent="STERNUM",
                offset_m=[d["sternoclavicular_x_m"], d["clavicle_from_spine3_y_m"], 0.0],
                end_site_m=[d["clavicle_length_m"], 0.0, 0.0],
                tpose_quat=t_left_shoulder,
                npose_quat=ident,
                bvh_name="LeftShoulder",
                mixamo_name="mixamorig:LeftShoulder",
                rigify_name="shoulder.L",
                label_es="Hombro Izq.",
                sensor_mount_offset_m=[
                    -d["scapula_sensor_medial_m"],
                    -d["scapula_sensor_inferior_m"],
                    -d["scapula_sensor_posterior_m"],
                ],
            ),
            SegmentDef(
                name="UPPER_ARM_L",
                parent="SHOULDER_L",
                offset_m=[d["clavicle_length_m"], 0.0, 0.0],
                end_site_m=[d["upper_arm_length_m"], 0.0, 0.0],
                tpose_quat=ident,
                npose_quat=n_left_arm,
                bvh_name="LeftArm",
                mixamo_name="mixamorig:LeftArm",
                rigify_name="upper_arm.L",
                label_es="Brazo Izq.",
            ),
            SegmentDef(
                name="FOREARM_L",
                parent="UPPER_ARM_L",
                offset_m=[d["upper_arm_length_m"], 0.0, 0.0],
                end_site_m=[d["forearm_length_m"], 0.0, 0.0],
                tpose_quat=ident,
                npose_quat=n_left_arm,
                bvh_name="LeftForeArm",
                mixamo_name="mixamorig:LeftForeArm",
                rigify_name="forearm.L",
                label_es="Antebrazo Izq.",
            ),
            SegmentDef(
                name="HAND_L",
                parent="FOREARM_L",
                offset_m=[d["forearm_length_m"], 0.0, 0.0],
                end_site_m=[d["hand_length_m"], 0.0, 0.0],
                tpose_quat=ident,
                npose_quat=n_left_arm,
                bvh_name="LeftHand",
                mixamo_name="mixamorig:LeftHand",
                rigify_name="hand.L",
                label_es="Mano Izq.",
            ),
            # Brazo derecho (-X) desde Articulación Esternoclavicular -> Centro Glenohumeral
            SegmentDef(
                name="SHOULDER_R",
                parent="STERNUM",
                offset_m=[-d["sternoclavicular_x_m"], d["clavicle_from_spine3_y_m"], 0.0],
                end_site_m=[-d["clavicle_length_m"], 0.0, 0.0],
                tpose_quat=t_right_shoulder,
                npose_quat=ident,
                bvh_name="RightShoulder",
                mixamo_name="mixamorig:RightShoulder",
                rigify_name="shoulder.R",
                label_es="Hombro Der.",
                sensor_mount_offset_m=[
                    d["scapula_sensor_medial_m"],
                    -d["scapula_sensor_inferior_m"],
                    -d["scapula_sensor_posterior_m"],
                ],
            ),
            SegmentDef(
                name="UPPER_ARM_R",
                parent="SHOULDER_R",
                offset_m=[-d["clavicle_length_m"], 0.0, 0.0],
                end_site_m=[-d["upper_arm_length_m"], 0.0, 0.0],
                tpose_quat=ident,
                npose_quat=n_right_arm,
                bvh_name="RightArm",
                mixamo_name="mixamorig:RightArm",
                rigify_name="upper_arm.R",
                label_es="Brazo Der.",
            ),
            SegmentDef(
                name="FOREARM_R",
                parent="UPPER_ARM_R",
                offset_m=[-d["upper_arm_length_m"], 0.0, 0.0],
                end_site_m=[-d["forearm_length_m"], 0.0, 0.0],
                tpose_quat=ident,
                npose_quat=n_right_arm,
                bvh_name="RightForeArm",
                mixamo_name="mixamorig:RightForeArm",
                rigify_name="forearm.R",
                label_es="Antebrazo Der.",
            ),
            SegmentDef(
                name="HAND_R",
                parent="FOREARM_R",
                offset_m=[-d["forearm_length_m"], 0.0, 0.0],
                end_site_m=[-d["hand_length_m"], 0.0, 0.0],
                tpose_quat=ident,
                npose_quat=n_right_arm,
                bvh_name="RightHand",
                mixamo_name="mixamorig:RightHand",
                rigify_name="hand.R",
                label_es="Mano Der.",
            ),
            # Pierna izquierda (+X lateral, -Y abajo, +Z pie y dedos)
            SegmentDef(
                name="THIGH_L",
                parent="PELVIS",
                offset_m=[d["hip_half_width_m"], 0.0, 0.0],
                end_site_m=[0.0, -d["thigh_length_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="LeftUpLeg",
                mixamo_name="mixamorig:LeftUpLeg",
                rigify_name="thigh.L",
                label_es="Muslo Izq.",
            ),
            SegmentDef(
                name="SHIN_L",
                parent="THIGH_L",
                offset_m=[0.0, -d["thigh_length_m"], 0.0],
                end_site_m=[0.0, -d["shin_length_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="LeftLeg",
                mixamo_name="mixamorig:LeftLeg",
                rigify_name="shin.L",
                label_es="Pantorrilla Izq.",
            ),
            SegmentDef(
                name="FOOT_L",
                parent="SHIN_L",
                offset_m=[0.0, -d["shin_length_m"], 0.0],
                end_site_m=[0.0, -d["ankle_to_sole_m"], d["foot_ball_z_m"]],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="LeftFoot",
                mixamo_name="mixamorig:LeftFoot",
                rigify_name="foot.L",
                label_es="Pie Izq.",
            ),
            SegmentDef(
                name="TOE_L",
                parent="FOOT_L",
                offset_m=[0.0, -d["ankle_to_sole_m"], d["foot_ball_z_m"]],
                end_site_m=[0.0, 0.0, d["toe_length_m"]],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="LeftToeBase",
                mixamo_name="mixamorig:LeftToeBase",
                rigify_name="toe.L",
                label_es="Dedos Pie Izq.",
            ),
            # Pierna derecha (-X lateral, -Y abajo, +Z pie y dedos)
            SegmentDef(
                name="THIGH_R",
                parent="PELVIS",
                offset_m=[-d["hip_half_width_m"], 0.0, 0.0],
                end_site_m=[0.0, -d["thigh_length_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="RightUpLeg",
                mixamo_name="mixamorig:RightUpLeg",
                rigify_name="thigh.R",
                label_es="Muslo Der.",
            ),
            SegmentDef(
                name="SHIN_R",
                parent="THIGH_R",
                offset_m=[0.0, -d["thigh_length_m"], 0.0],
                end_site_m=[0.0, -d["shin_length_m"], 0.0],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="RightLeg",
                mixamo_name="mixamorig:RightLeg",
                rigify_name="shin.R",
                label_es="Pantorrilla Der.",
            ),
            SegmentDef(
                name="FOOT_R",
                parent="SHIN_R",
                offset_m=[0.0, -d["shin_length_m"], 0.0],
                end_site_m=[0.0, -d["ankle_to_sole_m"], d["foot_ball_z_m"]],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="RightFoot",
                mixamo_name="mixamorig:RightFoot",
                rigify_name="foot.R",
                label_es="Pie Der.",
            ),
            SegmentDef(
                name="TOE_R",
                parent="FOOT_R",
                offset_m=[0.0, -d["ankle_to_sole_m"], d["foot_ball_z_m"]],
                end_site_m=[0.0, 0.0, d["toe_length_m"]],
                tpose_quat=ident,
                npose_quat=ident,
                bvh_name="RightToeBase",
                mixamo_name="mixamorig:RightToeBase",
                rigify_name="toe.R",
                label_es="Dedos Pie Der.",
            ),
        ]

        self.segments = {seg.name: seg for seg in defs}
        for custom in self.profile.custom_segments:
            cname = str(custom.get("name", "")).strip().upper()
            if not cname or cname in self.segments:
                continue
            parent = str(custom.get("parent") or "PELVIS").upper()
            if parent not in self.segments:
                parent = "PELVIS"
            offset_m = [float(v) for v in (custom.get("offset_m") or [0.0, 0.1, 0.0])[:3]]
            end_site_m = [float(v) for v in (custom.get("end_site_m") or [0.0, 0.1, 0.0])[:3]]
            self.segments[cname] = SegmentDef(
                name=cname,
                parent=parent,
                offset_m=offset_m,
                end_site_m=end_site_m,
                tpose_quat=ident,
                npose_quat=ident,
                mixamo_name=cname,
                rigify_name=cname.lower(),
                label_es=str(custom.get("label_es") or cname),
                is_custom=True,
            )

        self.children = {name: [] for name in self.segments}
        for seg in self.segments.values():
            if seg.parent and seg.parent in self.children:
                self.children[seg.parent].append(seg.name)

        # Orden topológico BFS desde PELVIS
        order: list[str] = []
        queue = ["PELVIS"]
        while queue:
            cur = queue.pop(0)
            order.append(cur)
            queue.extend(self.children.get(cur, []))
        self.order = order

    def to_summary(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "dimensions": self.dimensions,
            "segment_count": len(self.order),
            "order": self.order,
            "segments": {name: self.segments[name].to_dict() for name in self.order},
        }


class ProfileManager:
    """Gestiona la persistencia en JSON de perfiles antropométricos de sujetos."""

    def __init__(self, profiles_dir: Path) -> None:
        self.profiles_dir = profiles_dir
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._profiles: dict[str, AnthropometricProfile] = {}
        self.active_profile_id: str = "default_175"
        self._load_all()

    def _load_all(self) -> None:
        self._profiles.clear()
        for fpath in sorted(self.profiles_dir.glob("*.json")):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                prof = AnthropometricProfile.from_dict(data)
                self._profiles[prof.id] = prof
            except (OSError, json.JSONDecodeError, ValueError):
                continue

        if "default_175" not in self._profiles:
            default = AnthropometricProfile(
                id="default_175",
                name="Sujeto Estándar (175 cm)",
                height_cm=175.0,
            )
            self._profiles[default.id] = default
            self._save_profile(default)

        if self.active_profile_id not in self._profiles:
            self.active_profile_id = next(iter(self._profiles))

    def _save_profile(self, profile: AnthropometricProfile) -> None:
        target = self.profiles_dir / f"{profile.id}.json"
        target.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def list_profiles(self) -> list[dict[str, Any]]:
        out = []
        for prof in self._profiles.values():
            d = prof.to_dict()
            d["dimensions"] = compute_winter_dimensions(prof)
            d["active"] = prof.id == self.active_profile_id
            out.append(d)
        return out

    def get_active_profile(self) -> AnthropometricProfile:
        return self._profiles[self.active_profile_id]

    def set_active_profile(self, profile_id: str) -> AnthropometricProfile:
        if profile_id not in self._profiles:
            raise KeyError(f"Perfil no encontrado: {profile_id}")
        self.active_profile_id = profile_id
        return self._profiles[profile_id]

    def upsert_profile(self, payload: dict[str, Any]) -> AnthropometricProfile:
        prof_id = str(payload.get("id") or "").strip() or f"prof_{uuid.uuid4().hex[:6]}"
        existing = self._profiles.get(prof_id)
        if existing and "custom_segments" not in payload:
            payload["custom_segments"] = existing.custom_segments
        payload["id"] = prof_id
        prof = AnthropometricProfile.from_dict(payload)
        self._profiles[prof.id] = prof
        self._save_profile(prof)
        if payload.get("activate", True):
            self.active_profile_id = prof.id
        return prof

    def delete_profile(self, profile_id: str) -> None:
        if profile_id == "default_175":
            raise ValueError("El perfil predeterminado no puede eliminarse.")
        if profile_id not in self._profiles:
            raise KeyError(f"Perfil no encontrado: {profile_id}")
        del self._profiles[profile_id]
        fpath = self.profiles_dir / f"{profile_id}.json"
        if fpath.exists():
            fpath.unlink()
        if self.active_profile_id == profile_id:
            self.active_profile_id = "default_175"

    def add_custom_segment(
        self,
        name: str,
        parent: str,
        offset_m: list[float],
        end_site_m: list[float] | None = None,
        label_es: str | None = None,
    ) -> AnthropometricProfile:
        prof = self.get_active_profile()
        clean_name = name.strip().upper().replace(" ", "_")
        if not clean_name:
            raise ValueError("El nombre del segmento personalizado no puede estar vacío.")
        prof.custom_segments = [s for s in prof.custom_segments if s.get("name") != clean_name]
        prof.custom_segments.append(
            {
                "name": clean_name,
                "parent": parent.strip().upper(),
                "offset_m": [float(v) for v in offset_m[:3]],
                "end_site_m": [float(v) for v in (end_site_m or [0.0, 0.1, 0.0])[:3]],
                "label_es": label_es or clean_name,
            }
        )
        self._save_profile(prof)
        return prof
