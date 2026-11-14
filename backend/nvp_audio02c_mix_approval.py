"""AUDIO-02C: creator-approved final mix decision, separate from mastering.

The caller must be trusted native UI. Approval binds an exact source asset,
fresh objective QC report, and an immutable FilmIndex audio revision.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from backend.nvp_audio02b_loudness_qc import FORMAT as QC_FORMAT, measure_mix
from backend.nvp_film_index import _id

FORMAT="nvp.audio.final_mix_creator_decision.v1"


def approve_final_mix(capture,project_id,source_audio_id,mix_file,qc,
                      approval_id,creator_event,*,verify_creator_action):
    _id(source_audio_id,"source audio")
    _id(approval_id,"final mix approval identity")
    if not callable(verify_creator_action):
        raise TypeError("Trusted creator-policy callback required")
    source=capture.index.read_revision(project_id,source_audio_id,1)
    if source["kind"]!="audio" or source["data"].get("final_master") is not False:
        raise RuntimeError("Final-mix source must be unapproved technical audio")
    if (type(qc) is not dict or qc.get("format")!=QC_FORMAT or
        qc.get("qc_passed") is not True or
        qc.get("measured_not_normalized") is not True or
        qc.get("director_approved") is not False or
        qc.get("final_master") is not False):
        raise RuntimeError("Actual measured, passing technical QC required")
    path=Path(mix_file)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Final mix WAV missing")
    with path.open("rb") as handle:
        actual=hashlib.file_digest(handle,"sha256").hexdigest()
    if actual!=qc["source_sha256"]:
        raise RuntimeError("Final-mix source changed after QC")
    fresh=measure_mix(path,target_lufs=qc.get("target_lufs",-16.0),
                      ceiling_dbtp=qc.get("true_peak_ceiling_dbtp",-1.0))
    if fresh!=qc:
        raise RuntimeError("Submitted loudness QC does not match fresh measurement")
    try:
        capture.index.read_revision(project_id,approval_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Approval identity already committed")
    scope={"operation":"nvp.native.audio.final_mix_creator_approval",
           "project_id":project_id,"source_audio_id":source_audio_id,
           "source_document_sha256":source["document_sha256"],
           "mix_sha256":actual,
           "qc_sha256":hashlib.sha256(json.dumps(
               qc,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
           "director_approved":True,"final_mix":True,
           "final_master":False}
    if verify_creator_action(creator_event,dict(scope)) is not True:
        raise PermissionError("Creator explicitly refused final mix approval")
    # Recheck immutable evidence after user action, before FilmIndex commit.
    if capture.index.read_revision(project_id,source_audio_id,1)["document_sha256"]!=source["document_sha256"]:
        raise RuntimeError("Underlying audio revision changed during approval")
    with path.open("rb") as handle:
        if hashlib.file_digest(handle,"sha256").hexdigest()!=actual:
            raise RuntimeError("Mix WAV changed during approval")
    indexed=capture.index.put_media_file(project_id,path,"audio/wav")
    if indexed["sha256"]!=actual:
        raise RuntimeError("Immutable indexed mix media changed during ingest")
    document={"format":FORMAT,"status":"creator_approved_final_mix_not_master",
              "source_audio_id":source_audio_id,
              "source_audio_sha256":source["document_sha256"],
              "mix_sha256":actual,"indexed_mix_sha256":indexed["sha256"],"qc":qc,
              "final_mix":True,"director_approved":True,
              "final_master":False,"dcp_delivered":False}
    rec=capture.index.register_revision(project_id,approval_id,"audio",
        document,expected_revision=0,dependencies=[
            {"object_id":source_audio_id,"revision":1,"role":"audio"}])
    return {"status":"CREATOR_APPROVED_FINAL_MIX","approval_id":approval_id,
            "document_sha256":rec["document_sha256"],
            "final_mix":True,"final_master":False}


def verify_final_mix_approval(capture,project_id,approval_id,mix_file):
    record=capture.index.read_revision(project_id,approval_id,1)
    d=record["data"]
    if (record["kind"]!="audio" or d.get("format")!=FORMAT or
        d.get("director_approved") is not True or d.get("final_mix") is not True or
        d.get("final_master") is not False or
        d.get("qc",{}).get("qc_passed") is not True):
        raise RuntimeError("No valid approved technical final mix")
    src=capture.index.read_revision(project_id,d["source_audio_id"],1)
    if (src["document_sha256"]!=d["source_audio_sha256"] or
        record["dependencies"]!=[{"object_id":d["source_audio_id"],
                                 "revision":1,"role":"audio"}]):
        raise RuntimeError("Approved mix source lineage changed")
    path=Path(mix_file)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Approved WAV is missing")
    with path.open("rb") as f:
        digest=hashlib.file_digest(f,"sha256").hexdigest()
    if digest!=d["mix_sha256"] or digest!=d["qc"]["source_sha256"]:
        raise RuntimeError("Approved final mix no longer matches measured source")
    if d.get("indexed_mix_sha256")!=digest:
        raise RuntimeError("Approved mix immutable index identity changed")
    proof=capture.index.verify_media_file(project_id,digest,"audio/wav")
    if proof["sha256"]!=digest:
        raise RuntimeError("Approved final mix indexed media is unavailable")
    return {"status":"VERIFIED_CREATOR_APPROVED_FINAL_MIX",
            "final_mix":True,"final_master":False}
