"""WO5 read-only original-short readiness audit; never production acceptance.

Actual NVP authored <=30s short with varied frames is required. Synthetic
packaging success cannot certify the creator's intended story, acting, picture
or sound. No source mutations, FFmpeg, cloud service or automatic approvals.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from backend.nvp_film_index import FilmIndex
from backend.nvp_wo4_delivery_journal import CinemaDeliveryJournal
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure

FORMAT = "nvp.wo5.original_short_readiness.v1"
MAX_FRAMES = 720
MIN_FRAMES = 24
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def inspect_frame_variation(rows, frame_count):
    """Eligible SHA diversity is not proof of visible motion or originality."""
    if type(frame_count) is not int or not MIN_FRAMES <= frame_count <= MAX_FRAMES:
        raise ValueError("WO5 original proof must be 1 to 30 seconds at 24fps")
    if type(rows) is not list or len(rows) != frame_count:
        raise PermissionError("Complete ordered production frame receipts required")
    originals = []
    codestreams = []
    for position, item in enumerate(rows):
        if (type(item) is not dict or
                set(item) != {"position", "source_sha256", "j2k_sha256",
                              "segment_state"} or
                type(item["position"]) is not int or item["position"] != position):
            raise PermissionError("Non-contiguous source-authored film frames")
        if item["segment_state"] != "VERIFIED":
            raise PermissionError("A picture sample was not durably verified")
        for key in ("source_sha256", "j2k_sha256"):
            value = item[key]
            if type(value) is not str or not SHA256.fullmatch(value):
                raise PermissionError("Invalid original or J2K source SHA receipt")
        originals.append(item["source_sha256"])
        codestreams.append(item["j2k_sha256"])
    unique_originals = len(set(originals))
    unique_j2k = len(set(codestreams))
    # Pilot-specific technical diversity filter, NOT a universal artistic rule:
    # a real film is permitted to use intentional static shots outside this test.
    threshold = max(12, (frame_count + 1) // 2)
    if unique_originals < threshold or unique_j2k < threshold:
        raise PermissionError("WO5 original-short proof rejects repeated-frame/"
                              "low-variation synthetic packaging stand-ins")
    return {
        "frame_count": frame_count,
        "film_time_seconds": frame_count / 24,
        "distinct_source_sha256_count": unique_originals,
        "distinct_j2k_sha256_count": unique_j2k,
        "required_distinct_frame_count_for_this_pilot": threshold,
        "no_repeated_frame_stand_in": True,
        "visual_motion_or_originality_proven": False,
        "creative_intent_proven": False,
    }


def inspect_original_short_readiness(index, journal, project_id, job_id):
    """Reopen genuine trusted FilmIndex/native journal data, read-only.

    Success is only readiness for independent picture/audio/creative review.
    """
    if not isinstance(index, FilmIndex) or not isinstance(journal, CinemaDeliveryJournal):
        raise PermissionError("Original proof requires trusted native FilmIndex/journal")
    job = journal.status(job_id)
    reel = journal.reel(job_id)
    delivery = journal.delivery(job_id)
    if (job["project_id"] != project_id or job["state"] != "DCP_INDEXED" or
            delivery["phase"] != "INDEXED" or
            not delivery["filmindex_sha256"] or
            not MIN_FRAMES <= reel["frame_count"] <= MAX_FRAMES):
        raise PermissionError("No indexed <=30-second original NVP delivery")
    project_db = Path(delivery["project_db"])
    if (project_db.is_symlink() or not project_db.is_file() or
            Path(index.studio.db_path).resolve(strict=True) !=
            project_db.resolve(strict=True)):
        raise PermissionError("Project FilmIndex differs from native delivery ownership")
    take = index.read_revision(project_id, reel["take_id"], reel["take_revision"])
    decision = index.read_revision(project_id, reel["decision_id"], 1)
    if (take["kind"] != "take" or take["data"].get("frozen") is not True or
            take["document_sha256"] != reel["take_sha256"] or
            decision["kind"] != "presentation" or
            decision["document_sha256"] != reel["decision_sha256"]):
        raise PermissionError("Original Take/mastering FilmIndex custody mismatched")
    presentation_id = "WO3DCP_" + delivery["cpl_uuid"].replace("-", "")
    presentation = index.read_revision(project_id, presentation_id, 1)
    if (presentation["kind"] != "presentation" or
            presentation["document_sha256"] != delivery["filmindex_sha256"] or
            presentation["data"].get("source_job_id") != job_id or
            presentation["data"].get("original_take_sha256") != reel["take_sha256"] or
            presentation["data"].get("frame_count") != reel["frame_count"]):
        raise PermissionError("Published DCP not bound to original FilmIndex")
    from backend.nvp_openusd_take import OpenUSDTakeCapture
    verified = OpenUSDTakeCapture(index, verify_creator_action=lambda *_: False).verify_take(
        project_id, reel["take_id"])
    if (verified["status"] != "VERIFIED_FROZEN_DATA_TAKE" or
            verified["take_document_sha256"] != reel["take_sha256"]):
        raise PermissionError("Original USD/temporal Take failed independent review")
    # Native source, PCM, all J2K, picture and sound MXF SHA re-verification.
    journal._verify_all_production_sources(job_id)
    folder, file_shas = journal._check_published(job_id)
    with journal._read() as db:
        rows = [dict(row) for row in db.execute("""SELECT s.position,
                  s.expected_sha256 AS source_sha256,
                  f.file_sha256 AS j2k_sha256,
                  s.state AS segment_state
                  FROM production_segments s
                  LEFT JOIN production_cinema_frames f
                    ON f.job_id=s.job_id AND f.position=s.position
                  WHERE s.job_id=? ORDER BY s.position""", (job_id,))]
    variation = inspect_frame_variation(rows, reel["frame_count"])
    dcp = inspect_dcp_structure(folder)
    if (dcp["status"] != "STRUCTURE_AND_SHA_VERIFIED" or
            dcp["cpl_uuid"] != delivery["cpl_uuid"] or
            sum(dcp["reel_durations"]) != reel["frame_count"] or
            dcp["reel_count"] != 1):
        raise PermissionError("30-second audio/picture DCP timeline does not match")
    if file_shas != json.loads(delivery["dcp_files_json"]):
        raise PermissionError("Durable package receipt changed during review")
    return {
        "format": FORMAT,
        "status": "ELIGIBLE_FOR_LATER_CREATIVE_REVIEW_NOT_ACCEPTED",
        "project_id": project_id,
        "job_id": job_id,
        "source_take_sha256": reel["take_sha256"],
        "source_decision_sha256": reel["decision_sha256"],
        "source_filmindex_dcp_receipt_sha256": presentation["document_sha256"],
        "cpl_uuid": dcp["cpl_uuid"],
        "dcp_package_assets": dcp["asset_count"],
        **variation,
        "installed_nvp_export_verified": False,
        "original_film_story_acting_camera_and_audio_intent_verified": False,
        "independent_essence_decode_verified": False,
        "independent_theatrical_compliance_verified": False,
        "production_acceptance": False,
        "wo4_production_accepted": False,
        "wo5_production_accepted": False,
        "external_required": [
            "near_production_nvp_authored_original_short_30_seconds_max",
            "creator_compares_intended_vs_actual_moving_picture_and_edit",
            "creator_hears_synchronized_dialogue_sound_and_mix",
            "native_playback_essence_decode_and_source_custody",
            "physical_installed_workstation_and_restart_after_crash",
            "independent_specialist_picture_sound_and_cinema_acceptance_later",
        ],
        "ffmpeg_used": False,
    }
