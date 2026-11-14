"""SLATE-08: bounded, read-only film camera scene presentation for NVP UI.

Not a director approval service, Blender launcher, Take capture route, or
filesystem explorer. All selections come from the project's immutable
FilmIndex revisions; the only expensive read opens ONE selected native USD
scene for an explicit Film Time snapshot.
"""
from __future__ import annotations

from backend.nvp_camera_workbench import VirtualCameraWorkbench
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_openusd_scene import MAX_USD_EXACT_TICK

MAX_LISTED_SCENES = 64
MAX_SCANNED_SCENES = 256
MAX_CAMERA_CHOICES = 64


class FilmCameraReadBridge:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Trusted FilmIndex required")
        self.index = index
        self.camera = VirtualCameraWorkbench(index)

    def scenes(self, project_id: str):
        """Read only bounded current native scene metadata; never load USD."""
        _require_pid(project_id)
        rows = self.index.list_objects(project_id, kind="scene")
        items = []
        for row in rows[:MAX_SCANNED_SCENES]:
            record = self.index.read_revision(
                project_id, row["object_id"], row["head_revision"])
            data = record["data"]
            if data.get("native_schema_version") is None:
                continue
            roles = data.get("prim_roles")
            if not isinstance(roles, dict):
                raise RuntimeError("Native scene has invalid source prim roles")
            cameras = [{"path":path,"label":path.rsplit("/",1)[-1]}
                for path,role in sorted(roles.items()) if role=="camera"]
            if not cameras:
                continue
            if len(cameras)>MAX_CAMERA_CHOICES:
                raise RuntimeError("Native scene camera choices exceed editor limit")
            if len(items)==MAX_LISTED_SCENES:
                break
            items.append({
                "scene_id":record["object_id"],
                "revision":record["revision"],
                "document_sha256":record["document_sha256"],
                "cameras":cameras,
                "frozen_take_created":False,
            })
        return {
            "format":"nvp.slate08.camera_source_list.v1",
            "project_id":project_id,
            "scenes":items,
            "truncated":len(rows)>MAX_SCANNED_SCENES
                or len(items)==MAX_LISTED_SCENES,
            "usd_loaded":False,
            "worker_started":False,
            "source_scene_modified":False,
        }

    def snapshot(self, project_id: str, scene_id: str, revision: int,
                 *, tick: int, camera_path: str):
        """One exact source scene/tick/camera; no mutation or native worker."""
        _require_pid(project_id)
        _id(scene_id,"camera workbench scene")
        if type(revision) is not int or not 1<=revision<=1_000_000:
            raise ValueError("Select a positive exact scene revision")
        if type(tick) is not int or not 0<=tick<=MAX_USD_EXACT_TICK:
            raise ValueError("Select a bounded integer source Film Time")
        if type(camera_path) is not str or len(camera_path)>240:
            raise ValueError("Select an exact authored camera path")
        source = self.index.read_revision(project_id,scene_id,revision)
        if source["kind"]!="scene" or source["data"].get(
                "prim_roles",{}).get(camera_path)!="camera":
            raise ValueError("Selected camera not authored in this source scene")
        result = self.camera.snapshot(
            project_id,scene_id,revision,tick=tick,
            camera_path=camera_path)
        if (result["scene_document_sha256"]!=source["document_sha256"] or
            result["scene_id"]!=scene_id or
            result["scene_revision"]!=revision or
            result["source_tick"]!=tick or
            result["camera_path"]!=camera_path):
            raise RuntimeError("Source scene changed during camera evaluation")
        return result
