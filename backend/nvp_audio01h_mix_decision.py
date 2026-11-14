"""AUDIO-01H.3: immutable explicit creator decision over verified sound.

A review decision is not an export approval. It binds an exact immutable
automated-stem revision and independent measurement, and may be superseded
by a later decision revision; history is never overwritten.
"""
from __future__ import annotations
import math
from backend.nvp_audio01h_stem_revision import FORMAT as AUTOMATED_FORMAT
from backend.nvp_film_index import _id
from backend.nvp_audio01h_loudness import analyze_wav
from backend.nvp_approved_tasks import canonical_bytes

FORMAT = "nvp.audio01h.creator_mix_decision.v1"


def _check_evidence(evidence, wav_sha):
    if (type(evidence) is not dict or
        evidence.get("format") != "nvp.audio01h.loudness_evidence.v1" or
        evidence.get("wav_sha256") != wav_sha or
        evidence.get("normalized") is not False or
        evidence.get("final_mix") is not False or
        evidence.get("director_approved") is not False):
        raise RuntimeError("Untrusted or stale independent loudness evidence")
    for k in ("integrated_lufs", "true_peak_dbtp", "loudness_range_lu"):
        value = evidence.get(k)
        if type(value) not in (float, int) or not math.isfinite(value):
            raise RuntimeError("Invalid mix analysis: " + k)
    if evidence["loudness_range_lu"] < 0:
        raise RuntimeError("Invalid loudness range")


def record_mix_decision(capture, project_id, automated_id, decision_id,
                        evidence, *, decision, creator_event, authorize, ffmpeg="ffmpeg", measure=None):
    """Append an exact creator ACCEPT/REJECT/REVOKE decision to FilmIndex.

    Approval requires a current real creator action. Native host must bind
    event identity and authenticate creator; this library never grants itself
    permission, and cannot claim a final mastered export.
    """
    _id(decision_id, "mix decision stream")
    if decision not in ("ACCEPT", "REJECT", "REVOKE"):
        raise ValueError("Unknown mix review decision")
    source = capture.index.read_revision(project_id, automated_id, 1)
    data = source["data"]
    if (source["kind"] != "audio" or
        data.get("format") != AUTOMATED_FORMAT or
        data.get("final_mix") is not False or
        data.get("director_approved") is not False):
        raise RuntimeError("Must review a frozen unapproved automated stem")
    if data.get("source_stem_id") is not None:
        raise RuntimeError("Individual stem review cannot be approved as final composite mix")
    wav_sha = data["automated_wav_sha256"]
    stored = capture.index.verify_media_file(project_id, wav_sha, "audio/wav")
    _check_evidence(evidence, wav_sha)
    # Refuse self-reported loudness. Independent native FFmpeg evidence must
    # agree with the exact content-addressed FilmIndex WAV being approved.
    measured = (analyze_wav if measure is None else measure)(stored["path"], ffmpeg=ffmpeg,
                           expected_samples=data["samples_per_channel"])
    if canonical_bytes(measured) != canonical_bytes(evidence):
        raise RuntimeError("Full loudness evidence differs from indexed WAV remeasurement")
    try:
        previous = capture.index.read_revision(project_id, decision_id)
    except KeyError:
        previous = None
    if decision == "REVOKE" and (
            previous is None or previous["data"].get("decision") != "ACCEPT"):
        raise RuntimeError("Only a current accepted mix can be revoked")
    if previous is not None:
        p = previous["data"]
        if (previous["kind"] != "audio" or p.get("format") != FORMAT or
            p.get("source_audio_sha256") != source["document_sha256"]):
            raise RuntimeError("Decision identity cannot be reused for a different source")
        if p.get("decision") == decision:
            raise RuntimeError("Repeated review action has no state transition")
    scope = {
        "operation": "nvp.audio01h.creator_mix_decision",
        "project_id": project_id, "automated_id": automated_id,
        "automated_revision": 1,
        "automated_document_sha256": source["document_sha256"],
        "wav_sha256": wav_sha, "decision_id": decision_id,
        "prior_decision_revision": previous["revision"] if previous else 0,
        "decision": decision, "loudness_evidence": evidence,
        "final_master": False
    }
    if creator_event is None or not callable(authorize) or (
            authorize(creator_event, scope) is not True):
        raise PermissionError("Authenticated creator action is required")
    doc = {
        "format": FORMAT, "source_audio_id": automated_id,
        "source_audio_sha256": source["document_sha256"],
        "wav_sha256": wav_sha, "decision": decision,
        "creator_action_required": True,
        "evidence": evidence,
        "director_approved": decision == "ACCEPT",
        "final_mix": decision == "ACCEPT",
        "final_master": False, "dcp_delivered": False
    }
    rev = capture.index.register_revision(
        project_id, decision_id, "audio", doc,
        expected_revision=previous["revision"] if previous else 0,
        dependencies=[{"object_id": automated_id, "revision": 1, "role": "audio"}])
    return {
        "status": "CREATOR_REVIEW_" + decision,
        "revision": rev["revision"], "document_sha256": rev["document_sha256"],
        "director_approved": doc["director_approved"],
        "final_mix": doc["final_mix"], "final_master": False
    }
