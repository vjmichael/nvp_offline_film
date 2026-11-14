"""FILM03-07: real-WAV expressive voice audition evidence, NOT a voice worker.

No model is launched or approved here. A canonical ActorID, selected VoiceID,
immutable screenplay line, original Take and director direction must first be
resolved from FilmIndex. An operator can import an existing actual PCM WAV
from a separately reviewed experiment; the bytes are audited and hashed.
Independent human review is separate from mechanical audio validation.
"""
from __future__ import annotations

from hashlib import sha256
import math
import os
from pathlib import Path
import re
import stat
import wave

from backend.nvp_film03_actor_identity_core import ActorIdentityCore, digest, bounded
from backend.nvp_film03_expressive_voice_direction import (
    FORMAT as DIRECTION_FORMAT, FilmActorVoiceDirection,
    REQUIRED_QUALITY,
)
from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid

FORMAT = "nvp.film03.expressive_voice_audition.v1"
MAX_WAV_BYTES = 40 * 1024 * 1024
MAX_SECONDS = 180
MIN_SECONDS = 0.20
RUBRIC = (
    "naturalness", "emotion_and_arc", "word_emphasis", "pronunciation",
    "pause_and_breath", "whisper_or_soft_delivery", "shout_dynamics",
    "actor_voice_continuity", "retake_editability", "performance_intent",
)
RATES = frozenset({16000, 22050, 24000, 32000, 44100, 48000, 96000})
SLUG = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,79}\Z")


def frozen_case(index: FilmIndex, pid, source_route, *, profile_revision,
                direction_id, direction_revision):
    """Reopen authoritative actor/line/direction; no trust in supplied labels."""
    if not isinstance(index, FilmIndex):
        raise TypeError("Actual FilmIndex required")
    _require_pid(pid)
    _id(direction_id, "frozen direction ID")
    if type(direction_revision) is not int or direction_revision < 1:
        raise ValueError("Positive frozen direction revision required")
    plan = ActorIdentityCore(
        index, verify_creator_action=lambda *_: False
    ).prepare_generated_voice(pid, source_route, profile_revision=profile_revision)
    if direction_id != FilmActorVoiceDirection.identity(pid, plan):
        raise PermissionError("Direction is not owned by this source performance")
    record = index.read_revision(pid, direction_id, direction_revision)
    if record["kind"] != "performance":
        raise PermissionError("Only canonical performance direction is reviewable")
    doc = record["data"]
    expected = {
        "format": DIRECTION_FORMAT,
        "actor_id": plan["actor_id"],
        "voice_id": plan["voice_id"],
        "profile_revision": profile_revision,
        "profile_sha256": plan["actor_identity_profile_sha256"],
        "voice_cast_revision": plan["voice_cast_revision"],
        "voice_reference_sha256": plan["voice_reference_sha256"],
        "source_take_sha256": plan["source_take_sha256"],
        "script_line_id": plan["script_line_id"],
        "script_document_sha256": plan["script_document_sha256"],
        "source_selection_revision": plan["source_selection_revision"],
        "source_selection_sha256": plan["source_selection_document_sha256"],
        "performance_id": plan["source_performance_id"],
        "source_generation_contract_sha256": plan["contract_sha256"],
    }
    if any(doc.get(k) != v for k, v in expected.items()):
        raise PermissionError("Direction revision mismatches ActorID, VoiceID or frozen screenplay")
    if doc.get("directions_sha256") != digest(doc.get("directions")):
        raise PermissionError("Source director instructions failed SHA verification")
    return {
        "format": FORMAT, "project_id": pid,
        "actor_id": plan["actor_id"], "voice_id": plan["voice_id"],
        "voice_reference_sha256": plan["voice_reference_sha256"],
        "script_line_id": plan["script_line_id"],
        "script_text_sha256": sha256(plan["exact_script_text"].encode("utf8")).hexdigest(),
        "source_take_sha256": plan["source_take_sha256"],
        "source_generation_contract_sha256": plan["contract_sha256"],
        "direction_id": direction_id, "direction_revision": direction_revision,
        "direction_document_sha256": record["document_sha256"],
        "direction_sha256": doc["directions_sha256"],
        "delivery": doc["directions"]["delivery"],
        "emotion": doc["directions"]["emotion"],
        "profile_model_id": plan["generation_settings"]["model_id"],
        "lab_only_not_permission_to_generate_or_approve": True,
    }


