"""WO5 review actions on the existing exact-origin desktop bridge, never a second bridge."""
from __future__ import annotations

from pathlib import Path
import os
import json
import sys
from copy import deepcopy
from hashlib import sha256

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_wo4_feature_journal import FeatureJournal, ASSEMBLY_FORMAT
from backend.nvp_wo5_original_feature import inspect_indexed_feature
from backend.nvp_wo5_director_review import (
    INTENT_FORMAT, REVIEW_FORMAT,
    register_director_intent, record_director_review)

FORMAT = "nvp.wo5.trusted_desktop_director_review.v1"
MAX_CATALOG = 256


class FinishedReviewActions:
    """Only the original host owns origin, project locks, lifetime and approvals."""

    def _wo5_configure_review(self, *, production_root=None, bundle_root=None):
        # Host-only setter; the narrow WebView surface never exposes this.
        self._wo5_production_root = Path(production_root) if production_root is not None else None
        self._wo5_review_bundle = Path(bundle_root) if bundle_root is not None else None
        self._wo5_review_journal = None
        self._wo5_player = None
        self._wo5_pending_review_grant = None

    def _wo5_journal_for_review(self):
        self._native_window()
        from backend.nvp_wo4_pcm_stream import _protected_path
        root = self._wo5_production_root
        if root is None:
            raise PermissionError("No native cinema production journal is admitted")
        _protected_path(root, directory=True)
        _protected_path(root / "production-journal.sqlite3")
        if self._wo5_review_journal is None:
            self._wo5_review_journal = FeatureJournal(root)
        return self._wo5_review_journal

    def _wo5_existing_journal(self):
        root = self._wo5_production_root
        if root is None or not (root / "production-journal.sqlite3").exists():
            return None
        return self._wo5_journal_for_review()

    def _wo5_revoked(self):
        try:
            self._native_window()
            return False
        except PermissionError:
            return True

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
        approved = self._native_window().create_confirmation_dialog(
            "NVP — Approve Director Review", message) is True
        self._wo5_project(scope["project_id"])
        return approved

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
        journal = self._wo5_existing_journal()
        entries = []
        if journal is not None:
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
            "cinema_journal_available": journal is not None,
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
        return inspect_indexed_feature(
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


    def _wo5_distribution(self):
        """Read independently build-pinned, static Program Files codec roster."""
        from backend._nvp_wo5_release_pin import RELEASE_CODEC_MANIFEST_SHA256 as pin
        from backend.nvp_wo3_dcp_structure import _linked_entry
        from backend.nvp_wo3_codec_bundle_provenance import verify_native_codec_bundle
        if (os.name != "nt" or not getattr(sys, "frozen", False) or not pin or
                self._wo5_review_bundle is None):
            return None
        root = self._wo5_review_bundle
        file = root / "nvp-codec-manifest.json"
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"SOFTWARE\Microsoft\Windows\CurrentVersion") as key:
            program=Path(winreg.QueryValueEx(key,"ProgramFilesDir")[0]).resolve(strict=True)
        if (root != program/"NVP"/"native-codecs" or not root.is_absolute() or
                any(_linked_entry(p) for p in (file,*file.parents)) or
                not file.is_file() or not 1 <= file.stat().st_size <= 128*1024):
            return None
        raw = file.read_bytes()
        if sha256(raw).hexdigest() != pin:
            return None
        manifest = json.loads(raw)
        canonical = json.dumps(manifest,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")
        if raw != canonical:
            return None
        verify_native_codec_bundle(root,manifest)
        allowed={"nvp-codec-manifest.json"}
        for item in manifest["tools"].values():
            allowed.update((item["filename"],item["license_notice"]))
        if {p.name for p in root.iterdir()} != allowed or any(_linked_entry(p) or not p.is_file() for p in root.iterdir()):
            return None
        return root,manifest,pin

    def wo5_film_capabilities(self):
        self._native_window()
        available = self._wo5_existing_journal() is not None and self._wo5_distribution() is not None
        return {"format":"nvp.wo5.finished_dcp_pcm24_picture_review.v1",
                "native_finished_mxf_decode_configured":available,
                "actual_sustained_24fps_verified":False,"production_accepted":False}

    def _wo5_factory(self, project_id, cancel):
        from backend.nvp_wo3_native_codecs import ProtectedCodecAuthority
        from backend.nvp_wo5_codec_binding import pinned_codec_pair
        from backend.nvp_wo4_pcm_stream import _protected_path
        from backend.nvp_w1g_encrypted_source import require_efs_stage
        self._wo5_project(project_id)
        distribution=self._wo5_distribution()
        if distribution is None:
            raise PermissionError("Verified installed cinema viewer not available")
        root,manifest,pin=distribution
        journal=self._wo5_journal_for_review()
        runtime=journal.root/".finished-review-codecs"
        runtime.mkdir(mode=0o700,exist_ok=True)
        require_efs_stage(runtime)
        _protected_path(runtime,directory=True)
        grant={"project":project_id,"cancel":cancel,"pin":pin,"scope":None}
        self._wo5_pending_review_grant=grant
        def permitted(scope):
            # Native stage/execute still independently verify finite commands and
            # all sealed media bytes. One human-approved session can issue only
            # read-only, exact-reel operations while its window is live.
            approved=grant["scope"]
            return (approved is not None and not cancel() and not self._wo5_revoked()
                    and scope.get("project_id")==project_id
                    and scope.get("codec_manifest_sha256")==pin
                    and scope.get("source_sha256") in approved["ordered_reel_receipts"]
                    and type(scope.get("playback_inputs")) is dict
                    and scope.get("operation") in ("nvp.wo3.protected_stage.v1",
                        "nvp.wo3.native_codec.execute.v1")
                    and (scope.get("operation")!="nvp.wo3.native_codec.execute.v1"
                         or scope.get("product") in ("ASDCP-asdcp_unwrap","OpenJPEG-opj_decompress")))
        authority=ProtectedCodecAuthority(root,manifest,manifest_sha256=pin,
                    runtime=runtime,project_id=project_id,authorize_stage=permitted,
                    authorize_execution=permitted,check_cancel=cancel)
        return pinned_codec_pair(root,manifest,pin,authority=authority,
                                 project_id=project_id,check_cancel=cancel)

    def _wo5_confirm_finished_viewing(self,scope):
        self._wo5_project(scope["project_id"])
        grant=self._wo5_pending_review_grant
        if (scope.get("operation")!="nvp.wo5.approve_readonly_finished_mxf_playback.v1"
                or grant is None or grant["scope"] is not None or grant["cancel"]()
                or scope["project_id"]!=grant["project"]
                or scope["codec_manifest_sha256"]!=grant["pin"]):
            return False
        approved=self._native_window().create_confirmation_dialog(
            "NVP — Review finished film",
            "Watch the exact published film and listen to its sound?\n"
            "Film: "+scope["feature_id"]+"\nFilm receipt: "+scope["filmindex_sha256"]+
            "\nThe original movie will not change. Screen and stereo preview are not cinema certification.") is True
        self._wo5_project(scope["project_id"])
        if approved and not grant["cancel"]():
            grant["scope"]=deepcopy(scope)
            return True
        return False

    def _wo5_finished(self):
        self._native_window()
        with self._lock:
            if self._wo5_player is None:
                from backend.nvp_wo5_finished_playback import FinishedFilmPlayer
                self._wo5_player=FinishedFilmPlayer(self.index,self._wo5_journal_for_review(),
                    codec_factory=self._wo5_factory,native_window=self._native_window,
                    ask_native=self._wo5_confirm_finished_viewing,host_revoked=self._wo5_revoked)
            return self._wo5_player

    def wo5_film_begin(self,project_id,feature_id,single_reel=False):
        self._wo5_project(project_id)
        return self._wo5_finished().begin(project_id,feature_id,single_reel=single_reel)

    def wo5_film_frame(self,session_id,frame_index):
        return self._wo5_finished().frame(session_id,frame_index)

    def wo5_film_window(self,session_id,first_frame,count=4):
        return self._wo5_finished().window(session_id,first_frame,count)

    def wo5_film_stop(self,session_id):
        return self._wo5_finished().stop(session_id)

    def _wo5_close_review(self):
        try:
            if self._wo5_player is not None:
                self._wo5_player.close()
        finally:
            self._wo5_pending_review_grant=None
