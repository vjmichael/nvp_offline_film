"""CONV-06: Film03 ActorID and CAM-FX03 drafts on the ONE trusted WebView.

This is an IPC-only adapter to the existing project-locked, exact-origin
pywebview bridge. It never mounts FastAPI routes, owns a second native window,
starts Blender, treats local model advice as approval, or modifies source Takes.
"""
from __future__ import annotations

from pathlib import Path
from contextvars import ContextVar
import os

from backend.nvp_cam_fx03_04_desktop_mixin import CameraRailDirectorMixin
from backend.nvp_film_index import _require_pid


_DURABLE_RAIL_PUBLICATION = ContextVar("nvp_conv06_durable_rail_publication", default=False)


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

    def camfx03_draft_publish(self, request):
        """A verified durable camera draft is the only path to publication."""
        self._native_window()
        if _DURABLE_RAIL_PUBLICATION.get():
            raise PermissionError("Nested camera draft publication is prohibited")
        token = _DURABLE_RAIL_PUBLICATION.set(True)
        try:
            return super().camfx03_draft_publish(request)
        finally:
            _DURABLE_RAIL_PUBLICATION.reset(token)

    def camfx02_publish(self, request):
        """Reject direct JS calls, even if they carry valid source SHAs."""
        self._native_window()
        if not _DURABLE_RAIL_PUBLICATION.get():
            raise PermissionError("Direct browser rail publication is forbidden")
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

    def film02md_architecture_catalog(self, project_id):
        """List only independently reopened original architecture sources.

        No arbitrary source path, file picker, creator grant, GPU call or
        private source bytes crosses the browser/native boundary.
        """
        pid = self._wo5_project(project_id)
        from backend.nvp_usd_film02m_modular_buildings import (
            OriginalBuildingKit, BUILD_FORMAT)
        from backend.nvp_usd_film02m_d_cells import (
            OriginalBuildingCells, FORMAT as CELL_FORMAT)
        kit = OriginalBuildingKit(
            self.index, verify_director_action=lambda *_: False)
        cells = OriginalBuildingCells(
            self.index, verify_director_action=lambda *_: False)
        buildings = []
        for row in self.index.list_objects(pid, kind="world")[:64]:
            record = self.index.read_revision(
                pid, row["object_id"], row["head_revision"])
            if record["data"].get("format") != BUILD_FORMAT:
                continue
            with kit.open_building(
                    pid, row["object_id"], row["head_revision"]) as source:
                if (source["record"]["document_sha256"] !=
                        record["document_sha256"]):
                    raise RuntimeError("Original architecture source changed on reopen")
                buildings.append({
                    "building_id": row["object_id"],
                    "revision": row["head_revision"],
                    "document_sha256": record["document_sha256"],
                    "original_mesh_count": source["mesh_count"],
                    "rendered": False,
                })
        published_cells = []
        for row in self.index.list_objects(pid, kind="presentation")[:64]:
            record = self.index.read_revision(
                pid, row["object_id"], row["head_revision"])
            if record["data"].get("format") != CELL_FORMAT:
                continue
            with cells.open(pid, row["object_id"], row["head_revision"]) as source:
                published_cells.append({
                    "cell_world_id": row["object_id"],
                    "revision": row["head_revision"],
                    "document_sha256": record["document_sha256"],
                    "cell_ids": sorted(source.original),
                    "camera_distance_only_prefetch": True,
                    "source_take_binding_verified": False,
                })
        return {
            "format": "nvp.conv06.original_architecture_source_catalog.v1",
            "project_id": pid,
            "buildings": buildings, "cell_worlds": published_cells,
            "native_source_reopened": True,
            "actual_cycles_accepted": False,
            "original_take_or_pcm_modified": False,
        }

    def film02md_publish_cells(self, request):
        """One creator-confirmed, exact original source-only cell manifest.

        Publishing source cells does NOT stage/authorize a private film render
        or bind the cells into any original performance Take.
        """
        self._native_window()
        if type(request) is not dict or set(request) != {
            "project_id", "cell_world_id", "cells", "expected_revision"
        } or type(request["expected_revision"]) is not int:
            raise PermissionError("Exact source building-cell request required")
        pid = self._wo5_project(request["project_id"])
        from backend.nvp_usd_film02m_d_cells import OriginalBuildingCells
        used = False

        def approve(event, scope):
            nonlocal used
            if (used or event != "native_director" or
                scope.get("operation") !=
                    "nvp.film02m.publish_original_building_cells.v1" or
                scope.get("project_id") != pid or
                scope.get("cell_world_id") != request["cell_world_id"] or
                scope.get("expected_revision") != request["expected_revision"]):
                return False
            accepted = self._ask(
                "Publish ONE exact original architectural camera-cell inventory?\n"
                "Project: " + pid +
                "\nWorld: " + scope["cell_world_id"] +
                "\nOriginal cell SHA: " + scope["source_cell_sha256"] +
                "\nImmutable manifest SHA: " +
                scope["source_cell_manifest_sha256"] +
                "\nNative building sources remain original. This does NOT "
                "authorize render, camera/Take edits, project decryption, "
                "original PCM editing or film-master release.")
            # One human click permits at most one exact original publication.
            # The callback cannot be replayed by the original source layer.
            used = accepted is True
            return used
        result = OriginalBuildingCells(
            self.index, verify_director_action=approve).publish(
                pid, request["cell_world_id"],
                cells=request["cells"], expected_revision=request["expected_revision"],
                director_event="native_director")
        return {
            "format": "nvp.conv06.original_architecture_cell_native_receipt.v1",
            "project_id": pid,
            "cell_world_id": request["cell_world_id"],
            "revision": result["revision"],
            "document_sha256": result["document_sha256"],
            "native_director_approved": True,
            "original_take_or_pcm_modified": False,
            "film_master_approved": False,
        }

    def film01c_texture_catalog(self, project_id):
        """Expose only source-verified texture metadata, never PNG bytes/paths."""
        pid = self._wo5_project(project_id)
        from backend.nvp_usd_film01c_texture import source_texture_descriptors
        sources = []
        for kind in ("asset", "scene"):
            for row in self.index.list_objects(pid, kind=kind)[:64]:
                record = self.index.read_revision(
                    pid, row["object_id"], row["head_revision"])
                original = source_texture_descriptors(
                    self.index, pid, kind=kind, record=record)
                if not original:
                    continue
                sources.append({
                    "source_kind": kind,
                    "source_id": row["object_id"],
                    "revision": row["head_revision"],
                    "document_sha256": record["document_sha256"],
                    "png_sha256": sorted(original),
                    "original_png_hashes_verified": True,
                })
                if len(sources) > 64:
                    raise ValueError("Too many verified original film texture sources")
        return {
            "format": "nvp.conv06.original_texture_metadata_catalog.v1",
            "project_id": pid, "sources": sources,
            "original_png_bytes_exposed": False,
            "external_texture_paths_allowed": False,
            "film_master_approved": False,
        }

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
