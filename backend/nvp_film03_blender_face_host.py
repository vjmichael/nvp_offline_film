"""FILM03-09D.3: real native Blender render of the EXISTING original USD face.

This host is a review/render worker, NOT a film Take approval or acoustic
accuracy claim. It composes the 09D derived USD face over the immutable source
scene, samples actual native UsdSkel weights, and stages ONLY the fixed first-
party Blender script in NVP's existing journaled/contained supervisor.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import math
import shutil

from backend.nvp_blender_worker import (
    BlenderOperation, BlenderWorkerSupervisor, sha_file,
)
from backend.nvp_film03_facial_rig_compositor import (
    FORMAT as FACE_LAYER_FORMAT, inspect_original_rig,
    validate_stored_acoustic_output,
)
from backend.nvp_film03_independent_facial_direction import (
    FORMAT as DIRECTION_FORMAT, TICKS_PER_SAMPLE,
)
from backend.nvp_film03_phoneme_alignment import FORMAT as ALIGN_FORMAT
from backend.nvp_film03_voice_conversion_intent import verified_guide_signal
from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE
from backend.nvp_film_index import FilmIndex, _id, _sha
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_film03_actor_identity_core import canonical, digest

FORMAT = "nvp.film03.real_usd_face_blender_packet.v1"
AUDIT = "nvp.film03.real_usd_face_blender_audit.v1"
SCRIPT = "nvp_film03_real_face_blender_worker.py"


def _one_source(index, pid, dependencies, format_value):
    hits = []
    for item in dependencies:
        if item["role"] != "performance":
            continue
        source = index.read_revision(pid, item["object_id"], item["revision"])
        if source["data"].get("format") == format_value:
            hits.append((item, source))
    if len(hits) != 1:
        raise PermissionError("Original facial source dependencies are ambiguous")
    return hits[0]


class ReviewedBlenderFacialHost:
    def __init__(self, index: FilmIndex, supervisor: BlenderWorkerSupervisor,
                 *, verify_director_action):
        if (not isinstance(index, FilmIndex) or
                not isinstance(supervisor, BlenderWorkerSupervisor) or
                not callable(verify_director_action)):
            raise TypeError("Native FilmIndex and existing Blender supervisor required")
        self.index = index
        self.supervisor = supervisor
        self.approve = verify_director_action

    def source(self, pid, candidate_id):
        _id(candidate_id, "facial USD candidate")
        row = self.index.read_revision(pid, candidate_id, 1)
        d = row["data"]
        if row["kind"] != "performance" or d.get("format") != FACE_LAYER_FORMAT \
           or d.get("director_approved") is not False:
            raise PermissionError("Only an unapproved, original-source facial USD candidate")
        alignment_dep, alignment = _one_source(
            self.index, pid, row["dependencies"], ALIGN_FORMAT)
        face_dep, face = _one_source(
            self.index, pid, row["dependencies"], DIRECTION_FORMAT)
        a, f = alignment["data"], face["data"]
        # The original model-output JSON must be available and re-parsable.
        # A self-reported "model executed" field does not authorize renders.
        validate_stored_acoustic_output(self.index, pid, a)
        plan = a["source_plan"]
        if (d["source_09c_alignment_sha256"] != alignment["document_sha256"]
            or d["source_facial_direction_sha256"] != face["document_sha256"]
            or d["original_pcm_sha256"] != plan["original_pcm_sha256"]
            or d["source_take_sha256"] != plan["source_take_sha256"]
            or d["actor_id"] != plan["actor_id"]
            or d["voice_id"] != plan["voice_id"]
            or plan["face_direction_id"] != face_dep["object_id"]
            or plan["face_direction_sha256"] != face["document_sha256"]
            or f["audio_source"]["pcm16le_sha256"] != plan["original_pcm_sha256"]
            or a.get("native_acoustic_model_executed") is not True
            or a.get("review_state") != "UNREVIEWED_PHONEME_CANDIDATE"
            or a.get("native_result_exit_code") != 0):
            raise PermissionError("Unmatched or unaudited original audio/acoustic/face source")
        rig = inspect_original_rig(
            self.index, pid, plan["source_take_id"],
            d["actor_prim_path"], d["source_take_sha256"])
        if rig["skeleton_layer_sha256"] != d["source_rig_sha256"]:
            raise PermissionError("Original facial rig SHA differs from authored candidate")
        original_pcm = verified_guide_signal(
            self.index, pid, plan["audio_source_id"],
            plan["audio_source_revision"])
        if (original_pcm["pcm16le_sha256"] != plan["original_pcm_sha256"] or
            original_pcm["source_document_sha256"] !=
                plan["audio_source_document_sha256"] or
            original_pcm["sample_count"] != plan["sample_count"]):
            raise PermissionError("Recorded audio bytes changed since acoustic alignment")
        usda = self.index.get_blob(pid, d["usd_layer_sha256"])
        if (sha256(usda).hexdigest() != d["usd_layer_sha256"]
            or not 0 < len(usda) <= 8 * 1024 * 1024):
            raise PermissionError("Derived facial USD layer not stored immutably")
        return {
            "row": row, "alignment": alignment, "face": face,
            "plan": plan, "rig": rig, "face_layer_bytes": usda,
            "pcm": original_pcm,
        }

    def run(self, pid, candidate_id, *, job_id, director_event):
        _id(job_id, "Blender facial render job")
        if len(job_id) > 64:
            raise ValueError("Facial job ID plus independent reopen must fit native supervisor")
        src = self.source(pid, candidate_id)
        p, rig = src["plan"], src["rig"]
        if not p["original_pcm_sha256"] or not src["alignment"]["data"]["viseme_candidates"]:
            raise PermissionError("Original speech source and exact phoneme events required")
        library = src["alignment"]["data"]["viseme_candidates"]
        if len(library) < 2:
            raise ValueError("Need more than one actual speech mouth pose to compare")
        center_samples = [
            (library[0]["start_sample"] + library[0]["end_sample"]) // 2,
            (library[1]["start_sample"] + library[1]["end_sample"]) // 2,
        ]
        face_keyframes = src["face"]["data"]["facial_expression_track"]
        third = (face_keyframes[-1]["sample"] if len(face_keyframes) > 1
                 else min(p["sample_count"] - 1, center_samples[1] + 2400))
        sample_positions = center_samples + [third]
        if (len(set(sample_positions)) != 3 or
                any(not 0 <= n < p["sample_count"] for n in sample_positions)):
            raise ValueError("Face audition needs three distinct original sample offsets")
        script = Path(__file__).resolve().parents[1] / "tools" / SCRIPT
        if script.is_symlink() or not script.is_file():
            raise PermissionError("Fixed first-party Blender facial worker script is missing")
        scope = {
            "operation": "film03_render_original_face_audio_candidate",
            "project_id": pid, "candidate_id": candidate_id,
            "candidate_document_sha256": src["row"]["document_sha256"],
            "original_pcm_sha256": p["original_pcm_sha256"],
            "original_take_sha256": p["source_take_sha256"],
            "original_actor_id": p["actor_id"],
            "original_voice_id": p["voice_id"],
            "source_blender_script_sha256": sha_file(script),
            "blender_executable_sha256": self.supervisor.binary_sha256,
            "job_id": job_id,
        }
        if not self.approve(director_event, scope):
            raise PermissionError("Director did not select exact facial audition for rendering")
        # The source and exact packet must still be stable when approved.
        if self.source(pid, candidate_id) != src:
            raise PermissionError("Original character/audio/facial sources changed before stage")
        from pxr import Sdf, Usd, UsdSkel
        scene, original = OpenUSDSceneBridge(self.index).open(
            pid, rig["source_scene_id"], rig["source_scene_revision"])
        facial = Sdf.Layer.CreateAnonymous("nvp_actor_face_review.usda")
        if not facial.ImportFromString(src["face_layer_bytes"].decode("utf8")):
            raise RuntimeError("Actual source-bound facial USD cannot be reopened")
        composition = Sdf.Layer.CreateAnonymous("nvp_face_preview_composition.usda")
        composition.subLayerPaths = [
            facial.identifier, original.GetRootLayer().identifier]
        stage = Usd.Stage.Open(composition, Usd.Stage.LoadNone)
        stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
        animation = UsdSkel.Animation(stage.GetPrimAtPath(rig["animation_path"]))
        if not animation or [str(x) for x in (
                animation.GetBlendShapesAttr().Get() or [])] != rig["shape_names"]:
            raise RuntimeError("Actual animated actor facial shape order changed in composition")
        samples = []
        for frame, offset in enumerate(sample_positions, 1):
            tick = src["face"]["data"]["speech_start_film_tick"] + \
                   offset * TICKS_PER_SAMPLE
            weights = animation.GetBlendShapeWeightsAttr().Get(
                Usd.TimeCode(float(tick)))
            if weights is None or len(weights) != len(rig["shape_names"]):
                raise RuntimeError("Composed USD facial animation not evaluable in Film Time")
            vals = [float(v) for v in weights]
            if any(not math.isfinite(v) or not 0 <= v <= 1 for v in vals):
                raise RuntimeError("Original USD actor facial weights invalid")
            samples.append({
                "frame": frame, "pcm_sample": offset,
                "weights": dict(zip(rig["shape_names"], vals)),
            })
        if samples[0]["weights"] == samples[1]["weights"]:
            raise ValueError("Two actor speech poses are identical; cannot validate lip motion")
        job = self.supervisor.root / job_id
        if job.exists() or job.is_symlink():
            raise RuntimeError("Facial render job already staged")
        job.mkdir(mode=0o700)
        usd_path = job / "source.usda"
        if not stage.Export(str(usd_path)):
            raise RuntimeError("Cannot export genuine source USD for Blender")
        data = {
            "project_id": pid, "actor_id": p["actor_id"],
            "voice_id": p["voice_id"],
            "original_take_sha256": p["source_take_sha256"],
            "original_pcm_sha256": p["original_pcm_sha256"],
            "source_facial_candidate_sha256": src["row"]["document_sha256"],
            "source_usd_sha256": sha_file(usd_path),
            "source_usd_file": "source.usda",
            "source_mesh_vertex_count": rig["skinned_vertex_count"],
            "actor_prim_path": rig["actor_prim_path"],
            "shape_names": rig["shape_names"],
            "samples": samples,
            "preview_camera_not_editorial": True,
        }
        packet = {"format": FORMAT, "source": data,
                  "source_sha256": digest(data)}
        (job / "source.json").write_bytes(canonical(packet))
        (job / SCRIPT).write_bytes(script.read_bytes())
        op = BlenderOperation(
            job_id=job_id, script=SCRIPT, script_sha256=sha_file(job / SCRIPT),
            inputs={
                "source.json": sha_file(job / "source.json"),
                "source.usda": sha_file(usd_path),
            },
            outputs={
                "scene.blend": "blend", "audit.json": "json_audit",
                "facial_at_1.png": "png", "facial_at_2.png": "png",
                "facial_at_3.png": "png",
            },
            arguments={
                "--manifest": "source.json", "--output": "scene.blend",
                "--audit": "audit.json", "--preview": "facial_at_2.png",
            },
            timeout_seconds=600, memory_limit_mb=8192,
            gpu_memory_mb=0, require_linux_cgroup_v2=True, require_private_isolation=True,
        )
        outcome = self.supervisor.run(op)
        if outcome["state"] != "SUCCEEDED":
            return {
                "state": outcome["state"], "job_id": job_id,
                "render_approved_as_film": False,
            }
        self.supervisor.verify_completed(job_id)
        audit = json.loads((job / "audit.json").read_text("utf8"))
        if (audit.get("format") != AUDIT or audit.get("passed") is not True
            or audit.get("source_packet_sha256") != packet["source_sha256"]
            or audit.get("source_usd_sha256") != data["source_usd_sha256"]
            or audit.get("source_facial_candidate_sha256") !=
                src["row"]["document_sha256"]
            or audit.get("original_pcm_sha256") != p["original_pcm_sha256"]
            or audit.get("original_take_sha256") != p["source_take_sha256"]
            or audit.get("actor_id") != p["actor_id"]
            or audit.get("voice_id") != p["voice_id"]
            or audit.get("real_original_usd_mesh_imported") is not True
            or audit.get("source_shape_samples") != samples
            or audit.get("blend_sha256") != sha_file(job / "scene.blend")
            or any(audit.get("preview_shas", {}).get(f"facial_at_{i}.png")
                   != sha_file(job / f"facial_at_{i}.png") for i in (1, 2, 3))):
            raise PermissionError("Real native Blender facial render receipt does not match actual source")
        # A SECOND native Blender process must independently reopen and
        # check the same real ActorID face/PCM/Take and all three pose values.
        reopen_code = Path(__file__).resolve().parents[1] / "tools" / \
            "nvp_film03_real_face_blender_reopen.py"
        if reopen_code.is_symlink() or not reopen_code.is_file():
            raise PermissionError("Reviewed independent face verifier is missing")
        reopen_id = job_id + "_reopen"
        _id(reopen_id, "independent Blender reopen job")
        reopen_dir = self.supervisor.root / reopen_id
        if reopen_dir.exists() or reopen_dir.is_symlink():
            raise RuntimeError("Independent facial reopen already staged")
        reopen_dir.mkdir(mode=0o700)
        shutil.copyfile(job / "scene.blend", reopen_dir / "scene.blend")
        (reopen_dir / "source.json").write_bytes(canonical({
            "source": data,
            "source_blend_sha256": sha_file(reopen_dir / "scene.blend"),
        }))
        (reopen_dir / reopen_code.name).write_bytes(reopen_code.read_bytes())
        reopen_op = BlenderOperation(
            job_id=reopen_id, scene="scene.blend",
            script=reopen_code.name,
            script_sha256=sha_file(reopen_dir / reopen_code.name),
            inputs={
                "scene.blend": sha_file(reopen_dir / "scene.blend"),
                "source.json": sha_file(reopen_dir / "source.json"),
            },
            outputs={"audit.json": "json_audit"},
            arguments={
                "--manifest": "source.json", "--audit": "audit.json",
            },
            memory_limit_mb=8192, timeout_seconds=600,
            gpu_memory_mb=0, require_linux_cgroup_v2=True, require_private_isolation=True,
        )
        follow = self.supervisor.run(reopen_op)
        if follow["state"] != "SUCCEEDED":
            return {
                "state": follow["state"], "job_id": job_id,
                "independent_reopen_passed": False,
                "render_approved_as_film": False,
            }
        self.supervisor.verify_completed(reopen_id)
        proof = json.loads((reopen_dir / "audit.json").read_text("utf8"))
        if (proof.get("passed") is not True
            or proof.get("actor_id") != p["actor_id"]
            or proof.get("voice_id") != p["voice_id"]
            or proof.get("original_take_sha256") != p["source_take_sha256"]
            or proof.get("original_pcm_sha256") != p["original_pcm_sha256"]
            or proof.get("source_facial_candidate_sha256") !=
                src["row"]["document_sha256"]
            or proof.get("blender_reopen_sha256") != sha_file(job / "scene.blend")
            or proof.get("real_imported_mesh_shape_keys_reopened") is not True
            or proof.get("three_authored_mouth_face_poses_independently_reopened")
                is not True):
            raise PermissionError("Independent Blender process disagrees on saved facial source")
        # The reopened geometry has passed, but real human auditory/video
        # lip-sync quality and director Take approval remain separate gates.
        media = self.index.put_media_file(
            pid, job / "scene.blend", media_type="application/octet-stream",
            max_bytes=64 * 1024 * 1024)
        pngs = [self.index.put_blob(
            pid, (job / f"facial_at_{i}.png").read_bytes(),
            media_type="image/png") for i in (1, 2, 3)]
        if media["sha256"] != audit["blend_sha256"] or any(
                s != audit["preview_shas"][f"facial_at_{i}.png"]
                for i, s in enumerate(pngs, 1)):
            raise RuntimeError("Stored original actor preview differs from native Blender output")
        candidate = "FacialRender_" + job_id
        doc = {
            "format": "nvp.film03.unapproved_blender_face_render.v1",
            "actor_id": p["actor_id"], "voice_id": p["voice_id"],
            "original_pcm_sha256": p["original_pcm_sha256"],
            "original_take_sha256": p["source_take_sha256"],
            "source_facial_candidate_sha256": src["row"]["document_sha256"],
            "real_blender_binary_sha256": self.supervisor.binary_sha256,
            "reviewed_blender_script_sha256": op.script_sha256,
            "real_blender_scene_sha256": media["sha256"],
            "real_rendered_png_shas": pngs,
            "native_blender_audit_sha256": sha_file(job / "audit.json"),
            "actual_rendered_actor": True,
            "independent_fresh_blender_reopen_verified": True,
            "independent_reopen_audit_sha256": sha_file(
                reopen_dir / "audit.json"),
            "phoneme_to_rendered_lip_accuracy_verified": False,
            "director_take_approved": False,
        }
        saved = self.index.register_revision(
            pid, candidate, "performance", doc, expected_revision=0,
            dependencies=[
                {"object_id": candidate_id, "revision": 1, "role": "performance"},
                {"object_id": p["source_take_id"], "revision": 1,
                 "role": "source_take"},
                {"object_id": p["audio_source_id"],
                 "revision": p["audio_source_revision"], "role": "audio"},
            ],
        )
        return {
            "state": "SUCCEEDED", "render_candidate_id": candidate,
            "document_sha256": saved["document_sha256"],
            "blend_sha256": media["sha256"], "preview_png_sha256": pngs,
            "original_sources_unchanged": True,
            "independent_reopen_verified": True,
            "director_take_approved": False,
        }