def _real_audio_file(root: Path, filename: str):
    """Import only a top-level regular file in a designated audition folder."""
    if type(filename) is not str or not filename.endswith(".wav") or \
       not filename or Path(filename).name != filename or \
       filename in (".", "..") or "\\" in filename or "\x00" in filename:
        raise ValueError("Only a .wav filename inside the audition root is allowed")
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Audition root must be a directory")
    candidate = root / filename
    if candidate.is_symlink() or not candidate.exists():
        raise PermissionError("No symlink or missing audio in audition root")
    if not stat.S_ISREG(candidate.lstat().st_mode):
        raise PermissionError("Only a regular recorded WAV is permitted")
    fd = os.open(candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 44 <= info.st_size <= MAX_WAV_BYTES:
            raise ValueError("Real WAV file size outside review bounds")
        return os.fdopen(fd, "rb")
    except Exception:
        os.close(fd)
        raise


def inspect_real_wav(root, filename):
    """Independently parse PCM samples, inspect dynamics; never infer acting.

    Uses stdlib wave and streaming bounded PCM readback; no FFmpeg,
    external binary, or model dependency. Does not turn volume into emotion.
    """
    with _real_audio_file(Path(root), filename) as file:
        full_sha = sha256()
        while True:
            block = file.read(65536)
            if not block:
                break
            full_sha.update(block)
        file.seek(0)
        with wave.open(file, "rb") as wav:
            if wav.getcomptype() != "NONE":
                raise ValueError("Compressed or non-PCM WAV is not accepted")
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            duration = frames / sample_rate if sample_rate else 0
            if channels not in (1, 2) or width not in (2, 3) or \
               sample_rate not in RATES or not MIN_SECONDS <= duration <= MAX_SECONDS:
                raise ValueError("Unsupported or out-of-bounds actual PCM format")
            max_value = float((1 << (width * 8 - 1)) - 1)
            peak = 0.0
            sum_sq = 0.0
            low = 0
            clipped = 0
            samples = 0
            while True:
                block = wav.readframes(4096)
                if not block:
                    break
                if len(block) % width:
                    raise ValueError("Incomplete PCM sample")
                for offset in range(0, len(block), width):
                    val = int.from_bytes(block[offset:offset+width], "little", signed=True)
                    a = abs(val) / max_value
                    peak = max(peak, a)
                    sum_sq += a * a
                    low += a < 0.005
                    clipped += a >= 0.999
                    samples += 1
            if samples != frames * channels:
                raise ValueError("Truncated source WAV PCM payload")
            return {
                "format": "nvp.film03.independent_pcm_readback.v1",
                "actual_file_sha256": full_sha.hexdigest(),
                "sample_rate": sample_rate, "channels": channels,
                "pcm_bits": width * 8, "sample_frames": frames,
                "duration_s": round(duration, 6),
                "peak_dbfs": round(20 * math.log10(max(peak, 1e-12)), 3),
                "rms_dbfs": round(20 * math.log10(max(math.sqrt(sum_sq / samples), 1e-12)), 3),
                "near_silent_sample_fraction": round(low / samples, 6),
                "clipped_sample_fraction": round(clipped / samples, 6),
                "pronunciation_verified": False,
                "emotion_verified": False,
                "speaker_identity_verified": False,
                "whisper_verified": False,
                "real_human_review_required": True,
            }


def record_candidate(case, root, filename, *, producer, declared_wav_sha256):
    """Record existing external real-audio evidence; never execute producer."""
    if type(case) is not dict or case.get("format") != FORMAT or \
       case.get("lab_only_not_permission_to_generate_or_approve") is not True:
        raise ValueError("Only a canonical offline audition case may be evaluated")
    required = {"provider_id", "model_id", "model_revision",
                "model_execution_receipt_sha256", "original_reference_sha256"}
    if type(producer) is not dict or set(producer) != required:
        raise ValueError("External producer provenance must be complete and exact")
    for key in ("provider_id", "model_id", "model_revision"):
        if type(producer[key]) is not str or not SLUG.fullmatch(producer[key]):
            raise ValueError("Invalid provenance field " + key)
    for key in required - {"provider_id", "model_id", "model_revision"}:
        _sha(producer[key])
    _sha(declared_wav_sha256)
    if producer["original_reference_sha256"] != case["voice_reference_sha256"]:
        raise PermissionError("Producer audition references the wrong VoiceID source")
    sound = inspect_real_wav(root, filename)
    if sound["actual_file_sha256"] != declared_wav_sha256:
        raise PermissionError("Real recorded WAV bytes differ from claimed execution artifact")
    candidate = {
        "format": FORMAT, "case_sha256": digest(case),
        "case": case, "producer": dict(producer), "readback": sound,
        "review_state": "UNREVIEWED_EXPERIMENT",
        "run_receipt_independently_verified": False,
        "film_workforce_and_tts_qualified": False,
        "director_take_approved": False,
        "no_native_speech_worker_executed": True,
    }
    return {**candidate, "candidate_sha256": digest(candidate)}


def record_listening_review(candidate, *, reviewer_id, ratings, notes):
    """Record supplied listening scores; identity/authenticity remain unverified."""
    if type(candidate) is not dict or candidate.get("format") != FORMAT or \
       candidate.get("candidate_sha256") != digest({
           k: v for k, v in candidate.items() if k != "candidate_sha256"}):
        raise PermissionError("Audition candidate receipt was altered")
    _id(reviewer_id, "human reviewer ID")
    if type(ratings) is not dict or set(ratings) != set(RUBRIC):
        raise ValueError("Complete consistent blinded listening rubric required")
    for value in ratings.values():
        if type(value) is not int or not 1 <= value <= 5:
            raise ValueError("Review scores must be integers 1..5, not model claims")
    notes = bounded(notes, "real human listening observations", max_length=2400)
    if len(notes) < 30:
        raise ValueError("Specific listening notes required")
    result = {
        "format": "nvp.film03.audition_listening_review.v1",
        "candidate_sha256": candidate["candidate_sha256"],
        "reviewer_id": reviewer_id, "ratings": dict(sorted(ratings.items())),
        "notes": notes,
        "reviewer_identity_authenticated": False,
        "qualified_provider": False,
        "approved_cinematic_take": False,
    }
    return {**result, "review_sha256": digest(result)}


def compare_auditions(candidates, reviews):
    """Evidence table, NOT a ranking/approval by metadata or synthetic tests."""
    if type(candidates) is not list or not candidates or len(candidates) > 12:
        raise ValueError("Compare 1..12 source-bound auditory auditions")
    first_case = candidates[0]["case_sha256"]
    seen = set()
    rows = []
    for candidate in candidates:
        if candidate.get("candidate_sha256") != digest({
                k: v for k, v in candidate.items() if k != "candidate_sha256"}):
            raise PermissionError("Audition candidate receipt was altered")
        if candidate["case_sha256"] != first_case:
            raise PermissionError("Do not compare different ActorIDs, words or directions")
        sha = candidate["candidate_sha256"]
        if sha in seen:
            raise ValueError("Repeated audition evidence")
        seen.add(sha)
        qualified = [r for r in reviews if r.get("candidate_sha256") == sha]
        for review in qualified:
            if review.get("review_sha256") != digest({
                    k: v for k, v in review.items() if k != "review_sha256"}):
                raise PermissionError("Listening review SHA did not match its content")
            if review.get("reviewer_identity_authenticated") is not False:
                raise PermissionError("Unauthenticated review cannot claim authentication")
        if len({r.get("reviewer_id") for r in qualified}) != len(qualified):
            raise ValueError("Repeated reviewer is not independent evidence")
        rows.append({
            "candidate_sha256": sha,
            "provider_id": candidate["producer"]["provider_id"],
            "model_id": candidate["producer"]["model_id"],
            "actual_wav_sha256": candidate["readback"]["actual_file_sha256"],
            "review_count": len(qualified),
            "descriptive_mean_rubric": (
                round(sum(sum(r["ratings"].values()) / len(RUBRIC)
                          for r in qualified) / len(qualified), 3)
                if qualified else None),
            "provider_qualified": False,
        })
    return {
        "format": "nvp.film03.real_voice_audition_comparison.v1",
        "case_sha256": first_case,
        "rows": rows,
        "measured_acoustics_do_not_prove_acting_quality": True,
        "reviewer_authentication_and_independent_listening_not_yet_verified": True,
        "provider_qualification_and_human_director_approval_remain_open": True,
        "required_real_audio_capabilities": sorted(REQUIRED_QUALITY),
    }
