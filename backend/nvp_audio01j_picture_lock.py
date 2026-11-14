"""AUDIO-01J picture lock: explicit, immutable human approval of verified B14.

A technical picture conform is NOT an approved picture without this decision.
This is trusted host-side policy, never an authority exposed to native workers.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_b14_edited_movie import FORMAT as B14_FORMAT,verify_edited_technical_mov
from backend.nvp_film_index import _id

FORMAT="nvp.audio01j.picture_lock.v1"


def approve_picture(capture,project_id,candidate_id,lock_id,package,conform_dir,
                    movie_dir,*,creator_event,verify_creator_action,
                    ffmpeg="ffmpeg",ffprobe="ffprobe"):
    _id(lock_id,"picture lock ID")
    if not callable(verify_creator_action) or creator_event is None:
        raise PermissionError("Trusted creator event verifier required")
    try: capture.index.read_revision(project_id,lock_id)
    except KeyError: pass
    else: raise RuntimeError("Picture lock identity already used")
    candidate=capture.index.read_revision(project_id,candidate_id,1)
    data=candidate["data"]
    if (candidate["kind"]!="presentation" or data.get("format")!=B14_FORMAT
        or data.get("picture_locked") is not False
        or data.get("audio_included") is not False
        or data.get("approved_final_master") is not False):
        raise RuntimeError("Only original unapproved B14 conform may be locked")
    audit=verify_edited_technical_mov(capture,project_id,candidate_id,
         package,conform_dir,movie_dir,ffmpeg=ffmpeg,ffprobe=ffprobe)
    if audit.get("status")!="VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE":
        raise RuntimeError("No native source-verified B14 technical picture")
    scope={"operation":"nvp.audio01j.approve_picture_lock",
           "project_id":project_id,"candidate_id":candidate_id,
           "candidate_document_sha256":candidate["document_sha256"],
           "picture_sha256":data["movie_sha256"],
           "frames":data["frame_count"],"lock_id":lock_id,
           "final_master":False}
    if verify_creator_action(creator_event,scope) is not True:
        raise PermissionError("Director did not lock this exact picture")
    doc={"format":FORMAT,"status":"creator_locked_picture",
         "source_picture_id":candidate_id,"source_revision":1,
         "source_document_sha256":candidate["document_sha256"],
         "picture_sha256":data["movie_sha256"],"profile":data["profile"],
         "frame_count":data["frame_count"],"fps":24,
         "picture_locked":True,"director_approved":True,
         "audio_included":False,"final_master":False,"dcp_delivered":False}
    result=capture.index.register_revision(
        project_id,lock_id,"presentation",doc,expected_revision=0,
        dependencies=[{"object_id":candidate_id,"revision":1,"role":"presentation"}])
    return {"lock_id":lock_id,"document_sha256":result["document_sha256"],
            "status":"CREATOR_PICTURE_LOCKED","final_master":False}


def validate_picture_lock(capture,project_id,lock_id):
    row=capture.index.read_revision(project_id,lock_id,1)
    data=row["data"]
    if (row["kind"]!="presentation" or data.get("format")!=FORMAT
        or data.get("picture_locked") is not True
        or data.get("director_approved") is not True
        or data.get("final_master") is not False):
        raise PermissionError("No immutable creator-approved picture lock")
    if (row["revision"]!=1 or data.get("status")!="creator_locked_picture"
        or data.get("audio_included") is not False
        or data.get("fps")!=24
        or row["dependencies"]!=[
            {"object_id":data["source_picture_id"],"revision":1,
             "role":"presentation"}]):
        raise RuntimeError("Picture lock revision or dependencies changed")
    original=capture.index.read_revision(
        project_id,data["source_picture_id"],data["source_revision"])
    if (original["document_sha256"]!=data["source_document_sha256"]
        or original["data"].get("format")!=B14_FORMAT
        or original["data"].get("movie_sha256")!=data["picture_sha256"]
        or original["data"].get("frame_count")!=data["frame_count"]
        or original["data"].get("audio_included") is not False):
        raise RuntimeError("Picture lock source provenance changed")
    return row,original
