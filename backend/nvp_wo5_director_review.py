"""WO5-02: frozen director intent and later human observations in FilmIndex.

Never infer story quality from SHA hashes, an AI prompt or successful DCP
publication. The native host authenticates the creator approval callback;
this module does not implement authentication or a desktop review UI.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re

from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_wo4_feature_journal import ASSEMBLY_FORMAT, FRAME_TICKS
from backend.nvp_wo5_original_feature import (
    MAX_FRAMES, inspect_original_feature_readiness)

INTENT_FORMAT = "nvp.wo5.immutable_director_intent.v1"
REVIEW_FORMAT = "nvp.wo5.immutable_director_observation.v1"
MAX_SHOTS = 512
TEXT_LIMIT = 360
SHOT = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}\Z")
JUDGMENTS = frozenset(("MATCHED", "NEEDS_REVISION", "NOT_OBSERVED"))


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True,
                         separators=(",", ":"), allow_nan=False).encode("ascii")
    return sha256(encoded).hexdigest()


def _comment(value, label, *, empty=False):
    if (type(value) is not str or len(value) > TEXT_LIMIT or
            (not empty and not value.strip()) or
            any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise ValueError("Bounded plain-text " + label + " required")
    return value


def validate_director_shots(shots, duration_tick):
    """Complete non-overlapping exact-time shot intention, before review."""
    if (type(duration_tick) is not int or
            not FRAME_TICKS <= duration_tick <= MAX_FRAMES * FRAME_TICKS or
            duration_tick % FRAME_TICKS):
        raise ValueError("Creator's planned film must be <=30min at 24fps")
    if type(shots) is not list or not 1 <= len(shots) <= MAX_SHOTS:
        raise ValueError("Bounded original-shot intention list required")
    cursor = 0
    seen = set()
    approved = []
    for shot in shots:
        if (type(shot) is not dict or
                set(shot) != {"shot_id", "start_tick", "end_tick",
                              "expected_action", "expected_camera",
                              "expected_sound"}):
            raise PermissionError("Intent must specify film time, scene action, camera, sound")
        sid = shot["shot_id"]
        if type(sid) is not str or not SHOT.fullmatch(sid) or sid in seen:
            raise PermissionError("Original shot identity missing or reused")
        start, end = shot["start_tick"], shot["end_tick"]
        if (type(start) is not int or type(end) is not int or
                start != cursor or end <= start or end > duration_tick or
                start % FRAME_TICKS or end % FRAME_TICKS):
            raise PermissionError("Intended shot timeline has a gap, overlap or invalid Film Time")
        for field in ("expected_action", "expected_camera", "expected_sound"):
            _comment(shot[field], field)
        seen.add(sid)
        approved.append(dict(shot))
        cursor = end
    if cursor != duration_tick:
        raise PermissionError("The creator's shot intentions do not cover the whole film")
    return approved


def validate_director_observations(shots, observations,
                                   watched_entire_film, heard_entire_sound):
    """Validate attributable human report, without claiming perceptual truth."""
    if (type(watched_entire_film) is not bool or
            type(heard_entire_sound) is not bool or
            type(observations) is not list or len(observations) != len(shots)):
        raise PermissionError("Explicit complete director review status required")
    ordered = []
    for expected, actual in zip(shots, observations):
        if (type(actual) is not dict or
                set(actual) != {"shot_id", "observed_action",
                                "observed_camera", "observed_sound",
                                "judgment", "review_note"} or
                actual.get("shot_id") != expected["shot_id"] or
                actual.get("judgment") not in JUDGMENTS):
            raise PermissionError("Every creator observation must reference its planned shot")
        for field in ("observed_action", "observed_camera",
                      "observed_sound", "review_note"):
            _comment(actual[field], field, empty=True)
        if (actual["judgment"] == "MATCHED" and
                not all(actual[f].strip() for f in (
                    "observed_action", "observed_camera", "observed_sound"))):
            raise PermissionError("A matched shot requires concrete observed picture and sound")
        ordered.append(dict(actual))
    fully_reviewed = watched_entire_film and heard_entire_sound and all(
        o["judgment"] != "NOT_OBSERVED" for o in ordered)
    any_revision = any(o["judgment"] == "NEEDS_REVISION" for o in ordered)
    return {
        "observations": ordered,
        "creator_claims_entire_film_viewed": watched_entire_film,
        "creator_claims_entire_sound_heard": heard_entire_sound,
        "director_review_complete_by_self_report": fully_reviewed,
        "director_requests_revisions": any_revision,
        "director_reports_all_shots_matched": fully_reviewed and not any_revision,
        "independent_creative_intent_verified": False,
        "production_acceptance": False,
    }


def register_director_intent(index, project_id, *, assembly_id,
                             assembly_revision, intent_id, shots, approve):
    """Author and freeze director's *anticipated* shots before final review."""
    if not isinstance(index, FilmIndex) or not callable(approve):
        raise PermissionError("Only trusted FilmIndex and native creator consent")
    _id(intent_id, "director intent")
    if index.history(project_id, intent_id):
        raise FileExistsError("Director intent ID is immutable; create a new versioned object")
    assembly = index.read_revision(project_id, assembly_id, assembly_revision)
    data = assembly["data"]
    if (assembly["kind"] not in ("edit", "presentation") or
            data.get("format") != ASSEMBLY_FORMAT or
            data.get("start_tick") != 0):
        raise PermissionError("A frozen exact-time feature cut must exist first")
    duration = data.get("end_tick")
    prepared = validate_director_shots(shots, duration)
    scope = {
        "operation": "nvp.wo5.creator_confirm_director_intent.v1",
        "project_id": project_id,
        "assembly_id": assembly_id, "assembly_revision": assembly_revision,
        "assembly_sha256": assembly["document_sha256"],
        "intent_id": intent_id,
        "intent_shots_sha256": _digest(prepared),
        "shot_count": len(prepared),
        "end_tick": duration,
    }
    if approve(deepcopy(scope)) is not True:
        return {"status": "DENIED", "source_modified": False}
    if (index.read_revision(project_id, assembly_id, assembly_revision)[
            "document_sha256"] != assembly["document_sha256"] or
            index.history(project_id, intent_id)):
        raise PermissionError("Frozen director source changed during consent")
    record = {
        "format": INTENT_FORMAT,
        "source_assembly_id": assembly_id,
        "source_assembly_revision": assembly_revision,
        "source_assembly_sha256": assembly["document_sha256"],
        "end_tick": duration,
        "shots": prepared,
        "creator_intent_recorded": True,
        "film_created": False,
        "creative_intent_verified": False,
        "production_accepted": False,
    }
    saved = index.register_revision(
        project_id, intent_id, "presentation", record,
        expected_revision=0, dependencies=[
            {"object_id": assembly_id, "revision": assembly_revision,
             "role": "presentation"}])
    return {
        "status": "DIRECTOR_INTENT_FROZEN_NOT_FILM_ACCEPTED",
        "intent_id": intent_id,
        "intent_sha256": saved["document_sha256"],
        "shot_count": len(prepared),
        "production_acceptance": False,
    }


