# SPDX-License-Identifier: GPL-2.0-or-later
"""FILM02-02 fixed first-party Blender bpy shot-chunk render adapter.

Runs only as a SHA-pinned script inside the existing BlenderWorkerSupervisor.
No model/AI code, arbitrary commands, network access, external asset paths,
FFmpeg or source mutations. The host supplies trusted, frozen FilmIndex data.
Blender-side adapter is GPL-licensed separately from NVP's host.
"""
from __future__ import annotations

import bpy
from mathutils import Matrix, Vector
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

FORMAT = "nvp.film02.cycles.original_shot_chunk.v1"
RECEIPT = "nvp.film02.cycles.native_chunk_render.v1"
FPS = 24
WIDTH, HEIGHT = 640, 360
MAX_BATCH = 24
PATHS = {
    "/World/RelayCore": "prop",
    "/World/ServiceCraft": "actor",
    "/World/Engineer": "actor",
    "/World/CrossingBox": "actor",
    "/World/PassingSphere": "actor",
    "/World/Camera": "camera",
    "/World/PracticalLight": "light",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def accept_packet():
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) != 8 or len(set(argv[::2])) != 4:
        raise PermissionError("Only four reviewed worker file arguments are permitted")
    args = dict(zip(argv[::2], argv[1::2]))
    if set(args) != {"--manifest", "--output", "--audit", "--out"}:
        raise PermissionError("Unreviewed Blender worker option")
    manifest = Path(args["--manifest"]).resolve(strict=True)
    work = manifest.parent
    blend = Path(args["--output"])
    audit = Path(args["--audit"])
    frames = Path(args["--out"])
    if (any(path.parent != work for path in (blend, audit, frames)) or
            blend.exists() or audit.exists() or frames.exists()):
        raise PermissionError("Only fresh, host-owned per-job output files are allowed")
    packet = json.loads(manifest.read_text("utf8"))
    if packet.get("format") != FORMAT:
        raise PermissionError("Not an approved original-film Blender render packet")
    source = packet.get("source")
    if type(source) is not dict or hashlib.sha256(canonical(source)).hexdigest() != packet.get("source_sha256"):
        raise PermissionError("SHA-bound native original film render packet changed")
    shot = source.get("shot_number")
    first = source.get("first_frame")
    stop = source.get("stop_frame")
    rows = source.get("frames")
    assets = source.get("assets")
    if (type(shot) is not int or shot not in (0, 1, 2) or
            type(first) is not int or type(stop) is not int or
            not 240 * shot <= first < stop <= 240 * (shot + 1) or
            stop - first > MAX_BATCH or type(rows) is not list or
            len(rows) != stop - first or
            type(assets) is not dict or len(assets) != 5 or
            len(source.get("parent_manifest_sha256", "")) != 64 or
            len(source.get("source_edit_sha256", "")) != 64 or
            len(source.get("take_sha256", "")) != 64 or
            source.get("creator_approved_for_release") is not False):
        raise PermissionError("Unbounded or non-original 30-second shot batch")
    for n, frame in enumerate(rows, first):
        if (frame.get("output_frame_zero") != n or
                frame.get("source_take_sha256") != source["take_sha256"] or
                frame.get("segment_id") != source["segment_id"] or
                frame.get("output_film_tick") != str(n * 294000000) or
                frame.get("source_film_tick") != str((n % 240) * 294000000) or
                set(frame.get("world_matrices", {})) != set(PATHS)):
            raise PermissionError("Original FilmIndex source frame sequence changed")
        for matrix in frame["world_matrices"].values():
            if (len(matrix) != 4 or any(len(row) != 4 or
                    any(type(value) not in (int, float) or not math.isfinite(value)
                        for value in row) for row in matrix)):
                raise PermissionError("Non-finite or incomplete USD source transform")
    path_map = {}
    for asset_id, entry in assets.items():
        if (type(asset_id) is not str or not asset_id or
                len(entry.get("source_document_sha256", "")) != 64 or
                type(entry.get("bound_scene_paths")) is not list or
                len(entry["bound_scene_paths"]) != 1 or
                entry["bound_scene_paths"][0] not in PATHS or
                entry["bound_scene_paths"][0] in ("/World/Camera", "/World/PracticalLight") or
                entry["bound_scene_paths"][0] in path_map):
            raise PermissionError("Original USD asset binding invalid")
        data = entry.get("source_data")
        if (type(data) is not dict or
                data.get("shape") not in ("mesh", "cube", "sphere") or
                not isinstance(data.get("size_m"), (int, float)) or
                not 0 < data["size_m"] <= 1000):
            raise PermissionError("Unexpected original bounded USD geometry")
        path_map[entry["bound_scene_paths"][0]] = asset_id
    if set(path_map) != (set(PATHS) - {"/World/Camera", "/World/PracticalLight"}):
        raise PermissionError("Five original scene objects must remain bound")
    frames.mkdir(mode=0o700, exist_ok=False)
    return source, blend, audit, frames


