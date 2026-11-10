"""PLAN-02-E native 30-second film witness, inside the actual installed NVP.exe.

Create an original, recorded-P-C-M-shaped TEST FIXTURE and real OpenUSD scene
with three continuous authored camera intervals and a moving USD sphere.
This synthesized acceptance signal is not represented as physical microphone
capture or creator approval. The test independently reopens real SQLite and
streams ALL 1,440,000 native spatial PCM samples from the frozen source.

No PNG images, soundtracks, source frames, FFmpeg, or synthetic scene evaluator
are stored as the authoritative film.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import math
import os
import struct
import sys
import tempfile

from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_plan02e_continuous import (
    Continuous30SecondFilm, DURATION_TICK, AUDIO_SAMPLES, FRAME_COUNT,
    RATE, SECONDS,
)
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND as T

ROOT_NAME = "plan02e-native-restart"
TAKE_ID = "OriginalThirtySecondFilm"
SCENE_ID = "OriginalThirtySecondScene"
TIMELINE_ID = "OriginalThirtySecondEvents"
SOUND_ID = "OriginalThirtySecondPCM"
CAMERAS = ["/World/CameraA", "/World/CameraB", "/World/CameraC"]


def _source_pcm():
    """An explicit test-only, 48 kHz original recording fixture."""
    for second in range(SECONDS):
        # A 360Hz tone with 3 authored ten-second passages and nonzero level.
        freq = (330, 440, 550)[second // 10]
        wave = (int(6500 * math.sin(2 * math.pi * freq * i / RATE))
                for i in range(RATE))
        yield struct.pack("<" + "h" * RATE, *wave)


def create(index, pid):
    recorded = RecordedSoundSources(index)
    original_hasher = sha256()
    def chunks():
        for block in _source_pcm():
            original_hasher.update(block)
            yield block
    source = recorded.publish(pid, SOUND_ID, chunks())
    asset = OpenUSDAssetRegistry(index).publish(
        pid, "MovingSphereAsset", shape="sphere", size_m=1.5,
    )
    scene = OpenUSDSceneBridge(index).publish(
        pid, SCENE_ID, prims=[
            {"path": CAMERAS[0], "role": "camera", "position": [-1, 0, 0]},
            {"path": CAMERAS[1], "role": "camera", "position": [0, 0, 0]},
            {"path": CAMERAS[2], "role": "camera", "position": [1, 0, 0]},
            {"path": "/World/Emitter", "role": "prop", "position": [0, 0, -6]},
        ], curves=[
            {"path": "/World/Emitter", "samples": [
                {"tick": 0, "position": [-1.1, 0, -6]},
                {"tick": 15 * T, "position": [1.1, 0, -6]},
                {"tick": DURATION_TICK - 1, "position": [-0.2, 0, -6]},
            ]},
        ], asset_bindings=[{
            "path": "/World/Emitter",
            "asset_id": "MovingSphereAsset",
            "asset_revision": asset["revision"],
        }], native_schemas=True,
    )
    events = [{
        "event_id": f"CameraShot{idx + 1}",
        "event_kind": "camera",
        "subject_id": "Director",
        "start_tick": idx * 10 * T,
        "end_tick": (idx + 1) * 10 * T,
        "source_id": SCENE_ID,
        "source_revision": 1,
        "payload": {"usd_prim_path": CAMERAS[idx],
                    "film_continuous": True,
                    "original_scene": True},
    } for idx in range(3)]
    events.append({
        "event_id": "OriginalContinuousSound",
        "event_kind": "sound",
        "subject_id": "Speaker",
        "start_tick": 0, "end_tick": DURATION_TICK,
        "source_id": SOUND_ID, "source_revision": 1,
        "payload": {"usd_prim_path": "/World/Emitter",
                    "gain": 1.0, "original_recording": True},
    })
    timeline = TemporalLedger(index).publish(
        pid, TIMELINE_ID, events, duration_tick=DURATION_TICK,
    )
    take = OpenUSDTakeCapture(
        index,
        # CI/fixture-only authorization. It is NOT a real native OS consent.
        verify_creator_action=lambda event, scope:
            event == "test_only_original_fixture"
            and scope["operation"] == "nvp.freeze.usd_temporal_take.v1"
            and scope["duration_tick"] == DURATION_TICK,
    ).freeze(
        pid, TAKE_ID, scene_id=SCENE_ID, scene_revision=1,
        timeline_id=TIMELINE_ID, timeline_revision=1,
        sample_ticks=[0, 10 * T, 20 * T, DURATION_TICK - 1],
        creator_event="test_only_original_fixture",
    )
    return {
        "project_id": pid,
        "take_sha256": take["document_sha256"],
        "scene_sha256": scene["document_sha256"],
        "timeline_sha256": timeline["document_sha256"],
        "original_pcm_sha256": original_hasher.hexdigest(),
        "audio_manifest_sha256": source["document_sha256"],
        "human_os_consent_observed": False,
        "real_microphone_capture_observed": False,
    }


def _verify_original(index, receipt):
    pid = receipt["project_id"]
    source = RecordedSoundSources(index)
    total = 0
    digest = sha256()
    while total < AUDIO_SAMPLES:
        n = min(4096, AUDIO_SAMPLES - total)
        digest.update(source.read(pid, SOUND_ID, 1, total, n))
        total += n
    if (digest.hexdigest() != receipt["original_pcm_sha256"]
            or source.describe(pid, SOUND_ID, 1)[
                "document_sha256"] != receipt["audio_manifest_sha256"]
            or index.read_revision(pid, TAKE_ID, 1)[
                "document_sha256"] != receipt["take_sha256"]
            or index.read_revision(pid, SCENE_ID, 1)[
                "document_sha256"] != receipt["scene_sha256"]
            or index.read_revision(pid, TIMELINE_ID, 1)[
                "document_sha256"] != receipt["timeline_sha256"]):
        raise RuntimeError("Independent reopen changed original USD/PCM source")


def _accept(index, receipt, exhaustive):
    film = Continuous30SecondFilm(
        index, receipt["project_id"], TAKE_ID, receipt["take_sha256"],
        listener_path=CAMERAS[1],
    )
    try:
        report = film.verify_continuity(read_all_audio=exhaustive)
        counts = report["camera_sample_counts"]
        if (report["picture_sample_instants_checked"] != FRAME_COUNT
                or len(counts) != 3 or
                any(count != 240 for count in counts.values())
                or len(report["actual_native_png_probes"]) < 6
                or not all(item["png_bytes"] > 100
                           for item in report["actual_native_png_probes"])
                or report["original_source_modified"] is not False
                or report["ffmpeg_used"] is not False):
            raise RuntimeError("Original thirty-second picture continuity failed")
        before = film.picture_at_frame(0)
        after = film.picture_at_frame(FRAME_COUNT - 1)
        if (before["png_sha256"] == after["png_sha256"]
                or before["camera_path"] == after["camera_path"]):
            raise RuntimeError("Moving original OpenUSD film was a frozen picture")
        if exhaustive:
            if (report["audio_samples_evaluated"] != AUDIO_SAMPLES
                    or report["non_silent_audio_windows"] < 300
                    or not report["audio_pcm_sha256"]):
                raise RuntimeError("Full thirty-second PCM sequence not streamed")
        # Detect the exact original Film Time transitions and last sample.
        for tick, expected in (
            (10 * T - 1, CAMERAS[0]),
            (10 * T, CAMERAS[1]),
            (20 * T - 1, CAMERAS[1]),
            (20 * T, CAMERAS[2]),
            (DURATION_TICK - 1, CAMERAS[2]),
        ):
            if film.camera_at(tick)["camera_path"] != expected:
                raise RuntimeError("Native camera transition lost source Film Time")
        end = film.audio_window(AUDIO_SAMPLES - 256, 256)
        if end["next_tick"] != str(DURATION_TICK):
            raise RuntimeError("Final PCM buffer ends before exact Film Time")
        try:
            film.audio_window(AUDIO_SAMPLES, 1)
        except ValueError:
            pass
        else:
            raise RuntimeError("Native film emitted samples beyond its thirty seconds")
        return report
    finally:
        film.close()


def run_installed_plan02e_smoke(phase="ephemeral"):
    if phase not in ("ephemeral", "create", "reopen"):
        raise ValueError("Unknown native film installed phase")
    if phase == "ephemeral":
        tmp = tempfile.TemporaryDirectory(prefix="nvp-plan02e-installed-")
        base = Path(tmp.name)
    else:
        home = os.environ.get("NVP_HOME")
        if not home or not Path(home).is_absolute():
            raise PermissionError("An absolute approved test NVP_HOME is required")
        base = Path(home) / ROOT_NAME
        tmp = None
        if base.is_symlink():
            raise PermissionError("Source witness root must not be symlinked")
        if phase == "create":
            base.mkdir(parents=True, exist_ok=False)
    try:
        database = base / "studio.sqlite3"
        marker = base / "original-receipt.json"
        if phase == "reopen":
            receipt = json.loads(marker.read_text(encoding="utf-8"))
            index = FilmIndex(Studio(database))
            _verify_original(index, receipt)
            report = _accept(index, receipt, exhaustive=False)
            _verify_original(index, receipt)
        else:
            studio = Studio(database)
            pid = studio.create_project(
                "Thirty-second original OpenUSD film",
                "True continuous source timeline; no movie proxy",
            )["id"]
            index = FilmIndex(studio)
            receipt = create(index, pid)
            report = _accept(index, receipt, exhaustive=True)
            _verify_original(index, receipt)
            if phase == "create":
                marker.write_text(
                    json.dumps(receipt, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                (base / "playback-receipt.json").write_text(
                    json.dumps(report, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
        if sys.stdout is not None:
            print(
                "NVP_PLAN02E_30S_INSTALLED_NATIVE_SOURCE_PASS "
                + phase + " " + receipt["take_sha256"],
                flush=True,
            )
        return 0
    finally:
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=("ephemeral", "create", "reopen"),
                   default="ephemeral")
    options = p.parse_args()
    raise SystemExit(run_installed_plan02e_smoke(options.phase))
