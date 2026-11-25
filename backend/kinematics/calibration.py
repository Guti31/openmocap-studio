from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from backend.kinematics.anthropometry import SkeletonModel
from backend.kinematics.quaternions import (
    q_angle_deg,
    q_average_markley,
    q_extract_yaw_y,
    q_from_axis_angle,
    q_identity,
    q_inv,
    q_mul,
    q_normalize,
    q_rotate_vec,
    q_to_axis_angle,
)

PoseType = Literal["tpose", "npose"]
CalibrationMode = Literal["full", "quick"]
CalibrationState = Literal[
    "uncalibrated",
    "capturing_static",
    "static_done",
    "capturing_straight",
    "straight_done",
    "capturing_walk",
    "calibrated",
    "error",
]
CalibrationStage = Literal[
    "idle",
    "static_tpose",
    "static_straight",
    "dynamic_walk",
    "calibrated",
    "error",
]

# Tolerancias realistas para sujetos humanos usando sensores físicos Xsens MTw
MAX_STATIC_STD_DEG = 6.0
MAX_STATIC_GYRO_RAD_S = 0.35

# Segmentos cuyo movimiento en caminata tiene flexión sagital dominante alrededor del eje +X anatómico
SAGITTAL_LIMB_SEGMENTS = {
    "THIGH_L",
    "SHIN_L",
    "FOOT_L",
    "THIGH_R",
    "SHIN_R",
    "FOOT_R",
    "UPPER_ARM_L",
    "FOREARM_L",
    "HAND_L",
    "UPPER_ARM_R",
    "FOREARM_R",
    "HAND_R",
}


@dataclass
class WalkSample:
    q_raw: np.ndarray
    gyro: np.ndarray
    free_accel: np.ndarray


@dataclass
class SegmentCalibrationReport:
    segment: str
    quality_pct: float
    static_std_deg: float
    yaw_correction_deg: float
    sample_count_static: int
    sample_count_walk: int
    method: str
    mean_gyro_rad_s: float = 0.0
    within_tolerance: bool = True
    straight_residual_deg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment,
            "quality_pct": round(self.quality_pct, 1),
            "static_std_deg": round(self.static_std_deg, 3),
            "yaw_correction_deg": round(self.yaw_correction_deg, 2),
            "sample_count_static": self.sample_count_static,
            "sample_count_walk": self.sample_count_walk,
            "method": self.method,
            "mean_gyro_rad_s": round(self.mean_gyro_rad_s, 3),
            "within_tolerance": bool(self.within_tolerance),
            "straight_residual_deg": round(self.straight_residual_deg, 3),
        }


