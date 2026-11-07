"""WO5-01: read-only, source-custody audit for an original <=30-minute feature.

A valid film means an approved immutable FilmIndex multi-reel assembly and
verified picture/sound files, NOT a synthetic DCP throughput run. This module
does not render a film, change creator data, use FFmpeg, grant authorization,
or attest that the actual story/picture/sound meets the director's intent.

Use the existing independent FeatureJournal and FilmIndex. No new supervisor.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from backend.nvp_film_index import FilmIndex
from backend.nvp_wo4_feature_journal import (
    ASSEMBLY_FORMAT, FeatureJournal, FORMAT as FEATURE_FORMAT, FRAME_TICKS)
from backend.nvp_wo4_mastering_decision import FORMAT as DECISION_FORMAT
from backend.nvp_wo4_resource_budget import MAX_REELS

FORMAT = "nvp.wo5.original_feature_readiness.v1"
MAX_FRAMES = 30 * 60 * 24
MIN_FRAMES = 24
SHA = re.compile(r"[0-9a-f]{64}\Z")


def inspect_ordered_feature_reels(reels):
    """Check 24fps exact Film Time over up to 30 minutes, without frame data.

    Unlike a picture-sequence accumulator, this plans from bounded reel
    metadata. All source/essence verification happens in the trusted journal.
    """
    if type(reels) is not list or not 2 <= len(reels) <= MAX_REELS:
        raise PermissionError("A bounded multi-reel native feature is required")
    total = 0
    durations = []
    for part in reels:
        if type(part) is not dict:
            raise PermissionError("Untrusted reel manifest")
        frames = part.get("frames")
        start = part.get("start_tick")
        end = part.get("end_tick")
        if (type(frames) is not int or not 3 <= frames <= 7200 or
                type(start) is not int or type(end) is not int or
                start != total * FRAME_TICKS or
                end != start + frames * FRAME_TICKS):
            raise PermissionError("Source reel has a Film Time gap, overlap, or invalid duration")
        total += frames
        if total > MAX_FRAMES:
            raise ValueError("Original production proof exceeds 30 minutes")
        durations.append(frames)
    if total < MIN_FRAMES:
        raise ValueError("Original film proof must be at least one second")
    return {"frame_count": total, "duration_ticks": total * FRAME_TICKS,
            "seconds": total / 24, "reel_count": len(reels),
            "reel_durations": durations}


class _FrameDigestReview:
    """Bounded SHA receipt continuity and diversity, not a visual motion test."""

    def __init__(self, total):
        if type(total) is not int or not MIN_FRAMES <= total <= MAX_FRAMES:
            raise ValueError("Invalid bounded original-film frame count")
        self.total = total
        self.position = 0
        self.originals = set()
        self.codestreams = set()
        self.timeline_hash = sha256()

    def add(self, position, source_sha, j2k_sha, segment_state,
            approved_source_sha):
        if type(position) is not int or position != self.position:
            raise PermissionError("Non-contiguous approved original film sequence")
        if segment_state != "VERIFIED":
            raise PermissionError("Original source frame was not verified")
        for value in (source_sha, j2k_sha, approved_source_sha):
            if type(value) is not str or SHA.fullmatch(value) is None:
                raise PermissionError("Malformed original/encoded frame SHA receipt")
        if source_sha != approved_source_sha:
            raise PermissionError("Original picture disagrees with creator's FilmIndex approval")
        self.timeline_hash.update(position.to_bytes(8, "big"))
        self.timeline_hash.update(bytes.fromhex(source_sha))
        self.timeline_hash.update(bytes.fromhex(j2k_sha))
        self.originals.add(source_sha)
        self.codestreams.add(j2k_sha)
        self.position += 1

    def finish(self):
        if self.position != self.total:
            raise PermissionError("Original feature picture sequence is incomplete")
        # A deliberately narrow admission rule for this *varied-source pilot*.
        # Legitimate films can intentionally repeat stills; this is NOT an
        # artistic quality or general film-validity standard.
        threshold = max(12, (self.total + 1) // 2)
        if (len(self.originals) < threshold or
                len(self.codestreams) < threshold):
            raise PermissionError(
                "Original feature proof cannot be repeated synthetic source frames")
        return {
            "distinct_original_picture_sha256": len(self.originals),
            "distinct_native_j2k_sha256": len(self.codestreams),
            "minimum_distinct_pilot_frame_count": threshold,
            "ordered_picture_custody_sha256": self.timeline_hash.hexdigest(),
            "synthetic_three_frame_repeat_rejected": True,
            "visual_motion_quality_or_originality_verified": False,
        }


def _same_native_project(index, feature):
    project_db = Path(feature["project_db"])
    actual_db = Path(index.studio.db_path)
    if (project_db.is_symlink() or not project_db.is_file() or
            actual_db.is_symlink() or not actual_db.is_file() or
            project_db.resolve(strict=True) != actual_db.resolve(strict=True)):
        raise PermissionError("Feature and original native FilmIndex project differ")


def inspect_original_feature_readiness(index, journal, project_id, feature_id):
    """Audit an indexed, fully source-approved original <=30m multi-reel DCP.

    Entrypoint is trusted native host only. A synthetic or copied recording
    with internally consistent SHA values can still pass *technical* custody;
    creator must independently watch/hear the real result and judge intent.
    No filesystem path escapes into the report.
    """
    if (not isinstance(index, FilmIndex) or
            not isinstance(journal, FeatureJournal)):
        raise PermissionError("Trusted native FilmIndex and feature journal required")
    feature = journal.feature(feature_id)
    if (feature["project_id"] != project_id or
            feature["state"] != "INDEXED" or
            feature["cancel_requested"] or
            not feature["filmindex_sha256"]):
        raise PermissionError("Only exact FilmIndex-indexed native features may be reviewed")
    _same_native_project(index, feature)

    # Rehash native package and every approved source XYZ12/J2K/PCM24/MXF,
    # re-open each indexed source reel and audit exact SMPTE XML duration.
    current, manifest, folder, package_files = journal._recheck_feature(feature_id)
    if (current["filmindex_sha256"] != feature["filmindex_sha256"] or
            manifest.get("format") != FEATURE_FORMAT or
            manifest.get("project_id") != project_id or
            manifest.get("assembly_id") != feature["assembly_id"] or
            manifest.get("assembly_revision") != feature["assembly_revision"] or
            manifest.get("assembly_sha256") != feature["assembly_sha256"] or
            manifest.get("profile") != feature["profile"]):
        raise PermissionError("Indexed feature manifest/source identities differ")

    ordered_jobs = manifest.get("ordered_reel_job_ids")
    reels = manifest.get("reels")
    if (type(ordered_jobs) is not list or type(reels) is not list or
            len(set(ordered_jobs)) != len(ordered_jobs) or
            len(ordered_jobs) != len(reels)):
        raise PermissionError("Feature ordered source reel identities invalid")
    timeline = inspect_ordered_feature_reels(reels)

    assembly = index.read_revision(
        project_id, feature["assembly_id"], feature["assembly_revision"])
    assembly_data = assembly["data"]
    if (assembly["kind"] not in ("edit", "presentation") or
            assembly["document_sha256"] != feature["assembly_sha256"] or
            assembly_data.get("format") != ASSEMBLY_FORMAT or
            assembly_data.get("ordered_reel_job_ids") != ordered_jobs or
            assembly_data.get("start_tick") != 0 or
            assembly_data.get("end_tick") != timeline["duration_ticks"]):
        raise PermissionError("Frozen FilmIndex feature assembly does not match exact Film Time")

    presentation_id = "WO4FEATURE_" + manifest["ids"]["cpl"].replace("-", "")
    presentation = index.read_revision(project_id, presentation_id, 1)
    data = presentation["data"]
    if (presentation["kind"] != "presentation" or
            presentation["document_sha256"] != feature["filmindex_sha256"] or
            data.get("format") != FEATURE_FORMAT or
            data.get("source_assembly_sha256") != feature["assembly_sha256"] or
            data.get("ordered_reel_job_ids") != ordered_jobs or
            data.get("frame_count") != timeline["frame_count"] or
            data.get("reel_count") != timeline["reel_count"] or
            data.get("destination_name") != folder.name or
            data.get("file_sha256") != package_files or
            data.get("cpl_uuid") != "urn:uuid:" + manifest["ids"]["cpl"] or
            data.get("production_dcp_accepted") is not False):
        raise PermissionError("Published multi-reel FilmIndex receipt differs")

    from backend.nvp_openusd_take import OpenUSDTakeCapture
    verifier = OpenUSDTakeCapture(
        index, verify_creator_action=lambda *_: False)
    verified_takes = set()
    frame_review = _FrameDigestReview(timeline["frame_count"])
    global_position = 0
    take_ids = set()
    source_reels = []
    for i, (job_id, part) in enumerate(zip(ordered_jobs, reels)):
        job = journal.status(job_id)
        reel = journal.reel(job_id)
        delivery = journal.delivery(job_id)
        if (job["project_id"] != project_id or job["state"] != "DCP_INDEXED" or
                delivery["phase"] != "INDEXED" or
                not delivery["filmindex_sha256"] or
                reel["profile"] != feature["profile"] or
                reel["frame_count"] != part["frames"] or
                part["start_tick"] != global_position * FRAME_TICKS or
                part["picture"]["file_sha256"] != reel["track_sha256"] or
                part["picture"]["asset_uuid"] != reel["picture_uuid"] or
                part["sound"]["file_sha256"] != delivery["sound_sha256"] or
                part["sound"]["asset_uuid"] != delivery["sound_uuid"]):
            raise PermissionError("Indexed source reel does not match original film assembly")
        original = index.read_revision(
            project_id, reel["take_id"], reel["take_revision"])
        decision = index.read_revision(project_id, reel["decision_id"], 1)
        approved = decision["data"]
        if (original["kind"] != "take" or
                original["data"].get("frozen") is not True or
                original["document_sha256"] != reel["take_sha256"] or
                decision["kind"] != "presentation" or
                decision["document_sha256"] != reel["decision_sha256"] or
                approved.get("format") != DECISION_FORMAT or
                approved.get("source_take_id") != reel["take_id"] or
                approved.get("source_take_revision") != reel["take_revision"] or
                approved.get("source_take_sha256") != reel["take_sha256"] or
                approved.get("picture_profile") != feature["profile"] or
                approved.get("sound_frame_count") != reel["frame_count"] or
                approved.get("sound_sha256") != delivery["master_pcm_sha256"] or
                approved.get("source_modified") is not False):
            raise PermissionError("Creator-approved original Take and picture/sound decision differ")
        ordered_approved = approved.get("ordered_picture_sha256")
        source_start = approved.get("film_start_tick")
        source_step = approved.get("picture_tick_step")
        if (type(ordered_approved) is not list or
                len(ordered_approved) != reel["frame_count"] or
                type(source_start) is not int or source_start < 0 or
                source_step != FRAME_TICKS or
                type(original["data"].get("duration_tick")) is not int or
                source_start + reel["frame_count"] * FRAME_TICKS >
                    original["data"]["duration_tick"]):
            raise PermissionError("Original picture approval is incomplete or outside Take Film Time")
        source_reels.append({
            "reel_number": i + 1,
            "take_id": reel["take_id"],
            "take_document_sha256": reel["take_sha256"],
            "cut_start_tick": part["start_tick"],
            "cut_end_tick": part["end_tick"],
            "take_start_tick": source_start,
            "take_end_tick": source_start + reel["frame_count"] * FRAME_TICKS,
            "approved_frame_count": reel["frame_count"],
            "source_playback_only": True,
            "finished_dcp_playback_verified": False,
        })
        key = (reel["take_id"], reel["take_revision"], reel["take_sha256"])
        if key not in verified_takes:
            actual = verifier.verify_take(project_id, reel["take_id"])
            if (actual["status"] != "VERIFIED_FROZEN_DATA_TAKE" or
                    actual["take_document_sha256"] != reel["take_sha256"]):
                raise PermissionError("Real original OpenUSD/temporal Take custody invalid")
            verified_takes.add(key)
        take_ids.add(reel["take_id"])

        source_id = "WO3DCP_" + delivery["cpl_uuid"].replace("-", "")
        source_dcp = index.read_revision(project_id, source_id, 1)
        sd = source_dcp["data"]
        if (source_dcp["kind"] != "presentation" or
                source_dcp["document_sha256"] != delivery["filmindex_sha256"] or
                sd.get("source_job_id") != job_id or
                sd.get("original_take_sha256") != reel["take_sha256"] or
                sd.get("frame_count") != reel["frame_count"] or
                sd.get("production_dcp_accepted") is not False):
            raise PermissionError("Indexed source reel package no longer matches its Take")

        # Incremental SQLite cursor, not a 43,200-element Python result list.
        # File SHA rechecks have already been performed by _recheck_feature.
        local_position = 0
        with journal._read() as db:
            cursor = db.execute("""SELECT s.position,
                s.expected_sha256 AS source_sha256,
                f.file_sha256 AS j2k_sha256,
                s.state AS segment_state
                FROM production_segments s
                LEFT JOIN production_cinema_frames f
                  ON f.job_id=s.job_id AND f.position=s.position
                WHERE s.job_id=? ORDER BY s.position""", (job_id,))
            for row in cursor:
                if local_position >= reel["frame_count"] or (
                        type(row["position"]) is not int or
                        row["position"] != local_position):
                    raise PermissionError("Incomplete or unordered source picture reel")
                frame_review.add(global_position,
                                 row["source_sha256"], row["j2k_sha256"],
                                 row["segment_state"],
                                 ordered_approved[local_position])
                local_position += 1
                global_position += 1
        if local_position != reel["frame_count"]:
            raise PermissionError("Source picture reel frame count differs from FilmIndex")
    varied = frame_review.finish()
    # No creator-signed assessment, no actual perceived visual/aural evidence.
    return {
        "format": FORMAT,
        "status": "SOURCE_CUSTODY_READY_FOR_HUMAN_FILM_REVIEW_NOT_ACCEPTED",
        "project_id": project_id,
        "feature_id": feature_id,
        "assembly_id": feature["assembly_id"],
        "assembly_revision": feature["assembly_revision"],
        "assembly_sha256": feature["assembly_sha256"],
        "filmindex_feature_receipt_sha256": feature["filmindex_sha256"],
        "cpl_uuid": manifest["ids"]["cpl"],
        **timeline,
        **varied,
        "distinct_original_take_count": len(verified_takes),
        "source_reels_for_native_take_audition": source_reels,
        "no_source_mutation_verified": True,
        "published_package_structure_and_sha_verified": True,
        "original_visual_content_and_storyline_verified": False,
        "actual_actor_camera_sound_and_edit_creative_intent_verified": False,
        "human_viewed_and_heard_complete_film": False,
        "installed_30_minute_workstation_export_verified": False,
        "independent_native_essence_decode_verified": False,
        "smpte_dcp_bv21_conformant_verified": False,
        "external_theatrical_projection_verified": False,
        "wo4_production_accepted": False,
        "wo5_production_accepted": False,
        "production_acceptance": False,
        "ffmpeg_used": False,
        "next_required": [
            "independent_full_picture_and_audio_playback_decode",
            "director_review_compared_to_intended_action_sound_edit",
            "real_near_production_nvp_authored_original_no_more_than_30_minutes",
            "real_installed_gui_and_durable_supervisor_acceptance",
            "independent_smpte_dcp_bv21_validator_and_theater_ingest",
        ],
    }
