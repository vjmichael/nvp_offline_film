"""NVP-CAPTURE-01: capture real approved, timed proxy scenes as frozen FilmIndex takes.

A *capture* records exact approved scene geometry, camera/shot instructions,
actor paths, measured dialogue timings, cuts and source proof. It does not
render video, generate actor voices or pretend the proxy is hi-fi anatomy.

The source ShotSequence remains editable via its own explicit revision path.
Previously captured takes retain the ORIGINAL approved source version.
"""
from __future__ import annotations

import hashlib

from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_production_scene import digest
from backend.nvp_shot_sequence import ShotSequence, FPS
from backend.nvp_studio import Studio


def _require(condition, message):
    if not condition:
        raise RuntimeError("Frozen digital take rejected: " + message)


def _capture_audit(world, timed, plan, proof, review):
    """Independent *stored-data* audit; never relies on today's live scene.

    This validates structural/temporal source coherence, not rendered frames,
    contact biomechanics, actor emotional quality or external audio bytes.
    """
    _require(isinstance(world, dict) and isinstance(timed, dict), "missing source world/timed tracks")
    _require(isinstance(plan, dict) and isinstance(proof, dict), "missing sequence/approval proof")
    _require(world.get("format") == "nvp.world.manifest.v1" or
             world.get("format") == "nvp.production.world_state.v1" or
             "world_digest_sha256" in world, "unrecognized world snapshot")
    _require(timed.get("format") == "nvp.production.timed_proxy.v1", "unrecognized timed proxy track")
    _require(timed.get("project_id") == proof.get("project_id") and
             timed.get("scene_id") == proof.get("scene_id"), "project or scene mismatched")
    _require(timed.get("world_sha") == world.get("world_digest_sha256"), "source WorldState digest mismatch")
    _require(timed.get("dependency_sha") == proof.get("dependency_sha"), "dependency receipt mismatch")
    _require(timed.get("sequence_sha") == digest(plan), "sequence contents differ from approved plan")
    _require(proof.get("approved_digest") ==
             digest({"plan": plan, "dependency_sha": proof["dependency_sha"]}),
             "director approval digest mismatch")
    _require(plan.get("fps") == FPS and timed.get("fps") == FPS, "capture frame rate mismatch")
    _require(proof.get("source_sequence_revision") >= 1, "no source approval revision")
    _require(isinstance(review, dict) and not review.get("errors") and
             not review.get("unacknowledged_warnings"),
             "original sequence not independently approved")
    shots = timed.get("shots")
    planned = plan.get("shots")
    _require(isinstance(shots, list) and shots and isinstance(planned, list) and
             len(shots) == len(planned), "missing camera shots")
    position = 1
    shot_ids = set()
    for actual, original in zip(shots, planned):
        _require(isinstance(actual, dict) and isinstance(original, dict) and
                 all(actual.get(k) == original.get(k) for k in
                     ("id", "camera_id", "pattern", "start_frame", "stop_frame")),
                 "camera shot differs from source plan")
        start, stop = actual["start_frame"], actual["stop_frame"]
        _require(type(start) is int and type(stop) is int and
                 start == position and stop > start and stop <= 240001,
                 "invalid/noncontiguous shot timing")
        _require(actual["id"] not in shot_ids and isinstance(actual.get("solution"), dict) and
                 isinstance(actual.get("recipe"), dict), "missing or duplicate camera solution")
        shot_ids.add(actual["id"])
        position = stop
    cast = {x.get("instance_id") for x in world.get("instances", [])
            if isinstance(x, dict) and x.get("category") == "character"}
    actors = timed.get("actors", [])
    _require(isinstance(actors, list) and
             len(actors) == len({a.get("instance_id") for a in actors if isinstance(a, dict)}),
             "ambiguous actor identities")
    _require(all(isinstance(actor, dict) and actor.get("instance_id") in cast and
                 isinstance(actor.get("marks"), list) and
                 isinstance(actor.get("initial_xy"), list) and
                 len(actor["initial_xy"]) == 2 for actor in actors),
             "missing world actor or actor path")
    cues = plan.get("cues", [])
    dialogue = timed.get("dialogue", [])
    _require(isinstance(cues, list) and isinstance(dialogue, list) and
             len(cues) == len(dialogue), "dialogue line count differs")
    cue_ids = {(x.get("line_id"), x.get("start_frame"))
               for x in cues if isinstance(x, dict)}
    _require(len(cue_ids) == len(cues), "ambiguous original dialogue cues")
    for line in dialogue:
        _require(isinstance(line, dict) and
                 (line.get("line_id"), line.get("start_frame")) in cue_ids and
                 line.get("speaker") in cast and
                 type(line.get("duration_frames")) is int and line["duration_frames"] > 0 and
                 type(line.get("start_frame")) is int and line["start_frame"] >= 1 and
                 line["start_frame"] + line["duration_frames"] <= position and
                 line.get("timing_origin") in {"director_measured", "tts_measured"},
                 "dialogue speaker/timing invalid")
    return {
        "status": "passed_frozen_proxy_capture",
        "frame_rate": FPS,
        "frames": position - 1,
        "shot_count": len(shots),
        "actor_count": len(actors),
        "dialogue_line_count": len(dialogue),
        "world_sha256": digest(world),
        "timed_sha256": digest(timed),
        "source_sequence_sha256": digest(plan),
        "limitations": [
            "Validates stored approved 3D proxy world and timed instructions, not native Blender replay",
            "No actual audio waveform or acoustic microphone capture is implied by measured dialogue duration",
            "Not an independently certified human motion, full-foot contact or hi-fi visual result",
        ],
    }