def record_director_review(index, journal, project_id, *, feature_id,
                           intent_id, review_id, observations,
                           watched_entire_film, heard_entire_sound, approve):
    """Record explicit host-authorized viewing/listening assessment.

    The source-feature audit is repeated before any review document is
    admitted. NVP cannot determine the truth of a human's creative report.
    """
    if not isinstance(index, FilmIndex) or not callable(approve):
        raise PermissionError("Trusted native host and creator approval required")
    _id(review_id, "director review")
    if index.history(project_id, review_id):
        raise FileExistsError("Director review must be a new immutable identity")
    intent = index.read_revision(project_id, intent_id, 1)
    if intent["kind"] != "presentation" or intent["data"].get("format") != INTENT_FORMAT:
        raise PermissionError("No frozen original director intent exists")
    audited = inspect_original_feature_readiness(
        index, journal, project_id, feature_id)
    i = intent["data"]
    if (i.get("source_assembly_id") != audited["assembly_id"] or
            i.get("source_assembly_revision") != audited["assembly_revision"] or
            i.get("source_assembly_sha256") != audited["assembly_sha256"] or
            i.get("end_tick") != audited["duration_ticks"]):
        raise PermissionError("Director intent cannot be attached to an unrelated cut")
    shots = validate_director_shots(i["shots"], audited["duration_ticks"])
    report = validate_director_observations(
        shots, observations, watched_entire_film, heard_entire_sound)
    scope = {
        "operation": "nvp.wo5.creator_confirm_film_observations.v1",
        "project_id": project_id,
        "feature_id": feature_id,
        "feature_filmindex_sha256": audited["filmindex_feature_receipt_sha256"],
        "intent_id": intent_id,
        "intent_sha256": intent["document_sha256"],
        "review_id": review_id,
        "observations_sha256": _digest(report),
        "watched_entire_film": watched_entire_film,
        "heard_entire_sound": heard_entire_sound,
        "director_requests_revisions": report["director_requests_revisions"],
    }
    if approve(deepcopy(scope)) is not True:
        return {"status": "DENIED", "source_modified": False}
    if (index.history(project_id, review_id) or
            index.read_revision(project_id, intent_id, 1)[
                "document_sha256"] != intent["document_sha256"]):
        raise PermissionError("Director review source changed during confirmation")
    feature_record_id = "WO4FEATURE_" + audited["cpl_uuid"].replace("-", "")
    feature = index.read_revision(project_id, feature_record_id, 1)
    if feature["document_sha256"] != audited["filmindex_feature_receipt_sha256"]:
        raise PermissionError("The approved film receipt changed during review")
    record = {
        "format": REVIEW_FORMAT,
        "original_feature_id": feature_id,
        "original_feature_receipt_sha256": audited["filmindex_feature_receipt_sha256"],
        "original_picture_custody_sha256": audited["ordered_picture_custody_sha256"],
        "source_director_intent_id": intent_id,
        "source_director_intent_sha256": intent["document_sha256"],
        "observations_sha256": _digest(report),
        **report,
        "creator_self_report_only": True,
        "independently_verified_playback": False,
        "smpte_dcp_bv21_verified": False,
        "theatrical_projection_verified": False,
        "wo4_production_accepted": False,
        "wo5_production_accepted": False,
    }
    saved = index.register_revision(
        project_id, review_id, "presentation", record,
        expected_revision=0, dependencies=[
            {"object_id": intent_id, "revision": 1, "role": "presentation"},
            {"object_id": feature_record_id, "revision": 1, "role": "presentation"}])
    return {
        "status": "DIRECTOR_OBSERVATIONS_RECORDED_NOT_INDEPENDENTLY_VERIFIED",
        "review_id": review_id,
        "review_sha256": saved["document_sha256"],
        "director_review_complete_by_self_report":
            report["director_review_complete_by_self_report"],
        "director_requests_revisions": report["director_requests_revisions"],
        "production_acceptance": False,
    }
