from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

from backend.kinematics.anthropometry import SegmentDef, SkeletonModel
from backend.kinematics.quaternions import q_slerp, q_to_euler_zxy, unwrap_euler_sequence

RigNamingPreset = Literal["openmocap", "mixamo", "rigify"]

TPOSE_HOLD_FRAMES = 30
TPOSE_BLEND_FRAMES = 15


def _resolve_bone_name(seg: SegmentDef, naming: RigNamingPreset) -> str:
    if naming == "mixamo":
        return seg.mixamo_name
    if naming == "rigify":
        return seg.rigify_name
    return seg.bvh_name or seg.name


def _write_joint_block(
    lines: list[str],
    seg_name: str,
    skeleton: SkeletonModel,
    naming: RigNamingPreset,
    scale: float,
    depth: int,
    joint_order_out: list[str],
) -> None:
    indent = "  " * depth
    seg = skeleton.segments[seg_name]
    bname = _resolve_bone_name(seg, naming)
    ox, oy, oz = (v * scale for v in seg.offset_m)
    joint_order_out.append(seg_name)

    if depth == 0:
        lines.append(f"ROOT {bname}")
        lines.append("{")
        lines.append("  OFFSET 0.000000 0.000000 0.000000")
        lines.append("  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation")
    else:
        lines.append(f"{indent}JOINT {bname}")
        lines.append(f"{indent}{{")
        lines.append(f"{indent}  OFFSET {ox:.6f} {oy:.6f} {oz:.6f}")
        lines.append(f"{indent}  CHANNELS 3 Zrotation Xrotation Yrotation")

    children = skeleton.children.get(seg_name, [])
    if not children:
        ex, ey, ez = (v * scale for v in seg.end_site_m)
        lines.append(f"{indent}  End Site")
        lines.append(f"{indent}  {{")
        lines.append(f"{indent}    OFFSET {ex:.6f} {ey:.6f} {ez:.6f}")
        lines.append(f"{indent}  }}")
    else:
        for child_name in children:
            _write_joint_block(
                lines=lines,
                seg_name=child_name,
                skeleton=skeleton,
                naming=naming,
                scale=scale,
                depth=depth + 1,
                joint_order_out=joint_order_out,
            )
    lines.append(f"{indent}}}")


def _smoothstep_cubic(u: float) -> float:
    x = max(0.0, min(1.0, float(u)))
    return x * x * (3.0 - 2.0 * x)


