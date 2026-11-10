"""PLAN-02-D2: durable non-executing source-selected render intentions.

FilmIndex SQLite revisions hold immutable queue transitions. These are NOT
worker-execution tickets. Even an OS-approved selection authorizes neither
Blender/CPU raster, filesystem publication nor process restart. PLAN-02-D3
must separately prove OS supervisor custody and one-use launch consent.
"""
from __future__ import annotations

import threading

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_plan02d_source_selection import ExactSourceWindowSelector

FORMAT = "nvp.plan02d.durable_renderer_intention.v1"
QUEUED = "QUEUED_REQUIRES_NATIVE_REVIEW"
REFUSED = "NATIVE_REVIEW_REFUSED"
APPROVED = "SOURCE_SCOPE_APPROVED_NO_WORKER"
RECOVERY = "RESTART_REQUIRES_FRESH_OS_REVIEW"
TERMINAL = frozenset({REFUSED})
REVIEWABLE = frozenset({QUEUED, RECOVERY})


class DurableRenderIntentionQueue:
    def __init__(self, index: FilmIndex, *, ask_native):
        if not isinstance(index, FilmIndex) or not callable(ask_native):
            raise TypeError("FilmIndex and trusted native review callback are required")
        self.index = index
        self.ask_native = ask_native
        self.selector = ExactSourceWindowSelector(index)
        # Process-lifetime only; journal review is never restart authority.
        self._live_lock = threading.RLock()
        self._live_reviews = set()

    def _read(self, project_id, job_id):
        _require_pid(project_id)
        _id(job_id, "render intention ID")
        row = self.index.read_revision(project_id, job_id)
        data = row["data"]
        if row["kind"] != "edit" or data.get("format") != FORMAT:
            raise PermissionError("Object is not a durable native render intention")
        return row, data

    @staticmethod
    def _document(scope, request, status, *, previous=None):
        return {
            "format": FORMAT,
            "status": status,
            "selection_sha256": scope["selection_sha256"],
            "selection": request,
            "source_take_sha256": scope["take_document_sha256"],
            "camera_timeline_sha256": scope["camera_timeline_sha256"],
            "rail_document_sha256": (
                scope["approved_rail"]["rail_document_sha256"]
                if scope["approved_rail"] is not None else None),
            "previous_transition_sha256": previous,
            "authorizes_renderer_worker": False,
            "authorizes_export": False,
            "allows_unattended_replay": False,
            "ffmpeg_required": False,
            "original_source_mutated": False,
        }

    def enqueue(self, project_id, job_id, request):
        _require_pid(project_id)
        _id(job_id, "new render intention ID")
        scope = self.selector.preview(project_id, request)
        dependencies = [
            {"object_id": request["take_id"], "revision": 1,
             "role": "source_take"},
            {"object_id": request["camera_timeline_id"],
             "revision": request["camera_timeline_revision"], "role": "timeline"},
        ]
        if scope["approved_rail"] is not None:
            dependencies.append({
                "object_id": scope["approved_rail"]["rail_id"],
                "revision": scope["approved_rail"]["rail_revision"],
                "role": "presentation",
            })
        result = self.index.register_revision(
            project_id, job_id, "edit",
            self._document(scope, request, QUEUED),
            expected_revision=0, dependencies=dependencies)
        return self._public(result, QUEUED, scope["selection_sha256"])

    @staticmethod
    def _public(row, status, selection_sha256):
        return {
            "format": FORMAT,
            "job_id": row["object_id"],
            "revision": row["revision"],
            "document_sha256": row["document_sha256"],
            "status": status,
            "selection_sha256": selection_sha256,
            "renderer_worker_authorized": False,
            "export_authorized": False,
            "original_source_mutated": False,
        }

    def inspect(self, project_id, job_id):
        row, data = self._read(project_id, job_id)
        scope = self.selector.preview(project_id, data["selection"])
        if (data["selection_sha256"] != scope["selection_sha256"] or
                data["source_take_sha256"] != scope["take_document_sha256"] or
                data["camera_timeline_sha256"] != scope["camera_timeline_sha256"] or
                data["rail_document_sha256"] != (
                    scope["approved_rail"]["rail_document_sha256"]
                    if scope["approved_rail"] is not None else None) or
                data.get("authorizes_renderer_worker") is not False or
                data.get("authorizes_export") is not False or
                data.get("allows_unattended_replay") is not False):
            raise RuntimeError("Durable render intention no longer binds verified source")
        return self._public(row, data["status"], scope["selection_sha256"])

    def review(self, project_id, job_id, expected_revision):
        """Trusted OS dialog only; the persisted approval is NEVER a launch."""
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("Exact expected queue revision required")
        row, data = self._read(project_id, job_id)
        if row["revision"] != expected_revision or data["status"] not in REVIEWABLE:
            raise PermissionError("Already reviewed, refused or stale render intention")
        scope = self.selector.preview(project_id, data["selection"])
        if scope["selection_sha256"] != data["selection_sha256"]:
            raise RuntimeError("Original source selection changed before OS review")
        consent = self.ask_native({
            "operation": "nvp.plan02d.review_nonexecuting_source_scope.v1",
            "project_id": project_id, "job_id": job_id,
            "expected_revision": expected_revision,
            "source_take_sha256": scope["take_document_sha256"],
            "camera_timeline_sha256": scope["camera_timeline_sha256"],
            "approved_rail": scope["approved_rail"],
            "first_tick": scope["first_tick"],
            "last_tick_exclusive": scope["last_tick_exclusive"],
            "selection_sha256": scope["selection_sha256"],
            "does_not_authorize_worker_or_export": True,
        })
        # Re-evaluate after OS modal; source and rail may have changed.
        after = self.selector.preview(project_id, data["selection"])
        if after != scope:
            raise PermissionError("Original sources changed during native review")
        state = APPROVED if consent is True else REFUSED
        updated = self.index.register_revision(
            project_id, job_id, "edit",
            self._document(after, data["selection"], state,
                           previous=row["document_sha256"]),
            expected_revision=expected_revision,
            dependencies=row["dependencies"])
        if state == APPROVED:
            with self._live_lock:
                self._live_reviews.add((project_id, job_id, updated["revision"],
                                        after["selection_sha256"]))
        return self._public(updated, state, after["selection_sha256"])

    def consume_live_worker_review(self, project_id, job_id, revision,
                                   selection_sha256):
        # Not exposed through pywebview. A new process has no live tokens.
        key = (project_id, job_id, revision, selection_sha256)
        with self._live_lock:
            if key not in self._live_reviews:
                raise PermissionError("OS source review is not live in this NVP host")
            self._live_reviews.remove(key)

    def reconcile_restart(self, project_id, job_id):
        """Never carry OS modal consent through restart as a usable ticket."""
        row, data = self._read(project_id, job_id)
        with self._live_lock:
            self._live_reviews = {key for key in self._live_reviews
                                  if key[0] != project_id or key[1] != job_id}
        if data["status"] != APPROVED:
            return self.inspect(project_id, job_id)
        scope = self.selector.preview(project_id, data["selection"])
        if scope["selection_sha256"] != data["selection_sha256"]:
            raise RuntimeError("Stale durable render source after restart")
        updated = self.index.register_revision(
            project_id, job_id, "edit",
            self._document(scope, data["selection"], RECOVERY,
                           previous=row["document_sha256"]),
            expected_revision=row["revision"],
            dependencies=row["dependencies"])
        return self._public(updated, RECOVERY, scope["selection_sha256"])

    def execute(self, *_args, **_kwargs):
        raise PermissionError(
            "No renderer launch without separately accepted OS process-tree custody")
