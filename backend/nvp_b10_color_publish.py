"""B10 immutable ACEScg color-managed EXR derived film presentation.

Only a source-bound, OS-contained, completed native OCIO process may publish.
The original frozen Digital Take and raw Rec.709 EXR remain unchanged; the
derived ACEScg EXR + explicit pinned config and conversion receipt are stored
by content address and rechecked independently after NVP restart.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.nvp_b10_color_verify import verify_acescg_frame
from backend.nvp_b10_color_worker import NativeOCIOColorWorker,REPORT,SOURCE,OUTPUT
from backend.nvp_exr_publish import verify_indexed_exr_sequence
from backend.nvp_production_scene import compact,digest


FORMAT="nvp.presentation.aces2.ocio.acescg_frame.v1"


def publish_acescg_frame(host:NativeOCIOColorWorker,job_id:str):
    if not isinstance(host,NativeOCIOColorWorker):
        raise TypeError("Only the native NVP ACEScg color worker may publish")
    proof=host.verify_completed(job_id)
    row=host._read(job_id)
    root=host.root/job_id
    report_bytes=(root/REPORT).read_bytes()
    original=host.capture.index.read_revision(row["project_id"],
                                               row["source_presentation_id"])
    if original["document_sha256"]!=row["source_presentation_sha256"]:
        raise RuntimeError("Original indexed EXR presentation has changed")
    indexed=host.capture.index
    converted=indexed.put_media_file(row["project_id"],root/OUTPUT,"image/x-exr",
                                     max_bytes=512*1024*1024)
    if converted["sha256"]!=row["output_sha256"] or proof["acescg_exr_sha256"]!=converted["sha256"]:
        raise RuntimeError("Archived ACEScg pixels differ from native verified result")
    receipt_sha=indexed.put_blob(row["project_id"],report_bytes,
                                 "application/vnd.nvp.ocio+json")
    if not isinstance(receipt_sha,str) or len(receipt_sha)!=64:
        raise RuntimeError("Durable OCIO receipt blob missing")
    document={
        "format":FORMAT,"project_id":row["project_id"],
        "source_take_id":row["source_take_id"],
        "source_take_revision":1,
        "source_take_sha256":row["source_take_sha256"],
        "source_presentation_id":row["source_presentation_id"],
        "source_presentation_revision":1,
        "source_presentation_sha256":row["source_presentation_sha256"],
        "source_frame_number":row["frame"],
        "raw_scene_linear_exr_sha256":row["source_sha256"],
        "acescg_exr_sha256":converted["sha256"],
        "acescg_exr_size_bytes":converted["size_bytes"],
        "color_transform_receipt_sha256":receipt_sha,
        "ocio_config_uri":json.loads(report_bytes)["config"]["config_uri"],
        "ocio_config_serialized_sha256":proof["config_serialized_sha256"],
        "target_color_space":"ACEScg",
        "source_color_space":json.loads(report_bytes)["source_space"],
        "channel_type":"IEEE_FLOAT32",
        "alpha_unchanged":True,
        "working_aces2_cg_conversion_verified":True,
        "input_rec709_primaries_independently_proved":False,
        "display_output_transform_verified":False,
        "graded_video_delivered":False,
        "original_digital_take_modified":False,
    }
    ident="acescgframe_"+digest(document)[:32]
    deps=[
        {"object_id":row["source_take_id"],"revision":1,"role":"source_take"},
        {"object_id":row["source_presentation_id"],"revision":1,"role":"presentation"},
    ]
    try:
        record=indexed.register_revision(row["project_id"],ident,"presentation",
                                         document,dependencies=deps)
    except RuntimeError as exc:
        existing=indexed.read_revision(row["project_id"],ident)
        if (existing["kind"]!="presentation" or existing["revision"]!=1 or
            existing["data"]!=document):
            raise RuntimeError("ACEScg derived presentation identity collision") from exc
        record=existing
    verified=verify_indexed_acescg_frame(host.capture,row["project_id"],ident)
    return {**verified,"presentation_document_sha256":record["document_sha256"]}


def verify_indexed_acescg_frame(capture,project_id,presentation_id):
    index=capture.index
    doc=index.read_revision(project_id,presentation_id)
    data=doc["data"]
    if (doc["kind"]!="presentation" or doc["revision"]!=1 or
        data.get("format")!=FORMAT or data.get("project_id")!=project_id or
        data.get("target_color_space")!="ACEScg" or
        data.get("channel_type")!="IEEE_FLOAT32" or
        data.get("ocio_config_uri")!="ocio://cg-config-v4.0.0_aces-v2.0_ocio-v2.5" or
        data.get("working_aces2_cg_conversion_verified") is not True or
        data.get("original_digital_take_modified") is not False or
        data.get("display_output_transform_verified") is not False):
        raise RuntimeError("Indexed ACEScg frame did not retain honest source authority")
    source_index=verify_indexed_exr_sequence(capture,project_id,
                                           data["source_presentation_id"])
    base=index.read_revision(project_id,data["source_presentation_id"])
    if (base["document_sha256"]!=data["source_presentation_sha256"] or
        source_index["source_take_id"]!=data["source_take_id"] or
        source_index["source_take_sha256"]!=data["source_take_sha256"]):
        raise RuntimeError("ACEScg derived frame not linked to original frozen take")
    dependencies=doc["dependencies"]
    expected=[{"object_id":data["source_take_id"],"revision":1,"role":"source_take"},
              {"object_id":data["source_presentation_id"],"revision":1,"role":"presentation"}]
    if sorted(dependencies,key=lambda e:(e["object_id"],e["revision"],e["role"]))!=sorted(
          expected,key=lambda e:(e["object_id"],e["revision"],e["role"])):
        raise RuntimeError("Derived color presentation lost FilmIndex source dependency")
    frame=base["data"]["frames"][data["source_frame_number"]-1]
    if (frame["frame"]!=data["source_frame_number"] or
        frame["sha256"]!=data["raw_scene_linear_exr_sha256"]):
        raise RuntimeError("ACEScg frame source film time index changed")
    original=index.verify_media_file(project_id,frame["sha256"],"image/x-exr")
    converted=index.verify_media_file(project_id,data["acescg_exr_sha256"],"image/x-exr")
    if converted["size_bytes"]!=data["acescg_exr_size_bytes"]:
        raise RuntimeError("Stored ACEScg image size changed")
    receipt=json.loads(index.get_blob(
        project_id,data["color_transform_receipt_sha256"]))
    if receipt.get("source_space")!=data["source_color_space"]:
        raise RuntimeError("Indexed conversion input color space changed")
    width,height=base["data"]["resolution"]
    proof=verify_acescg_frame(
        Path(original["path"]),Path(converted["path"]),receipt,
        width=width,height=height)
    if (proof["acescg_exr_sha256"]!=data["acescg_exr_sha256"] or
        proof["config_serialized_sha256"]!=data["ocio_config_serialized_sha256"]):
        raise RuntimeError("Indexed ACEScg pixel data or official OCIO config changed")
    return {"format":FORMAT,"status":"VERIFIED_INDEXED_ACESCG_FLOAT32",
            "project_id":project_id,"presentation_id":presentation_id,
            "source_take_id":data["source_take_id"],
            "source_frame":data["source_frame_number"],
            "color_space":"ACEScg",
            "frame_sha256":proof["acescg_exr_sha256"],
            "ocio_config_sha256":proof["config_serialized_sha256"],
            "sampled_pixel_checks":proof["sampled_pixels"],
            "original_take_unchanged":True,
            "output_display_transform_not_applied":True}
