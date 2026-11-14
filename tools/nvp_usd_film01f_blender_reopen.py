# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent native Blender reopen of original USD-FILM-01F world shot."""
from __future__ import annotations

import bpy
import json
from hashlib import sha256
from pathlib import Path
import sys

FORMAT="nvp.usd_film01f.independent_cycles_scene_reopen.v1"


def digest(path):
    h=sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda:stream.read(1<<20),b""):
            h.update(part)
    return h.hexdigest()


def run():
    tokens=sys.argv[sys.argv.index("--")+1:]
    if len(tokens)!=4 or set(tokens[::2])!={"--manifest","--audit"}:
        raise PermissionError("Only fixed original-world independent reopen options")
    args=dict(zip(tokens[::2],tokens[1::2]))
    here=Path.cwd().resolve(strict=True)
    manifest=Path(args["--manifest"]).resolve(strict=True)
    audit=Path(args["--audit"]).resolve()
    if (manifest.parent!=here or audit.parent!=here or
        manifest.is_symlink() or audit.is_symlink() or audit.exists()):
        raise PermissionError("Independent Blender files not confined to approved job")
    packet=json.loads(manifest.read_text("utf8"))
    if type(packet) is not dict or set(packet)!={"source","source_blend_sha256"}:
        raise PermissionError("No original source .blend provenance")
    scene_file=Path(bpy.data.filepath).resolve(strict=True)
    if (scene_file.parent!=here or scene_file.is_symlink() or
        digest(scene_file)!=packet["source_blend_sha256"]):
        raise PermissionError("Reopened Blender scene differs from pinned original")
    source=packet["source"]
    scene=bpy.context.scene
    expected={
        "nvp_original_world_take_sha256":source["original_world_take_sha256"],
        "nvp_original_world_sha256":source["original_world_sha256"],
        "nvp_original_camera_shot_sha256":source["original_camera_shot_sha256"],
        "nvp_source_usd_sha256":source["source_usd_sha256"],
        "nvp_original_film_tick":source["original_film_tick"],
        "nvp_original_camera_path":source["original_camera_path"],
        "nvp_no_film_master_approval":True,
    }
    for key,value in expected.items():
        if scene.get(key)!=value:
            raise PermissionError("Scene world/actor/camera source provenance changed")
    try:
        actors=json.loads(scene.get("nvp_source_actors_json","null"))
    except (TypeError,ValueError) as exc:
        raise PermissionError("Saved actor identity manifest invalid") from exc
    if actors!=source["actor_sources"]:
        raise RuntimeError("World ActorID source was substituted")
    objects=list(bpy.data.objects)
    names={obj.name.split(".")[0] for obj in objects}
    if (scene.camera is None or scene.camera.type!="CAMERA" or
        scene.camera.name.split(".")[0]!=
            source["original_camera_path"].split("/")[-1] or
        sum(o.type=="MESH" and len(o.data.vertices)>=3 for o in objects)<1):
        raise RuntimeError("Independent Blender scene lacks original camera/geometry")
    if any(a["source_prim"].split("/")[-1] not in names for a in actors):
        raise RuntimeError("Original world ActorID hierarchy absent in saved Blender")
    report={
        "format":FORMAT,"passed":True,
        "source_blend_sha256":packet["source_blend_sha256"],
        "original_take_sha256":source["original_world_take_sha256"],
        "original_world_sha256":source["original_world_sha256"],
        "source_usd_sha256":source["source_usd_sha256"],
        "actor_count":len(actors),
        "camera":source["original_camera_path"],
        "actual_blender_version":bpy.app.version_string,
        "real_saved_usd_actor_objects_reopened":True,
        "new_pixels_rendered_in_reopen":False,
        "photorealism_independently_accepted":False,
        "finished_audio_mix_verified":False,
    }
    audit.write_text(json.dumps(report,sort_keys=True,
                               separators=(",",":")),"utf8")


if __name__=="__main__":
    run()
