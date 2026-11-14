# SPDX-License-Identifier: GPL-2.0-or-later
"""Fresh, independent native Blender process reopens real facial .blend."""
from __future__ import annotations

import bpy
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

FORMAT = "nvp.film03.independent_blender_face_reopen.v1"


def check():
    tokens = sys.argv[sys.argv.index("--") + 1:]
    if len(tokens) != 4 or set(tokens[::2]) != {"--manifest", "--audit"}:
        raise PermissionError("Only exact independent Blender reopen options")
    args = dict(zip(tokens[::2], tokens[1::2]))
    folder = Path.cwd().resolve(strict=True)
    manifest = Path(args["--manifest"])
    audit_path = Path(args["--audit"])
    if (manifest.parent != folder or audit_path.parent != folder
        or manifest.is_symlink() or audit_path.is_symlink()
        or audit_path.exists()):
        raise PermissionError("Independent Blender review paths are not pinned")
    doc = json.loads(manifest.read_text("utf8"))
    if type(doc) is not dict or set(doc) != {
        "source", "source_blend_sha256"
    }:
        raise PermissionError("No pinned original render/Blender source")
    scene_file = Path(bpy.data.filepath)
    if scene_file.parent != folder or scene_file.is_symlink():
        raise PermissionError("Not an independent reopened source .blend")
    source_sha = sha256(scene_file.read_bytes()).hexdigest()
    if source_sha != doc["source_blend_sha256"]:
        raise PermissionError("Saved Blender source differs from first supervised worker")
    src = doc["source"]
    originals = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.data.shape_keys:
            continue
        if (obj.get("nvp_original_actor_id") == src["actor_id"] and
            obj.get("nvp_original_frozen_take_sha256") ==
                src["original_take_sha256"] and
            obj.get("nvp_pcm_source_sha256") ==
                src["original_pcm_sha256"]):
            originals.append(obj)
    if len(originals) != 1:
        raise RuntimeError("Fresh Blender found no unique source ActorID face")
    actor = originals[0]
    keys = actor.data.shape_keys.key_blocks
    if (len(actor.data.vertices) != src["source_mesh_vertex_count"]
        or not set(src["shape_names"]) <= set(keys.keys())):
        raise RuntimeError("Native mesh shape keys were not preserved through .blend")
    for record in src["samples"]:
        bpy.context.scene.frame_set(record["frame"])
        for name, target in record["weights"].items():
            found = float(keys[name].value)
            if not math.isclose(found, target, abs_tol=0.0002):
                raise RuntimeError(
                    "Reopened actual facial pose did not preserve sample and expression")
    report = {
        "format": FORMAT, "passed": True,
        "blender_reopen_sha256": source_sha,
        "actor_id": src["actor_id"], "voice_id": src["voice_id"],
        "source_facial_candidate_sha256": src["source_facial_candidate_sha256"],
        "original_pcm_sha256": src["original_pcm_sha256"],
        "original_take_sha256": src["original_take_sha256"],
        "real_imported_mesh_shape_keys_reopened": True,
        "three_authored_mouth_face_poses_independently_reopened": True,
        "voice_quality_or_lipsync_not_proven": True,
        "director_film_take_approved": False,
    }
    audit_path.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")), "utf8")


if __name__ == "__main__":
    check()
