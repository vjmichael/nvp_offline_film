"""NVP B9 publish only a FULL verified float32 EXR image sequence.

Each EXR is content-addressed on disk, the complete frame manifest is one
immutable FilmIndex presentation derived from the ORIGINAL frozen take.
An incomplete/missing/duplicated frame or a fake pixel-readback refuses
publication. No movie, graded master or ACES compliance is implied.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

from backend.nvp_exr_fidelity import inspect_exr_header
from backend.nvp_exr_sequence import NativeEXRSequence,FORMAT,PLAN_FILE,AUDIT_JSON
from backend.nvp_frozen_take_stage import _source
from backend.nvp_production_scene import digest


PRESENTATION="nvp.presentation.scene_linear_float32_exr_sequence.v1"


def publish_exr_sequence(host:NativeEXRSequence,sequence_id:str):
    if not isinstance(host,NativeEXRSequence):
        raise TypeError("Trusted NVP EXR native renderer required")
    seq=host._row(sequence_id)
    if seq["revoked_at"] is not None or time.time()>seq["expires_at"]:
        raise PermissionError("Native full-sequence publication consent no longer valid")
    source,_=host._verify_source(seq)
    expected=list(host._plans(seq,source))
    # Never silently publish partial take output, a Blender still or a
    # converted 8-bit proxy under a full sequence label.
    rows=[]
    audit_assets=[]
    index=host.capture.index
    for start,stop,plan in expected:
        chunk=host._chunk(sequence_id,start)
        if chunk is None or chunk["stop"]!=stop:
            raise RuntimeError("EXR take sequence has an unrendered frame chunk")
        evidence=host.verify_or_audit_batch(sequence_id,start)
        if evidence["state"]!="VERIFIED":
            raise RuntimeError("Independent native EXR image readback incomplete")
        job=host.worker.verify_completed(chunk["job_id"])
        audit_op=host._chunk(sequence_id,start)["audit_op"]
        review=host.worker.verify_completed(audit_op.job_id)
        audit_path=host.worker.root/audit_op.job_id/AUDIT_JSON
        raw=audit_path.read_bytes()
        audit_sha=index.put_blob(seq["project_id"],raw,"application/vnd.nvp.blender.audit+json")
        if audit_sha!=review["outputs"][AUDIT_JSON]["sha256"]:
            raise RuntimeError("Indexed EXR audit differs from independent native source")
        audit_assets.append({"start_frame":start,"stop_frame":stop,
                             "native_audit_sha256":audit_sha,
                             "checked_frames":len(plan["frames"]),
                             "render_job_id":chunk["job_id"],
                             "audit_job_id":audit_op.job_id})
        for row in plan["frames"]:
            frame=row["frame"]
            path=host.worker.root/chunk["job_id"]/row["file"]
            detail=inspect_exr_header(path,width=seq["width"],height=seq["height"])
            if detail["rgba_float32"] is not True:
                raise RuntimeError("Only real RGBA FLOAT32 can enter professional EXR archive")
            stored=index.put_media_file(seq["project_id"],path,media_type="image/x-exr",
                                        max_bytes=512*1024*1024)
            if stored["sha256"]!=job["outputs"][row["file"]]["sha256"]:
                raise RuntimeError("EXR frame index byte stream differs from native worker")
            rows.append({"frame":frame,"sha256":stored["sha256"],
                         "bytes":stored["size_bytes"]})
    if ([x["frame"] for x in rows]!=list(range(1,seq["frame_count"]+1)) or
        len(audit_assets)!=(seq["frame_count"]+seq["chunk_size"]-1)//seq["chunk_size"]):
        raise RuntimeError("Native EXR timeline has missing or duplicate frames")
    data={
        "format":PRESENTATION,
        "state":"native_float32_exr_sequence_verified",
        "project_id":seq["project_id"],
        "source_take_id":seq["take_id"],"source_take_revision":1,
        "source_take_sha256":seq["capture_sha256"],
        "source_preview_id":seq["preview_id"],
        "source_preview_sha256":seq["preview_sha256"],
        "source_blend_sha256":seq["blend_sha256"],
        "fps":seq["fps"],"frame_count":seq["frame_count"],
        "resolution":[seq["width"],seq["height"]],
        "sample_type":"IEEE_754_FLOAT32",
        "channels":["R","G","B","A"],"exr_compression":"ZIP",
        "render_engine":"BLENDER_WORKBENCH",
        "view_transform":"Raw",
        "writer_color_pipeline":"Blender scene-linear Raw output",
        "ocio_config_identity_verified":False,
        "aces_compliance_verified":False,
        "blender_version":host.worker.blender_version,
        "blender_executable_sha256":host.worker.binary_sha256,
        "frames":rows,
        "audited_chunks":audit_assets,
        "frames_in_memory_between_jobs":0,
        "original_digital_take_modified":False,
        "video_container_mastered":False,
        "sound_mix_delivered":False,
    }
    ident="exrseq_"+digest(data)[:32]
    deps=[{"object_id":seq["take_id"],"revision":1,"role":"source_take"}]
    try:
        revision=index.register_revision(seq["project_id"],ident,"presentation",
                                        data,dependencies=deps)
    except RuntimeError as exc:
        old=index.read_revision(seq["project_id"],ident)
        if (old["kind"]!="presentation" or old["revision"]!=1 or
            old["data"]!=data or old["dependencies"]!=deps):
            raise RuntimeError("EXR presentation identity collides with existing film") from exc
        revision=old
    result=verify_indexed_exr_sequence(host.capture,seq["project_id"],ident)
    return {**result,"presentation_document_sha256":revision["document_sha256"]}


def verify_indexed_exr_sequence(capture,project_id,presentation_id):
    """Restart-safe full frame-by-frame FilmIndex and OpenEXR proof."""
    index=capture.index
    doc=index.read_revision(project_id,presentation_id)
    data=doc["data"]
    if (doc["kind"]!="presentation" or doc["revision"]!=1 or
        data.get("format")!=PRESENTATION or
        data.get("project_id")!=project_id or
        data.get("state")!="native_float32_exr_sequence_verified" or
        doc["dependencies"]!=[{"object_id":data.get("source_take_id"),
                               "revision":1,"role":"source_take"}] or
        data.get("sample_type")!="IEEE_754_FLOAT32" or
        data.get("view_transform")!="Raw" or
        data.get("aces_compliance_verified") is not False or
        data.get("ocio_config_identity_verified") is not False or
        data.get("original_digital_take_modified") is not False or
        data.get("video_container_mastered") is not False):
        raise RuntimeError("EXR presentation source, type or honesty flags differ")
    frozen=_source(capture,project_id,data["source_take_id"])
    if (frozen["capture_sha256"]!=data["source_take_sha256"] or
        frozen["frame_count"]!=data["frame_count"] or
        frozen["frame_rate"]!=data["fps"]):
        raise RuntimeError("Original frozen take no longer matches indexed frame range")
    preview=index.read_revision(project_id,data["source_preview_id"])
    if preview["document_sha256"]!=data["source_preview_sha256"]:
        raise RuntimeError("EXR source native Blender preview identity changed")
    width,height=data["resolution"]
    frames=data["frames"]
    if (type(frames) is not list or len(frames)!=data["frame_count"] or
        [r["frame"] for r in frames]!=list(range(1,data["frame_count"]+1)) or
        data.get("channels")!=["R","G","B","A"]):
        raise RuntimeError("EXR sequence frame list is missing, duplicated or noncontiguous")
    for f in frames:
        media=index.verify_media_file(project_id,f["sha256"],"image/x-exr")
        if media["size_bytes"]!=f["bytes"]:
            raise RuntimeError("Indexed EXR frame size disagrees with original worker")
        inspect_exr_header(Path(media["path"]),width=width,height=height)
    audits=data["audited_chunks"]
    if type(audits) is not list or not audits:
        raise RuntimeError("EXR sequence is missing independent pixel-audit receipts")
    checked=[]
    for row in audits:
        audit=json.loads(index.get_blob(project_id,row["native_audit_sha256"]))
        if (audit.get("format")!="nvp.exr.native_float_readback.v1" or
            audit.get("passed") is not True or audit.get("required_channel_depth")!=32 or
            audit.get("linear_write_transform")!="Raw" or
            len(audit.get("frames",[]))!=row["checked_frames"] or
            len(audit.get("checks",[]))!=4*row["checked_frames"] or
            any(c.get("passed") is not True for c in audit["checks"])):
            raise RuntimeError("Indexed independent native EXR pixel review invalid")
        for f in audit["frames"]:
            checked.append(f["frame"])
            if (f.get("sha256")!=frames[f["frame"]-1]["sha256"] or
                f.get("decoded_float_buffer") is not True):
                raise RuntimeError("Indexed float pixel proof has mismatched source image")
    if checked!=list(range(1,len(frames)+1)):
        raise RuntimeError("Independent EXR float review omitted or duplicated frames")
    return {"format":PRESENTATION,"status":"VERIFIED_COMPLETE_EXR_SEQUENCE",
            "project_id":project_id,"presentation_id":presentation_id,
            "source_take_id":data["source_take_id"],
            "source_take_sha256":data["source_take_sha256"],
            "frames":len(frames),"fps":data["fps"],
            "width":width,"height":height,
            "actual_rgba_float32":True,"independent_pixel_readback":True,
            "scene_linear_raw_write":True,
            "aces_verified":False,"video_delivered":False}
