"""FILM03-09D: REAL original UsdSkel facial rig inspection and derived lip layer.

No surrogate actor mesh, fictional mouth, emotional inference, or renderer.
The actual original SkinMesh/UsdSkel.BlendShape names, target geometry and
UsdSkel.Animation source are reopened before any new speech keyframes.
A separately authored USD layer may be stored as an unapproved film source
candidate. It NEVER changes the original frozen USD scene or dialogue Take.

Face normally follows director-approved vocal emotion; explicit face
keyframes ALWAYS win. Body and skeletal joint animation are not rewritten.
"""
from __future__ import annotations

from hashlib import sha256
import math

from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid
from backend.nvp_openusd_scene import OpenUSDSceneBridge, MAX_USD_EXACT_TICK
from backend.nvp_openusd_take import FORMAT as TAKE_FORMAT
from backend.nvp_film03_independent_facial_direction import (
    FORMAT as FACE_FORMAT, TICKS_PER_SAMPLE, VISEMES, FACES,
)
from backend.nvp_film03_phoneme_alignment import (
    FORMAT as PHONEME_FORMAT, import_mfa_json,
)
from backend.nvp_film03_voice_conversion_intent import verified_guide_signal
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_production_bible_actors import ProductionBibleActors

FORMAT = "nvp.film03.actor_facial_rig_overlay.v1"
MAX_KEYS = 4096
MAX_LAYER_BYTES = 8 * 1024 * 1024
MAX_MAPPED = 40
RAMP_SAMPLES = 480  # 10ms at 48k; genuinely overlapping phonemes
EPSILON = 1e-7


def inspect_original_rig(index: FilmIndex, pid, take_id, actor_path, expected_take_sha):
    """Reopen actual original USD mesh and nonzero BlendShape geometry.

    A rig without an authored, nonzero mouth shape is *unsupported*:
    it is not repaired with an invented avatar. Caller may instead select
    the separate no-mouth object-actor mode.
    """
    if not isinstance(index, FilmIndex):
        raise TypeError("Real native FilmIndex required")
    _require_pid(pid)
    _id(take_id, "original USD Take")
    _sha(expected_take_sha)
    if type(actor_path) is not str or not actor_path.startswith("/World/"):
        raise ValueError("An authored original actor prim path is required")
    take = index.read_revision(pid, take_id, 1)
    td = take["data"]
    if (take["kind"] != "take" or td.get("format") != TAKE_FORMAT
            or take["document_sha256"] != expected_take_sha):
        raise PermissionError("Not the exact frozen source OpenUSD Digital Take")
    scene, stage = OpenUSDSceneBridge(index).open(
        pid, td["scene_id"], td["scene_revision"])
    if scene["document_sha256"] != td["scene_document_sha256"] or \
       scene["data"]["prim_roles"].get(actor_path) != "actor":
        raise PermissionError("Actor prim does not belong to the frozen source scene")
    rigs = [r for r in scene["data"].get("skeleton_rigs", [])
            if r.get("path") == actor_path]
    if len(rigs) != 1 or not rigs[0].get("skin_weighted"):
        raise ValueError("Original actor has no actual weighted USD facial mesh")
    rig = rigs[0]
    from pxr import UsdSkel, UsdGeom
    from backend.nvp_openusd_skinning import SKIN_MESH_SUFFIX
    mesh_path = actor_path + SKIN_MESH_SUFFIX
    if rig.get("skin_mesh_path") != mesh_path:
        raise PermissionError("USD actor's original skin mesh path changed")
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(mesh_path))
    animation_path = actor_path + "/Rig/Skeleton/Animation"
    animation = UsdSkel.Animation(stage.GetPrimAtPath(animation_path))
    skeleton = UsdSkel.Skeleton(
        stage.GetPrimAtPath(actor_path + "/Rig/Skeleton"))
    if not mesh or not animation or not skeleton:
        raise RuntimeError("Original actor's actual USD mesh, skeleton or animation is missing")
    if not mesh.GetPrim().HasAPI(UsdSkel.BindingAPI):
        raise PermissionError("Original mesh has no actual UsdSkel binding")
    binding = UsdSkel.BindingAPI(mesh.GetPrim())
    mesh_names = [str(x) for x in (binding.GetBlendShapesAttr().Get() or [])]
    anim_names = [str(x) for x in (animation.GetBlendShapesAttr().Get() or [])]
    paths = list(binding.GetBlendShapeTargetsRel().GetTargets() or [])
    expected = rig.get("facial_shape_names", [])
    if not mesh_names or mesh_names != anim_names or \
       mesh_names != expected or len(paths) != len(mesh_names):
        raise PermissionError("No complete original, named USD facial rig")
    points = mesh.GetPointsAttr().Get()
    if points is None or len(points) != rig["skin_vertex_count"]:
        raise RuntimeError("Skinned face mesh source topology changed")
    usable = []
    deformed_vertices = {}
    for name, target_path in zip(mesh_names, paths):
        if str(target_path) != mesh_path + "/Blend_" + name:
            raise PermissionError("Original source BlendShape target was substituted")
        shape = UsdSkel.BlendShape(stage.GetPrimAtPath(str(target_path)))
        if not shape:
            raise RuntimeError("A declared actual native USD face shape is absent")
        offsets = shape.GetOffsetsAttr().Get()
        if offsets is None or len(offsets) != len(points):
            raise RuntimeError("Actual USD face shape offsets do not match mesh")
        affected = []
        for vertex, offset in enumerate(offsets):
            coords = [float(x) for x in offset]
            if any(not math.isfinite(x) or abs(x) > 2 for x in coords):
                raise RuntimeError("Unbounded actual facial deformation")
            if any(abs(x) > EPSILON for x in coords):
                affected.append(vertex)
        deformed_vertices[name] = affected
        if affected:
            usable.append(name)
    return {
        "format": "nvp.film03.original_usd_facial_rig_readback.v1",
        "project_id": pid, "source_take_id": take_id,
        "source_take_sha256": expected_take_sha,
        "source_scene_id": td["scene_id"],
        "source_scene_revision": td["scene_revision"],
        "source_scene_sha256": scene["document_sha256"],
        "actor_prim_path": actor_path,
        "mesh_path": mesh_path, "animation_path": animation_path,
        "skeleton_layer_sha256": scene["data"]["skeleton_layer_sha256"],
        "shape_names": mesh_names, "nonzero_offset_shapes": usable,
        "shape_deformed_vertices": deformed_vertices,
        "skinned_vertex_count": len(points),
        "real_usd_mesh_and_shape_offsets_verified": True,
        "artistic_mouth_semantics_verified_by_human": False,
        "source_scene_preserved": True,
    }


