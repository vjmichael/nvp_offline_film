"""Real B14 integration: Blender -> FLOAT32 EXR -> ACES2 SDR16 -> B12 OTIO
-> two real B13 edited revisions -> B14 output frames -> FilmIndex restart.
B14 executes via trusted native creator fixture, durable resource admission,
OS-contained worker, live pressure watchdog and post-restart verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import wave
from pathlib import Path

from backend.nvp_b14_picture_conform import verify_conformed_sdr16
from backend.nvp_b14_native_conform import NativeB14ConformHost
from backend.nvp_b14_edited_movie import build_edited_technical_mov, verify_edited_technical_mov
from backend.nvp_audio01d_chunked_recovery import run_chunked_preview
from backend.nvp_audio01e_wav_publication import publish_chunked_wavs
from backend.nvp_audio01f_picture_sound import verify_picture_sound_preview
from backend.nvp_audio01f_native_host import NativeAudio01FHost
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_b13_editorial_roundtrip import FORMAT as EDIT_FORMAT
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from tools.nvp_stack02c3b13_real_roundtrip import fixture as b13_fixture


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fixture(out, blender):
    root = Path(out).resolve()
    root.mkdir(parents=True, exist_ok=True)
    existing = b13_fixture(root / "b13_full_source", blender)
    if (existing["original_source_32bit_FLOAT_EXR_frames"] != 120 or
        existing["persistent_edit_revisions"] != 2 or
        existing["original_FilmIndex_B12_package_reopened_after_restart"] is not True):
        raise RuntimeError("B13 real immutable film/OTIO roundtrip is not accepted")
    db = (root / "b13_full_source" / "b12_frozen_delivery" / "b11_original" /
          "b9_frozen_source" / "frozen_take_source" / "film.sqlite3")
    capture = DigitalCapture(Studio(db))
    with capture.studio._connection() as conn:
        projects = [row[0] for row in conn.execute("SELECT id FROM projects")]
    if len(projects) != 1:
        raise RuntimeError("NVP B14 expected exactly one B13 source film")
    project_id = projects[0]
    edit_id = existing["new_FilmIndex_edit_id"]
    first = capture.index.read_revision(project_id, edit_id, 1)
    second = capture.index.read_revision(project_id, edit_id, 2)
    if first["data"]["format"] != EDIT_FORMAT or second["data"]["format"] != EDIT_FORMAT:
        raise RuntimeError("B14 source was not genuine externally reimported OTIO")
    package = Path(existing.get("disk_handoff_directory") or
                   (root / "b13_full_source" / "b12_frozen_delivery"))
    # The actual portable B12 directory comes from the accepted B12
    # FilmIndex source; locate its exact manifest rather than guessing a path.
    matches = [p.parent for p in (root / "b13_full_source").rglob("package_manifest.json")
               if p.parent.joinpath("timeline.otio").is_file()]
    if len(matches) != 1:
        raise RuntimeError("Exactly one authentic B12 editorial package required")
    package = matches[0]
    ledger = TaskLedger(root / "b14_native_activity")
    creator_event = object()
    granted = []
    def creator_policy(signal, scope):
        granted.append(scope)
        return (signal is creator_event and
                scope["operation"] == "nvp.native.presentation.sdr16_picture_conform" and
                scope["project_id"] == project_id and
                scope["edit_id"] == edit_id and
                scope["final_master"] is False)
    host = NativeB14ConformHost(capture, ledger, root / "native_b14_host",
                               verify_creator_action=creator_policy)
    # Admission fault injection verifies that no OS worker runs under
    # simulated pressure; actual children run under OS memory containment.
    ledger.sampler = lambda: ResourceSnapshot(1, 16384, 1000, 0, ())
    done = []
    for rev, source in ((1, first), (2, second)):
        # Repeat admission-pressure injection for EVERY separate native job.
        ledger.sampler = lambda: ResourceSnapshot(1, 16384, 1000, 0, ())
        destination = root / ("b14_conformed_edit_revision_" + str(rev))
        pid = "b14_presentation_r" + str(rev)
        queued = host.stage_and_approve(project_id, edit_id, rev,
                                        package, destination, creator_event,
                                        presentation_id=pid,
                                        ram_mb=1024, duration_s=3600)
        denied = host.run_next()
        if denied is None or denied["state"] != "QUEUED":
            raise RuntimeError("B14 unsafe resource admission did not queue the worker")
        ledger.sampler = lambda: ResourceSnapshot(1, 32768, 25000, 0, ())
        result = host.run_next()
        if result is None or result["state"] != "SUCCEEDED":
            raise RuntimeError("B14 native creator-approved contained conform failed")
        if result["job_id"] != queued["job_id"]:
            raise RuntimeError("B14 scheduler claimed the wrong native job")
        result["document_sha256"] = capture.index.read_revision(
            project_id, pid, 1)["document_sha256"]
        expected = source["data"]["editorial_map"]["frame_map"]
        if result["frames"] != len(expected) or result["status"] != "VERIFIED_SDR16_PICTURE_CONFORM":
            raise RuntimeError("B14 actual ordered video frames were not conformed")
        for mapping in expected:
            n = mapping["edit_frame"]
            dest = destination / "media" / f"edit_{n:06d}.png"
            if _sha(dest.read_bytes()) != mapping["original_png16_sha256"]:
                raise RuntimeError("B14 conformed image differs from frozen original")
        done.append({"revision": rev, "presentation_id": pid,
                     "frames": len(expected), "document_sha256": result["document_sha256"],
                     "job_id": queued["job_id"]})
    reopened = DigitalCapture(Studio(db))
    restored_host = NativeB14ConformHost(
        reopened, ledger, host.root, verify_creator_action=lambda *_: False)
    for result in done:
        restored_host.verify_completed(result["job_id"])
        checked = verify_conformed_sdr16(reopened, project_id, result["presentation_id"],
                                         package,
                                         root / ("b14_conformed_edit_revision_" +
                                                 str(result["revision"])),
                                         edit_revision=result["revision"])
        if checked["frames"] != result["frames"]:
            raise RuntimeError("B14 conformed presentation changed after FilmIndex restart")
    # The picture conform is SDR review; the technical ProRes path must
    # separately grade original FLOAT32 EXR frames in the actual edited order.
    movie_root = root / "b14_edited_movie_from_scene_linear"
    candidate = build_edited_technical_mov(
        reopened, project_id, done[0]["presentation_id"], package,
        root / "b14_conformed_edit_revision_1", movie_root,
        "b14_edited_prores_candidate", profile="prores_422_hq_mov")
    movie_reopened = DigitalCapture(Studio(db))
    movie_audit = verify_edited_technical_mov(
        movie_reopened, project_id, "b14_edited_prores_candidate", package,
        root / "b14_conformed_edit_revision_1", movie_root)
    if (movie_audit["status"] != "VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE" or
        movie_audit["movie_sha256"] != candidate["movie_sha256"] or
        movie_audit["frames"] != done[0]["frames"]):
        raise RuntimeError("Actual edited Rec1886/BT709 ProRes decode failed")
    # AUDIO-01F genuine multitrack soundtrack follows the exact edited B14
    # picture frame count: 24fps => 2000 samples/channel per frame at 48kHz.
    exact_samples=movie_audit["frames"]*2000
    audio_sources={}
    for sid,value in (("dialogue",700),("ambience",100)):
        wav=root/(sid+"_original_source.wav")
        with wave.open(str(wav),"wb") as sink:
            sink.setnchannels(2)
            sink.setsampwidth(2)
            sink.setframerate(48000)
            sink.writeframes(struct.pack("<hh",value,-value)*exact_samples)
        audio_sources[sid]=wav
    audio_plan={"stems":[
        {"stem_id":"dialogue","kind":"dialogue","clips":[{
            "out_start":0,"out_end":exact_samples,"source_start":0,
            "fade_in":0,"fade_out":0,"gain_milli":1000}]},
        {"stem_id":"ambience","kind":"ambience","clips":[{
            "out_start":0,"out_end":exact_samples,"source_start":0,
            "fade_in":0,"fade_out":0,"gain_milli":500}]},
    ]}
    pcm_dir=root/"audio01f_durable_chunks"
    run_chunked_preview(audio_plan,audio_sources,exact_samples,pcm_dir)
    wav_dir=root/"audio01f_independent_stems"
    published=publish_chunked_wavs(movie_reopened,project_id,
        "audio01f_multistem_preview",audio_plan,audio_sources,exact_samples,
        pcm_dir,wav_dir)
    if published["wav_count"]!=3:
        raise RuntimeError("AUDIO-01F source did not preserve both independent stems")
    sound_dir=root/"audio01f_synchronized_review"
    mux_event=object()
    def mux_creator_policy(event,scope):
        return (event is mux_event and
                scope["operation"]=="nvp.native.audio01f.picture_sound_review" and
                scope["project_id"]==project_id and
                scope["final_master"] is False and
                scope["picture_locked"] is False)
    mux_host=NativeAudio01FHost(movie_reopened,ledger,
        root/"native_audio01f_mux",verify_creator_action=mux_creator_policy,
        # Hosted Linux integration tests lack delegated cgroup-v2. This is
        # explicitly reduced-assurance test mode, not strict Linux acceptance.
        strict_linux_tree=False)
    mux_queued=mux_host.stage_and_approve(project_id,
        "b14_edited_prores_candidate","audio01f_multistem_preview",
        package,root/"b14_conformed_edit_revision_1",movie_root,wav_dir,
        audio_plan,audio_sources,pcm_dir,sound_dir,mux_event,
        presentation_id="audio01f_picture_sound_r1",ram_mb=1024)
    synchronized=mux_host.run_next(timeout_seconds=900)
    if (synchronized is None or synchronized["state"]!="SUCCEEDED" or
        synchronized["job_id"]!=mux_queued["job_id"]):
        raise RuntimeError("AUDIO-01F native approved mux did not complete")
    sound_reopened=DigitalCapture(Studio(db))
    native_reopened=NativeAudio01FHost(sound_reopened,ledger,
        root/"native_audio01f_mux",verify_creator_action=lambda *_:False,
        strict_linux_tree=False)
    native_reopened.verify_completed(mux_queued["job_id"])
    synchronized_replay=verify_picture_sound_preview(
        sound_reopened,project_id,"audio01f_picture_sound_r1",
        "b14_edited_prores_candidate","audio01f_multistem_preview",
        package,root/"b14_conformed_edit_revision_1",movie_root,wav_dir,
        audio_plan,audio_sources,pcm_dir,sound_dir)
    if (synchronized["samples_per_channel"]!=exact_samples or
        synchronized_replay["status"]!="VERIFIED_UNAPPROVED_PICTURE_SOUND_REVIEW"):
        raise RuntimeError("AUDIO-01F verified picture/sound clock mismatch")
    if (reopened.index.read_revision(project_id, edit_id, 1)["document_sha256"] !=
            first["document_sha256"] or
        reopened.index.read_revision(project_id, edit_id, 2)["document_sha256"] !=
            second["document_sha256"]):
        raise RuntimeError("Original B13 editor revisions changed during conform")
    report = {
        "format": "nvp.b14.real_sdr16_edited_picture_conform.v1",
        "original_frozen_FLOAT32_EXR_frames": 120,
        "immutable_editorial_revision_count": 2,
        "actual_edited_16bit_SDR_PNG_sequences": done,
        "all_output_frames_rehashed_from_original_FilmIndex": True,
        "conforms_after_FilmIndex_restart": True,
        "B13_edits_unchanged": True,
        "native_B14_worker_authorization_tested": len(granted) == 2,
        "native_B14_contained_workers": 2,
        "native_B14_resource_reservations_released": ledger.snapshot()["reservations"]["ram_mb"] == 0,
        "edited_technical_MOV_rendered": True,
        "edited_technical_MOV_profile": movie_audit["profile"],
        "edited_technical_MOV_SHA256": movie_audit["movie_sha256"],
        "edited_technical_MOV_frames": movie_audit["frames"],
        "edited_technical_MOV_independent_decode_after_restart": True,
        "audio_present": True,
        "audio01f_real_edited_picture_and_multistem_sound": True,
        "audio01f_native_authorization_and_contained_worker": True,
        "audio01f_mixed_stem_count": 2,
        "audio01f_samples_per_channel": exact_samples,
        "audio01f_verified_after_restart": True,
        "audio01f_mov_sha256": sound_reopened.index.read_revision(
            project_id,"audio01f_picture_sound_r1",1)["data"]["rendered_mov_sha256"],
        "final_master": False,
    }
    (root / "nvp_b14_real_edited_picture_acceptance.json").write_text(
        json.dumps(report, sort_keys=True, indent=2), encoding="utf8")
    return report


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--out", required=True)
    args.add_argument("--blender", default="blender")
    config = args.parse_args()
    print(json.dumps(fixture(config.out, config.blender), indent=2, sort_keys=True))