def export_take_to_bvh(
    output_path: Path,
    frames: list[dict[str, Any]],
    skeleton: SkeletonModel,
    fps: float = 120.0,
    scale: float = 1.0,
    naming: RigNamingPreset = "openmocap",
    include_tpose_frame0: bool = True,
    tpose_lead_in_out: bool = True,
) -> dict[str, Any]:
    """
    Exporta una lista de fotogramas capturados hacia un archivo .bvh estándar (23 huesos tipo Vicon/MVN)
    con Pose T al inicio y final (30 cuadros estáticos + 15 cuadros de mezcla cúbica/SLERP) y
    desempaquetado Euler Z-X-Y continuo para Blender, Mixamo y Rigify.
    """
    if not frames:
        raise ValueError("No existen fotogramas para exportar a BVH.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["HIERARCHY"]
    joint_order: list[str] = []

    _write_joint_block(
        lines=lines,
        seg_name="PELVIS",
        skeleton=skeleton,
        naming=naming,
        scale=float(scale),
        depth=0,
        joint_order_out=joint_order,
    )

    ident = [1.0, 0.0, 0.0, 0.0]
    pelvis_off = skeleton.segments["PELVIS"].offset_m
    pelvis_rest_y = float(pelvis_off[1]) * float(scale)

    def _frame_pos(fr: dict[str, Any]) -> list[float]:
        p_pos = fr.get("world_pos", {}).get("PELVIS", pelvis_off)
        return [float(p_pos[0]) * scale, float(p_pos[1]) * scale, float(p_pos[2]) * scale]

    def _frame_quats(fr: dict[str, Any]) -> dict[str, list[float]]:
        lq = fr.get("local_quat", {})
        return {seg: [float(v) for v in lq.get(seg, ident)] for seg in joint_order}

    raw_seq: dict[str, list[tuple[float, float, float]]] = {seg: [] for seg in joint_order}
    root_positions: list[list[float]] = []

    def _append_sample(rpos: list[float], qmap: dict[str, list[float]]) -> None:
        root_positions.append(rpos)
        for seg in joint_order:
            z_deg, x_deg, y_deg = q_to_euler_zxy(qmap.get(seg, ident))
            raw_seq[seg].append((z_deg, x_deg, y_deg))

    first_pos = _frame_pos(frames[0])
    first_quats = _frame_quats(frames[0])
    last_pos = _frame_pos(frames[-1])
    last_quats = _frame_quats(frames[-1])

    if tpose_lead_in_out:
        tpose_in_pos = [first_pos[0], pelvis_rest_y, first_pos[2]]
        tpose_quats = {seg: ident for seg in joint_order}
        for _ in range(TPOSE_HOLD_FRAMES):
            _append_sample(list(tpose_in_pos), tpose_quats)
        for step_idx in range(1, TPOSE_BLEND_FRAMES + 1):
            w = _smoothstep_cubic(step_idx / float(TPOSE_BLEND_FRAMES + 1))
            b_pos = [tpose_in_pos[i] + w * (first_pos[i] - tpose_in_pos[i]) for i in range(3)]
            b_quats = {
                seg: q_slerp(ident, first_quats[seg], w).tolist() for seg in joint_order
            }
            _append_sample(b_pos, b_quats)
    elif include_tpose_frame0:
        _append_sample([v * scale for v in pelvis_off], {seg: ident for seg in joint_order})

    for frame in frames:
        _append_sample(_frame_pos(frame), _frame_quats(frame))

    if tpose_lead_in_out:
        tpose_out_pos = [last_pos[0], pelvis_rest_y, last_pos[2]]
        tpose_quats = {seg: ident for seg in joint_order}
        for step_idx in range(1, TPOSE_BLEND_FRAMES + 1):
            w = _smoothstep_cubic(step_idx / float(TPOSE_BLEND_FRAMES + 1))
            b_pos = [last_pos[i] + w * (tpose_out_pos[i] - last_pos[i]) for i in range(3)]
            b_quats = {
                seg: q_slerp(last_quats[seg], ident, w).tolist() for seg in joint_order
            }
            _append_sample(b_pos, b_quats)
        for _ in range(TPOSE_HOLD_FRAMES):
            _append_sample(list(tpose_out_pos), tpose_quats)

    unwrapped_seq: dict[str, list[tuple[float, float, float]]] = {
        seg: unwrap_euler_sequence(seq) for seg, seq in raw_seq.items()
    }

    total_frames = len(root_positions)
    frame_time = 1.0 / max(1.0, float(fps))
    lines.append("MOTION")
    lines.append(f"Frames: {total_frames}")
    lines.append(f"Frame Time: {frame_time:.6f}")

    for idx in range(total_frames):
        px, py, pz = root_positions[idx]
        vals = [f"{px:.6f}", f"{py:.6f}", f"{pz:.6f}"]
        for seg in joint_order:
            ez, ex, ey = unwrapped_seq[seg][idx]
            vals.extend([f"{ez:.4f}", f"{ex:.4f}", f"{ey:.4f}"])
        lines.append(" ".join(vals))

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    validation = validate_bvh(output_path)
    return {
        "file_path": str(output_path),
        "file_name": output_path.name,
        "frames": total_frames,
        "fps": fps,
        "naming": naming,
        "scale": scale,
        "tpose_lead_in_out": tpose_lead_in_out,
        "joint_count": len(joint_order),
        "validation": validation,
    }


def validate_bvh(bvh_path: Path) -> dict[str, Any]:
    """Audita estructuralmente un archivo .bvh verificando jerarquía, canales y finitud de valores."""
    text = bvh_path.read_text(encoding="utf-8")
    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not raw_lines or raw_lines[0] != "HIERARCHY":
        raise ValueError("El archivo BVH no comienza con HIERARCHY.")

    motion_idx = -1
    open_braces = 0
    close_braces = 0
    channel_count = 0
    end_site_count = 0
    joints: list[str] = []

    for i, ln in enumerate(raw_lines):
        if ln == "MOTION":
            motion_idx = i
            break
        open_braces += ln.count("{")
        close_braces += ln.count("}")
        if ln.startswith("ROOT ") or ln.startswith("JOINT "):
            joints.append(ln.split(None, 1)[1])
        elif ln == "End Site":
            end_site_count += 1
        elif ln.startswith("CHANNELS "):
            parts = ln.split()
            channel_count += int(parts[1])

    if motion_idx < 0:
        raise ValueError("Falta la sección MOTION en el archivo BVH.")
    if open_braces == 0 or open_braces != close_braces:
        raise ValueError(f"Llaves desbalanceadas en BVH: {{={open_braces}, }}={close_braces}")

    frames_hdr = raw_lines[motion_idx + 1]
    frametime_hdr = raw_lines[motion_idx + 2]
    if not frames_hdr.startswith("Frames:") or not frametime_hdr.startswith("Frame Time:"):
        raise ValueError("Encabezado MOTION inválido en BVH.")

    declared_frames = int(frames_hdr.split(":")[1].strip())
    data_lines = raw_lines[motion_idx + 3 :]
    if len(data_lines) != declared_frames:
        raise ValueError(f"Número de fotogramas inconsistente: declarados={declared_frames}, reales={len(data_lines)}")

    parsed_rows: list[list[float]] = []
    for ridx, dline in enumerate(data_lines):
        nums = [float(x) for x in dline.split()]
        if len(nums) != channel_count:
            raise ValueError(f"Frame {ridx} tiene {len(nums)} canales; se esperaban {channel_count}.")
        if any(not math.isfinite(x) for x in nums):
            raise ValueError(f"Valores no finitos (NaN/Inf) detectados en el frame {ridx}.")
        parsed_rows.append(nums)

    return {
        "valid": True,
        "joints": joints,
        "joint_count": len(joints),
        "end_site_count": end_site_count,
        "expected_channels": channel_count,
        "frame_count": declared_frames,
        "first_frame_rotations": parsed_rows[0][3:] if parsed_rows else [],
        "last_frame_rotations": parsed_rows[-1][3:] if parsed_rows else [],
    }