def _map_controls(rig, viseme_events, face_events, viseme_shapes,
                  face_shapes, neutralize_expressions):
    if (type(viseme_shapes) is not dict or type(face_shapes) is not dict or
        type(neutralize_expressions) is not list or
        len(viseme_shapes) > MAX_MAPPED or len(face_shapes) > MAX_MAPPED or
        len(neutralize_expressions) > MAX_MAPPED):
        raise ValueError("Explicit bounded mouth/face rig control maps required")
    if type(viseme_events) is not list or type(face_events) is not list:
        raise ValueError("Speech and face keyframes must be actual typed source lists")
    if any(type(x) is not str or x not in VISEMES for x in viseme_shapes):
        raise ValueError("Unknown canonical speech-viseme mapping")
    if any(type(x) is not str or x not in FACES for x in face_shapes):
        raise ValueError("Unknown canonical facial expression mapping")
    names = set(rig["shape_names"])
    available = set(rig["nonzero_offset_shapes"])
    required_visemes = {x["viseme"] for x in viseme_events
                        if x["viseme"] not in ("rest", "silence")}
    required_faces = {x["value"] for x in face_events
                      if x["value"] != "neutral"}
    if not required_visemes <= set(viseme_shapes):
        raise ValueError("Actor has no director-reviewed mapping for a spoken viseme")
    if not required_faces <= set(face_shapes):
        raise ValueError("Actor has no authored blend shape for facial emotion")
    if (any(type(s) is not str or s not in available
            for s in list(viseme_shapes.values()) + list(face_shapes.values()))
        or any(type(s) is not str or s not in names
               for s in neutralize_expressions)):
        raise PermissionError("Do not animate absent or zero-offset facial rig geometry")
    if len(set(viseme_shapes.values())) != len(viseme_shapes) or \
       len(set(face_shapes.values())) != len(face_shapes) or \
       len(set(neutralize_expressions)) != len(neutralize_expressions):
        raise ValueError("Duplicate semantic shape targets are ambiguous")
    if set(viseme_shapes.values()) & (
        set(face_shapes.values()) | set(neutralize_expressions)
    ):
        raise PermissionError(
            "Mouth and emotion tracks share this shape: a reviewed corrective rig is needed")
    if not set(face_shapes.values()) <= set(neutralize_expressions):
        raise ValueError("All active emotion targets require explicit neutralization")
    # Distinct shape *names* can still act on the SAME mesh vertices.
    # That geometry collides without a genuine shape corrective solve.
    affected = rig["shape_deformed_vertices"]
    mouth_vertices = set().union(
        *(set(affected[name]) for name in viseme_shapes.values()))
    emotion_vertices = set().union(
        *(set(affected[name]) for name in neutralize_expressions))
    if mouth_vertices & emotion_vertices:
        raise PermissionError(
            "Actual mouth and facial emotion shapes deform shared vertices; "
            "a reviewed corrective rig is required")
    return {
        "visemes": dict(viseme_shapes),
        "emotions": dict(face_shapes),
        "emotion_reset_targets": list(neutralize_expressions),
    }