class DigitalCapture:
    def __init__(self, studio: Studio, index: FilmIndex | None = None):
        self.studio = studio
        self.index = index if index is not None else FilmIndex(studio)
        self.sequence = ShotSequence(studio)

    def _source(self, project_id, scene_id):
        """Read and independently validate a *currently approved* timed sequence."""
        bundle = self.sequence.export(project_id, scene_id)
        state = self.sequence.read(project_id, scene_id)
        _require(state["status"] == "approved" and not state["stale"] and
                 not state["review"]["errors"] and
                 not state["review"]["unacknowledged_warnings"],
                 "timed sequence is not current and approved")
        with self.studio._connection() as db:
            row = self.sequence._stored(db, project_id, scene_id)
        _require(row["status"] == "approved" and
                 row["revision"] == state["revision"] and
                 row["dependency_sha"] == bundle["take"]["dependency_sha"],
                 "sequence approval changed during source read")
        proof = {
            "project_id": project_id,
            "scene_id": scene_id,
            "source_sequence_revision": state["revision"],
            "approved_digest": row["approved_digest"],
            "dependency_sha": row["dependency_sha"],
            "source_world_sha": row["world_sha"],
        }
        audit = _capture_audit(bundle["manifest"], bundle["take"], state["plan"],
                               proof, bundle["review"])
        return {
            "world": bundle["manifest"],
            "timed": bundle["take"],
            "plan": state["plan"],
            "proof": proof,
            "review": bundle["review"],
            "audit": audit,
        }

    def _ensure_source(self, project_id, object_id, kind, data, dependencies):
        """Reuse a source-by-content snapshot, never update an old snapshot."""
        try:
            existing = self.index.read_revision(project_id, object_id)
        except KeyError:
            try:
                return self.index.register_revision(
                    project_id, object_id, kind, data, dependencies=dependencies)
            except RuntimeError as exc:
                # A concurrent, *identical* snapshot might have been published.
                if "conflict" not in str(exc):
                    raise
                existing = self.index.read_revision(project_id, object_id)
        _require(existing["kind"] == kind and existing["data"] == data and
                 existing["dependencies"] == sorted(
                     dependencies, key=lambda d: (d["object_id"], d["revision"], d["role"])),
                 "existing source snapshot does not match its content-addressed identity")
        return existing

    def capture(self, project_id: str, scene_id: str, take_id: str):
        """Freeze real approved source data; refuse stale source at commit boundary.

        No preview render or model runs. Source snapshots can be indexed before
        the final take; a failed capture leaves no false-approved take.
        """
        _id(take_id, "digital take ID")
        source = self._source(project_id, scene_id)
        world_sha = source["audit"]["world_sha256"]
        performance_sha = digest({"timed": source["timed"], "plan": source["plan"],
                                  "proof": source["proof"], "review": source["review"]})
        world_id = "world_" + world_sha[:32]
        performance_id = "performance_" + performance_sha[:32]
        w = self._ensure_source(project_id, world_id, "world",
            {"format": "nvp.capture.world.v1", "scene_id": scene_id,
             "manifest": source["world"]}, [])
        p = self._ensure_source(project_id, performance_id, "performance",
            {"format": "nvp.capture.timed_performance.v1", "scene_id": scene_id,
             "timed_take": source["timed"], "plan": source["plan"],
             "approval_proof": source["proof"], "review": source["review"]},
            [{"object_id": world_id, "revision": 1, "role": "world"}])
        expected_fingerprint = digest({"world":source["world"], "timed":source["timed"],
                                       "plan":source["plan"], "proof":source["proof"],
                                       "review":source["review"]})

        def guard(_db):
            # Invoked by FilmIndex INSIDE BEGIN IMMEDIATE, after resolving the
            # exact source reference links and BEFORE committing the take.
            # Every other SQLite writer is excluded for the duration.
            latest = self._source(project_id, scene_id)
            if digest({"world":latest["world"], "timed":latest["timed"],
                       "plan":latest["plan"], "proof":latest["proof"],
                       "review":latest["review"]}) != expected_fingerprint:
                raise RuntimeError("Source changed during capture; no frozen take was committed")

        receipt = self.index.register_revision(
            project_id, take_id, "take",
            {"format": "nvp.digital.take.v1",
             "scene_id": scene_id,
             "source_world_id": world_id,
             "source_world_revision": 1,
             "source_performance_id": performance_id,
             "source_performance_revision": 1,
             "source_world_sha256": world_sha,
             "source_timed_sha256": source["audit"]["timed_sha256"],
             "source_sequence_sha256": source["audit"]["source_sequence_sha256"],
             "capture_fingerprint_sha256": expected_fingerprint,
             "source_sequence_revision": source["proof"]["source_sequence_revision"],
             "capture_state": "frozen_proxy_data",
             "frame_count": source["audit"]["frames"],
             "frame_rate": FPS,
             "limitations": source["audit"]["limitations"]},
            dependencies=[
                {"object_id": world_id, "revision": w["revision"], "role": "world"},
                {"object_id": performance_id, "revision": p["revision"], "role": "performance"},
            ],
            precommit_guard=guard,
        )
        reopened = self.reopen(project_id, take_id)
        return {"receipt": receipt, "audit": reopened["audit"]}

    def reopen(self, project_id: str, take_id: str):
        """Independent saved-source audit: no live scene, Blender, VRAM or AI."""
        _id(take_id, "digital take ID")
        record = self.index.read_revision(project_id, take_id)
        _require(record["kind"] == "take" and record["revision"] == 1,
                 "not a frozen first-revision take")
        item = record["data"]
        _require(item.get("format") == "nvp.digital.take.v1" and
                 item.get("capture_state") == "frozen_proxy_data",
                 "unknown capture format/status")
        w = self.index.read_revision(project_id, item["source_world_id"],
                                     item["source_world_revision"])
        p = self.index.read_revision(project_id, item["source_performance_id"],
                                     item["source_performance_revision"])
        _require(w["kind"] == "world" and p["kind"] == "performance",
                 "capture sources have incorrect kinds")
        expected_edges = {
            (w["object_id"], w["revision"], "world"),
            (p["object_id"], p["revision"], "performance"),
        }
        _require({(x["object_id"], x["revision"], x["role"])
                  for x in record["dependencies"]} == expected_edges,
                 "take source-lineage edges do not match frozen references")
        _require(p["dependencies"] == [{"object_id": w["object_id"],
                                        "revision":w["revision"], "role":"world"}],
                 "timed performance is not bound to source world")
        world = w["data"]["manifest"]
        timed = p["data"]["timed_take"]
        plan = p["data"]["plan"]
        proof = p["data"]["approval_proof"]
        review = p["data"]["review"]
        audit = _capture_audit(world, timed, plan, proof, review)
        _require(proof["project_id"] == project_id and proof["scene_id"] == item["scene_id"] and
                 w["data"]["scene_id"] == item["scene_id"] and
                 p["data"]["scene_id"] == item["scene_id"],
                 "cross-scene/project source record")
        _require(audit["world_sha256"] == item["source_world_sha256"] and
                 audit["timed_sha256"] == item["source_timed_sha256"] and
                 audit["source_sequence_sha256"] == item["source_sequence_sha256"] and
                 audit["frames"] == item["frame_count"] and
                 item["frame_rate"] == FPS and
                 item["source_sequence_revision"] == proof["source_sequence_revision"],
                 "frozen take metadata and source snapshot disagree")
        expected_fingerprint = digest({"world":world, "timed":timed, "plan":plan,
                                       "proof":proof, "review":review})
        _require(item["capture_fingerprint_sha256"] == expected_fingerprint,
                 "capture content fingerprint mismatch")
        _require(w["object_id"] == "world_"+audit["world_sha256"][:32] and
                 p["object_id"] == "performance_"+digest(
                     {"timed":timed, "plan":plan, "proof":proof, "review":review})[:32],
                 "source snapshot identity mismatch")
        return {"record":record,"world":world,"timed_take":timed,
                "source_plan":plan,"approval_proof":proof,"review":review,"audit":audit}