class CalibrationEngine:
    """
    Motor de calibración en dos etapas (T-Pose/N-Pose estática + Caminata dinámica opcional):
    1. Fase estática (4 s): elimina rotaciones arbitrarias de montaje de los sensores sobre las correas.
       Soporta traje completo o parcial (1 a 17+ sensores) y micro-balanceo realista humano.
    2. Fase dinámica (6 s): identifica ejes funcionales de flexión y propulsión por sensor para
       anular la deriva magnética en interiores (corrección individual de rumbo psi_i alrededor de +Y).
    """

    def __init__(self, skeleton: SkeletonModel) -> None:
        self._lock = threading.RLock()
        self.skeleton = skeleton
        self.state: CalibrationState = "uncalibrated"
        self.mode: CalibrationMode = "full"
        self.pose_type: PoseType = "tpose"
        self.ok: bool = True
        self.error_es: str | None = None
        self._transition_seq: int = 0

        self.static_duration_s: float = 4.0
        self.straight_duration_s: float = 3.0
        self.walk_duration_s: float = 6.0
        self._phase_start_ts: float = 0.0
        self._straight_complete_after: bool = False

        self._static_buffers: dict[str, list[np.ndarray]] = {}
        self._static_gyro_buffers: dict[str, list[float]] = {}
        self._straight_buffers: dict[str, list[np.ndarray]] = {}
        self._straight_gyro_buffers: dict[str, list[float]] = {}
        self._walk_buffers: dict[str, list[WalkSample]] = {}
        self._unassigned_seen: set[str] = set()
        self._raw_packets_seen: int = 0
        self._live_segments_static: set[str] = set()
        self._live_packet_count_static: int = 0
        self._live_segments_straight: set[str] = set()
        self._live_packet_count_straight: int = 0
        self._last_hal_feed_ts: float = 0.0

        self.q_raw_static: dict[str, np.ndarray] = {}
        self.q_raw_straight: dict[str, np.ndarray] = {}
        self.straight_anchored: bool = False
        self.q_heading: dict[str, np.ndarray] = {}
        self.q_offset_final: dict[str, np.ndarray] = {}
        self.reports: dict[str, SegmentCalibrationReport] = {}
        self.overall_quality_pct: float = 0.0
        self.max_static_std_deg: float = 0.0
        self.mean_static_gyro_rad_s: float = 0.0
        self.last_message_es: str = "Sin calibrar: coloque al sujeto en T-Pose o N-Pose."
        self._backup_state: dict[str, Any] | None = None

    def is_capturing(self) -> bool:
        with self._lock:
            return self.state in ("capturing_static", "capturing_straight", "capturing_walk")

    def has_recent_hal_samples(self, window_s: float = 0.25) -> bool:
        with self._lock:
            return (time.monotonic() - self._last_hal_feed_ts) <= window_s

    def _current_stage(self) -> CalibrationStage:
        if self.state == "capturing_static":
            return "static_tpose"
        if self.state in ("static_done", "capturing_straight"):
            return "static_straight"
        if self.state in ("straight_done", "capturing_walk"):
            return "dynamic_walk"
        if self.state == "calibrated":
            return "calibrated"
        if self.state == "error":
            return "error"
        return "idle"

    def update_skeleton(self, skeleton: SkeletonModel) -> None:
        with self._lock:
            self.skeleton = skeleton

    def _ref_quat(self, segment: str) -> np.ndarray:
        seg_def = self.skeleton.segments.get(segment)
        if not seg_def:
            return q_identity()
        return np.asarray(
            seg_def.tpose_quat if self.pose_type == "tpose" else seg_def.npose_quat,
            dtype=np.float64,
        )

    def reset(self) -> dict[str, Any]:
        with self._lock:
            self.state = "uncalibrated"
            self.ok = True
            self.error_es = None
            self._static_buffers.clear()
            self._static_gyro_buffers.clear()
            self._straight_buffers.clear()
            self._straight_gyro_buffers.clear()
            self._walk_buffers.clear()
            self._unassigned_seen.clear()
            self._raw_packets_seen = 0
            self._live_segments_static.clear()
            self._live_packet_count_static = 0
            self._live_segments_straight.clear()
            self._live_packet_count_straight = 0
            self.q_raw_static.clear()
            self.q_raw_straight.clear()
            self.straight_anchored = False
            self._straight_complete_after = False
            self.q_heading.clear()
            self.q_offset_final.clear()
            self.reports.clear()
            self._backup_state = None
            self.overall_quality_pct = 0.0
            self.max_static_std_deg = 0.0
            self.mean_static_gyro_rad_s = 0.0
            self._transition_seq += 1
            self.last_message_es = "Calibración reiniciada."
            return self.get_status()

    def restore_backup(self) -> dict[str, Any]:
        """Restaura la calibración previa válida si el usuario cancela un reintento."""
        with self._lock:
            if self._backup_state and self._backup_state.get("q_offset_final"):
                bk = self._backup_state
                self.q_raw_static = {k: v.copy() for k, v in bk["q_raw_static"].items()}
                self.q_raw_straight = {k: v.copy() for k, v in bk.get("q_raw_straight", {}).items()}
                self.straight_anchored = bool(bk.get("straight_anchored", False))
                self.q_heading = {k: v.copy() for k, v in bk["q_heading"].items()}
                self.q_offset_final = {k: v.copy() for k, v in bk["q_offset_final"].items()}
                self.reports = dict(bk["reports"])
                self.overall_quality_pct = float(bk["overall_quality_pct"])
                self.max_static_std_deg = float(bk["max_static_std_deg"])
                self.mean_static_gyro_rad_s = float(bk["mean_static_gyro_rad_s"])
                self.mode = bk["mode"]
                self.pose_type = bk["pose_type"]
                self.state = "calibrated"
                self.ok = True
                self.error_es = None
                self.last_message_es = str(bk["last_message_es"])
                self._backup_state = None
                self._transition_seq += 1
            return self.get_status()

    def start_static(
        self,
        pose_type: PoseType = "tpose",
        duration_s: float = 4.0,
        mode: CalibrationMode = "full",
    ) -> dict[str, Any]:
        with self._lock:
            if self.state == "calibrated" and self.q_offset_final:
                self._backup_state = {
                    "q_raw_static": {k: v.copy() for k, v in self.q_raw_static.items()},
                    "q_raw_straight": {k: v.copy() for k, v in self.q_raw_straight.items()},
                    "straight_anchored": self.straight_anchored,
                    "q_heading": {k: v.copy() for k, v in self.q_heading.items()},
                    "q_offset_final": {k: v.copy() for k, v in self.q_offset_final.items()},
                    "reports": dict(self.reports),
                    "overall_quality_pct": self.overall_quality_pct,
                    "max_static_std_deg": self.max_static_std_deg,
                    "mean_static_gyro_rad_s": self.mean_static_gyro_rad_s,
                    "mode": self.mode,
                    "pose_type": self.pose_type,
                    "last_message_es": self.last_message_es,
                }
            self.pose_type = pose_type
            self.mode = mode
            self.static_duration_s = max(0.5, float(duration_s))
            self._static_buffers = {}
            self._static_gyro_buffers = {}
            self._straight_buffers = {}
            self._straight_gyro_buffers = {}
            self._unassigned_seen.clear()
            self._raw_packets_seen = 0
            self._live_segments_static.clear()
            self._live_packet_count_static = 0
            self._live_segments_straight.clear()
            self._live_packet_count_straight = 0
            self.q_raw_static.clear()
            self.q_raw_straight.clear()
            self.straight_anchored = False
            self._straight_complete_after = False
            self.q_heading.clear()
            self.q_offset_final.clear()
            self.reports.clear()
            self.overall_quality_pct = 0.0
            self.max_static_std_deg = 0.0
            self.mean_static_gyro_rad_s = 0.0
            self.ok = True
            self.error_es = None
            self._phase_start_ts = time.monotonic()
            self.state = "capturing_static"
            self._transition_seq += 1
            label = "T-Pose" if pose_type == "tpose" else "N-Pose"
            mode_label = "rápida" if mode == "quick" else "completa"
            self.last_message_es = (
                f"Capturando postura estática {label} ({mode_label}, {self.static_duration_s:.1f} s)..."
            )
            return self.get_status()

    def start_straight(self, duration_s: float = 3.0, complete_after: bool = False) -> dict[str, Any]:
        """Captura postura recta de reposo (N-Pose 3 s) para refinar el cero vertical de torso, escápulas y brazos."""
        with self._lock:
            if not self.q_raw_static:
                raise ValueError("Debe completar primero la Posición T / postura estática inicial.")
            self.straight_duration_s = max(0.4, float(duration_s))
            self._straight_complete_after = bool(complete_after)
            self._straight_buffers = {}
            self._straight_gyro_buffers = {}
            self._live_segments_straight.clear()
            self._live_packet_count_straight = 0
            self.ok = True
            self.error_es = None
            self._phase_start_ts = time.monotonic()
            self.state = "capturing_straight"
            self._transition_seq += 1
            self.last_message_es = (
                f"Capturando Posición Recta ({self.straight_duration_s:.1f} s) para alinear torso, escápulas y brazos..."
            )
            return self.get_status()

    def start_walk(self, duration_s: float = 6.0) -> dict[str, Any]:
        with self._lock:
            if not self.q_raw_static:
                raise ValueError("Debe completar primero la calibración estática (T-Pose / N-Pose).")
            self.walk_duration_s = max(0.8, float(duration_s))
            self._walk_buffers = {}
            self.ok = True
            self.error_es = None
            self._phase_start_ts = time.monotonic()
            self.state = "capturing_walk"
            self._transition_seq += 1
            self.last_message_es = f"Capturando caminata dinámica ({self.walk_duration_s:.1f} s)..."
            return self.get_status()

    def feed_sample(
        self,
        segment: str,
        q_raw: np.ndarray,
        gyro: np.ndarray,
        free_accel: np.ndarray,
        sensor_id: str | None = None,
        from_hal: bool = False,
    ) -> None:
        """Ingresa una muestra de sensor mapeado directamente cuando una fase de captura está activa."""
        with self._lock:
            if self.state not in ("capturing_static", "capturing_straight", "capturing_walk"):
                return
            if from_hal:
                self._last_hal_feed_ts = time.monotonic()
            self._raw_packets_seen += 1

            if not segment or segment == "UNASSIGNED" or segment not in self.skeleton.segments:
                if sensor_id:
                    self._unassigned_seen.add(str(sensor_id).upper())
                return

            qn = q_normalize(q_raw)
            gyro_arr = np.asarray(gyro, dtype=np.float64)

            if self.state == "capturing_static":
                self._static_buffers.setdefault(segment, []).append(qn)
                gyro_norm = float(np.linalg.norm(gyro_arr))
                self._static_gyro_buffers.setdefault(segment, []).append(gyro_norm)
                self._live_segments_static.add(segment)
                self._live_packet_count_static += 1
            elif self.state == "capturing_straight":
                self._straight_buffers.setdefault(segment, []).append(qn)
                gyro_norm = float(np.linalg.norm(gyro_arr))
                self._straight_gyro_buffers.setdefault(segment, []).append(gyro_norm)
                self._live_segments_straight.add(segment)
                self._live_packet_count_straight += 1
            elif self.state == "capturing_walk":
                self._walk_buffers.setdefault(segment, []).append(
                    WalkSample(
                        q_raw=qn,
                        gyro=gyro_arr,
                        free_accel=np.asarray(free_accel, dtype=np.float64),
                    )
                )

    def tick(self) -> None:
        """Verifica expiración automática de temporizadores de fase."""
        with self._lock:
            now = time.monotonic()
            if self.state == "capturing_static":
                if (now - self._phase_start_ts) >= self.static_duration_s:
                    self.finalize_static()
            elif self.state == "capturing_straight":
                if (now - self._phase_start_ts) >= self.straight_duration_s:
                    self.finalize_straight()
            elif self.state == "capturing_walk":
                if (now - self._phase_start_ts) >= self.walk_duration_s:
                    self.finalize_walk()

    def finalize_static(self) -> dict[str, Any]:
        """Calcula promedios de Markley y offsets estáticos con tolerancia realista para MTw."""
        with self._lock:
            active_segments = {seg: samples for seg, samples in self._static_buffers.items() if samples}
            if not active_segments or len(self._live_segments_static) < 1 or self._live_packet_count_static < 1:
                self.state = "error"
                self.ok = False
                self._transition_seq += 1
                if self._unassigned_seen:
                    sample_ids = ", ".join(sorted(self._unassigned_seen)[:4])
                    base_err = (
                        f"Se detectaron {len(self._unassigned_seen)} sensor(es) ({sample_ids}) sin segmento corporal asignado. "
                        "Asígnalos en Mapa Corporal antes de calibrar."
                    )
                else:
                    base_err = (
                        "No se recibieron paquetes de sensores durante los 4 segundos. "
                        "Verifica que la antena Xsens Awinda y al menos un sensor MTw estén encendidos y vinculados."
                    )
                if self._backup_state and self._backup_state.get("q_offset_final"):
                    bk = self._backup_state
                    self.q_raw_static = {k: v.copy() for k, v in bk["q_raw_static"].items()}
                    self.q_heading = {k: v.copy() for k, v in bk["q_heading"].items()}
                    self.q_offset_final = {k: v.copy() for k, v in bk["q_offset_final"].items()}
                    self.reports = dict(bk["reports"])
                    self.overall_quality_pct = float(bk["overall_quality_pct"])
                    self.max_static_std_deg = float(bk["max_static_std_deg"])
                    self.mean_static_gyro_rad_s = float(bk["mean_static_gyro_rad_s"])
                    base_err += " Se conservó la calibración previa activa."
                self.error_es = base_err
                self.last_message_es = self.error_es
                return self.get_status()

            # Estimar el rumbo inicial de la pelvis solo si está presente en un traje completo/parcial
            pelvis_yaw = 0.0
            if "PELVIS" in active_segments:
                q_pelvis_avg = q_average_markley(active_segments["PELVIS"])
                pelvis_yaw = q_extract_yaw_y(q_pelvis_avg)

            qualities: list[float] = []
            max_std = 0.0
            gyro_means: list[float] = []

            for seg, samples in active_segments.items():
                q_avg = q_average_markley(samples)
                angles = [q_angle_deg(s, q_avg) for s in samples]
                std_deg = float(math.sqrt(sum(a * a for a in angles) / max(1, len(angles))))

                g_samples = self._static_gyro_buffers.get(seg, [])
                mean_gyro = float(sum(g_samples) / len(g_samples)) if g_samples else 0.0

                # Recorte robusto al 70% más estable ante micro-balanceo o picos breves en MTw reales
                if len(samples) >= 10 and (std_deg > MAX_STATIC_STD_DEG or mean_gyro >= MAX_STATIC_GYRO_RAD_S):
                    ranked_idx = sorted(range(len(samples)), key=lambda i: angles[i])
                    keep_n = max(5, int(math.ceil(0.70 * len(samples))))
                    trimmed = [samples[i] for i in ranked_idx[:keep_n]]
                    q_avg = q_average_markley(trimmed)
                    trimmed_angles = [q_angle_deg(s, q_avg) for s in trimmed]
                    std_deg = float(math.sqrt(sum(a * a for a in trimmed_angles) / max(1, len(trimmed_angles))))
                    if g_samples and len(g_samples) == len(samples):
                        trimmed_g = [g_samples[i] for i in ranked_idx[:keep_n]]
                        mean_gyro = float(sum(trimmed_g) / len(trimmed_g))

                within_tol = (std_deg <= MAX_STATIC_STD_DEG) and (mean_gyro < MAX_STATIC_GYRO_RAD_S)
                if within_tol:
                    quality = max(65.0, min(100.0, 100.0 - std_deg * 5.8))
                else:
                    quality = max(45.0, min(64.0, 65.0 - max(0.0, std_deg - MAX_STATIC_STD_DEG) * 3.0))

                qualities.append(quality)
                max_std = max(max_std, std_deg)
                gyro_means.append(mean_gyro)

                self.q_raw_static[seg] = q_avg
                q_head = q_from_axis_angle([0.0, 1.0, 0.0], -pelvis_yaw)
                self.q_heading[seg] = q_head
                q_ref = self._ref_quat(seg)
                # q_bone = q_head * q_raw * q_offset => en estático: q_ref = q_head * q_avg * q_offset
                self.q_offset_final[seg] = q_normalize(
                    q_mul(q_inv(q_avg), q_mul(q_inv(q_head), q_ref))
                )

                self.reports[seg] = SegmentCalibrationReport(
                    segment=seg,
                    quality_pct=quality,
                    static_std_deg=std_deg,
                    yaw_correction_deg=math.degrees(-pelvis_yaw),
                    sample_count_static=len(samples),
                    sample_count_walk=0,
                    method="static_quick" if self.mode == "quick" else "static_only",
                    mean_gyro_rad_s=mean_gyro,
                    within_tolerance=within_tol,
                )

            self.overall_quality_pct = round(sum(qualities) / max(1, len(qualities)), 1)
            self.max_static_std_deg = round(max_std, 3)
            self.mean_static_gyro_rad_s = round(
                (sum(gyro_means) / max(1, len(gyro_means))) if gyro_means else 0.0,
                3,
            )
            self.ok = True
            self.error_es = None
            self._transition_seq += 1

            if self.mode == "quick":
                self._backup_state = None
                self.state = "calibrated"
                self.last_message_es = (
                    f"Calibración rápida (T-Pose 4s) lista con {len(self.q_offset_final)} sensor(es). "
                    f"Calidad: {self.overall_quality_pct:.1f} %."
                )
            else:
                self.state = "static_done"
                self.last_message_es = (
                    f"Postura estática lista ({len(self.q_offset_final)} sensor(es), "
                    f"calidad {self.overall_quality_pct:.1f} %). Continúa con la caminata de 6 s o finaliza directo."
                )
            return self.get_status()

    def finalize_straight(self) -> dict[str, Any]:
        """Ancla el cero vertical de postura recta (N-Pose) desacoplando inclinación residual escapular."""
        with self._lock:
            if not self.q_raw_static:
                return self.finalize_static()

            active_segments = {seg: samples for seg, samples in self._straight_buffers.items() if samples}
            if not active_segments or len(self._live_segments_straight) < 1 or self._live_packet_count_straight < 1:
                self.state = "error"
                self.ok = False
                self._transition_seq += 1
                self.error_es = (
                    "No se recibieron paquetes durante la Posición Recta (3 s). "
                    "Verifica que la antena y sensores sigan transmitiendo."
                )
                self.last_message_es = self.error_es
                return self.get_status()

            qualities: list[float] = []
            residuals: list[float] = []

            for seg, samples in active_segments.items():
                q_avg = q_average_markley(samples)
                angles = [q_angle_deg(s, q_avg) for s in samples]
                std_deg = float(math.sqrt(sum(a * a for a in angles) / max(1, len(angles))))

                g_samples = self._straight_gyro_buffers.get(seg, [])
                mean_gyro = float(sum(g_samples) / len(g_samples)) if g_samples else 0.0

                if len(samples) >= 10 and (std_deg > MAX_STATIC_STD_DEG or mean_gyro >= MAX_STATIC_GYRO_RAD_S):
                    ranked_idx = sorted(range(len(samples)), key=lambda i: angles[i])
                    keep_n = max(5, int(math.ceil(0.70 * len(samples))))
                    trimmed = [samples[i] for i in ranked_idx[:keep_n]]
                    q_avg = q_average_markley(trimmed)
                    trimmed_angles = [q_angle_deg(s, q_avg) for s in trimmed]
                    std_deg = float(math.sqrt(sum(a * a for a in trimmed_angles) / max(1, len(trimmed_angles))))

                seg_def = self.skeleton.segments.get(seg)
                q_ref_straight = (
                    np.asarray(seg_def.npose_quat, dtype=np.float64) if seg_def else q_identity()
                )
                q_head = self.q_heading.get(seg, q_identity())

                residual_deg = 0.0
                if seg in self.q_offset_final:
                    q_pred = q_normalize(q_mul(q_head, q_mul(q_avg, self.q_offset_final[seg])))
                    residual_deg = q_angle_deg(q_pred, q_ref_straight)

                self.q_raw_straight[seg] = q_avg
                self.q_offset_final[seg] = q_normalize(
                    q_mul(q_inv(q_avg), q_mul(q_inv(q_head), q_ref_straight))
                )

                prev_rep = self.reports.get(seg)
                within_tol = (std_deg <= MAX_STATIC_STD_DEG) and (mean_gyro < MAX_STATIC_GYRO_RAD_S)
                base_q = prev_rep.quality_pct if prev_rep else 95.0
                straight_q = max(70.0, min(100.0, 100.0 - std_deg * 4.5))
                quality = round(0.5 * base_q + 0.5 * straight_q, 1)
                qualities.append(quality)
                residuals.append(residual_deg)

                self.reports[seg] = SegmentCalibrationReport(
                    segment=seg,
                    quality_pct=quality,
                    static_std_deg=prev_rep.static_std_deg if prev_rep else std_deg,
                    yaw_correction_deg=prev_rep.yaw_correction_deg if prev_rep else 0.0,
                    sample_count_static=prev_rep.sample_count_static if prev_rep else len(samples),
                    sample_count_walk=prev_rep.sample_count_walk if prev_rep else 0,
                    method="tpose_straight_quick" if self._straight_complete_after else "tpose_straight",
                    mean_gyro_rad_s=prev_rep.mean_gyro_rad_s if prev_rep else mean_gyro,
                    within_tolerance=(prev_rep.within_tolerance if prev_rep else True) and within_tol,
                    straight_residual_deg=residual_deg,
                )

            self.straight_anchored = True
            self.overall_quality_pct = round(sum(qualities) / max(1, len(qualities)), 1)
            self.ok = True
            self.error_es = None
            self._transition_seq += 1

            max_res = max(residuals) if residuals else 0.0
            if self._straight_complete_after:
                self.mode = "quick"
                self._backup_state = None
                self.state = "calibrated"
                self.last_message_es = (
                    f"Calibración rápida (T-Pose + Postura Recta) lista para {len(self.q_offset_final)} sensor(es). "
                    f"Calidad: {self.overall_quality_pct:.1f} % · Alineación recta corregida ({max_res:.1f}°)."
                )
            else:
                self.state = "straight_done"
                self.last_message_es = (
                    f"Postura recta anclada ({len(self.q_offset_final)} sensor(es), desvío escapular/corporal "
                    f"compensado {max_res:.1f}°). Continúa con la caminata de 6 s o finaliza directo."
                )
            return self.get_status()

    def complete_quick_from_static(self) -> dict[str, Any]:
        """Aplica directamente los offsets estáticos para saltar la caminata cuando ya terminó la fase de 4 s."""
        with self._lock:
            if (
                not self.q_offset_final
                or len(self._live_segments_static) < 1
                or self._live_packet_count_static < 1
            ):
                self.state = "error"
                self.ok = False
                self._transition_seq += 1
                self.error_es = (
                    "Primero captura flujo activo real durante los 4 segundos estáticos antes de aplicar calibración rápida."
                )
                self.last_message_es = self.error_es
                return self.get_status()

            self.mode = "quick"
            self._backup_state = None
            self.ok = True
            self.error_es = None
            self.state = "calibrated"
            self._transition_seq += 1
            for rep in self.reports.values():
                rep.method = "tpose_straight_quick" if self.straight_anchored else "static_quick"
            label_q = "T-Pose + Postura Recta" if self.straight_anchored else "T-Pose"
            self.last_message_es = (
                f"Calibración rápida ({label_q}) aplicada para {len(self.q_offset_final)} sensor(es). "
                f"Calidad: {self.overall_quality_pct:.1f} %."
            )
            return self.get_status()

    @staticmethod
    def _mean_delta_rotvec_xz(samples: list[WalkSample], q_static: np.ndarray) -> tuple[float, float]:
        """Vector de rotación promedio en XZ respecto a la postura estática (elimina q_strap)."""
        q_st_inv = q_inv(q_static)
        sx = 0.0
        sz = 0.0
        cnt = 0
        for sp in samples:
            dq = q_mul(sp.q_raw, q_st_inv)
            axis, ang = q_to_axis_angle(dq)
            sx += float(axis[0]) * ang
            sz += float(axis[2]) * ang
            cnt += 1
        if cnt == 0:
            return 0.0, 0.0
        return sx / float(cnt), sz / float(cnt)

    def _estimate_limb_yaw_from_gyro(
        self,
        samples: list[WalkSample],
        seg_name: str = "",
        q_static: np.ndarray | None = None,
        ref_psi: float | None = None,
    ) -> tuple[float | None, float, bool]:
        """
        Estima el error de guiñada psi_err (rad) de un segmento con flexión sagital alrededor de +X.
        Desambigua 180° usando asimetría cinemática independiente de correas (flexión de rodilla/codo/caída de brazo),
        consenso circular multi-segmento y rumbo estático para cubrir los 360° completos.
        """
        xz_pts: list[list[float]] = []
        for sp in samples:
            omega_world_prov = q_rotate_vec(sp.q_raw, sp.gyro)
            if float(np.hypot(omega_world_prov[0], omega_world_prov[2])) > 0.15:
                xz_pts.append([float(omega_world_prov[0]), float(omega_world_prov[2])])

        if len(xz_pts) < 15:
            return None, 0.0, False

        pts = np.asarray(xz_pts, dtype=np.float64)
        cov = (pts.T @ pts) / float(len(pts))
        eigvals, eigvecs = np.linalg.eigh(cov)
        l1 = float(eigvals[1])
        l2 = float(eigvals[0])
        ratio = l1 / max(l2, 1e-9)
        if l1 < 0.05 or ratio < 2.2:
            return None, ratio, False

        u = np.array([float(eigvecs[0, 1]), float(eigvecs[1, 1])], dtype=np.float64)
        confident = False

        # Nivel 1: Asimetría biomecánica respecto a q_static (q_strap se cancela en q_raw * q_static^-1)
        if q_static is not None:
            mx, mz = self._mean_delta_rotvec_xz(samples, q_static)
            proj_x = u[0] * mx + u[1] * mz
            # En Y-up: u = [cos(psi), -sin(psi)] (+X), e_z = [-u[1], u[0]] (+Z)
            proj_z = (-u[1]) * mx + u[0] * mz
            if seg_name in ("SHIN_L", "SHIN_R") and abs(proj_x) > 0.08:
                if proj_x < 0.0:
                    u = -u
                confident = True
            elif seg_name in ("UPPER_ARM_L", "FOREARM_L", "HAND_L") and self.pose_type == "tpose" and abs(proj_z) > 0.35:
                # Bajar brazo izquierdo desde T-Pose rota alrededor de -Z
                if proj_z > 0.0:
                    u = -u
                confident = True
            elif seg_name in ("UPPER_ARM_R", "FOREARM_R", "HAND_R") and self.pose_type == "tpose" and abs(proj_z) > 0.35:
                # Bajar brazo derecho desde T-Pose rota alrededor de +Z
                if proj_z < 0.0:
                    u = -u
                confident = True
            elif seg_name in ("FOREARM_L", "FOREARM_R", "HAND_L", "HAND_R") and self.pose_type == "npose" and abs(proj_x) > 0.15:
                # Desde N-Pose la flexión de codo hacia delante rota alrededor de -X
                if proj_x > 0.0:
                    u = -u
                confident = True

        # Nivel 2: Consenso de rumbo de la pasada 1
        if not confident and ref_psi is not None:
            if (u[0] * math.cos(ref_psi) - u[1] * math.sin(ref_psi)) < 0.0:
                u = -u
            confident = True

        # Nivel 3: Fallback clásico cuando ningún segmento tuvo asimetría cinemática
        if not confident and ref_psi is None:
            if float(u[0]) < 0.0:
                u = -u

        psi = math.atan2(-float(u[1]), float(u[0]))
        return psi, ratio, confident

    def _estimate_axial_yaw_from_accel(
        self,
        samples: list[WalkSample],
        seg_name: str = "",
        q_static: np.ndarray | None = None,
        ref_psi: float | None = None,
    ) -> tuple[float | None, float, bool]:
        """
        Estima psi_err (rad) a partir de la aceleración horizontal de propulsión/frenado (a_x, a_z)
        desambiguando ±180° mediante inclinación sagital y consenso multi-segmento.
        """
        xz_pts: list[list[float]] = []
        for sp in samples:
            ax, az = float(sp.free_accel[0]), float(sp.free_accel[2])
            if math.hypot(ax, az) > 0.12:
                xz_pts.append([ax, az])

        if len(xz_pts) < 15:
            return None, 0.0, False

        pts = np.asarray(xz_pts, dtype=np.float64)
        pts_centered = pts - np.mean(pts, axis=0, keepdims=True)
        cov = (pts_centered.T @ pts_centered) / float(len(pts_centered))
        eigvals, eigvecs = np.linalg.eigh(cov)
        l1 = float(eigvals[1])
        l2 = float(eigvals[0])
        ratio = l1 / max(l2, 1e-9)
        if l1 < 0.03 or ratio < 2.0:
            return None, ratio, False

        v = np.array([float(eigvecs[0, 1]), float(eigvecs[1, 1])], dtype=np.float64)
        confident = False

        # v representa +Z = [sin(psi), cos(psi)], por lo que +X = [v[1], -v[0]]
        if q_static is not None and seg_name in ("PELVIS", "STERNUM"):
            mx, mz = self._mean_delta_rotvec_xz(samples, q_static)
            proj_x = v[1] * mx - v[0] * mz
            if abs(proj_x) > 0.045:
                if proj_x < 0.0:
                    v = -v
                confident = True

        if not confident and ref_psi is not None:
            if (v[0] * math.sin(ref_psi) + v[1] * math.cos(ref_psi)) < 0.0:
                v = -v
            confident = True

        if not confident and ref_psi is None:
            if float(v[1]) < 0.0:
                v = -v

        psi = math.atan2(float(v[0]), float(v[1]))
        return psi, ratio, confident

    def finalize_walk(self) -> dict[str, Any]:
        """
        Calcula la corrección individual de deriva magnética (psi_i) combinando análisis PCA
        de velocidad angular en extremidades y aceleración de marcha en tronco/cabeza en 360°.
        """
        with self._lock:
            if not self.q_raw_static:
                return self.finalize_static()

            pass1_results: dict[str, tuple[float, str, bool]] = {}

            for seg, samples in self._walk_buffers.items():
                if seg not in self.q_raw_static:
                    continue
                q_st = self.q_raw_static.get(seg)
                if seg in SAGITTAL_LIMB_SEGMENTS:
                    psi, ratio, conf = self._estimate_limb_yaw_from_gyro(samples, seg_name=seg, q_static=q_st)
                    if psi is not None:
                        pass1_results[seg] = (psi, f"pca_gyro_sagittal(ratio={ratio:.1f})", conf)

            for seg, samples in self._walk_buffers.items():
                if seg not in self.q_raw_static or seg in pass1_results:
                    continue
                q_st = self.q_raw_static.get(seg)
                psi_acc, ratio_acc, conf_a = self._estimate_axial_yaw_from_accel(samples, seg_name=seg, q_static=q_st)
                if psi_acc is not None:
                    pass1_results[seg] = (psi_acc, f"pca_accel_propulsion(ratio={ratio_acc:.1f})", conf_a)
                else:
                    psi_gyro, ratio_g, conf_g = self._estimate_limb_yaw_from_gyro(samples, seg_name=seg, q_static=q_st)
                    if psi_gyro is not None:
                        pass1_results[seg] = (psi_gyro, f"pca_gyro_fallback(ratio={ratio_g:.1f})", conf_g)

            # Pasada 2: usar consenso circular de segmentos con orientación inequívoca (360°)
            confident_psis = [psi for psi, _m, conf in pass1_results.values() if conf]
            anchor_psi: float | None = None
            if confident_psis:
                anchor_psi = math.atan2(
                    sum(math.sin(p) for p in confident_psis),
                    sum(math.cos(p) for p in confident_psis),
                )

            detected_psis: dict[str, tuple[float, str]] = {}
            for seg, (psi, method, conf) in pass1_results.items():
                if not conf and anchor_psi is not None:
                    if math.cos(psi - anchor_psi) < 0.0:
                        psi = math.atan2(math.sin(psi + math.pi), math.cos(psi + math.pi))
                detected_psis[seg] = (psi, method)

            consensus_psi = 0.0
            has_walk_heading = bool(detected_psis)
            if has_walk_heading:
                sin_sum = sum(math.sin(p) for p, _ in detected_psis.values())
                cos_sum = sum(math.cos(p) for p, _ in detected_psis.values())
                consensus_psi = math.atan2(sin_sum, cos_sum)

            self._backup_state = None

            qualities: list[float] = []
            for seg, q_avg in self.q_raw_static.items():
                prev_rep = self.reports.get(seg)
                if seg in detected_psis:
                    psi, method = detected_psis[seg]
                    q_head = q_from_axis_angle([0.0, 1.0, 0.0], -psi)
                elif has_walk_heading:
                    psi = consensus_psi
                    method = "consensus_yaw"
                    q_head = q_from_axis_angle([0.0, 1.0, 0.0], -psi)
                else:
                    q_head = self.q_heading.get(seg, q_identity())
                    psi = -math.radians(prev_rep.yaw_correction_deg) if prev_rep else 0.0
                    method = "static_heading_kept"

                self.q_heading[seg] = q_head
                if seg in self.q_raw_straight:
                    anchor_raw = self.q_raw_straight[seg]
                    seg_def = self.skeleton.segments.get(seg)
                    anchor_ref = (
                        np.asarray(seg_def.npose_quat, dtype=np.float64) if seg_def else q_identity()
                    )
                    if seg in detected_psis:
                        method = f"{method}+straight"
                    elif has_walk_heading:
                        method = "consensus_yaw+straight"
                else:
                    anchor_raw = q_avg
                    anchor_ref = self._ref_quat(seg)

                self.q_offset_final[seg] = q_normalize(
                    q_mul(q_inv(anchor_raw), q_mul(q_inv(q_head), anchor_ref))
                )

                static_std = prev_rep.static_std_deg if prev_rep else 0.0
                static_cnt = prev_rep.sample_count_static if prev_rep else 0
                mean_gyro = prev_rep.mean_gyro_rad_s if prev_rep else 0.0
                within_tol = prev_rep.within_tolerance if prev_rep else True
                straight_res = prev_rep.straight_residual_deg if prev_rep else 0.0
                walk_cnt = len(self._walk_buffers.get(seg, []))
                bonus = 4.0 if seg in detected_psis else 0.0
                quality = max(60.0, min(100.0, 96.0 + bonus - static_std * 5.0))
                qualities.append(quality)

                self.reports[seg] = SegmentCalibrationReport(
                    segment=seg,
                    quality_pct=quality,
                    static_std_deg=static_std,
                    yaw_correction_deg=math.degrees(-psi),
                    sample_count_static=static_cnt,
                    sample_count_walk=walk_cnt,
                    method=method,
                    mean_gyro_rad_s=mean_gyro,
                    within_tolerance=within_tol,
                    straight_residual_deg=straight_res,
                )

            self.overall_quality_pct = round(sum(qualities) / max(1, len(qualities)), 1)
            self.ok = True
            self.error_es = None
            self.state = "calibrated"
            self._transition_seq += 1
            self.last_message_es = (
                f"Calibración completa (T-Pose + Caminata) activa para {len(self.q_offset_final)} sensor(es). "
                f"Calidad global: {self.overall_quality_pct:.1f} %."
            )
            return self.get_status()

    def quick_heading_reset(self, current_raw_quats: dict[str, np.ndarray]) -> dict[str, Any]:
        """Re-centra el rumbo global de todos los segmentos para que la pelvis mire hacia +Z."""
        with self._lock:
            if "PELVIS" not in current_raw_quats:
                return self.get_status()

            if "PELVIS" in self.q_offset_final:
                q_pelvis_world = self.apply("PELVIS", current_raw_quats["PELVIS"])
            else:
                q_pelvis_world = q_normalize(current_raw_quats["PELVIS"])

            delta_yaw = q_extract_yaw_y(q_pelvis_world)
            q_corr = q_from_axis_angle([0.0, 1.0, 0.0], -delta_yaw)
            for seg in list(self.q_heading.keys()):
                self.q_heading[seg] = q_normalize(q_mul(q_corr, self.q_heading[seg]))
            self._transition_seq += 1
            self.last_message_es = f"Rumbo reiniciado ({math.degrees(-delta_yaw):+.1f}°)."
            return self.get_status()

    def apply(self, segment: str, q_raw: np.ndarray) -> np.ndarray:
        """Transforma un cuaternión crudo del sensor al marco mundial anatómico del segmento."""
        qn = q_normalize(q_raw)
        with self._lock:
            if segment not in self.q_offset_final:
                return qn
            q_head = self.q_heading.get(segment, q_identity())
            q_off = self.q_offset_final[segment]
        return q_normalize(q_mul(q_head, q_mul(qn, q_off)))

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            progress = 0.0
            remaining_s = 0.0
            if self.state == "capturing_static":
                active_captured = len(self._static_buffers)
                elapsed = now - self._phase_start_ts
                progress = min(1.0, max(0.0, elapsed / self.static_duration_s))
                remaining_s = max(0.0, self.static_duration_s - elapsed)
            elif self.state == "capturing_straight":
                active_captured = len(self._straight_buffers)
                elapsed = now - self._phase_start_ts
                progress = min(1.0, max(0.0, elapsed / self.straight_duration_s))
                remaining_s = max(0.0, self.straight_duration_s - elapsed)
            elif self.state == "capturing_walk":
                active_captured = len(self.q_offset_final)
                elapsed = now - self._phase_start_ts
                progress = min(1.0, max(0.0, elapsed / self.walk_duration_s))
                remaining_s = max(0.0, self.walk_duration_s - elapsed)
            else:
                active_captured = len(self.q_offset_final)
                if self.state in ("static_done", "straight_done", "calibrated"):
                    progress = 1.0

            return {
                "ok": self.ok,
                "error_es": self.error_es,
                "state": self.state,
                "stage": self._current_stage(),
                "mode": self.mode,
                "pose_type": self.pose_type,
                "straight_anchored": self.straight_anchored,
                "transition_seq": self._transition_seq,
                "progress": round(progress, 3),
                "remaining_s": round(remaining_s, 2),
                "overall_quality_pct": self.overall_quality_pct,
                "calibrated_segments": len(self.q_offset_final),
                "active_sensors_captured": active_captured,
                "active_stream_count": len(self._live_segments_static),
                "live_packet_count": self._live_packet_count_static,
                "max_static_std_deg": self.max_static_std_deg,
                "mean_static_gyro_rad_s": self.mean_static_gyro_rad_s,
                "message_es": self.last_message_es,
                "reports": {seg: rep.to_dict() for seg, rep in self.reports.items()},
            }
