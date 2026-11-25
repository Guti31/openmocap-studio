"""
Puente automatizado Blender para convertir archivos .bvh de OpenMocap Studio hacia .fbx limpio
compatible con Rigify, Mixamo, Unreal y Unity.
Uso:
  blender --background --factory-startup --python convertir_a_fbx.py -- --input clip.bvh --output clip.fbx --rig-preset openmocap --fps 120
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


MIXAMO_RENAME = {
    "Pelvis": "mixamorig:Hips",
    "Spine": "mixamorig:Spine",
    "Spine1": "mixamorig:Spine1",
    "Spine2": "mixamorig:Spine2",
    "Spine3": "mixamorig:Spine3",
    "Neck": "mixamorig:Neck",
    "Head": "mixamorig:Head",
    "LeftShoulder": "mixamorig:LeftShoulder",
    "LeftArm": "mixamorig:LeftArm",
    "LeftForeArm": "mixamorig:LeftForeArm",
    "LeftHand": "mixamorig:LeftHand",
    "RightShoulder": "mixamorig:RightShoulder",
    "RightArm": "mixamorig:RightArm",
    "RightForeArm": "mixamorig:RightForeArm",
    "RightHand": "mixamorig:RightHand",
    "LeftUpLeg": "mixamorig:LeftUpLeg",
    "LeftLeg": "mixamorig:LeftLeg",
    "LeftFoot": "mixamorig:LeftFoot",
    "LeftToeBase": "mixamorig:LeftToeBase",
    "RightUpLeg": "mixamorig:RightUpLeg",
    "RightLeg": "mixamorig:RightLeg",
    "RightFoot": "mixamorig:RightFoot",
    "RightToeBase": "mixamorig:RightToeBase",
}

RIGIFY_RENAME = {
    "Pelvis": "hips",
    "Spine": "spine",
    "Spine1": "spine.001",
    "Spine2": "spine.002",
    "Spine3": "spine.003",
    "Neck": "spine.004",
    "Head": "spine.006",
    "LeftShoulder": "shoulder.L",
    "LeftArm": "upper_arm.L",
    "LeftForeArm": "forearm.L",
    "LeftHand": "hand.L",
    "RightShoulder": "shoulder.R",
    "RightArm": "upper_arm.R",
    "RightForeArm": "forearm.R",
    "RightHand": "hand.R",
    "LeftUpLeg": "thigh.L",
    "LeftLeg": "shin.L",
    "LeftFoot": "foot.L",
    "LeftToeBase": "toe.L",
    "RightUpLeg": "thigh.R",
    "RightLeg": "shin.R",
    "RightFoot": "foot.R",
    "RightToeBase": "toe.R",
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="Convertidor BVH -> FBX OpenMocap Studio")
    parser.add_argument("--input", required=True, help="Ruta de entrada .bvh")
    parser.add_argument("--output", required=True, help="Ruta de salida .fbx")
    parser.add_argument("--rig-preset", default="openmocap", choices=["openmocap", "mixamo", "rigify"])
    parser.add_argument("--fps", type=int, default=120)
    parser.add_argument("--scale", type=float, default=1.0)
    return parser.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def rename_armature_bones(arm_obj: bpy.types.Object, preset: str) -> None:
    mapping = MIXAMO_RENAME if preset == "mixamo" else (RIGIFY_RENAME if preset == "rigify" else {})
    if not mapping:
        return
    for bone in arm_obj.data.bones:
        if bone.name in mapping:
            bone.name = mapping[bone.name]


def main() -> None:
    args = parse_args()
    in_path = Path(args.input).resolve()
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    clear_scene()

    bpy.ops.import_anim.bvh(
        filepath=str(in_path),
        filter_glob="*.bvh",
        target="ARMATURE",
        global_scale=float(args.scale),
        frame_start=1,
        use_fps_scale=True,
        update_scene_fps=True,
        update_scene_duration=True,
        axis_forward="-Z",
        axis_up="Y",
    )

    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not armatures:
        raise RuntimeError("No se importó ninguna armadura desde el archivo BVH.")

    arm = armatures[0]
    arm.name = "OpenMocap_Armature"
    rename_armature_bones(arm, args.rig_preset)

    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm

    scene = bpy.context.scene
    scene.render.fps = max(24, min(240, int(args.fps)))
    if arm.animation_data and arm.animation_data.action:
        f_start, f_end = arm.animation_data.action.frame_range
        scene.frame_start = int(round(f_start))
        scene.frame_end = int(round(f_end))

    bpy.ops.export_scene.fbx(
        filepath=str(out_path),
        use_selection=True,
        object_types={"ARMATURE"},
        use_mesh_modifiers=False,
        add_leaf_bones=False,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        bake_anim=True,
        bake_anim_use_all_actions=False,
        bake_anim_use_nla_strips=False,
        bake_anim_simplify_factor=0.0,
        axis_forward="-Z",
        axis_up="Y",
        path_mode="AUTO",
    )

    summary = {
        "status": "ok",
        "input": str(in_path),
        "output": str(out_path),
        "rig_preset": args.rig_preset,
        "bones": len(arm.data.bones),
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "fps": scene.render.fps,
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