def run_frozen_take_acceptance(capture: DigitalCapture, project_id: str,
                               take_id: str, directory, *, executable="blender",
                               render_preview=True, timeout=180):
    """Actually save/reopen/audit *stored* frozen capture in native Blender.

    Uses existing independently accepted PROD-05 native scene+camera+actor
    audit, but its source is FilmIndex frozen objects, NEVER the live stage.
    The regular Blender acceptance outputs are reportable, not automatically
    director-approved presentation packages.
    """
    from backend.nvp_shot_sequence import run_shot_acceptance

    frozen = capture.reopen(project_id, take_id)
    scene_id = frozen["record"]["data"]["scene_id"]

    class FrozenSource:
        def export(self, selected_project, selected_scene):
            if selected_project != project_id or selected_scene != scene_id:
                raise RuntimeError("Frozen take cannot be replayed as another project or scene")
            return {"manifest": frozen["world"], "take": frozen["timed_take"],
                    "review": frozen["review"]}

    result = run_shot_acceptance(
        FrozenSource(), project_id, scene_id, directory,
        executable=executable, render_preview=render_preview, timeout=timeout)
    return {"capture_id":take_id,
            "source_world_sha256":frozen["audit"]["world_sha256"],
            "capture_document_sha256":frozen["record"]["document_sha256"],
            **result}
