# SPDX-License-Identifier: GPL-2.0-or-later
"""FILM03-09D: reviewed native Blender 5.2 real USD BlendShape render worker.

This fixed script imports the source-authoritative USD mesh and its shape
keys; it NEVER creates a stand-in character or infers facial emotions.
A preview-only camera/light may be added for inspection if the original USD
source camera is not a Blender Camera after import. Film editorial remains
unmodified. All frame weights originate in the NVP-host-authored packet.
"""
from __future__ import annotations

import bpy
from hashlib import sha256
import json
from pathlib import Path
import sys
from mathutils import Vector

FORMAT = "nvp.film03.real_usd_face_blender_packet.v1"
AUDIT = "nvp.film03.real_usd_face_blender_audit.v1"


def canonical(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf8")


def digest_file(path):
    h = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def trusted_paths():
    tokens = sys.argv[sys.argv.index("--") + 1:]
    if len(tokens) != 8:
        raise PermissionError("Fixed NVP Blender source facial worker arguments required")
    args = dict(zip(tokens[::2], tokens[1::2]))
    if set(args) != {"--manifest", "--output", "--audit", "--preview"}:
        raise PermissionError("Unreviewed Blender facial worker option")
    cwd = Path.cwd().resolve(strict=True)
    targets = {}
    for k, val in args.items():
        file = Path(val)
        # Existing NVP BlenderWorkerSupervisor passes absolute paths under
        # the pinned job directory, not relative CLI values.
        path = file.resolve()
        if path.parent != cwd or file.is_symlink() or path.name in (".", ".."):
            raise PermissionError("All facial worker paths must remain inside the job")
        if (k == "--manifest" and not path.is_file()) or (
                k != "--manifest" and path.exists()):
            raise PermissionError("Facial worker may not overwrite source files")
        targets[k] = path
    return targets


def validate(packet, directory):
    if type(packet) is not dict or set(packet) != {
        "format", "source", "source_sha256"
    } or packet["format"] != FORMAT:
        raise PermissionError("No exact reviewed USD facial render packet")
    d = packet["source"]
    if packet["source_sha256"] != sha256(canonical(d)).hexdigest():
        raise PermissionError("Original USD facial render source SHA mismatch")
    if type(d) is not dict or set(d) != {
        "project_id", "actor_id", "voice_id",
        "original_take_sha256", "original_pcm_sha256",
        "source_facial_candidate_sha256", "source_usd_sha256",
        "source_usd_file", "source_mesh_vertex_count",
        "actor_prim_path", "shape_names", "samples",
        "preview_camera_not_editorial",
    }:
        raise PermissionError("Unexpected original actor/USD facial render schema")
    if d["preview_camera_not_editorial"] is not True:
        raise PermissionError("Preview may not pretend to be an original film camera")
    if type(d["source_mesh_vertex_count"]) is not int or not 3 <= d["source_mesh_vertex_count"] <= 512:
        raise PermissionError("No bounded actual skinned source mesh vertices")
    shapes = d["shape_names"]
    if (type(shapes) is not list or not 1 <= len(shapes) <= 8 or
            len(set(shapes)) != len(shapes)):
        raise PermissionError("Original facial blendshape names are not unique")
    samples = d["samples"]
    if (type(samples) is not list or len(samples) != 3 or
        [s.get("frame") for s in samples] != [1, 2, 3]):
        raise PermissionError("Three exact original facial performance samples required")
    for s in samples:
        if (type(s) is not dict or set(s) != {"frame", "pcm_sample", "weights"} or
            type(s["pcm_sample"]) is not int or s["pcm_sample"] < 0 or
            type(s["weights"]) is not dict or set(s["weights"]) != set(shapes)):
            raise PermissionError("Bad exact actor facial sample")
        for w in s["weights"].values():
            if type(w) not in (float, int) or not 0 <= w <= 1:
                raise PermissionError("Facial sample outside original shape weights")
    file = Path(d["source_usd_file"])
    if file.name != str(file) or (directory / file).is_symlink():
        raise PermissionError("Untrusted original USD geometry source path")
    if digest_file(directory / file) != d["source_usd_sha256"]:
        raise PermissionError("Blender USD source file differs from FilmIndex staging")
    return d


def setup_preview_camera(scene, actor):
    # Only the camera/light of this temporary REVIEW frame are created.
    # Absolutely no character mesh or substitute facial shape is authored.
    bounds = [actor.matrix_world @ Vector(corner) for corner in actor.bound_box]
    center = sum(bounds, Vector((0, 0, 0))) / len(bounds)
    span = max(max((p - center).length for p in bounds), 1.0)
    camera_data = bpy.data.cameras.new("NVP_Facial_Inspection_Camera")
    camera = bpy.data.objects.new("NVP_Facial_Inspection_Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + Vector((span * 1.1, -span * 3.5, span * 0.7))
    target = center - camera.location
    camera.rotation_euler = target.to_track_quat("-Z", "Y").to_euler()
    camera_data.lens = 45
    scene.camera = camera
    light_data = bpy.data.lights.new("NVP_Facial_Inspection_Light", "AREA")
    light = bpy.data.objects.new("NVP_Facial_Inspection_Light", light_data)
    scene.collection.objects.link(light)
    light.location = center + Vector((span * 0.8, -span, span * 2.1))
    light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()
    light_data.energy = 800
    light_data.size = span * 1.5
    return center


def run():
    locations = trusted_paths()
    directory = Path.cwd().resolve(strict=True)
    packet = json.loads(locations["--manifest"].read_text("utf8"))
    source = validate(packet, directory)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    operation = bpy.ops.wm.usd_import
    properties = operation.get_rna_type().properties.keys()
    if "import_blendshapes" not in properties:
        raise RuntimeError("Blender version cannot import native USD BlendShapes")
    result = operation(
        filepath=str(directory / source["source_usd_file"]),
        import_blendshapes=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError("Native Blender failed to import original USD scene")
    # Match the actual source mesh and shape-key names/vertex count, not a
    # filename, invented primitive or superficially similar object.
    matches = []
    for obj in bpy.data.objects:
        keys = (obj.data.shape_keys.key_blocks if obj.type == "MESH"
                and obj.data.shape_keys is not None else None)
        if (keys is not None and
            len(obj.data.vertices) == source["source_mesh_vertex_count"] and
            set(keys.keys()) >= set(source["shape_names"])):
            matches.append(obj)
    if len(matches) != 1:
        raise RuntimeError("Exactly one genuine original USD actor with all face shapes is required")
    actor = matches[0]
    keys = actor.data.shape_keys.key_blocks
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 10
    scene.render.resolution_x = 400
    scene.render.resolution_y = 300
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.frame_start = 1
    scene.frame_end = 3
    scene.render.fps = 24
    setup_preview_camera(scene, actor)
    for row in source["samples"]:
        for name in source["shape_names"]:
            value = float(row["weights"][name])
            keys[name].value = value
            keys[name].keyframe_insert("value", frame=row["frame"])
    actor["nvp_original_actor_id"] = source["actor_id"]
    actor["nvp_original_usd_prim"] = source["actor_prim_path"]
    actor["nvp_pcm_source_sha256"] = source["original_pcm_sha256"]
    actor["nvp_original_frozen_take_sha256"] = source["original_take_sha256"]
    scene.frame_set(2)
    bpy.ops.wm.save_as_mainfile(filepath=str(locations["--output"]), check_existing=False)
    if locations["--output"].stat().st_size < 100:
        raise RuntimeError("Blender did not save a real imported USD facial rig")
    previews = ["facial_at_1.png", "facial_at_2.png", "facial_at_3.png"]
    hashes = []
    for frame, file in enumerate(previews, 1):
        scene.frame_set(frame)
        scene.render.filepath = str(directory / file)
        bpy.ops.render.render(write_still=True)
        image = directory / file
        if not image.is_file() or image.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError("Blender did not actually render a facial preview")
        hashes.append(digest_file(image))
    if len(set(hashes)) < 2:
        raise RuntimeError("Original facial mesh renders are identical across speech poses")
    audit = {
        "format": AUDIT, "passed": True,
        "source_packet_sha256": packet["source_sha256"],
        "actor_id": source["actor_id"], "voice_id": source["voice_id"],
        "original_take_sha256": source["original_take_sha256"],
        "original_pcm_sha256": source["original_pcm_sha256"],
        "source_usd_sha256": source["source_usd_sha256"],
        "source_facial_candidate_sha256": source["source_facial_candidate_sha256"],
        "real_original_usd_mesh_imported": True,
        "real_actor_blendshape_names": sorted(source["shape_names"]),
        "real_actor_vertex_count": len(actor.data.vertices),
        "source_shape_sample_count": len(source["samples"]),
        "source_shape_samples": source["samples"],
        "original_body_and_film_not_edited": True,
        "review_camera_not_original_film_shot": True,
        "actual_blender_version": bpy.app.version_string,
        "actual_renderer": "Blender Cycles CPU",
        "blend_sha256": digest_file(locations["--output"]),
        "preview_shas": dict(zip(previews, hashes)),
        "lip_sync_accuracy_not_verified_from_render_only": True,
        "director_film_take_approved": False,
    }
    locations["--audit"].write_bytes(canonical(audit))


if __name__ == "__main__":
    run()
