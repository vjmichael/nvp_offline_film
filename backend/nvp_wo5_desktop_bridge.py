"""WO5 installed desktop director review IPC; NO HTTP or browser approvals.

This is a pywebview js_api subclass of NVP's existing trusted desktop bridge.
No independent worker, alternate scene viewer or production supervisor is
created. Actual OpenUSD sound/picture audition reuses data_av_* on this bridge.
The finished DCP's independently decoded video+sound playback is NOT yet
implemented by this desktop feature.
"""
from __future__ import annotations

from pathlib import Path
import os

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_wo4_feature_journal import FeatureJournal, ASSEMBLY_FORMAT
from backend.nvp_wo5_original_feature import inspect_original_feature_readiness
from backend.nvp_wo5_director_review import (
    INTENT_FORMAT, REVIEW_FORMAT,
    register_director_intent, record_director_review)

FORMAT = "nvp.wo5.trusted_desktop_director_review.v1"
MAX_CATALOG = 256


class TrustedDesktopWO5Bridge(TrustedDesktopCameraBridge):
    """Use the actual OS-confirmed WebView2 bridge; not FastAPI routes."""

    def __init__(self, index: FilmIndex, *, origin, production_root=None,
                 host_factory=None):
        super().__init__(index, origin=origin, host_factory=host_factory)
        if production_root is None:
            home = Path(os.environ.get("NVP_HOME", str(
                Path(index.studio.db_path).parent)))
            production_root = home / ".native-production-runtime"
        root = Path(production_root)
        if not root.is_absolute() or root.is_symlink():
            raise PermissionError("Host-owned native production state root required")
        self._wo5_state = root.resolve()
        self._wo5_journal = None

    def _wo5_project(self, project_id):
        self._native_window()  # exact current first-party pywebview origin
        _require_pid(project_id)
        self.index.studio.get_project(project_id)
        return project_id

    def _wo5_journal_for_review(self):
        self._native_window()
        if self._wo5_journal is None:
            # Identical durable FeatureJournal backing store used by
            # NativeProductionHost, never an alternate job/supervisor.
            self._wo5_journal = FeatureJournal(self._wo5_state)
        return self._wo5_journal

    def _wo5_approve(self, scope):
        """Native OS confirmation, over the EXACT source-hashed operation."""
        if type(scope) is not dict:
            return False
        allowed = {
            "nvp.wo5.creator_confirm_director_intent.v1",
            "nvp.wo5.creator_confirm_film_observations.v1",
        }
        if scope.get("operation") not in allowed:
            return False
        message = (
            "Director-only immutable film review record.\n"
            "Operation: " + scope["operation"] + "\n"
            "Film project: " + str(scope.get("project_id", "")) + "\n"
            "Original FilmIndex source SHA: " +
                str(scope.get("assembly_sha256") or
                    scope.get("feature_filmindex_sha256") or "") + "\n"
            "Review/intent SHA: " + str(scope.get("intent_shots_sha256") or
                                      scope.get("observations_sha256") or "") +
            "\nNo worker, exported film or original Take will be modified.\n"
            "Your report is NOT theatrical certification or AI approval.\n"
            "Approve this exact operation?")
        return self._native_window().create_confirmation_dialog(
            "NVP — Approve Director Review", message) is True

    def wo5_review_catalog(self, project_id):
        """Return safe, project-bound durable feature/edit/intent/review metadata."""
        self._wo5_project(project_id)
        index = self.index
        assemblies, intents, reviews = [], [], []
        for kind in ("edit", "presentation"):
            for entry in index.list_objects(project_id, kind=kind)[:MAX_CATALOG]:
                object_id = entry["object_id"]
                revision = entry["head_revision"]
                record = index.read_revision(project_id, object_id, revision)
                data = record["data"]
                fmt = data.get("format")
                if fmt == ASSEMBLY_FORMAT:
                    assemblies.append({
                        "assembly_id": object_id,
                        "assembly_revision": revision,
                        "assembly_sha256": record["document_sha256"],
                        "end_tick": data.get("end_tick"),
                        "reel_count": len(data.get("ordered_reel_job_ids", [])),
                    })
                elif fmt == INTENT_FORMAT:
                    intents.append({
                        "intent_id": object_id,
                        "source_assembly_id": data["source_assembly_id"],
                        "source_assembly_revision": data["source_assembly_revision"],
                        "source_assembly_sha256": data["source_assembly_sha256"],
                        "shot_count": len(data["shots"]),
                        "intent_sha256": record["document_sha256"],
                    })
                elif fmt == REVIEW_FORMAT:
                    reviews.append({
                        "review_id": object_id,
                        "source_director_intent_id": data["source_director_intent_id"],
                        "original_feature_id": data["original_feature_id"],
                        "director_requests_revisions": data["director_requests_revisions"],
                        "production_acceptance": False,
                    })
        journal = self._wo5_journal_for_review()
        with journal._read() as db:
            entries = [dict(row) for row in db.execute(
                """SELECT feature_id,assembly_id,assembly_revision,
                   assembly_sha256,project_id,state,updated_at FROM
                   production_features WHERE project_id=?
                   ORDER BY created_at DESC LIMIT ?""",
                (project_id, MAX_CATALOG))]
        features = [{
            "feature_id": r["feature_id"],
            "assembly_id": r["assembly_id"],
            "assembly_revision": r["assembly_revision"],
            "assembly_sha256": r["assembly_sha256"],
            "state": r["state"],
            "updated_at": r["updated_at"],
            "production_accepted": False,
        } for r in entries]
        return {
            "format": FORMAT, "status": "NATIVE_PROJECT_SCOPED_READ_ONLY",
            "project_id": project_id, "assemblies": assemblies,
            "features": features, "director_intents": intents,
            "director_reviews": reviews,
            "native_source_preview_available": True,
            "full_finished_dcp_playback_verified": False,
            "smpte_bv21_validated": False,
            "production_accepted": False,
            "host_native_only": True, "source_paths_exposed": False,
        }

    def wo5_review_read_intent(self, project_id, intent_id):
        self._wo5_project(project_id)
        _id(intent_id, "director intent")
        record = self.index.read_revision(project_id, intent_id, 1)
        if record["kind"] != "presentation" or (
                record["data"].get("format") != INTENT_FORMAT):
            raise PermissionError("Only the exact frozen creator intent may be read")
        return {"format": INTENT_FORMAT, "intent_id": intent_id,
                "intent_sha256": record["document_sha256"],
                "data": record["data"], "source_paths_exposed": False}

    def wo5_review_save_intent(self, payload):
        self._native_window()
        required = {"project_id", "assembly_id", "assembly_revision",
                    "intent_id", "shots"}
        if type(payload) is not dict or set(payload) != required:
            raise PermissionError("Exactly scoped creator intent request required")
        self._wo5_project(payload["project_id"])
        return register_director_intent(
            self.index, payload["project_id"],
            assembly_id=payload["assembly_id"],
            assembly_revision=payload["assembly_revision"],
            intent_id=payload["intent_id"], shots=payload["shots"],
            approve=self._wo5_approve)

    def wo5_review_inspect_feature(self, project_id, feature_id):
        """A real, possibly slow native hash audit. Never mark film passed."""
        self._wo5_project(project_id)
        return inspect_original_feature_readiness(
            self.index, self._wo5_journal_for_review(),
            project_id, feature_id)

    def wo5_review_save_observations(self, payload):
        self._native_window()
        required = {"project_id", "feature_id", "intent_id", "review_id",
                    "observations", "watched_entire_film",
                    "heard_entire_sound"}
        if type(payload) is not dict or set(payload) != required:
            raise PermissionError("Exactly scoped native film review request required")
        self._wo5_project(payload["project_id"])
        return record_director_review(
            self.index, self._wo5_journal_for_review(),
            payload["project_id"], feature_id=payload["feature_id"],
            intent_id=payload["intent_id"], review_id=payload["review_id"],
            observations=payload["observations"],
            watched_entire_film=payload["watched_entire_film"],
            heard_entire_sound=payload["heard_entire_sound"],
            approve=self._wo5_approve)
