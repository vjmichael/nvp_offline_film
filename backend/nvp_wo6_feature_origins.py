"""WO6-02: project-owned published DCP -> original scene/Take custody.

This is a READ-ONLY *expensive verification* operation, enabled only if an
authenticated native host explicitly supplies its real FeatureJournal.
It reuses WO5's existing complete original-source/film DCP SHA audit;
the resulting authored source mapping is not an AI guess from decoded
JPEG2000 pixels. A standalone third-party DCP without that native
production journal has no reconstructible USD scene through this path.

No second FilmIndex, supervisor, codec, worker or approval authority.
"""
from __future__ import annotations
from hashlib import sha256
import json

from backend.nvp_film_index import FilmIndex, _require_pid
from backend.nvp_wo4_feature_journal import FeatureJournal
from backend.nvp_wo5_original_feature import inspect_original_feature_readiness
from backend.nvp_wo6_creator_plan import plan_source_retake

FORMAT="nvp.wo6.published_feature_original_source_map.v1"
MAX_ORIGIN_REELS=64

CAPABILITY={
    "id":"nvp.film.resolve_published_sources.v1",
    "description":"Read-only heavyweight original FilmIndex + FeatureJournal "
                  "SHA verification of published DCP reel -> Take -> scene",
    "effect":"read",
    "input_schema":{
        "project_id":"current native-authorized film project",
        "feature_id":"exact existing native FeatureJournal feature ID",
    },
    "result_schema":FORMAT,
    "requires_host_authorization":True,
    "requires_native_feature_journal":True,
    "potentially_expensive_full_source_audit":True,
    "executable_by_model":False,
}


def resolve_published_feature_origins(index: FilmIndex,
                                      journal: FeatureJournal,
                                      project_id: str,
                                      feature_id: str) -> dict:
    if not isinstance(index,FilmIndex) or not isinstance(journal,FeatureJournal):
        raise PermissionError("Native trusted FilmIndex and FeatureJournal required")
    _require_pid(project_id)
    if (type(feature_id) is not str or not 1<=len(feature_id)<=128):
        raise ValueError("A bounded original feature ID is required")
    current=journal.feature(feature_id)
    if (current["project_id"]!=project_id or current["state"]!="INDEXED" or
            current["cancel_requested"] or not current["filmindex_sha256"]):
        raise PermissionError("Only committed native indexed project DCPs can be resolved")
    # Existing WO5 reader checks actual indexed original Take, edited
    # source approval, all native production picture/PCM/J2K/MXF hashes,
    # final DCP CPL/PKL/AssetMap, multi-reel time and original USD reopen.
    audited=inspect_original_feature_readiness(
        index,journal,project_id,feature_id)
    reels=audited.get("source_reels_for_native_take_audition")
    if (audited.get("status") !=
            "SOURCE_CUSTODY_READY_FOR_HUMAN_FILM_REVIEW_NOT_ACCEPTED" or
            audited.get("filmindex_feature_receipt_sha256") !=
                current["filmindex_sha256"] or
            audited.get("production_acceptance") is not False or
            type(reels) is not list or
            not 2<=len(reels)<=MAX_ORIGIN_REELS or
            len(reels)!=audited.get("reel_count")):
        raise PermissionError("Verified feature source-chain receipt incomplete")
    evidence=[]
    take_sources={}
    for pos,reel in enumerate(reels,1):
        if (type(reel) is not dict or reel.get("reel_number") != pos or
                type(reel.get("take_id")) is not str or
                type(reel.get("take_document_sha256")) is not str or
                type(reel.get("approved_frame_count")) is not int or
                reel["approved_frame_count"]<1 or
                reel.get("source_playback_only") is not True or
                reel.get("finished_dcp_playback_verified") is not False):
            raise PermissionError("Film reel source cannot be verified")
        take=index.read_revision(project_id,reel["take_id"],1)
        if (take["kind"]!="take" or take["document_sha256"]!=
                reel["take_document_sha256"]):
            raise PermissionError("Reel source Take SHA is inconsistent")
        source=take_sources.get(reel["take_id"])
        if source is None:
            plan=plan_source_retake(index,project_id,reel["take_id"],1)
            if (plan["status"]!="PINNED_USD_RETAKE_SOURCES_FOUND_NOT_AUTHORIZED"
                    or len(plan["source_takes"])!=1):
                raise PermissionError("Approved reel lacks bounded source scene map")
            source=plan["source_takes"][0]
            take_sources[reel["take_id"]]=source
        evidence.append({
            "reel_number":pos,
            "take_id":reel["take_id"],
            "take_revision":1,
            "take_document_sha256":take["document_sha256"],
            "original_scene":source["source_scene"],
            "original_temporal_events":source["source_timeline"],
            "original_source_start_tick":reel["take_start_tick"],
            "original_source_end_tick":reel["take_end_tick"],
            "finished_film_start_tick":reel["cut_start_tick"],
            "finished_film_end_tick":reel["cut_end_tick"],
            "original_picture_frame_count":reel["approved_frame_count"],
            "native_original_take_independently_reopened_by_wo5":True,
            "human_film_review_verified":False,
        })
    # Recheck the mutable journal state after full-source audit to avoid
    # returning a plan bound to a now-replaced or cancelled publication.
    again=journal.feature(feature_id)
    if (again["state"]!="INDEXED" or again["cancel_requested"] or
            again["filmindex_sha256"]!=current["filmindex_sha256"]):
        raise PermissionError("Feature publication changed during source audit")
    result={
        "format":FORMAT,
        "status":"PUBLISHED_ORIGINAL_SOURCES_REOPENED_NOT_RETAKEN",
        "project_id":project_id,
        "feature_id":feature_id,
        "filmindex_feature_receipt_sha256":current["filmindex_sha256"],
        "cpl_uuid":audited["cpl_uuid"],
        "duration_ticks":audited["duration_ticks"],
        "frame_count":audited["frame_count"],
        "reel_count":len(reels),
        "source_reels":evidence,
        "distinct_original_take_count":len(take_sources),
        "real_native_source_files_audited":True,
        "published_dcp_cpl_mxf_sha_audited":True,
        "independent_dcp_bv21_theater_validation":False,
        "standalone_dcp_reverse_engineered_into_usd":False,
        "new_scene_created":False,
        "new_take_created":False,
        "master_or_dcp_replaced":False,
        "native_creator_approval_granted":False,
        "model_executed":False,
        "sensitive_source_bytes_exposed":False,
        "source_read_side_effects":False,
    }
    result["receipt_sha256"]=sha256(json.dumps(
        result,sort_keys=True,separators=(",",":"),ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()
    return result