def material(name, data):
    source = data.get("preview_material")
    if type(source) is dict:
        rgb = source["base_color_rgb"]
        roughness = source["roughness"]
        metallic = source["metallic"]
    else:
        rgb, roughness, metallic = [0.55, 0.55, 0.6], 0.5, 0.0
    shader = bpy.data.materials.new(name)
    shader.use_nodes = True
    principled = shader.node_tree.nodes.get("Principled BSDF")
    if principled is None:
        raise RuntimeError("Genuine Blender 5.x Principled BSDF unavailable")
    principled.inputs["Base Color"].default_value = (*rgb, 1.0)
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    return shader


def make_asset(asset_id, entry):
    data = entry["source_data"]
    kind = data["shape"]
    if kind == "mesh":
        points, faces = data["points"], data["triangles"]
        if not 3 <= len(points) <= 2048 or not 1 <= len(faces) <= 4096:
            raise PermissionError("Unbounded USD triangle source")
        mesh = bpy.data.meshes.new("NVP_Source_" + asset_id)
        mesh.from_pydata(points, [], faces)
        mesh.update()
        if len(mesh.vertices) != len(points) or len(mesh.polygons) != len(faces):
            raise RuntimeError("Blender mesh differs from original USD mesh")
        for polygon in mesh.polygons:
            polygon.use_smooth = True
        obj = bpy.data.objects.new("NVP_" + asset_id, mesh)
        bpy.context.collection.objects.link(obj)
    elif kind == "cube":
        bpy.ops.mesh.primitive_cube_add(size=data["size_m"])
        obj = bpy.context.object
        obj.name = "NVP_" + asset_id
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=32, ring_count=16, radius=data["size_m"] / 2)
        obj = bpy.context.object
        obj.name = "NVP_" + asset_id
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    obj.data.materials.append(material("NVP_Material_" + asset_id, data))
    obj["nvp_source_asset_sha256"] = entry["source_document_sha256"]
    obj["nvp_source_asset_id"] = asset_id
    obj["nvp_prim_path"] = entry["bound_scene_paths"][0]
    obj["nvp_original_role"] = PATHS[obj["nvp_prim_path"]]
    return obj


def original_xform(rows):
    # USD GfMatrix4d is row-vector oriented with translation in last ROW.
    # Blender mathutils expects translation in the last COLUMN.
    return Matrix(rows).transposed()


def set_performance(source, items):
    # Source already carries one exact world matrix per frame/actor. No
    # procedural Blender-side poses or across-cut interpolated keys.
    for row in source["frames"]:
        frame_number = row["output_frame_zero"] + 1
        for path, obj in items.items():
            obj.matrix_world = original_xform(row["world_matrices"][path])
            obj.keyframe_insert(data_path="location", frame=frame_number)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame_number)
            obj.keyframe_insert(data_path="scale", frame=frame_number)
    scene = bpy.context.scene
    scene.frame_start = source["first_frame"] + 1
    scene.frame_end = source["stop_frame"]
    scene.frame_set(source["first_frame"] + 1)