def _event_strength(at, item):
    start, end = item["start_sample"], item["end_sample"]
    duration = end - start
    if duration <= 0:
        raise ValueError("Empty actual phone interval")
    fade = min(RAMP_SAMPLES, max(1, duration // 3))
    if at < start - fade or at > end + fade:
        return 0.0
    if at < start:
        return max(0.0, 0.5 * (at - (start - fade)) / fade)
    if at <= start + fade:
        return 0.5 + 0.5 * (at - start) / fade
    if at < end - fade:
        return 1.0
    if at <= end:
        return 0.5 + 0.5 * (end - at) / fade
    return max(0.0, 0.5 * (end + fade - at) / fade)


def _sample_keys(phonemes, face, total):
    keys = {0, total}
    for item in phonemes:
        start, end = item["start_sample"], item["end_sample"]
        fade = min(RAMP_SAMPLES, max(1, (end - start) // 3))
        keys.update((max(0, start - fade), start, min(total, start + fade),
                     (start + end) // 2, max(0, end - fade), end,
                     min(total, end + fade)))
    keys.update(x["sample"] for x in face)
    keys = sorted(keys)
    if len(keys) > MAX_KEYS:
        raise ValueError("Too many real speech-to-rig keyframes for one candidate")
    return keys


def compose_usd_facial_overlay(index: FilmIndex, rig, *, phonemes,
                               face_track, body_track, controls,
                               source_start_tick, sample_count):
    """Author a NEW genuine USD facial animation layer; never touch source.

    Inputs are typed original or derived candidate sources; caller validates
    exact ActorID/audio/alignment hashes before publishing to FilmIndex.
    The returned layer animates the original mesh's actual BlendShape channels
    while leaving every joint/body transform sourced from the original Take.
    """
    if type(sample_count) is not int or not 1 <= sample_count <= 180 * 48000:
        raise ValueError("Finite original recorded dialogue is required")
    if type(source_start_tick) is not int or not 0 <= source_start_tick \
       or source_start_tick + sample_count * TICKS_PER_SAMPLE > MAX_USD_EXACT_TICK:
        raise ValueError("Facial animation exceeds exact source Film Time")
    if type(phonemes) is not list or type(face_track) is not list or \
       type(body_track) is not list:
        raise ValueError("Independent voice/face/body source tracks required")
    if type(rig) is not dict or rig != inspect_original_rig(
            index, rig["project_id"], rig["source_take_id"],
            rig["actor_prim_path"], rig["source_take_sha256"]):
        raise PermissionError("Facial source map differs from actual original USD rig")
    controls = _map_controls(rig, phonemes, face_track,
                             controls["visemes"], controls["emotions"],
                             controls["emotion_reset_targets"])
    last_end = 0
    for item in phonemes:
        if type(item) is not dict or set(item) != {
            "start_sample", "end_sample", "phoneme", "viseme", "weight"
        } or (type(item["start_sample"]) is not int or
               type(item["end_sample"]) is not int or
               not last_end <= item["start_sample"] < item["end_sample"] <= sample_count
               or type(item["weight"]) not in (float, int) or
               not 0 <= item["weight"] <= 1):
            raise ValueError("Unreviewed or overlapping phoneme source")
        last_end = item["end_sample"]
    prior = -1
    for event in face_track:
        if type(event) is not dict or set(event) != {"sample","value","intensity"} or \
           type(event["sample"]) is not int or not prior < event["sample"] < sample_count \
           or type(event["intensity"]) not in (int, float) or not math.isfinite(event["intensity"]) or \
           not 0 <= event["intensity"] <= 1:
            raise ValueError("Unreviewed director face expression keyframes")
        prior = event["sample"]
    # Body source is NEVER materialized into the facial layer.
    _ = body_track
    take = index.read_revision(rig["project_id"], rig["source_take_id"], 1)
    if take["document_sha256"] != rig["source_take_sha256"]:
        raise PermissionError("Frozen actor take changed before facial overlay")
    if (source_start_tick < 0 or
            source_start_tick + sample_count * TICKS_PER_SAMPLE >
            take["data"]["duration_tick"]):
        raise PermissionError("Actor spoken mouth motion cannot exceed the frozen Take")
    scene, original_stage = OpenUSDSceneBridge(index).open(
        rig["project_id"], rig["source_scene_id"], rig["source_scene_revision"])
    if scene["document_sha256"] != rig["source_scene_sha256"]:
        raise PermissionError("Frozen original actor rig changed before animation")
    from pxr import Sdf, Usd, UsdSkel, Vt
    anim = UsdSkel.Animation(
        original_stage.GetPrimAtPath(rig["animation_path"]))
    names = rig["shape_names"]
    if [str(x) for x in (anim.GetBlendShapesAttr().Get() or [])] != names:
        raise PermissionError("Original animation shape order changed")
    layer = Sdf.Layer.CreateAnonymous("nvp_derived_actor_face.usda")
    stage = Usd.Stage.Open(layer)
    stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
    override = UsdSkel.Animation.Define(stage, rig["animation_path"])
    if not override.GetBlendShapesAttr().Set(Vt.TokenArray(names)):
        raise RuntimeError("Could not retain original facial shape ordering")
    shape_index = {name: i for i, name in enumerate(names)}
    for at in _sample_keys(phonemes, face_track, sample_count):
        tick = source_start_tick + at * TICKS_PER_SAMPLE
        original_weights = anim.GetBlendShapeWeightsAttr().Get(Usd.TimeCode(float(tick)))
        if original_weights is None or len(original_weights) != len(names):
            raise RuntimeError("No original source facial animation weights at film time")
        values = [float(value) for value in original_weights]
        if any(not math.isfinite(v) or v < 0 or v > 1 for v in values):
            raise PermissionError("Original actor facial source weights are invalid")
        # Only actor-approved semantic controls are reauthored. All other
        # source animation values, including joints, remain inherited.
        for name in controls["emotion_reset_targets"]:
            values[shape_index[name]] = 0.0
        for name in controls["visemes"].values():
            values[shape_index[name]] = 0.0
        current_face = next((ev for ev in reversed(face_track)
                             if ev["sample"] <= at), None)
        if current_face and current_face["value"] in controls["emotions"]:
            values[shape_index[controls["emotions"][current_face["value"]]]] = (
                float(current_face["intensity"]))
        for item in phonemes:
            target = controls["visemes"].get(item["viseme"])
            if target is not None:
                values[shape_index[target]] += (
                    float(item["weight"]) * _event_strength(at, item))
        if any(value > 1 + EPSILON for value in values):
            raise ValueError("Facial shape sum exceeds actual USD rig domain")
        values = [min(1.0, v) for v in values]
        if not override.GetBlendShapeWeightsAttr().Set(
                Vt.FloatArray(values), Usd.TimeCode(float(tick))):
            raise RuntimeError("Failed to author real USD facial keyframe")
    raw = layer.ExportToString().encode("utf8")
    if not 0 < len(raw) <= MAX_LAYER_BYTES:
        raise ValueError("Derived USD facial layer is too large")
    # Independent native USD composition: preserved source *plus* new face only.
    combined = Sdf.Layer.CreateAnonymous("nvp_review_face_composition.usda")
    combined.subLayerPaths = [
        layer.identifier, original_stage.GetRootLayer().identifier]
    review_stage = Usd.Stage.Open(combined, Usd.Stage.LoadNone)
    confirm = UsdSkel.Animation(
        review_stage.GetPrimAtPath(rig["animation_path"]))
    if not confirm or not confirm.GetBlendShapeWeightsAttr().Get(
            Usd.TimeCode(float(source_start_tick))):
        raise RuntimeError("Actual USD actor face overlay failed native composition")
    return {
        "format": FORMAT, "actor_prim_path": rig["actor_prim_path"],
        "shape_order": names, "control_mapping": controls,
        "keyframe_count": len(_sample_keys(phonemes, face_track, sample_count)),
        "sample_start_film_tick": source_start_tick,
        "sample_end_film_tick": source_start_tick + sample_count * TICKS_PER_SAMPLE,
        "usd_layer_bytes": raw, "usd_layer_sha256": sha256(raw).hexdigest(),
        "real_native_usd_blendshape_layer_authored": True,
        "all_original_joint_body_animation_untouched": True,
        "original_usd_mesh_and_take_untouched": True,
        "phoneme_accuracy_not_independently_proven_here": True,
        "rigged_visual_lip_sync_not_rendered": True,
        "human_shape_semantic_review_open": True,
    }


def validate_stored_acoustic_output(index: FilmIndex, pid, record):
    """Verify real stored model JSON exactly matches the claimed word/phone rows.

    This proves bytes/structured labels are preserved, not that a microphone
    actor spoke those words or an external model truly executed.
    """
    if not isinstance(index, FilmIndex) or type(record) is not dict:
        raise TypeError("Original FilmIndex and typed native output required")
    _require_pid(pid)
    plan = record.get("source_plan")
    if type(plan) is not dict:
        raise PermissionError("Original audio/source alignment plan missing")
    native_sha = record.get("native_output_blob_sha256")
    if type(native_sha) is not str or native_sha != record.get("native_output_sha256"):
        raise PermissionError("No independently reopenable native acoustic output")
    _sha(native_sha)
    raw = index.get_blob(pid, native_sha)
    if sha256(raw).hexdigest() != native_sha:
        raise PermissionError("Native acoustic bytes changed")
    rederived = import_mfa_json(
        raw, exact_script_text=plan["exact_script_text"],
        pcm_sample_count=plan["sample_count"])
    if any(record.get(field) != rederived[field] for field in (
        "word_intervals", "phoneme_intervals", "viseme_candidates",
        "ticks_per_sample", "source_sample_count", "sample_rate_hz",
    )):
        raise PermissionError("Stored phonemes do not match actual native output")
    return rederived


def publish_verified_alignment_overlay(index: FilmIndex, pid,
                                       alignment_id, face_id, actor_path,
                                       *, controls, candidate_id):
    """Publish derived USD facial candidate only from a source-pinned 09C record.

    A boolean in model output is not evidence: only a stored native alignment
    with source hashes, expected output hash, and exact original film deps is
    eligible for staging. Genuine acoustic and image acceptance stay open.
    """
    for value in (alignment_id, face_id, candidate_id):
        _id(value, "film face source")
    source = index.read_revision(pid, alignment_id, 1)
    face = index.read_revision(pid, face_id, 1)
    s = source["data"]
    f = face["data"]
    if source["kind"] != "performance" or s.get("format") != PHONEME_FORMAT or \
       s.get("native_acoustic_model_executed") is not True or \
       s.get("review_state") != "UNREVIEWED_PHONEME_CANDIDATE" or \
       face["kind"] != "performance" or f.get("format") != FACE_FORMAT:
        raise PermissionError("Only genuine source-bound 09C and authored face inputs")
    plan = s["source_plan"]
    if (plan["face_direction_id"] != face_id or
            plan["face_direction_sha256"] != face["document_sha256"] or
            plan["actor_id"] != f["actor_id"] or
            plan["voice_id"] != f["voice_id"] or
            plan["original_pcm_sha256"] != f["audio_source"]["pcm16le_sha256"] or
            plan["source_take_sha256"] != f["source_take_sha256"]):
        raise PermissionError("Phoneme candidate is for another actor, face or audio")
    if candidate_id in {alignment_id, face_id, plan["audio_source_id"],
                        plan["source_take_id"]}:
        raise ValueError("Cannot overwrite an original actor, Take, voice or alignment")
    # Never trust a "model executed" flag without independently reparsing
    # the original SHA-addressed native output from FilmIndex.
    validate_stored_acoustic_output(index, pid, s)
    sound = verified_guide_signal(
        index, pid, plan["audio_source_id"], plan["audio_source_revision"])
    if (sound["pcm16le_sha256"] != plan["original_pcm_sha256"] or
        sound["source_document_sha256"] !=
            plan["audio_source_document_sha256"] or
        sound["sample_count"] != plan["sample_count"]):
        raise PermissionError("Original dialogue changed after phoneme execution")
    cast = ProductionBibleActors(index.studio).require_complete_cast(
        pid, plan["source_take_id"])
    if (cast["actor_id_by_prim"].get(actor_path) != plan["actor_id"] or
            cast["take_sha256"] != plan["source_take_sha256"]):
        raise PermissionError("Rig actor prim does not match actual StoryBible ActorID")
    rig = inspect_original_rig(
        index, pid, plan["source_take_id"], actor_path,
        plan["source_take_sha256"])
    overlay = compose_usd_facial_overlay(
        index, rig, phonemes=s["viseme_candidates"],
        face_track=f["facial_expression_track"],
        body_track=f["body_performance_track"],
        controls=controls, source_start_tick=f["speech_start_film_tick"],
        sample_count=plan["sample_count"])
    # Reopen original sources after native USD authoring, not relying only
    # on a cached descriptor created before the operation.
    refreshed = inspect_original_rig(
        index, pid, plan["source_take_id"], actor_path,
        plan["source_take_sha256"])
    if refreshed != rig or \
       index.read_revision(pid, alignment_id, 1)["document_sha256"] != \
           source["document_sha256"] or \
       index.read_revision(pid, face_id, 1)["document_sha256"] != \
           face["document_sha256"]:
        raise PermissionError("Source audio/rig/face revisions changed during animation")
    blob = index.put_blob(
        pid, overlay["usd_layer_bytes"],
        media_type="application/vnd.pixar.usd.ascii")
    if blob != overlay["usd_layer_sha256"]:
        raise RuntimeError("Derived native USD layer stored with wrong content hash")
    doc = {k: v for k, v in overlay.items() if k != "usd_layer_bytes"}
    result = index.register_revision(
        pid, candidate_id, "performance",
        {**doc, "actor_id":plan["actor_id"], "voice_id":plan["voice_id"],
         "source_take_sha256":plan["source_take_sha256"],
         "source_rig_sha256":rig["skeleton_layer_sha256"],
         "source_09c_alignment_sha256":source["document_sha256"],
         "source_facial_direction_sha256":face["document_sha256"],
         "original_pcm_sha256":plan["original_pcm_sha256"],
         "director_approved":False},
        expected_revision=0,
        dependencies=[
            {"object_id":alignment_id,"revision":1,"role":"performance"},
            {"object_id":face_id,"revision":1,"role":"performance"},
            {"object_id":plan["audio_source_id"],
             "revision":plan["audio_source_revision"],"role":"audio"},
            {"object_id":plan["source_take_id"],"revision":1,"role":"source_take"},
        ],
    )
    return {
        "format": FORMAT, "candidate_id":candidate_id,
        "candidate_revision":result["revision"],
        "candidate_sha256":result["document_sha256"],
        "derived_usd_sha256":blob,
        "native_usd_facial_layer_authored":True,
        "actual_blender_render_verified":False,
        "actor_mouth_shape_semantics_human_verified":False,
        "director_final_take_approved":False,
    }
