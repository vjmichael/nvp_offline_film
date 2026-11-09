"""USD-FILM-01Q: immutable data-first director edit into SELECTED view frames.

One frozen original ActorID/Takes/scene is authoritative. Camera viewpoints
are separate revisioned presentation data. An edit selects one camera for
each source frame; no requirement to render unused 720-frame camera rolls.
This module persists creator-approved 30s EDL and produces exact 90 x 8
frame-shot plans for the existing protected native renderer to execute.

Source evaluation still occurs for every source tick; selected-view pixels
are produced later, never faked by this module.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_usd_film01p_source_multicam_film_conform import (
    _validate_edl,FRAMES,FPS)
from backend.nvp_usd_film01r_quality import (reviewed_quality,quality_hash)
from backend.nvp_usd_film01o_original_camera_roll_source import (
    MANIFEST,STAGE,canonical,digest,file_sha)

EDIT_FORMAT="nvp.usd_film01q.selected_view_edit.v1"
RENDER_PLAN_FORMAT="nvp.usd_film01q.source_selected_view_render_plan.v1"
CHUNK_FORMAT="nvp.usd_film01q.selected_view_native_chunk.v1"
CHUNK=8
CHUNKS=FRAMES//CHUNK
MAX_CUTS=96

def edit_sha(data):
    return sha256(canonical(data)).hexdigest()

class OriginalSelectedViewEdit:
    def __init__(self,index:FilmIndex,*,verify_director_action):
        if not isinstance(index,FilmIndex) or not callable(verify_director_action):
            raise TypeError("FilmIndex and host-held director authorization required")
        self.index=index
        self._approve=verify_director_action

    def _build(self,pid,bank_id,bank_revision,cuts,previous=None):
        _require_pid(pid)
        _id(bank_id,"original viewpoint bank")
        if type(bank_revision) is not int or bank_revision<1:
            raise ValueError("Exact viewpoint revision required")
        bank=DirectorCameraBank(
            self.index,verify_director_action=lambda *_:False).verify(
                pid,bank_id,bank_revision)
        if bank["camera_count"]<1:
            raise ValueError("A finished film needs at least one virtual viewpoint")
        source=self.index.read_revision(pid,bank_id,bank_revision)
        take=self.index.read_revision(pid,bank["world_take_id"],1)
        _validate_edl(cuts,[c["camera_id"] for c in bank["cameras"]])
        if bank["source_duration_ticks"]<30*bank["source_ticks_per_second"]:
            raise RuntimeError("Original world Take is shorter than 30s")
        return {
            "format":EDIT_FORMAT,
            "camera_bank_id":bank_id,"camera_bank_revision":bank_revision,
            "camera_bank_sha256":source["document_sha256"],
            "original_world_take_id":bank["world_take_id"],
            "original_world_take_sha256":take["document_sha256"],
            "original_world_sha256":bank["source_world_sha256"],
            "original_performance_sha256":bank["source_performance_sha256"],
            "fps":FPS,"film_frames":FRAMES,
            "cuts":[dict(c) for c in cuts],
            "previous_edit_revision_sha256":previous,
            "selected_viewpoint_ids":list(dict.fromkeys(
                c["camera_id"] for c in cuts)),
            "renders_required_for_final_cut":FRAMES,
            "unused_camera_rolls_not_required":True,
            "original_actor_performance_unchanged":True,
            "original_audio_is_one_shared_source":True,
            "film_rendered":False,
            "director_picture_reviewed":False}

    def _commit(self,pid,edit_id,bank_id,revision,cuts,
                *,expected_revision,previous,action):
        _id(edit_id,"original source film edit")
        doc=self._build(pid,bank_id,revision,cuts,previous)
        scope={
            "operation":"nvp.film01q.publish_selected_view_edit.v1",
            "project_id":pid,"edit_id":edit_id,
            "expected_edit_revision":expected_revision,
            "camera_bank_id":bank_id,"camera_bank_revision":revision,
            "camera_bank_sha256":doc["camera_bank_sha256"],
            "original_performance_sha256":doc["original_performance_sha256"],
            "proposed_edit_sha256":edit_sha(doc),
            "selected_viewpoint_ids":doc["selected_viewpoint_ids"],
            "final_frame_count":FRAMES}
        if self._approve(action,scope) is not True:
            raise PermissionError("A model or browser cannot approve an original film edit")
        return self.index.register_revision(
            pid,edit_id,"edit",doc,
            expected_revision=expected_revision,
            dependencies=[
                {"object_id":bank_id,"revision":revision,"role":"presentation"},
                {"object_id":doc["original_world_take_id"],
                 "revision":1,"role":"source_take"}])

    def create(self,pid,edit_id,*,camera_bank_id,camera_bank_revision,cuts,
               director_event):
        return self._commit(
            pid,edit_id,camera_bank_id,camera_bank_revision,cuts,
            expected_revision=0,previous=None,action=director_event)

    def revise(self,pid,edit_id,*,expected_revision,cuts,director_event,
               camera_bank_revision=None):
        prior=self.verify(pid,edit_id,expected_revision)
        previous=self.index.read_revision(pid,edit_id,expected_revision)
        return self._commit(
            pid,edit_id,prior["camera_bank_id"],
            prior["camera_bank_revision"] if camera_bank_revision is None
            else camera_bank_revision,
            cuts,expected_revision=expected_revision,
            previous=previous["document_sha256"],action=director_event)

    def verify(self,pid,edit_id,revision):
        _require_pid(pid)
        _id(edit_id,"original source film edit")
        if type(revision) is not int or revision<1:
            raise ValueError("Exact immutable edit revision required")
        record=self.index.read_revision(pid,edit_id,revision)
        if record["kind"]!="edit" or record["data"].get("format")!=EDIT_FORMAT:
            raise PermissionError("Source object is not a reviewed director edit")
        old_sha=None
        if revision>1:
            old=self.index.read_revision(pid,edit_id,revision-1)
            if old["kind"]!="edit" or old["data"].get("format")!=EDIT_FORMAT:
                raise RuntimeError("Original edit history changed type")
            if old["data"]["camera_bank_id"]!=record["data"]["camera_bank_id"]:
                raise RuntimeError("Original edit switched source camera bank")
            old_sha=old["document_sha256"]
        doc=record["data"]
        rebuilt=self._build(
            pid,doc["camera_bank_id"],doc["camera_bank_revision"],
            doc["cuts"],old_sha)
        if rebuilt!=doc:
            raise RuntimeError("Frozen original edit and source content mismatch")
        expected_edges={
            ("presentation",doc["camera_bank_id"],doc["camera_bank_revision"]),
            ("source_take",doc["original_world_take_id"],1)}
        actual_edges={(e["role"],e["object_id"],e["revision"])
                      for e in record["dependencies"]}
        if expected_edges!=actual_edges:
            raise RuntimeError("Director edit source dependencies were altered")
        return doc


def selected_render_plan(index,pid,edit_id,revision,
                         *,original_source_directory,
                         render_quality='technical_smoke'):
    """Derive 720 source-authenticated selected view choices from 01O USD.

    No unselected camera is rendered. Unused camera metadata remains
    available in the original world for preview/new edit revisions.
    """
    profile=reviewed_quality(render_quality)
    profile_sha=quality_hash(profile)
    edit=OriginalSelectedViewEdit(
        index,verify_director_action=lambda *_:False).verify(
            pid,edit_id,revision)
    source_dir=Path(original_source_directory)
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise PermissionError("Only pinned on-disk original source animation")
    manifest_file=source_dir/MANIFEST
    usd=source_dir/STAGE
    if (manifest_file.is_symlink() or usd.is_symlink() or
        not manifest_file.is_file() or not usd.is_file()):
        raise RuntimeError("Original USD source is missing or symlinked")
    source=json.loads(manifest_file.read_text("utf8"))
    if (source.get("format")!="nvp.usd_film01o.original_720frame_director_rig_source.v1" or
        source.get("source_camera_bank_sha256")!=edit["camera_bank_sha256"] or
        source.get("original_world_take_sha256")!=edit["original_world_take_sha256"] or
        source.get("original_performance_sha256")!=edit["original_performance_sha256"] or
        source.get("source_usd_sha256")!=file_sha(usd) or
        source.get("source_usd_size_bytes")!=usd.stat().st_size or
        source.get("frame_count")!=FRAMES or source.get("fps")!=FPS or
        len(source.get("original_frame_evidence",[]))!=FRAMES):
        raise PermissionError("Derived source does not match immutable approved edit")
    cameras={c["camera_id"]:c for c in source["cameras"]}
    original_frames=source["original_frame_evidence"]
    if set(edit["selected_viewpoint_ids"])-set(cameras):
        raise RuntimeError("Selected director camera does not exist in original world")
    edit_record=index.read_revision(pid,edit_id,revision)
    frames=[]
    cuts=edit["cuts"]
    cut_index=0
    for number in range(FRAMES):
        while number>=cuts[cut_index]["edit_out_frame"]:
            cut_index+=1
        cut=cuts[cut_index]
        cam=cameras[cut["camera_id"]]
        original=original_frames[number]
        if (original["frame"]!=number or
            original["original_film_tick"]!=number*source[
                "original_ticks_per_second"]//FPS):
            raise RuntimeError("Original Film Time no longer matches source world")
        position=next((p for p in original["original_camera_positions"]
                       if p["camera_id"]==cut["camera_id"]),None)
        if position is None or position["source_prim"]!=cam["source_camera_prim"]:
            raise RuntimeError("Selected camera trajectory not from original actor scene")
        selected={
            "frame":number,
            "original_film_tick":original["original_film_tick"],
            "original_actor_state_sha256":original[
                "original_actor_state_sha256"],
            "camera_id":cam["camera_id"],
            "source_camera_prim":cam["source_camera_prim"],
            "source_camera_position_m":position["position_m"],
            "focal_length_mm":cam["source_focal_length_mm"],
            "camera_ray_exclusions":list(cam["camera_ray_exclusions"]),
            "cut_index":cut_index}
        # A cache key is based on actual source/version, frame,
        # camera/view and quality choices; not merely a mutable shot name.
        selected["view_cache_sha256"]=edit_sha({
            "source_usd_sha256":source["source_usd_sha256"],
            "source_performance_sha256":source["original_performance_sha256"],
            "camera_bank_sha256":source["source_camera_bank_sha256"],
            "original_film_tick":selected["original_film_tick"],
            "original_actor_state_sha256":selected["original_actor_state_sha256"],
            "camera_id":selected["camera_id"],
            "camera_position":position["position_m"],
            "focal_length_mm":selected["focal_length_mm"],
            "primary_ray_exclusions":selected["camera_ray_exclusions"],
            "renderer":"blender_cycles_cpu_v1",
            "quality_profile_sha256":profile_sha})
        frames.append(selected)
    chunks=[]
    for start in range(0,FRAMES,CHUNK):
        subset=frames[start:start+CHUNK]
        chunks.append({
            "start_frame":start,"frame_count":len(subset),
            "camera_ids":list(dict.fromkeys(x["camera_id"] for x in subset)),
            "view_cache_sha256":[x["view_cache_sha256"] for x in subset],
            "source_frames_sha256":edit_sha(subset)})
    body={
        "format":RENDER_PLAN_FORMAT,
        "edit_id":edit_id,"edit_revision":revision,
        "edit_document_sha256":edit_record["document_sha256"],
        "source_bank_sha256":edit["camera_bank_sha256"],
        "original_world_take_sha256":edit["original_world_take_sha256"],
        "original_performance_sha256":edit["original_performance_sha256"],
        "original_usd_sha256":source["source_usd_sha256"],
        "source_manifest_sha256":file_sha(manifest_file),
        "source_film_fps":FPS,"selected_final_frame_count":FRAMES,
        "render_profile":profile,"render_profile_sha256":profile_sha,
        "all_original_camera_rolls_required":False,
        "all_720_selected_frames_original_source_verified":True,
        "frames":frames,"chunks":chunks,
        "cycles_pixels_rendered":False,
        "director_visual_approval":False}
    return {"plan":body,"plan_sha256":edit_sha(body)}
