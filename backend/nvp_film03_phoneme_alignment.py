"""FILM03-09C: original-film-audio -> phoneme alignment -> viseme candidates.

Uses the existing original PCM/FilmIndex and OS-contained worker execution.
This is real phoneme alignment only when an actual reviewed external MFA
acoustic model has executed and its genuine output passes independent checks.
No TTS, FFmpeg, legal administration or emotional face matching is added.

MFA is NOT bundled. Native executable/model acceptance remains separately
gated. A fixture JSON tests the importer, NOT the acoustic model's accuracy.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import wave

from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE
from backend.nvp_film03_dialogue_manager import ActorDialogueManager
from backend.nvp_film03_independent_facial_direction import (
    FORMAT as FACE_FORMAT, VISEMES, TICKS_PER_SAMPLE,
)
from backend.nvp_film03_voice_conversion_intent import verified_guide_signal
from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid
from backend.nvp_worker_containment import launch_contained

FORMAT = "nvp.film03.real_audio_phoneme_alignment.v1"
OUTPUT_LIMIT = 512 * 1024
MAX_INTERVALS = 1200
MAX_SPEECH_SECONDS = 180
SILENCE = frozenset({"", "sil", "sp", "spn", "silence", "<eps>"})
# ARPABET/CMU phones produced by the *reviewed English pronunciation dictionary*.
# A different acoustic model/phone set requires its own reviewed mapping.
PHONES = {
    "P": "MBP", "B": "MBP", "M": "MBP",
    "F": "FV", "V": "FV",
    "TH": "TH", "DH": "TH",
    "T": "DD", "D": "DD",
    "K": "KG", "G": "KG", "NG": "KG",
    "CH": "CH", "JH": "CH", "SH": "CH", "ZH": "CH",
    "S": "SS", "Z": "SS",
    "N": "NN",
    "R": "RR", "ER": "RR",
    "AA": "AA", "AE": "AA", "AH": "AA", "AO": "AA",
    "EH": "E", "EY": "E",
    "IH": "IH", "IY": "IH",
    "OW": "OH", "OY": "OH",
    "UW": "OU", "UH": "OU", "AW": "OU", "AY": "AA",
    "W": "WQ", "Y": "WQ", "HH": "rest",
    "L": "L",
}
assert set(PHONES.values()) <= VISEMES
ARPA = re.compile(r"[A-Z]{1,3}[012]?\Z")
WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _words(text):
    if type(text) is not str or not text.strip() or len(text) > 3000:
        raise ValueError("Original screenplay must contain bounded dialogue")
    words = [w.lower().replace("'", "") for w in WORD.findall(text)]
    if not words:
        raise ValueError("No spoken words in original screenplay")
    return words


def _sample(seconds, total, *, endpoint=False):
    if type(seconds) not in (int, float, str, Decimal):
        raise ValueError("Acoustic alignment time must be numeric")
    try:
        value = Decimal(str(seconds))
    except InvalidOperation as error:
        raise ValueError("Invalid acoustic model time") from error
    if not value.is_finite() or value < 0:
        raise ValueError("Non-finite or negative acoustic time")
    pos = int((value * SAMPLE_RATE).to_integral_value(rounding=ROUND_HALF_UP))
    if pos > total or (pos == total and not endpoint):
        raise ValueError("Alignment exceeds original PCM source duration")
    return pos


def _intervals(entries, total, *, phones):
    if type(entries) is not list or not 1 <= len(entries) <= MAX_INTERVALS:
        raise ValueError("Missing or excessive actual acoustic alignment intervals")
    result = []
    last_end = 0
    for item in entries:
        if type(item) is not list or len(item) != 3 or type(item[2]) is not str:
            raise ValueError("Unexpected MFA interval record")
        start = _sample(item[0], total)
        end = _sample(item[1], total, endpoint=True)
        if start < last_end or end <= start:
            raise ValueError("Overlapping, empty or out-of-order phoneme timing")
        last_end = end
        label = item[2].strip()
        if not label and phones:
            # Silence gaps belong to the audio signal, not an invented phoneme.
            continue
        if not label and not phones:
            continue
        if len(label) > 60:
            raise ValueError("Unbounded acoustic interval label")
        if phones:
            if label.lower() in SILENCE:
                continue
            canonical = label.upper()
            if not ARPA.fullmatch(canonical):
                raise ValueError("Non-ARPABET phone requires a reviewed phoneme mapper")
            bare = re.sub(r"[012]$", "", canonical)
            if bare not in PHONES:
                raise ValueError("Unknown acoustic phone; no invented viseme mapping")
            result.append({
                "start_sample": start, "end_sample": end,
                "phoneme": canonical, "viseme": PHONES[bare],
                "weight": 1.0,
                "alignment_result_not_rendered": True,
            })
        else:
            normalized = label.lower().replace("'", "")
            if not WORD.fullmatch(label) or normalized in {"unk", "spn"}:
                raise ValueError("Unaligned or unknown screenplay word")
            result.append({
                "start_sample": start, "end_sample": end,
                "text": label, "normalized": normalized,
            })
    if not result:
        raise ValueError("Acoustic aligner returned no phonetic observations")
    return result


def import_mfa_json(content, *, exact_script_text, pcm_sample_count):
    """Independently validate exact MFA JSON against the chosen screenplay.

    A correctly-shaped result is *not* proof MFA ran or correctly heard the
    actor. A genuine reviewed OS execution receipt is required separately.
    """
    if type(content) is not bytes or not 0 < len(content) <= OUTPUT_LIMIT:
        raise ValueError("Missing or oversized MFA native output")
    if type(pcm_sample_count) is not int or not (
        SAMPLE_RATE // 5 <= pcm_sample_count <= MAX_SPEECH_SECONDS * SAMPLE_RATE
    ):
        raise ValueError("Original PCM duration outside phoneme review bounds")
    try:
        raw = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Corrupt native MFA JSON output") from exc
    if type(raw) is not dict or set(raw) != {"start", "end", "tiers"}:
        raise ValueError("MFA output must have exact start, end and speaker tiers")
    tiers = raw["tiers"]
    if type(tiers) is not dict or set(tiers) != {"words", "phones"}:
        raise ValueError("Single-actor recording requires exact MFA word/phone tiers")
    if _sample(raw["start"], pcm_sample_count, endpoint=True) != 0:
        raise ValueError("MFA audio alignment must start at original audio zero")
    endpoint = _sample(raw["end"], pcm_sample_count, endpoint=True)
    if abs(endpoint - pcm_sample_count) > SAMPLE_RATE // 50:
        raise ValueError("MFA alignment duration differs from real recorded audio")
    for name in ("words", "phones"):
        row = tiers[name]
        if type(row) is not dict or set(row) != {"type", "entries"} or \
           row["type"] != "interval":
            raise ValueError("Unexpected or unbounded MFA tier schema")
    words = _intervals(tiers["words"]["entries"], pcm_sample_count, phones=False)
    phones = _intervals(tiers["phones"]["entries"], pcm_sample_count, phones=True)
    if [x["normalized"] for x in words] != _words(exact_script_text):
        raise PermissionError(
            "Acoustic word alignment differs from canonical selected screenplay")
    for word in words:
        if not any(
            p["start_sample"] < word["end_sample"] and
            p["end_sample"] > word["start_sample"] for p in phones
        ):
            raise ValueError("No acoustic phone covers a claimed spoken word")
    return {
        "format": FORMAT, "sample_rate_hz": SAMPLE_RATE,
        "source_sample_count": pcm_sample_count,
        "word_intervals": words, "phoneme_intervals": phones,
        "viseme_candidates": [
            {key: row[key] for key in (
                "start_sample", "end_sample", "phoneme", "viseme", "weight")}
            for row in phones
        ],
        "ticks_per_sample": TICKS_PER_SAMPLE,
        "exact_script_word_sequence_verified_against_alignment_labels": True,
        "source_audio_automatically_transcribed": False,
        "audio_to_phoneme_timing_independently_accuracy_scored": False,
        "rigged_mouth_motion_rendered": False,
        "director_expressions_preserved": True,
    }


def source_alignment_plan(index: FilmIndex, pid, dialogue_route,
                          face_direction_id, face_revision):
    """Pin original audio + exact spoken script before supervised alignment."""
    if not isinstance(index, FilmIndex):
        raise TypeError("Native FilmIndex required")
    _require_pid(pid)
    _id(face_direction_id, "director facial direction")
    if type(face_revision) is not int or face_revision < 1:
        raise ValueError("Positive facial direction revision required")
    routed = ActorDialogueManager(index).route(pid, dialogue_route)
    facial = index.read_revision(pid, face_direction_id, face_revision)
    data = facial["data"]
    if facial["kind"] != "performance" or data.get("format") != FACE_FORMAT:
        raise PermissionError("Not an original voice-sourced facial direction")
    required = {
        "actor_id": routed["actor_id"],
        "voice_id": routed["canonical_voice_id"],
        "source_take_sha256": routed["source_take_sha256"],
        "script_line_id": routed["script_line_id"],
        "exact_original_script_text_sha256":
            sha256(routed["exact_director_selected_text"].encode("utf8")).hexdigest(),
    }
    if any(data.get(k) != value for k, value in required.items()):
        raise PermissionError("Face, audio and screenplay belong to different actor/take")
    audio = data["audio_source"]
    rechecked = verified_guide_signal(
        index, pid, audio["source_id"], audio["revision"])
    if rechecked != audio:
        raise RuntimeError("Original dialogue signal changed since facial direction")
    return {
        "format": FORMAT, "project_id": pid,
        "actor_id": routed["actor_id"], "voice_id": routed["canonical_voice_id"],
        "exact_script_text": routed["exact_director_selected_text"],
        "script_sha256": required["exact_original_script_text_sha256"],
        "source_take_sha256": routed["source_take_sha256"],
        "source_take_id": routed["source_take_id"],
        "face_direction_id": face_direction_id,
        "face_direction_revision": face_revision,
        "face_direction_sha256": facial["document_sha256"],
        "audio_source_id": audio["source_id"],
        "audio_source_revision": audio["revision"],
        "audio_source_document_sha256": audio["source_document_sha256"],
        "original_pcm_sha256": audio["pcm16le_sha256"],
        "sample_count": audio["sample_count"],
        "sample_rate_hz": SAMPLE_RATE,
        "speech_is_final_selected_film_audio": False,
        "language": "en-US",
        "phoneme_model_already_executed": False,
    }


def _pinned_file(path, expected_sha):
    _sha(expected_sha)
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise PermissionError("Reviewed aligner binary/model must be a regular file")
    p = p.resolve(strict=True)
    if not stat.S_ISREG(p.stat().st_mode) or p.is_symlink():
        raise PermissionError("No external model symlink accepted")
    h = sha256()
    with p.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != expected_sha:
        raise PermissionError("Acoustic model/executable hash differs from reviewed original")
    return p


def run_reviewed_mfa_one(index, plan, *, work_root, mfa_binary, mfa_sha256,
                         dictionary_file, dictionary_sha256,
                         acoustic_model_file, acoustic_model_sha256,
                         timeout_seconds=240, candidate_object_id=None):
    """Real OS-contained single-utterance alignment; no unreviewed fallback.

    Only a trusted native host supplies binary/model paths/hashes and scoped
    work_root. Linux requires a working cgroup v2 custody layer. NVP does not
    download or bundle an aligner on demand. Actual MFA/FFmpeg-free dependency
    acceptance is a separate required gate.
    """
    if type(plan) is not dict or plan.get("format") != FORMAT:
        raise PermissionError("An exact original audio alignment plan is required")
    if type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 900:
        raise ValueError("Bounded native model execution deadline required")
    if candidate_object_id is not None:
        _id(candidate_object_id, "derived lip-sync candidate")
        if candidate_object_id in {
            plan["face_direction_id"], plan["audio_source_id"],
            plan["source_take_id"]
        }:
            raise ValueError("Derived lip-sync candidate cannot alias original film source")
    binary = _pinned_file(mfa_binary, mfa_sha256)
    dictionary = _pinned_file(dictionary_file, dictionary_sha256)
    acoustic = _pinned_file(acoustic_model_file, acoustic_model_sha256)
    root = Path(work_root)
    if root.is_symlink() or not root.is_absolute() or not root.is_dir():
        raise PermissionError("Native host must supply an existing private alignment directory")
    root = root.resolve(strict=True)
    if any(p.is_relative_to(root) for p in (binary, dictionary, acoustic)):
        raise PermissionError("Untrusted workspace cannot provide an executable or acoustic model")
    if type(plan["sample_count"]) is not int or not (
        SAMPLE_RATE // 5 <= plan["sample_count"] <= MAX_SPEECH_SECONDS * SAMPLE_RATE):
        raise ValueError("Invalid source sample length")
    doc = verified_guide_signal(
        index, plan["project_id"], plan["audio_source_id"],
        plan["audio_source_revision"])
    if (doc["source_document_sha256"] != plan["audio_source_document_sha256"]
            or doc["pcm16le_sha256"] != plan["original_pcm_sha256"]
            or doc["sample_count"] != plan["sample_count"]):
        raise PermissionError("Original sound bytes changed before acoustic execution")
    with tempfile.TemporaryDirectory(prefix="nvp-phoneme-", dir=root) as tmp:
        work = Path(tmp)
        wav = work / "original.wav"
        script = work / "original.txt"
        result = work / "phones.json"
        scratch = work / "mfa-temp"
        scratch.mkdir()
        source = RecordedSoundSources(index).describe(
            plan["project_id"], plan["audio_source_id"],
            plan["audio_source_revision"])["data"]
        h = sha256()
        with wave.open(str(wav), "wb") as sound:
            sound.setnchannels(1)
            sound.setsampwidth(2)
            sound.setframerate(SAMPLE_RATE)
            for item in source["chunks"]:
                pcm = index.get_blob(plan["project_id"], item["blob_sha256"])
                if len(pcm) != item["byte_count"]:
                    raise RuntimeError("Original PCM source changed mid-export")
                h.update(pcm)
                sound.writeframesraw(pcm)
        if h.hexdigest() != plan["original_pcm_sha256"]:
            raise RuntimeError("Original audio export did not match input source SHA")
        script.write_text(plan["exact_script_text"], encoding="utf8")
        args = [
            str(binary), "align_one", "--output_format", "json",
            "-t", str(scratch), "-j", "1",
            str(wav), str(script), str(dictionary), str(acoustic), str(result),
        ]
        stdout = work / "stdout.log"
        stderr = work / "stderr.log"
        process = None
        with stdout.open("wb") as out, stderr.open("wb") as err:
            try:
                process = launch_contained(
                    args, cwd=work, stdout=out, stderr=err,
                    memory_mb=8192, linux_cgroup_tree_required=True,
                )
                rc = process.wait(timeout=timeout_seconds)
                if rc != 0:
                    raise RuntimeError("Reviewed acoustic aligner failed without valid output")
            except (subprocess.TimeoutExpired, TimeoutError) as exc:
                if process is not None:
                    process.terminate_tree()
                raise RuntimeError("Acoustic alignment exceeded native time budget") from exc
            finally:
                if process is not None:
                    process.close()
        if result.is_symlink() or not result.is_file() or \
           not 0 < result.stat().st_size <= OUTPUT_LIMIT:
            raise RuntimeError("No bounded, regular native acoustic alignment output")
        output = result.read_bytes()
        accepted = import_mfa_json(
            output, exact_script_text=plan["exact_script_text"],
            pcm_sample_count=plan["sample_count"])
        # Store the actual native model JSON bytes, NOT just a declarative
        # "model ran" boolean. Downstream face rigs reopen and reparse this.
        native_output_blob_sha = index.put_blob(
            plan["project_id"], output, media_type="application/json")
        if native_output_blob_sha != sha256(output).hexdigest():
            raise RuntimeError("Original acoustic output blob differs from executed output")
        receipt = {
            **accepted,
            "source_plan": plan,
            "native_acoustic_model_executed": True,
            "executed_mfa_binary_sha256": mfa_sha256,
            "executed_acoustic_model_sha256": acoustic_model_sha256,
            "executed_dictionary_sha256": dictionary_sha256,
            "native_output_sha256": sha256(output).hexdigest(),
            "native_output_blob_sha256": native_output_blob_sha,
            "native_result_exit_code": 0,
            "output_is_viseme_candidates_not_rig_animation": True,
            "manual_lip_sync_review_pending": True,
        }
        if candidate_object_id is None:
            return receipt
        # Only successful in-process, source-locked native alignment publishes
        # derived candidate keyframes. Never promote these to an approved Take.
        face = index.read_revision(
            plan["project_id"], plan["face_direction_id"],
            plan["face_direction_revision"])
        sound = verified_guide_signal(
            index, plan["project_id"], plan["audio_source_id"],
            plan["audio_source_revision"])
        if (face["document_sha256"] != plan["face_direction_sha256"] or
                sound["pcm16le_sha256"] != plan["original_pcm_sha256"] or
                sound["source_document_sha256"] != plan["audio_source_document_sha256"]):
            raise PermissionError("Original actor, face direction or PCM changed after alignment")
        published = index.register_revision(
            plan["project_id"], candidate_object_id, "performance",
            {**receipt, "review_state": "UNREVIEWED_PHONEME_CANDIDATE",
             "director_selected": False, "real_rig_animation_produced": False},
            expected_revision=0,
            dependencies=[
                {"object_id": plan["audio_source_id"],
                 "revision": plan["audio_source_revision"], "role": "audio"},
                {"object_id": plan["face_direction_id"],
                 "revision": plan["face_direction_revision"], "role": "performance"},
                {"object_id": plan["source_take_id"], "revision": 1,
                 "role": "source_take"},
            ],
        )
        return {
            **receipt,
            "candidate_id": candidate_object_id,
            "candidate_revision": published["revision"],
            "candidate_document_sha256": published["document_sha256"],
            "original_sources_preserved": True,
            "film_take_approved": False,
        }
