# SPDX-License-Identifier: GPL-2.0-or-later
"""FILM02 — separate real Blender process reopens a saved shot-chunk .blend.

This is an independent native source/scene readback, not a fake renderer and
not a creator's artistic approval. Only invoked after the supervised render.
"""
import bpy
from mathutils import Matrix
import hashlib
import json
from pathlib import Path
import sys


def digest(doc):
    return hashlib.sha256(json.dumps(
        doc, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ensure_ascii=True).encode("ascii")).hexdigest()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) != 4 or set(argv[::2]) != {"--manifest", "--audit"}:
        raise PermissionError("Only source manifest and new native audit are allowed")
    args = dict(zip(argv[::2], argv[1::2]))
    source = Path(args["--manifest"]).resolve(strict=True)
    result = Path(args["--audit"])
    if not result.is_absolute() or result.exists() or result.is_symlink():
        raise PermissionError("Reopened Blender proof requires a fresh absolute file")
    packet = json.loads(source.read_text("utf8"))
    if (packet.get("format") != "nvp.film02.cycles.original_shot_chunk.v1" or
            digest(packet["source"]) != packet.get("source_sha256")):
        raise PermissionError("Tampered source edit packet")
    body = packet["source"]
    scene = bpy.context.scene
    if (scene.render.engine != "CYCLES" or scene.cycles.device != "CPU" or
            scene.cycles.samples < 8 or scene.cycles.glossy_bounces < 4 or
            scene.render.fps != 24 or scene.render.resolution_x != 640 or
            scene.render.resolution_y != 360 or
            scene.frame_start != body["first_frame"] + 1 or
            scene.frame_end != body["stop_frame"]):
        raise RuntimeError("Saved .blend is not the approved original Cycles shot")
    asset_map = {}
    for aid, asset in body["assets"].items():
        obj = bpy.data.objects.get("NVP_" + aid)
        path = asset["bound_scene_paths"][0]
        if (obj is None or obj.type != "MESH" or
                obj.get("nvp_source_asset_sha256") != asset["source_document_sha256"] or
                obj.get("nvp_prim_path") != path or
                obj.get("nvp_original_role") not in ("actor", "prop") or
                len(obj.data.materials) != 1):
            raise PermissionError("Original Blender object/asset source identity changed")
        data = asset["source_data"]
        if data["shape"] == "mesh" and (
                len(obj.data.vertices) != len(data["points"]) or
                len(obj.data.polygons) != len(data["triangles"])):
            raise RuntimeError("Authored torus source topology altered")
        asset_map[path] = obj
    camera = bpy.data.objects.get("NVP_Original_Camera")
    light = bpy.data.objects.get("NVP_Source_PracticalLight")
    if (camera is None or camera.type != "CAMERA" or scene.camera != camera or
            camera.get("nvp_prim_path") != "/World/Camera" or
            light is None or light.type != "LIGHT" or
            light.get("nvp_prim_path") != "/World/PracticalLight" or
            bpy.data.objects.get("NVP_Actual_Shadow_Receiver") is None):
        raise RuntimeError("Saved real Blender camera, light or shadow receiver missing")
    asset_map["/World/Camera"] = camera
    asset_map["/World/PracticalLight"] = light
    for source_row in (body["frames"][0], body["frames"][-1]):
        frame = source_row["output_frame_zero"]
        scene.frame_set(frame + 1)
        for path, obj in asset_map.items():
            expected = Matrix(source_row["world_matrices"][path]).transposed()
            if any(abs(obj.matrix_world[i][j] - expected[i][j]) > 2e-4
                   for i in range(4) for j in range(4)):
                raise RuntimeError(
                    "Independent Blender reopen changed source pose/camera at frame " + str(frame))
    result.write_text(json.dumps({
        "format": "nvp.film02.blender.independent_shot_reopen.v1",
        "passed": True,
        "genuine_separate_native_blender_readback": True,
        "cycles_engine": "CYCLES",
        "source_packet_sha256": packet["source_sha256"],
        "parent_source_manifest_sha256": body["parent_manifest_sha256"],
        "source_edit_sha256": body["source_edit_sha256"],
        "shot_number": body["shot_number"],
        "first_frame": body["first_frame"],
        "stop_frame": body["stop_frame"],
        "checked_frames": [
            body["frames"][0]["output_frame_zero"],
            body["frames"][-1]["output_frame_zero"]],
        "source_bound_scene_object_count": 7,
        "mastered_audio_verified": False,
        "human_director_approval": False,
        "independent_theatrical_approval": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
