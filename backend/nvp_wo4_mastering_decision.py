"""WO4-04 immutable derived mastering-decision ledger on frozen FilmIndex Takes.

This produces a new source-bound presentation decision; it does not change
source Takes, scenes, actor recordings or derived candidate bytes. Host must
approve the exact SHA-scoped operation separately from UI/network prompts.
"""
from __future__ import annotations
from backend.nvp_film_index import FilmIndex,_id,_sha
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_wo4_master_qc import FORMAT as QC_FORMAT, evaluate_master_candidates
from backend.nvp_wo4_xyz12_master import FORMAT as PICTURE_FORMAT
from backend.nvp_wo4_pcm_master import FORMAT as SOUND_FORMAT
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from hashlib import sha256
from copy import deepcopy
from backend.nvp_wo3_j2k_audit import PROFILES

FORMAT="nvp.wo4.approved_mastering_decision.v1"


def register_mastering_decision(index:FilmIndex,pid,*,take_id,take_revision,
        take_sha256,picture,sound,qc,decision_id,approve,
        ordered_pictures=None,start_tick=0):
    if not isinstance(index,FilmIndex) or not callable(approve):
        raise PermissionError("Trusted native FilmIndex and approval required")
    _id(take_id,"source Take")
    _id(decision_id,"new mastering presentation")
    _sha(take_sha256)
    if type(take_revision) is not int or take_revision!=1 or decision_id==take_id:
        raise PermissionError("Exact original Take revision and new decision identity required")
    if index.history(pid,decision_id):
        raise FileExistsError("Mastering decision IDs cannot be revised or reused")
    take=index.read_revision(pid,take_id,take_revision)
    if (take["kind"]!="take" or take["document_sha256"]!=take_sha256
            or take["data"].get("frozen") is not True):
        raise PermissionError("Only an exact frozen original Take can be mastered")
    verifier=OpenUSDTakeCapture(index,verify_creator_action=lambda *_:False)
    original=verifier.verify_take(pid,take_id)
    if (original["status"]!="VERIFIED_FROZEN_DATA_TAKE" or
            original["take_document_sha256"]!=take_sha256):
        raise PermissionError("Original Take scene/temporal custody invalid")
    if (any(type(x) is not dict for x in (picture,sound,qc)) or
            picture.get("format")!=PICTURE_FORMAT or
            sound.get("format")!=SOUND_FORMAT or
            qc.get("format")!=QC_FORMAT or
            picture.get("original_take_sha256")!=take_sha256 or
            sound.get("original_take_sha256")!=take_sha256 or
            qc.get("source_take_sha256")!=take_sha256 or
            qc.get("picture_xyz12_sha256")!=picture.get("xyz12_sha256") or
            qc.get("sound_pcm24_sha256")!=sound.get("master_pcm_sha256") or
            qc.get("production_master_accepted") is not False or
            picture.get("production_picture_accepted") is not False or
            sound.get("production_audio_accepted") is not False):
        raise PermissionError("Original approved picture/audio/QC identities disagree")
    count=sound.get("frame_count")
    if type(count) is not int or not 3<=count<=7200:
        raise PermissionError("Bounded ordered cinema frames required")
    if ordered_pictures is None:
        ordered_pictures=[picture]*count
    if (type(ordered_pictures) is not list or len(ordered_pictures)!=count or
            type(start_tick) is not int or start_tick<0 or
            start_tick>2**63-1-count*(TICKS_PER_SECOND//24)):
        raise PermissionError("Ordered native picture Film Time sequence required")
    if (take["data"].get("ticks_per_second")!=TICKS_PER_SECOND or
            type(take["data"].get("duration_tick")) is not int or
            start_tick+count*(TICKS_PER_SECOND//24)>take["data"]["duration_tick"]):
        raise PermissionError("Cinema mastering sequence exceeds frozen Take Film Time")
    # Snapshot immutable byte objects and mutable metadata before consent.
    original_sequence=ordered_pictures
    ordered_pictures=tuple(ordered_pictures)
    picture_before=deepcopy(picture)
    sound_before=deepcopy(sound)
    qc_before=deepcopy(qc)
    frames_before=tuple(deepcopy(frame) for frame in ordered_pictures)
    profile=picture.get("profile")
    if profile not in PROFILES:
        raise PermissionError("Known native 2K/4K cinema profile required")
    width,height,_=PROFILES[profile]
    frame_shas=[]
    for frame in ordered_pictures:
        if (type(frame) is not dict or
                frame.get("format")!=PICTURE_FORMAT or
                frame.get("profile")!=profile or
                frame.get("width")!=width or frame.get("height")!=height or
                frame.get("original_take_sha256")!=take_sha256 or
                frame.get("source_modified") is not False or
                frame.get("production_picture_accepted") is not False or
                type(frame.get("xyz12")) is not bytes or
                len(frame["xyz12"])!=width*height*6 or
                frame.get("xyz12_sha256")!=sha256(frame["xyz12"]).hexdigest()):
            raise PermissionError("Unapproved or mismatched ordered picture frame")
        if any(value & 0xf0 for value in frame["xyz12"][::2]):
            raise PermissionError("Ordered picture contains illegal XYZ12 samples")
        frame_shas.append(frame["xyz12_sha256"])
    if frame_shas[0]!=picture["xyz12_sha256"]:
        raise PermissionError("QC reference must bind sequence first picture")
    measured=evaluate_master_candidates(picture,sound)
    if qc!=measured:
        raise PermissionError("Mastering QC receipt differs from original bytes")
    approved={
        "format":FORMAT,
        "operation":"nvp.wo4.authorize_frozen_take_master_candidate.v1",
        "project_id":pid,"decision_id":decision_id,
        "source_take_id":take_id,"source_take_revision":take_revision,
        "source_take_sha256":take_sha256,
        "picture_sha256":picture["xyz12_sha256"],
        "ordered_picture_sha256":frame_shas,
        "film_start_tick":start_tick,
        "picture_tick_step":TICKS_PER_SECOND//24,
        "sound_sha256":sound["master_pcm_sha256"],
        "picture_profile":picture["profile"],
        "sound_frame_count":sound["frame_count"],
        "channel_order":list(sound["channel_order"]),
        "source_pcm_sha256":sound["source_pcm_sha256"],
        "gain":deepcopy(sound["gain"]),
        "picture_source_sha256":picture.get("source_linear_float32_sha256"),
        "output_white_intent":picture.get("output_white_intent"),
        "source_modified":False,
        "production_master_accepted":False,
    }
    if approve(deepcopy(approved)) is not True:
        return {"format":FORMAT,"status":"DENIED","source_modified":False}
    if (index.read_revision(pid,take_id,take_revision)["document_sha256"]
            !=take_sha256 or
            verifier.verify_take(pid,take_id)["take_document_sha256"]!=take_sha256):
        raise PermissionError("Original Take changed during creator approval")
    if index.history(pid,decision_id):
        raise FileExistsError("Mastering decision was committed during consent")
    if (tuple(original_sequence)!=frames_before or picture!=picture_before or
            sound!=sound_before or qc!=qc_before):
        raise PermissionError("Mastering source changed after approval")
    if evaluate_master_candidates(picture_before,sound_before)!=measured:
        raise PermissionError("Mastering source changed after approval")
    # Register a bounded JSON receipt only. Real XYZ/PCM are derivatives,
    # not source-of-truth film takes or mutable original recording blobs.
    data=dict(approved)
    data["qc_summary"]={
        "xyz12_component_min":measured["xyz12_component_min"],
        "xyz12_component_max":measured["xyz12_component_max"],
        "sound_peak_dbfs":measured["sound_peak_dbfs"],
        "loudness_lufs_measured":measured["sound_loudness_lufs_measured"],
        "integrated_lufs":measured["sound_integrated_lufs"],
        "true_peak_measured":False,
        "calibrated_projector_verified":False,
    }
    def guard(db):
        row=index._read_revision(db,pid,take_id,take_revision)
        if row is None or row["document_sha"]!=take_sha256 or row["kind"]!="take":
            raise PermissionError("Original Take changed before mastering publication")
        # verify_take initialized the journal before consent. Do not open
        # another writer (its constructor performs DDL) inside this lease.
        journal=db.execute("SELECT state FROM nvp_filming_publications WHERE project_id=? AND take_id=?",
                           (pid,take_id)).fetchone()
        if journal is not None and journal["state"]!="COMPLETED":
            raise PermissionError("Original filming publication no longer visible")
    rec=index.register_revision(pid,decision_id,"presentation",data,
        expected_revision=0,precommit_guard=guard,dependencies=[{"object_id":take_id,
                       "revision":take_revision,"role":"source_take"}])
    return {"format":FORMAT,"status":"MASTERING_DECISION_RECORDED",
            "decision_id":decision_id,"receipt_sha256":rec["document_sha256"],
            "source_take_sha256":take_sha256,
            "source_modified":False,"production_master_accepted":False}
