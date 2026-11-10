"""PLAN-02-D1: read-only exact-Film-Time renderer source selection.

This is an admission *preview*, not an approved render ticket. It never
executes a worker, creates frames, writes a queue, grants OS authority, or
mutates the original OpenUSD/ActorID/PCM Digital Take. An eventual supervised
renderer must independently recheck this scope after new human permission.
"""
from __future__ import annotations

from hashlib import sha256
import json

from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_plan02c_rails import CanonicalSourceRails, evaluate_rail
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT = "nvp.plan02d.source_selected_renderer_preview.v1"
WINDOW_MAX_TICKS = 5 * TICKS_PER_SECOND
REQUEST_KEYS = frozenset({
    "take_id", "take_document_sha256",
    "camera_timeline_id", "camera_timeline_revision",
    "camera_timeline_sha256", "first_tick", "last_tick_exclusive",
    "camera_mode", "rail_id", "rail_revision", "rail_document_sha256",
})


def _hash(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


class ExactSourceWindowSelector:
    """Produce source-bound *unapproved* renderer inputs; no worker authority."""

    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Native FilmIndex is the only renderer source authority")
        self.index = index

    def preview(self, project_id, request):
        pid = _require_pid(project_id)
        if type(request) is not dict or set(request) != REQUEST_KEYS:
            raise PermissionError("Only exact typed source selection fields permitted")
        _id(request["take_id"], "frozen original Digital Take")
        _id(request["camera_timeline_id"], "authored camera timeline")
        _sha(request["take_document_sha256"])
        _sha(request["camera_timeline_sha256"])
        rev = request["camera_timeline_revision"]
        first, last = request["first_tick"], request["last_tick_exclusive"]
        if type(rev) is not int or rev < 1:
            raise ValueError("Camera timeline revision must be exact and positive")
        if (type(first) is not int or type(last) is not int or
                first < 0 or not first < last or
                last - first > WINDOW_MAX_TICKS or last > 2**53 - 1):
            raise ValueError("Only bounded exact Film Time source windows permitted")

        take = self.index.read_revision(pid, request["take_id"], 1)
        if (take["kind"] != "take" or
                take["document_sha256"] != request["take_document_sha256"] or
                take["data"].get("frozen") is not True or
                take["data"].get("format") != "nvp.digital_take.openusd_temporal.v1"):
            raise PermissionError("Renderer source must be an unchanged frozen Digital Take")
        attestation = OpenUSDTakeCapture(
            self.index, verify_creator_action=lambda *_: False
        ).verify_take(pid, request["take_id"])
        if attestation["take_document_sha256"] != take["document_sha256"]:
            raise RuntimeError("Original Take failed independent source verification")

        timeline = ExactTimeShotSequence(self.index).read(
            pid, request["camera_timeline_id"], rev)
        if (timeline["document_sha256"] != request["camera_timeline_sha256"] or
                timeline["scene_id"] != take["data"]["scene_id"] or
                timeline["scene_revision"] != take["data"]["scene_revision"] or
                timeline["scene_document_sha256"] != take["data"]["scene_document_sha256"]):
            raise PermissionError("Selected camera timeline is not bound to this source Take")
        if last > min(int(take["data"]["duration_tick"]),
                      int(timeline["duration_tick"])):
            raise ValueError("Source window exceeds frozen Take or authored camera duration")

        covering = [
            row for row in timeline["shots"]
            if int(row["start_tick"]) <= first and
               int(row["end_tick"]) >= last
        ]
        if len(covering) != 1:
            raise PermissionError("Render window crosses a camera cut, gap or overlap")
        shot = covering[0]
        mode = request["camera_mode"]
        if mode not in ("original", "approved_rail") or type(mode) is not str:
            raise ValueError("Only original or separately approved director camera")

        rail_identity = None
        if mode == "original":
            if any(request[key] is not None for key in (
                    "rail_id", "rail_revision", "rail_document_sha256")):
                raise PermissionError("Original source camera cannot silently select a rail")
        else:
            _id(request["rail_id"], "approved director rail")
            _sha(request["rail_document_sha256"])
            rail_revision = request["rail_revision"]
            if type(rail_revision) is not int or rail_revision < 1:
                raise PermissionError("Only an exact approved rail revision can render")
            rail_record = self.index.read_revision(
                pid, request["rail_id"], rail_revision)
            if rail_record["document_sha256"] != request["rail_document_sha256"]:
                raise PermissionError("Stale director rail revision identity")
            doc = CanonicalSourceRails(
                self.index, approve=lambda *_: False
            ).verify(pid, request["rail_id"], rail_revision)
            spec = doc["rail_spec"]
            if (spec["take_id"] != request["take_id"] or
                    spec["take_document_sha256"] != take["document_sha256"] or
                    spec["camera_timeline_id"] != request["camera_timeline_id"] or
                    spec["camera_timeline_revision"] != rev or
                    spec["camera_timeline_sha256"] != timeline["document_sha256"] or
                    spec["source_camera_path"] != shot["camera_path"] or
                    not spec["film_start_tick"] <= first < last <= spec["film_end_tick"]):
                raise PermissionError("Approved rail does not cover this exact original shot")
            rail_identity = {
                "rail_id": request["rail_id"],
                "rail_revision": rail_revision,
                "rail_document_sha256": rail_record["document_sha256"],
                "rail_layer_sha256": doc["rail_layer_sha256"],
            }

        scope = {
            "format": FORMAT,
            "project_id": pid,
            "take_id": request["take_id"],
            "take_document_sha256": take["document_sha256"],
            "original_scene_sha256": take["data"]["scene_document_sha256"],
            "original_timeline_sha256": take["data"]["timeline_document_sha256"],
            "camera_timeline_id": request["camera_timeline_id"],
            "camera_timeline_revision": rev,
            "camera_timeline_sha256": timeline["document_sha256"],
            "shot_id": shot["shot_id"],
            "source_camera_path": shot["camera_path"],
            "first_tick": first,
            "last_tick_exclusive": last,
            "camera_mode": mode,
            "approved_rail": rail_identity,
            "original_take_mutated": False,
            "derived_sample_cadence_is_not_source_time": True,
            "renderer_worker_authorized": False,
            "native_os_approval_granted": False,
            "ffmpeg_required": False,
        }
        return {**scope, "selection_sha256": _hash(scope)}

    def sample_at(self, project_id, request, selection_sha256, tick):
        """Recheck before each bounded source sample, without a render launch."""
        if type(tick) is not int:
            raise ValueError("Film Time sample must be an exact integer")
        scope = self.preview(project_id, request)
        if (type(selection_sha256) is not str or
                scope["selection_sha256"] != selection_sha256):
            raise PermissionError("Stale or changed source-selected render preview")
        if not scope["first_tick"] <= tick < scope["last_tick_exclusive"]:
            raise PermissionError("Sample is outside selected original Film Time")
        source = FrozenSceneAV(
            self.index, project_id, request["take_id"],
            expected_take_sha256=scope["take_document_sha256"],
            listener_path=scope["source_camera_path"])
        try:
            snapshot = source.snapshot(tick)
        finally:
            source.close()
        camera_pose = None
        if scope["approved_rail"] is not None:
            record = self.index.read_revision(
                project_id, scope["approved_rail"]["rail_id"],
                scope["approved_rail"]["rail_revision"])
            camera_pose = evaluate_rail(record["data"]["rail_spec"], tick)
        return {
            "format": "nvp.plan02d.source_sample_no_worker.v1",
            "selection_sha256": selection_sha256,
            "source_tick": tick,
            "source_snapshot": snapshot,
            "source_camera_path": scope["source_camera_path"],
            "approved_director_camera_pose": camera_pose,
            "renderer_worker_authorized": False,
            "original_take_mutated": False,
            "ffmpeg_required": False,
        }
