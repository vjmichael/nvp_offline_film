"""CONV-06: Film03 ActorID and CAM-FX03 drafts on the ONE trusted WebView.

This is an IPC-only adapter to the existing project-locked, exact-origin
pywebview bridge. It never mounts FastAPI routes, owns a second native window,
starts Blender, treats local model advice as approval, or modifies source Takes.
"""
from __future__ import annotations

from pathlib import Path
import os

from backend.nvp_cam_fx03_04_desktop_mixin import CameraRailDirectorMixin
from backend.nvp_film_index import _require_pid


class ConvergedDirectorDesktopActions(CameraRailDirectorMixin):
    def _wo5_project(self, project_id):
        # The old WO5 methods must not regain their old window/permission broker.
        self._native_window()
        pid = _require_pid(project_id)
        self.index.studio.get_project(pid)
        return pid

    @property
    def _wo5_state(self):
        self._native_window()
        # Installed NVP selects the home before starting pywebview. Never
        # accept a project/browser-selected journal path or a symlink escape.
        home = Path(os.environ["NVP_HOME"]).resolve()
        root = home / ".native-camera-runtime"
        if root.is_symlink():
            raise PermissionError("Native camera state must not be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        if root.resolve() != root:
            raise PermissionError("Native camera state escaped the host home")
        return root

    def camfx03_camera_sources(self, project_id):
        """Give the filmmaker a valid *unapproved* rail starting point.

        Source cameras must already exist in a verified director camera bank.
        This does not mint a bank, a Take, a render or creator authority.
        """
        pid = self._wo5_project(project_id)
        from backend.nvp_temporal_ledger import TICKS_PER_SECOND
        from backend.nvp_usd_film01m_director_camera_bank import (
            DirectorCameraBank, FORMAT as BANK_FORMAT)
        banks = DirectorCameraBank(self.index, verify_director_action=lambda *_: False)
        sources = []
        for row in self.index.list_objects(pid, kind="presentation")[:128]:
            original = self.index.read_revision(
                pid, row["object_id"], row["head_revision"])
            if original["data"].get("format") != BANK_FORMAT:
                continue
            bank = banks.verify(pid, row["object_id"], row["head_revision"])
            end = min(bank["source_duration_ticks"], 5 * TICKS_PER_SECOND)
            if end < 1:
                continue
            for camera in bank["cameras"][:16]:
                origin = list(camera["position_m"])
                node = {
                    "position_m": [0.0, 0.0, 0.0],
                    "target_m": [0.0, 3.0, 0.0],
                    "tangent_in_mps": [0.0, 0.0, 0.0],
                    "tangent_out_mps": [0.0, 0.0, 0.0],
                    "roll_deg": 0.0,
                    "focal_length_mm": float(camera["focal_length_mm"]),
                    "focus_distance_m": float(camera["focus_distance_m"]),
                    "f_stop": 5.6, "segment_mode": "hold",
                    "easing": "linear"
                }
                spec = {
                    "camera_bank_id": row["object_id"],
                    "camera_bank_revision": row["head_revision"],
                    "camera_id": camera["camera_id"],
                    "film_start_tick": 0, "film_end_tick": end,
                    "technique": "static", "rail_origin_m": origin,
                    "filmback_mm": [36.0, 20.25],
                    "nodes": [{**node, "tick": 0}, {**node, "tick": end}]
                }
                sources.append({
                    "camera_bank_id": row["object_id"],
                    "camera_bank_sha256": original["document_sha256"],
                    "source_world_take_sha256": bank["world_take_sha256"],
                    "camera_id": camera["camera_id"],
                    "rail_spec": spec
                })
                if len(sources) >= 48:
                    break
            if len(sources) >= 48:
                break
        return {
            "format": "nvp.conv06.original_camera_bank_sources.v1",
            "project_id": pid, "sources": sources,
            "unapproved_source_only": True,
            "actor_take_pcm_modified": False
        }

    def camfx02_publish(self, request):
        """Called only by the recovered durable-draft publish transaction."""
        if type(request) is not dict or set(request) != {
            "project_id", "rail_id", "rail_spec",
            "expected_revision", "preview_sha256"
        }:
            raise PermissionError("Exact persisted rail publication required")
        pid = self._wo5_project(request["project_id"])
        from backend.nvp_cam_fx01_camera_rails import OriginalCameraRails

        def approve(event, scope):
            if (event != "native_director" or
                scope.get("operation") !=
                    "nvp.cam_fx02.publish_exact_director_camera_rail.v1"):
                return False
            return self._ask(
                "Publish one REVIEWED durable director camera rail?\n"
                "Project: " + scope["project_id"] +
                "\nRail: " + scope["rail_id"] +
                "\nOriginal world Take SHA: " + scope["world_take_sha256"] +
                "\nDirector camera bank SHA: " + scope["camera_bank_sha256"] +
                "\nFilm Time: " + str(scope["film_start_tick"]) +
                " .. " + str(scope["film_end_tick"]) +
                "\nPreview SHA: " + scope["proposed_rail_sha256"] +
                "\nNew USD layer SHA: " + scope["stronger_usd_layer_sha256"] +
                "\nActorID, original PCM and Takes are unchanged. "
                "No Blender, release or film-master authorization.")

        return OriginalCameraRails(
            self.index, verify_director_action=approve
        ).publish(
            pid, request["rail_id"], request["rail_spec"],
            expected_revision=request["expected_revision"],
            preview_sha256=request["preview_sha256"],
            director_event="native_director"
        )

    def film03_actor_catalog(self, project_id):
        pid = self._wo5_project(project_id)
        from backend.nvp_production_bible_actors import ProductionBibleActors
        catalog = ProductionBibleActors(self.index.studio).catalog(pid)
        return {
            "format": "nvp.conv06.story_bible_actorid_catalog.v1",
            "project_id": pid, "actors": catalog["actors"],
            "source_revision_verified": True,
            "voice_or_motion_generated": False
        }

    def film03_actor_profile(self, project_id, actor_id):
        pid = self._wo5_project(project_id)
        from backend.nvp_film03_actor_identity_core import ActorIdentityCore
        core = ActorIdentityCore(
            self.index, verify_creator_action=lambda *_: False)
        result = core.current(pid, actor_id)
        actor = core.bible.get_entity(pid, actor_id)
        return {**result, "bible_revision": actor["revision"],
                "native_director_approval_granted": False}

    def film03_actor_profile_publish(self, request):
        self._native_window()
        if type(request) is not dict or set(request) != {
            "project_id", "actor_id", "profile",
            "expected_profile_revision", "expected_bible_revision",
            "director_note"
        }:
            raise PermissionError("Only typed canonical ActorID identity publication")
        pid = self._wo5_project(request["project_id"])
        from backend.nvp_film03_actor_identity_core import ActorIdentityCore

        def approve(event, scope):
            if (event != "native_director" or
                scope.get("operation") != "film03_publish_actor_identity_profile"):
                return False
            return self._ask(
                "Approve ONE immutable canonical ActorID identity revision?\n"
                "ActorID: " + scope["actor_id"] +
                "\nBible revision: " + str(scope["expected_bible_revision"]) +
                "\nPrior identity revision: " +
                    str(scope["expected_profile_revision"]) +
                "\nTyped profile SHA: " + scope["profile_sha256"] +
                "\nVoiceID: " + str(scope["voice_id"]) +
                "\nVoice cast revision: " + str(scope["voice_cast_revision"]) +
                "\nNo AI voice, model worker, animation, film-master "
                "or distribution authorization.")

        core = ActorIdentityCore(self.index, verify_creator_action=approve)
        published = core.publish(
            pid, request["actor_id"], request["profile"],
            expected_profile_revision=request["expected_profile_revision"],
            expected_bible_revision=request["expected_bible_revision"],
            director_note=request["director_note"],
            creator_event="native_director"
        )
        return {**published, "native_director_identity_approved": True,
                "voice_or_animation_generated": False}