def make_scene(source):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 4
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.fps = FPS
    objs = {}
    for aid, entry in source["assets"].items():
        objs[entry["bound_scene_paths"][0]] = make_asset(aid, entry)
    camera_data = bpy.data.cameras.new("NVP_Original_Camera")
    camera = bpy.data.objects.new("NVP_Original_Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera_data.lens = 50
    camera["nvp_prim_path"] = "/World/Camera"
    scene.camera = camera
    objs["/World/Camera"] = camera

    light_data = bpy.data.lights.new("NVP_Source_PracticalLight", "AREA")
    lamp = bpy.data.objects.new("NVP_Source_PracticalLight", light_data)
    bpy.context.collection.objects.link(lamp)
    light_data.energy = 700
    light_data.shape = "DISK"
    light_data.size = 2.0
    lamp["nvp_prim_path"] = "/World/PracticalLight"
    objs["/World/PracticalLight"] = lamp

    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, -6.0))
    backdrop = bpy.context.object
    backdrop.name = "NVP_Actual_Shadow_Receiver"
    backdrop.data.materials.append(material(
        "NVP_Neutral_Studio_Backdrop",
        {"preview_material": {
            "base_color_rgb": [0.13, 0.15, 0.19],
            "roughness": 0.92, "metallic": 0.0
        }}))
    world = bpy.data.worlds.new("NVP_Source_Studio")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (
        0.2, 0.24, 0.31, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.25
    scene.world = world
    set_performance(source, objs)
    return scene, objs


def main():
    source, blend, audit, frames = accept_packet()
    scene, objects = make_scene(source)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), check_existing=False)
    if not blend.is_file() or blend.stat().st_size < 100:
        raise RuntimeError("Genuine Blender source-derived shot chunk did not save")
    rows = []
    for row in source["frames"]:
        n = row["output_frame_zero"]
        scene.frame_set(n + 1)
        for path, obj in objects.items():
            expected = original_xform(row["world_matrices"][path])
            # Authoritative shot matrices are never replaced by arbitrary
            # Blender-side actor movement, and native keyframe readback is
            # required at the real source film frame.
            if any(abs(obj.matrix_world[i][j] - expected[i][j]) > 2e-4
                   for i in range(4) for j in range(4)):
                raise RuntimeError("Saved Blender actor/camera/light deviated from frozen source")
        png = frames / f"frame_{n:04d}.png"
        scene.render.filepath = str(png)
        bpy.ops.render.render(write_still=True)
        if not png.is_file() or png.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("Real Cycles shot frame missing")
        rows.append({
            "frame_zero": n,
            "output_film_tick": row["output_film_tick"],
            "source_film_tick": row["source_film_tick"],
            "source_take_sha256": row["source_take_sha256"],
            "snapshot_sha256": row["snapshot_sha256"],
            "original_sound_event_ids": row["source_sound_event_ids"],
            "png_sha256": sha(png),
            "png_bytes": png.stat().st_size,
        })
    preview = blend.parent / "preview.png"
    shutil.copyfile(frames / f'frame_{source["first_frame"]:04d}.png', preview)
    report = {
        "format": RECEIPT, "passed": True,
        "engine": scene.render.engine, "device": scene.cycles.device,
        "samples": scene.cycles.samples,
        "diffuse_bounces": scene.cycles.diffuse_bounces,
        "glossy_bounces": scene.cycles.glossy_bounces,
        "actual_blender_version": bpy.app.version_string,
        "source_parent_manifest_sha256": source["parent_manifest_sha256"],
        "source_edit_sha256": source["source_edit_sha256"],
        "source_take_sha256": source["take_sha256"],
        "shot_number": source["shot_number"],
        "first_frame": source["first_frame"],
        "stop_frame": source["stop_frame"],
        "original_assets": {
            aid: entry["source_document_sha256"]
            for aid, entry in source["assets"].items()
        },
        "rendered_frame_rows": rows,
        "blend_sha256": sha(blend),
        "original_source_modified": False,
        "picture_rendered_in_genuine_cycles": True,
        "original_audio_rendered": False,
        "creator_visual_approval": False,
        "theatrical_compliance": False,
    }
    audit.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", "utf8")


if __name__ == "__main__":
    main()
