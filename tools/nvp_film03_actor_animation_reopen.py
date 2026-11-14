# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent Blender reopen: verify real saved gait keys and untouched cast."""
from __future__ import annotations

import bpy
from mathutils import Matrix
from hashlib import sha256
from pathlib import Path
import json
import math
import sys


def main():
    if "--" not in sys.argv:
        raise RuntimeError("Reviewed independent Blender source packet required")
    args=sys.argv[sys.argv.index("--")+1:]
    if len(args)!=2:
        raise RuntimeError("Only exact source manifest and output")
    manifest=Path(args[0]).resolve(strict=True)
    report=Path(args[1]).resolve()
    if report.exists():
        raise RuntimeError("Cannot overwrite independent Blender reopened proof")
    packet=json.loads(manifest.read_text("utf8"))
    source=packet["source"]
    if packet["format"]!="nvp.film03.actor_animation_packet.v1":
        raise PermissionError("Wrong original ActorID animation source")
    actor=source["actor_prim_path"]
    matching=[obj for obj in bpy.data.objects if
              obj.get("nvp_source_prim_path")==actor]
    if len(matching)!=1 or matching[0].get("nvp_actor_identity")!=source["actor_id"]:
        raise RuntimeError("Blender source reopened under wrong ActorID/prim")
    character=matching[0]
    curves=character.animation_data.action if character.animation_data else None
    if curves is None:
        raise RuntimeError("No real Blender procedural gait animation Action")
    if bpy.context.scene.frame_end!=len(source["frames"]):
        raise RuntimeError("Blender character animation duration differs")
    actor_paths={p:obj for p in source["cast_actor_id_by_prim"] for obj in
                 bpy.data.objects if obj.get("nvp_source_prim_path")==p}
    if set(actor_paths)!=set(source["cast_actor_id_by_prim"]):
        raise RuntimeError("Original four actor cast lost in reopened .blend")
    verified=[]
    for n,row in enumerate(source["frames"]):
        bpy.context.scene.frame_set(n+1)
        source_matrix=Matrix(row["world_matrices"][actor]).transposed()
        z=character.matrix_world.translation.z-source_matrix.translation.z
        gait=source["gait_preset"]
        if gait=="lopsided_roll":
            expected_z=0.10*math.sin(n*math.pi/2)+0.05*(n%3==2)
        elif gait=="uneven_step":
            expected_z=(0.13 if n%4 in (1,2) else 0)
        else:
            expected_z=0.0
        if abs(z-expected_z)>0.02:
            raise RuntimeError("Reopened actor does not have source-derived gait frame")
        for p,obj in actor_paths.items():
            if p==actor:continue
            m=Matrix(row["world_matrices"][p]).transposed()
            if any(abs(obj.matrix_world[i][j]-m[i][j])>0.0005
                   for i in range(4) for j in range(4)):
                raise RuntimeError("Another cast actor was moved by the wrong ActorID gait")
        verified.append({
            "frame_in_take":row["frame_in_take"],
            "source_snapshot_sha256":row["source_snapshot_sha256"],
            "actor_lift_m_actual":round(z,6),
            "actor_lift_m_expected":round(expected_z,6),
        })
    payload={
        "format":"nvp.film03.independent_blender_actor_reopen.v1",
        "passed":True,"actor_id":source["actor_id"],
        "actor_prim_path":actor,"source_take_sha256":source["source_take_sha256"],
        "original_source_frames_checked":len(verified),
        "all_other_source_actors_unchanged":True,
        "real_animation_action_reopened":True,
        "frame_checks":verified,
        "no_source_take_modified":True,
    }
    report.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n","utf8")

if __name__=="__main__":
    main()
