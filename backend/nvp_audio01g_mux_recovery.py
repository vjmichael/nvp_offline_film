"""AUDIO-01G recovery: never trust a partly written movie.

Only a trusted caller with a genuine OS-owned stop witness may inspect an
interrupted native mux. Incomplete output is quarantined and its ACTIVE memory
reservation stays held pending explicit native cleanup.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from backend.nvp_audio01f_picture_sound import verify_picture_sound_preview
from backend.nvp_audio01g_mux_intent import read, transition


def verify_finished_media(host, job):
    grant=host._grant(job)
    plan_file=host.root/job/"native_plan.json"
    if (plan_file.is_symlink() or not plan_file.is_file() or
        hashlib.sha256(plan_file.read_bytes()).hexdigest()!=grant["plan_sha"]):
        raise RuntimeError("Native mux plan changed")
    p=json.loads(plan_file.read_text("ascii"))
    result=verify_picture_sound_preview(
        host.capture,p["project_id"],p["presentation_id"],
        p["candidate_id"],p["audio_id"],p["package"],p["conform_dir"],
        p["movie_dir"],p["audio_dir"],p["audio_plan"],p["audio_sources"],
        p["audio_chunks"],p["destination"],
        ffmpeg=p["ffmpeg"],ffprobe=p["ffprobe"])
    record=host.capture.index.read_revision(p["project_id"],p["presentation_id"],1)
    receipt_file=host.root/job/"worker_receipt.json"
    if receipt_file.is_symlink() or not receipt_file.is_file():
        raise RuntimeError("Missing durable native mux worker receipt")
    receipt=json.loads(receipt_file.read_text("ascii"))
    if (receipt.get("document_sha256")!=record["document_sha256"] or
        receipt.get("presentation_id")!=p["presentation_id"] or
        receipt.get("samples_per_channel")!=result["samples_per_channel"] or
        receipt.get("final_master") is not False):
        raise RuntimeError("Unverified native worker receipt")
    return record["document_sha256"]


def inspect_stopped_worker(host,job,attest_stopped):
    if not callable(attest_stopped) or attest_stopped(job) is not True:
        raise PermissionError("Native worker tree has not been attested stopped")
    task=host.ledger.get_task(job)
    if task is None or task["state"]!="ACTIVE":
        raise RuntimeError("Cannot recover non-active native mux reservation")
    intent=read(host.ledger,job)
    if intent["state"] not in ("running","quarantined","verified"):
        raise RuntimeError("No interrupted native mux execution")
    try:
        sha=verify_finished_media(host,job)
    except (OSError,KeyError,RuntimeError,ValueError):
        if intent["state"]=="running":
            transition(host.ledger,job,"running","quarantined")
        return {"state":"QUARANTINED_PARTIAL_MUX","released":False}
    if intent["state"] in ("running","quarantined"):
        transition(host.ledger,job,intent["state"],"verified",sha)
    elif intent["result_sha"]!=sha:
        raise RuntimeError("Verified mux SHA has changed")
    return {"state":"VERIFIED_STOPPED_MUX","result_sha":sha,"released":False}


def finalize_verified_worker(host,job,attest_stopped):
    report=inspect_stopped_worker(host,job,attest_stopped)
    if report["state"]!="VERIFIED_STOPPED_MUX":
        raise RuntimeError("Incomplete mux may not be promoted")
    sha=report["result_sha"]
    with host.ledger._db() as db:
        db.execute("BEGIN IMMEDIATE")
        changed=db.execute("""UPDATE native_audio01f_grants SET result_sha=?
            WHERE job_id=? AND (result_sha IS NULL OR result_sha=?)""",
            (sha,job,sha)).rowcount
        if changed!=1:
            db.rollback()
            raise RuntimeError("Conflicting mux result")
        db.commit()
    host.ledger.finish(job,"SUCCEEDED","Verified recovered technical mux")
    transition(host.ledger,job,"verified","committed",sha)
    return {"state":"SUCCEEDED","result_sha":sha,"recovered":True}


def reconcile_post_commit_gap(host,job):
    """Finish journal after successful TaskLedger commit interrupted host.

    This never recreates a finished worker, reuses FilmIndex IDs, or changes
    the original media. Exact result SHA must match all prior durable proofs.
    """
    intent=read(host.ledger,job)
    task=host.ledger.get_task(job)
    grant=host._grant(job)
    if (task is None or task["state"]!="SUCCEEDED" or
        intent["state"] not in ("verified","committed") or
        grant["result_sha"] is None):
        raise RuntimeError("Cannot close unverified or active mux publication")
    if not host._attest_reaped(job):
        raise RuntimeError("Completed mux has no native reaped-worker witness")
    actual=verify_finished_media(host,job)
    if (actual!=grant["result_sha"] or intent["result_sha"]!=actual):
        raise RuntimeError("Finalized mux media or journal SHA disagrees")
    if intent["state"]=="verified":
        transition(host.ledger,job,"verified","committed",actual)
    return {"job_id":job,"state":"COMMITTED_VERIFIED",
            "document_sha256":actual,"rerendered":False}
