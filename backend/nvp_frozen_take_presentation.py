"""B8 derived technical preview in authoritative NVP FilmIndex.

This publishes only already verified source-bound native Blender results;
it never starts an OS process, grants user consent, or overwrites a DTP.
The immutable original take is a source dependency, and the rendered .blend,
audit JSON and PNG are separately SHA-addressed indexed artifacts.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from backend.nvp_film_index import FilmIndex
from backend.nvp_frozen_take_audit import (
    NativeFrozenTakeAuditor,AUDIT_OUTPUT,PREVIEW_OUTPUT)
from backend.nvp_frozen_take_stage import BLEND,_source
from backend.nvp_production_scene import digest

FORMAT="nvp.presentation.frozen_take_technical_preview.v1"


def _require_completed_review(auditor,approval_id):
    if not isinstance(auditor,NativeFrozenTakeAuditor):
        raise TypeError("Approved native frozen Digital Take auditor required")
    with auditor.ledger._db() as db:
        row=db.execute("""SELECT job_id,operation_json FROM native_frozen_take_audits
            WHERE approval_id=?""",(approval_id,)).fetchone()
    if row is None:
        raise RuntimeError("Native review has not been executed")
    task=auditor.ledger.get_task(auditor.worker._activity_id(row[0]))
    if not task or task["state"]!="SUCCEEDED":
        raise RuntimeError("Native review is not independently verified complete")
    # The replay is idempotent after SUCCEEDED: rechecks both worker/source
    # journals and exact output bytes; it does not launch Blender again.
    from backend.nvp_blender_worker import BlenderOperation
    recorded_operation=BlenderOperation(**json.loads(row[1]))
    outcome=auditor.reopen_and_verify(
        approval_id,ram_mb=recorded_operation.memory_limit_mb)
    if outcome["state"]!="VERIFIED":
        raise RuntimeError("Native technical preview has no verified output")
    return outcome


def publish_verified_preview(auditor:NativeFrozenTakeAuditor,approval_id:str):
    """Publish a new derived presentation revision linked to take:1.

    No B8 technical preview is a fully rendered movie or master.
    """
    proof=_require_completed_review(auditor,approval_id)
    capture=auditor.host.capture
    pid=proof["project_id"]
    tid=proof["take_id"]
    original=capture.reopen(pid,tid)
    if original["record"]["revision"]!=1 or (
        original["record"]["document_sha256"]!=proof["capture_sha256"]):
        raise RuntimeError("Original frozen take fingerprint changed during presentation")
    native_root=auditor.worker.root
    blend=native_root/proof["build_job_id"]/BLEND
    json_path=native_root/proof["audit_job_id"]/AUDIT_OUTPUT
    png=native_root/proof["audit_job_id"]/PREVIEW_OUTPUT
    if (not blend.is_file() or not json_path.is_file() or not png.is_file() or
        any(p.is_symlink() for p in (blend,json_path,png))):
        raise RuntimeError("Previously audited native output no longer safe/available")
    if any(not 0 < p.stat().st_size <= 32*1024*1024 for p in (json_path,png)):
        raise RuntimeError("Technical preview or audit exceeds FilmIndex bounded blob size")
    if (sha256(json_path.read_bytes()).hexdigest()!=proof["audit_json_sha256"] or
        sha256(png.read_bytes()).hexdigest()!=proof["preview_png_sha256"]):
        raise RuntimeError("Original verified audit or PNG bytes were changed")
    index=capture.index
    # Native .blend may exceed FilmIndex's 32-MiB small blob limit: use the
    # existing bounded streaming content-addressed media publication route.
    blend_asset=index.put_media_file(pid,blend,"application/octet-stream")
    if blend_asset["sha256"]!=proof["build_blend_sha256"]:
        raise RuntimeError("Published Blender artifact differs from native audit")
    audit_sha=index.put_blob(pid,json_path.read_bytes(),
                             "application/vnd.nvp.blender.audit+json")
    png_sha=index.put_blob(pid,png.read_bytes(),"image/png")
    if audit_sha!=proof["audit_json_sha256"] or png_sha!=proof["preview_png_sha256"]:
        raise RuntimeError("Published preview assets changed on indexing")

    data={
        "format":FORMAT,
        "production_state":"verified_proxy_technical_preview",
        "project_id":pid,"scene_id":proof["scene_id"],
        "source_take_id":tid,"source_take_revision":1,
        "source_capture_sha256":proof["capture_sha256"],
        "world_sha256":proof["world_sha256"],
        "timed_render_sha256":proof["timed_render_sha256"],
        "approved_script_sha256":proof["script_sha256"],
        "fps":proof["frame_rate"],"timeline_frames":proof["frame_count"],
        "shots":proof["shot_count"],"actors":proof["actor_count"],
        "independently_checked_native_features":
            proof["independently_checked_timeline_features"],
        "build_job_id":proof["build_job_id"],
        "audit_job_id":proof["audit_job_id"],
        "technical_blend_asset_sha256":blend_asset["sha256"],
        "technical_blend_size_bytes":blend_asset["size_bytes"],
        "native_timed_audit_asset_sha256":audit_sha,
        "technical_preview_png_asset_sha256":png_sha,
        "rendered_full_frame_sequence":False,
        "rendered_preview_frame_count":1,
        "genuine_scene_linear_exr_sequence":False,
        "digital_take_modified":False,
    }
    presentation_id="preview_"+digest(data)[:32]
    edges=[{"object_id":tid,"revision":1,"role":"source_take"}]
    try:
        record=index.register_revision(pid,presentation_id,"presentation",
                                       data,dependencies=edges)
    except RuntimeError as exc:
        # A previous identical output publication can be read idempotently.
        previous=index.read_revision(pid,presentation_id)
        if (previous["kind"]!="presentation" or previous["revision"]!=1 or
            previous["data"]!=data or previous["dependencies"]!=edges):
            raise RuntimeError("Technical presentation identity collided") from exc
        record=previous
    # Independently read index *after commit*; all source links must exist.
    verify_presentation(capture,pid,presentation_id)
    return {"format":FORMAT,"presentation_id":presentation_id,
            "project_id":pid,"take_id":tid,
            "presentation_document_sha256":record["document_sha256"],
            "published_original_take_unchanged":True,
            "verified_native_output":True,
            "complete_video":False}


def verify_presentation(capture,project_id,presentation_id):
    """Restart-safe source+derived artifact verification without native execution."""
    if not hasattr(capture,"index") or not isinstance(capture.index,FilmIndex):
        raise TypeError("NVP FilmIndex-backed capture required")
    index=capture.index
    record=index.read_revision(project_id,presentation_id)
    item=record["data"]
    if (record["kind"]!="presentation" or record["revision"]!=1 or
        item.get("format")!=FORMAT or
        item.get("production_state")!="verified_proxy_technical_preview" or
        item.get("project_id")!=project_id or
        record["dependencies"]!=[{"object_id":item["source_take_id"],
                                  "revision":1,"role":"source_take"}] or
        item.get("rendered_full_frame_sequence") is not False or
        item.get("rendered_preview_frame_count")!=1 or
        item.get("genuine_scene_linear_exr_sequence") is not False or
        item.get("digital_take_modified") is not False):
        raise RuntimeError("Derived presentation record or lineage is inconsistent")
    original=capture.reopen(project_id,item["source_take_id"])
    if (original["record"]["document_sha256"]!=item["source_capture_sha256"] or
        item["world_sha256"]!=original["audit"]["world_sha256"] or
        item["scene_id"]!=original["record"]["data"]["scene_id"]):
        raise RuntimeError("Technical preview source no longer matches original frozen take")
    expected=_source(capture,project_id,item["source_take_id"])
    if (expected["timed_render_sha256"]!=item["timed_render_sha256"] or
        expected["script_sha256"]!=item["approved_script_sha256"] or
        expected["frame_count"]!=item["timeline_frames"] or
        expected["frame_rate"]!=item["fps"] or
        expected["shot_count"]!=item["shots"] or
        expected["actor_count"]!=item["actors"]):
        raise RuntimeError("Technical presentation timeline disagrees with indexed take")
    blend=index.verify_media_file(project_id,item["technical_blend_asset_sha256"],
                                  "application/octet-stream")
    if blend["size_bytes"]!=item["technical_blend_size_bytes"]:
        raise RuntimeError("Persisted Blender media length changed")
    audit_raw=index.get_blob(project_id,item["native_timed_audit_asset_sha256"])
    png_raw=index.get_blob(project_id,item["technical_preview_png_asset_sha256"])
    if not png_raw.startswith(bytes.fromhex("89504e470d0a1a0a")):
        raise RuntimeError("Technical presentation PNG not a valid PNG header")
    report=json.loads(audit_raw)
    checks=NativeFrozenTakeAuditor._verify_checks(report,expected)
    if checks!=item["independently_checked_native_features"]:
        raise RuntimeError("FilmIndex technical preview audit check count changed")
    return {"format":FORMAT,"status":"VERIFIED_INDEXED_PREVIEW",
            "project_id":project_id,"presentation_id":presentation_id,
            "source_take_id":item["source_take_id"],
            "source_capture_sha256":item["source_capture_sha256"],
            "blend_sha256":item["technical_blend_asset_sha256"],
            "png_sha256":item["technical_preview_png_asset_sha256"],
            "audit_sha256":item["native_timed_audit_asset_sha256"],
            "timeline_frames":item["timeline_frames"],
            "timeline_checks":checks,
            "complete_video":False}
