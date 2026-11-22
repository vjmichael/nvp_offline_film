"""CONV-12: protected, independently reopened 720-frame USD source cache.

No full-camera roll renderer or bypass of the current encrypted-source policy.
Any persisted derived original source requires actual Windows EFS; on systems
without approved encrypted storage, original camera source rendering fails closed.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from backend.nvp_w1g_encrypted_source import verify_efs_inputs

from backend.nvp_blender_worker import BlenderWorkerSupervisor
from backend.nvp_film_index import FilmIndex
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_usd_film01o_original_camera_roll_source import (
    original_camera_roll_source,STAGE,MANIFEST,FORMAT as SOURCE_FORMAT,
    canonical,file_sha)

FRAMES=720


class ProtectedOriginalSelectedSource:
    def __init__(self,index:FilmIndex,supervisor:BlenderWorkerSupervisor):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor)):
            raise TypeError("Original FilmIndex, contained supervisor and host approvals required")
        self.index=index
        self.supervisor=supervisor

    def _bank(self,pid,bank_id,revision):
        bank=DirectorCameraBank(
            self.index,verify_director_action=lambda *_:False)
        doc=bank.verify(pid,bank_id,revision)
        if not 1<=doc["camera_count"]<=96 or doc["source_duration_ticks"]<30*7056000000:
            raise ValueError("Only full 30s original director camera performance admitted")
        record=self.index.read_revision(pid,bank_id,revision)
        return doc,record

    def source(self,pid,bank_id,revision):
        """Build once, then revalidate pinned source identities on restart."""
        doc,record=self._bank(pid,bank_id,revision)
        directory=self.supervisor.root/("filmQ_protected_source_"+record[
            "document_sha256"][:24])
        if not directory.exists():
            original_camera_roll_source(self.index,pid,bank_id,
                revision=revision,folder=directory,
                protected_source=True)
        if directory.is_symlink():
            raise PermissionError("Original render source was replaced by symlink")
        verify_efs_inputs(directory,names=(MANIFEST,STAGE))
        manifest=directory/MANIFEST
        stage=directory/STAGE
        if (manifest.is_symlink() or stage.is_symlink() or
            not manifest.is_file() or not stage.is_file()):
            raise RuntimeError("Restart found missing original camera source bundle")
        src=json.loads(manifest.read_text("utf8"))
        take=self.index.read_revision(pid,doc["world_take_id"],1)
        if (src.get("format")!=SOURCE_FORMAT or
            src.get("source_camera_bank_sha256")!=record["document_sha256"] or
            src.get("original_world_take_sha256")!=take["document_sha256"] or
            src.get("original_world_sha256")!=doc["source_world_sha256"] or
            src.get("original_performance_sha256")!=doc["source_performance_sha256"] or
            src.get("source_usd_sha256")!=file_sha(stage) or
            src.get("source_usd_size_bytes")!=stage.stat().st_size or
            src.get("frame_count")!=FRAMES or
            type(src.get("original_frame_evidence")) is not list or
            len(src["original_frame_evidence"])!=FRAMES or
            [x["camera_id"] for x in src["cameras"]]!=[
                c["camera_id"] for c in doc["cameras"]]):
            raise RuntimeError("Saved camera-roll source no longer matches authoritative FilmIndex")
        # Do not trust a self-consistent sidecar to replace the actual source
        # motion: independently evaluate checkpoint actor poses from
        # reopened immutable FilmIndex scene, not the derived file's claims.
        from pxr import Usd,UsdGeom
        from backend.nvp_usd_film01_world import OpenUSDWorldComposer
        original=take["data"]
        with OpenUSDWorldComposer(self.index).open(
                pid,original["world_id"],original["world_revision"]) as world:
            world.load([original["original_scene_takes"][0]["set"]])
            for frame in (0,239,240,479,480,719):
                evidence=src["original_frame_evidence"][frame]
                if (evidence["frame"]!=frame or
                    evidence["original_film_tick"]!=frame*7056000000//24):
                    raise RuntimeError("Original source frame clock changed on restart")
                actors={x["actor_id"]:x for x in evidence["original_actor_positions"]}
                for actor in original["canonical_original_actors"]:
                    original_prim=world.stage.GetPrimAtPath(
                        actor["composed_actor_prim"])
                    xyz=UsdGeom.Xformable(
                        original_prim).ComputeLocalToWorldTransform(
                            Usd.TimeCode(float(evidence["original_film_tick"]))
                        ).ExtractTranslation()
                    expected=actors[actor["actor_id"]]["position_m"]
                    if any(abs(float(xyz[i])-expected[i])>1e-6 for i in range(3)):
                        raise RuntimeError("Saved camera-roll performer no longer matches original USD")
        return directory,src

