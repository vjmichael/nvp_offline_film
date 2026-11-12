"""INT-02B: committed slate edit -> original-time 30s picture+PCM derivative.

An AUTHENTIC committed SlateSequenceAssembly edit chooses immutable OpenUSD
Takes. Frames and sound are sampled at that edit's exact, source-relative Film
Time. A native host supplies one human authorization, trusted output location
and real OpenUSD renderer. This is NOT a model/browser API or cinema master.

Deliberately refuses uncomposed shot-override layers and subframe editorial
cuts: silently dropping them would misrepresent the director's committed film.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
import wave

from backend.nvp_data_av_scene import FrozenSceneAV, MAX_SAMPLES
from backend.nvp_final_2d_native import (
    _file_sha256, _png_header, MAX_FRAMES, SAMPLE_RATE,
)
from backend.nvp_film_index import _require_pid, _id
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly, FORMAT as EDIT_FORMAT
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, tick_from_frame

FORMAT = "nvp.int02.edited_original_30s.v1"
OUTPUT_FRAMES = 720
AUDIO_SAMPLES = 30 * SAMPLE_RATE
SOURCE_SAMPLE_TICKS = TICKS_PER_SECOND // SAMPLE_RATE
FRAME_TICKS = tick_from_frame(1, 24, 1)
DURATION_TICKS = 30 * TICKS_PER_SECOND


def _read_edit(assembly, project_id, edit_id, edit_revision):
    _require_pid(project_id)
    _id(edit_id, "committed native edit")
    if type(edit_revision) is not int or edit_revision < 1:
        raise ValueError("Exact committed edit revision required")
    edit = assembly.open_edit(project_id, edit_id, edit_revision)
    data = edit["data"]
    if (edit["kind"] != "edit" or data.get("format") != EDIT_FORMAT or
        data.get("explicit_editor_commit") is not True or
        data.get("render_approved") is not False or
        data.get("retimed") is not False or
        data.get("duration_tick") != DURATION_TICKS):
        raise RuntimeError("Only an original-time committed 30-second slate edit is eligible")
    rows = data.get("segments")
    if type(rows) is not list or not 1 <= len(rows) <= OUTPUT_FRAMES:
        raise RuntimeError("Edited film needs a bounded contiguous source sequence")
    cursor = 0
    checked = []
    for row in rows:
        start, end = row["timeline_start_tick"], row["timeline_end_tick"]
        si, so = row["source_in_tick"], row["source_out_tick"]
        if (any(type(tick) is not int for tick in (start, end, si, so)) or
            start != cursor or not 0 <= si < so or end - start != so - si or
            start % FRAME_TICKS or end % FRAME_TICKS or
            si % SOURCE_SAMPLE_TICKS or so % SOURCE_SAMPLE_TICKS):
            raise RuntimeError("Editorial cut cannot be silently shifted or retimed on output")
        if row["source_shot_id"] is not None:
            raise RuntimeError("Native shot override composition is required before delivery")
        take = assembly.index.read_revision(project_id, row["source_take_id"], 1)
        tdata = take["data"]
        if (take["kind"] != "take" or tdata.get("frozen") is not True or
            tdata.get("format") != "nvp.digital_take.openusd_temporal.v1" or
            take["document_sha256"] != row["source_take_document_sha256"] or
            so > tdata["duration_tick"]):
            raise RuntimeError("Committed edit references changed/unfrozen original performance")
        checked.append({
            "segment_id": row["segment_id"],
            "source_take_id": row["source_take_id"],
            "source_take_sha256": take["document_sha256"],
            "source_in_tick": si, "source_out_tick": so,
            "timeline_start_tick": start, "timeline_end_tick": end,
            "scene_document_sha256": tdata["scene_document_sha256"],
            "timeline_document_sha256": tdata["timeline_document_sha256"],
        })
        cursor = end
    if cursor != DURATION_TICKS:
        raise RuntimeError("Native edited original is not a complete 30-second film")
    return edit, checked


class NativeEditedFilm30s:
    def __init__(self, assembly: SlateSequenceAssembly, *,
                 native_creator_approval, render_png,
                 cancelled=lambda: False, progress=lambda stage, value: None):
        if (not isinstance(assembly, SlateSequenceAssembly) or
            not callable(native_creator_approval) or not callable(render_png)):
            raise TypeError("Committed native slate, OS creator consent and USD raster required")
        self.assembly = assembly
        self.approve = native_creator_approval
        self.render = render_png
        self.cancelled = cancelled
        self.progress = progress

    def preflight(self, project_id, edit_id, edit_revision):
        edit, segments = _read_edit(self.assembly, project_id, edit_id, edit_revision)
        return {
            "format": FORMAT, "project_id": project_id,
            "edit_id": edit_id, "edit_revision": edit_revision,
            "edit_sha256": edit["document_sha256"],
            "duration_tick": str(DURATION_TICKS), "fps_num": 24, "fps_den": 1,
            "frame_count": OUTPUT_FRAMES, "pcm_samples": AUDIO_SAMPLES,
            "segments": segments, "source_take_modified": False,
            "editorial_revision_modified": False, "render_approved": False,
        }

    def export(self, project_id, edit_id, edit_revision, presentation_id,
               output_parent, *, listener_path):
        _id(presentation_id, "unique edited delivery identity")
        if (type(listener_path) is not str or
            not listener_path.startswith("/World/") or len(listener_path) > 240):
            raise ValueError("Exact authored listener path required")
        plan = self.preflight(project_id, edit_id, edit_revision)
        parent = Path(output_parent)
        if parent.is_symlink() or not parent.is_dir():
            raise RuntimeError("Host-selected output parent is unavailable")
        parent = parent.resolve()
        target = parent / ("NVPEdit30_" + presentation_id)
        if target.exists() or target.is_symlink():
            raise FileExistsError("Edited film derivative already exists")
        scope = {k: v for k, v in plan.items() if k != "segments"}
        scope["segment_sha256"] = sha256(json.dumps(
            plan["segments"], sort_keys=True, separators=(",", ":")
        ).encode("utf8")).hexdigest()
        scope["presentation_id"] = presentation_id
        scope["output_directory"] = str(target)
        scope["listener_path"] = listener_path
        scope["operation"] = "nvp.int02.native_approved_edited_30s_derivative"
        scope["no_ffmpeg"] = True
        scope["original_sources_immutable"] = True
        scope["export_is_plaintext_derivative"] = True
        if self.approve(dict(scope)) is not True:
            raise PermissionError("Native director refused exact committed 30-second edit")
        if self.preflight(project_id, edit_id, edit_revision) != plan:
            raise RuntimeError("Committed edit/source changed while creator authorized output")
        if self.cancelled():
            raise InterruptedError("Creator cancelled edited film before publication")
        staged = Path(tempfile.mkdtemp(prefix=".nvp-int02-", dir=parent))
        source_cache = {}
        try:
            with ExitStack() as resources:
                for seg in plan["segments"]:
                    take_id = seg["source_take_id"]
                    if take_id not in source_cache:
                        take = FrozenSceneAV(
                            self.assembly.index, project_id, take_id,
                            expected_take_sha256=seg["source_take_sha256"],
                            listener_path=listener_path)
                        resources.callback(take.close)
                        source_cache[take_id] = take
                pictures = staged / "pictures"
                pictures.mkdir()
                entries = []
                dims = None
                seg_index = 0
                for frame in range(OUTPUT_FRAMES):
                    if self.cancelled():
                        raise InterruptedError("Creator cancelled native picture derivation")
                    if frame % 24 == 0:
                        self.progress("picture", frame)
                    output_tick = tick_from_frame(frame, 24, 1)
                    while (seg_index + 1 < len(plan["segments"]) and
                           output_tick >= plan["segments"][seg_index]["timeline_end_tick"]):
                        seg_index += 1
                    seg = plan["segments"][seg_index]
                    original_tick = seg["source_in_tick"] + output_tick - seg["timeline_start_tick"]
                    take = source_cache[seg["source_take_id"]]
                    state = take.snapshot(original_tick)
                    active = take.timeline.events_at(
                        project_id, take.data["timeline_id"],
                        take.data["timeline_revision"], tick=original_tick,
                        event_kind="camera", limit=2)
                    if len(active) > 1:
                        raise RuntimeError("Ambiguous source camera at edited output time")
                    camera = active[0]["payload"].get("usd_prim_path") if active else None
                    if camera is not None and take.roles.get(camera) != "camera":
                        raise RuntimeError("Committed shot does not reference an original USD camera")
                    if camera is None:
                        # A blank gap is an authentic output, never invented source.
                        pass
                    rendering_scope = {
                        **scope, "source_take_id": seg["source_take_id"],
                        "source_take_sha256": seg["source_take_sha256"],
                        "scene_document_sha256": seg["scene_document_sha256"],
                        "timeline_document_sha256": seg["timeline_document_sha256"],
                    }
                    png = self.render(scope=rendering_scope,
                                      tick=original_tick, camera_path=camera,
                                      source_snapshot=state)
                    width, height = _png_header(png)
                    if dims is None:
                        dims = [width, height]
                    elif dims != [width, height]:
                        raise RuntimeError("Original edited cameras changed output geometry")
                    name = f"{frame+1:07d}.png"
                    with (pictures / name).open("xb") as fd:
                        fd.write(png)
                        fd.flush()
                        os.fsync(fd.fileno())
                    entries.append({
                        "sample_index": frame,
                        "output_tick": str(output_tick),
                        "source_tick": str(original_tick),
                        "segment_id": seg["segment_id"],
                        "source_take_sha256": seg["source_take_sha256"],
                        "camera_path": camera,
                        "png_file": name,
                        "sha256": sha256(png).hexdigest(),
                    })
                with wave.open(str(staged / "soundtrack.wav"), "wb") as audio:
                    audio.setnchannels(2)
                    audio.setsampwidth(2)
                    audio.setframerate(SAMPLE_RATE)
                    for seg in plan["segments"]:
                        take = source_cache[seg["source_take_id"]]
                        first = seg["source_in_tick"] // SOURCE_SAMPLE_TICKS
                        count = (seg["source_out_tick"] - seg["source_in_tick"]) // SOURCE_SAMPLE_TICKS
                        for offset in range(0, count, MAX_SAMPLES):
                            if self.cancelled():
                                raise InterruptedError("Creator cancelled native PCM derivation")
                            n = min(MAX_SAMPLES, count - offset)
                            result = take.audio_window(first + offset, n)
                            pcm = base64.b64decode(result["pcm_base64"], validate=True)
                            if (len(pcm) != 4*n or
                                result["take_document_sha256"] != seg["source_take_sha256"]):
                                raise RuntimeError("Edited PCM no longer belongs to immutable Take")
                            audio.writeframesraw(pcm)
                with wave.open(str(staged / "soundtrack.wav"), "rb") as wav:
                    if wav.getnframes() != AUDIO_SAMPLES:
                        raise RuntimeError("Edited output lost original PCM samples at cut")
                self.progress("audio", AUDIO_SAMPLES)
                if self.cancelled():
                    raise InterruptedError("Creator cancelled native film before publication")
                if self.preflight(project_id, edit_id, edit_revision) != plan:
                    raise RuntimeError("Film source changed during edited output")
                manifest = {
                    **plan, "status": "DERIVED_EDITED_30S_PICTURE_PCM",
                    "presentation_id": presentation_id,
                    "listener_path": listener_path, "picture_dimensions": dims,
                    "pictures": entries, "audio_file": "soundtrack.wav",
                    "audio_sha256": _file_sha256(staged / "soundtrack.wav"),
                    "audio_sample_rate": SAMPLE_RATE, "audio_channels": 2,
                    "audio_bit_depth": 16, "ffmpeg_used": False,
                    "conventional_single_file_master": False,
                    "original_sources_modified": False,
                    "export_is_plaintext_derivative": True,
                }
                with (staged / "manifest.json").open("x", encoding="utf8") as fd:
                    json.dump(manifest, fd, sort_keys=True, separators=(",", ":"))
                    fd.flush()
                    os.fsync(fd.fileno())
                os.replace(staged, target)
            proof = verify_edited_film(self.assembly, project_id, edit_id,
                                       edit_revision, target)
            self.progress("verified", OUTPUT_FRAMES)
            return {
                "independent_reopen_status": proof["status"],
                "status": "DERIVED_EDITED_30S_PICTURE_PCM",
                "directory": str(target),
                "manifest_sha256": _file_sha256(target / "manifest.json"),
                "edit_sha256": plan["edit_sha256"],
                "picture_count": OUTPUT_FRAMES,
                "pcm_samples": AUDIO_SAMPLES,
                "original_sources_modified": False,
                "production_renderer_accepted": False,
                "single_file_master": False,
            }
        finally:
            if staged.exists():
                shutil.rmtree(staged)


def verify_edited_film(assembly: SlateSequenceAssembly, project_id: str,
                       edit_id: str, edit_revision: int, package_dir: Path) -> dict:
    """Reopen every picture and PCM sample directly against committed source.

    This read-only verifier never accepts a manifest as its own authority;
    the original FilmIndex edit and all original sound windows are reopened.
    """
    if not isinstance(assembly, SlateSequenceAssembly):
        raise TypeError("Actual approved slate editor required")
    edit, segments = _read_edit(assembly, project_id, edit_id, edit_revision)
    parent = Path(package_dir)
    manifest_path = parent/"manifest.json"
    if (not parent.is_dir() or parent.is_symlink() or
        not manifest_path.is_file() or manifest_path.is_symlink() or
        manifest_path.stat().st_size > 4*1024*1024):
        raise RuntimeError("Edited film package or bounded manifest unavailable")
    manifest = json.loads(manifest_path.read_bytes())
    if (type(manifest) is not dict or
        manifest.get("format") != FORMAT or
        manifest.get("status") != "DERIVED_EDITED_30S_PICTURE_PCM" or
        manifest.get("project_id") != project_id or
        manifest.get("edit_id") != edit_id or
        manifest.get("edit_revision") != edit_revision or
        manifest.get("edit_sha256") != edit["document_sha256"] or
        manifest.get("segments") != segments or
        manifest.get("duration_tick") != str(DURATION_TICKS) or
        manifest.get("frame_count") != OUTPUT_FRAMES or
        manifest.get("pcm_samples") != AUDIO_SAMPLES or
        manifest.get("fps_num") != 24 or manifest.get("fps_den") != 1 or
        manifest.get("ffmpeg_used") is not False or
        manifest.get("conventional_single_file_master") is not False or
        manifest.get("original_sources_modified") is not False or
        manifest.get("export_is_plaintext_derivative") is not True):
        raise RuntimeError("Edited film manifest is not bound to the committed original")
    listener_path = manifest.get("listener_path")
    if type(listener_path) is not str or not listener_path.startswith("/World/"):
        raise RuntimeError("Edited film has no original authored listener")
    pictures = manifest.get("pictures")
    folder = parent/"pictures"
    dims = manifest.get("picture_dimensions")
    if (type(pictures) is not list or len(pictures) != OUTPUT_FRAMES or
        type(dims) is not list or len(dims) != 2 or
        not folder.is_dir() or folder.is_symlink() or
        len(list(folder.iterdir())) != OUTPUT_FRAMES):
        raise RuntimeError("Edited film picture sequence incomplete")
    with ExitStack() as resources:
        sources = {}
        for seg in segments:
            ident = seg["source_take_id"]
            if ident not in sources:
                source = FrozenSceneAV(
                    assembly.index, project_id, ident,
                    expected_take_sha256=seg["source_take_sha256"],
                    listener_path=listener_path)
                resources.callback(source.close)
                sources[ident] = source
        current = 0
        for i, item in enumerate(pictures):
            tick = tick_from_frame(i, 24, 1)
            while (current + 1 < len(segments) and
                   tick >= segments[current]["timeline_end_tick"]):
                current += 1
            seg = segments[current]
            source_tick = seg["source_in_tick"] + tick - seg["timeline_start_tick"]
            expected = {
                "sample_index": i, "output_tick": str(tick),
                "source_tick": str(source_tick),
                "segment_id": seg["segment_id"],
                "source_take_sha256": seg["source_take_sha256"],
                "png_file": f"{i+1:07d}.png",
            }
            if type(item) is not dict or any(item.get(k) != v for k, v in expected.items()):
                raise RuntimeError("Edited frame is not ordered at authoritative Film Time")
            path = folder/expected["png_file"]
            if (not path.is_file() or path.is_symlink() or
                path.stat().st_size > 24*1024*1024):
                raise RuntimeError("Edited frame absent or exceeds native bound")
            encoded = path.read_bytes()
            if sha256(encoded).hexdigest() != item.get("sha256"):
                raise RuntimeError("Edited frame data SHA mismatch")
            if list(_png_header(encoded)) != dims:
                raise RuntimeError("Edited picture geometry mismatch")
            source = sources[seg["source_take_id"]]
            active = source.timeline.events_at(
                project_id, source.data["timeline_id"],
                source.data["timeline_revision"], tick=source_tick,
                event_kind="camera", limit=2)
            if len(active) > 1:
                raise RuntimeError("Edited Film Time source camera is ambiguous")
            camera = active[0]["payload"].get("usd_prim_path") if active else None
            if item.get("camera_path") != camera:
                raise RuntimeError("Derived edited picture changed source camera")
        wav_path = parent/"soundtrack.wav"
        if (not wav_path.is_file() or wav_path.is_symlink() or
            manifest.get("audio_file") != "soundtrack.wav" or
            _file_sha256(wav_path) != manifest.get("audio_sha256") or
            manifest.get("audio_sample_rate") != SAMPLE_RATE or
            manifest.get("audio_channels") != 2 or
            manifest.get("audio_bit_depth") != 16):
            raise RuntimeError("Edited original PCM soundtrack changed")
        with wave.open(str(wav_path),"rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(),
                wav.getnframes(), wav.getcomptype()) != (
                    2, 2, SAMPLE_RATE, AUDIO_SAMPLES, "NONE"):
                raise RuntimeError("Edited original PCM format or duration changed")
            for seg in segments:
                source = sources[seg["source_take_id"]]
                begin = seg["source_in_tick"] // SOURCE_SAMPLE_TICKS
                count = (seg["source_out_tick"] - seg["source_in_tick"]) // SOURCE_SAMPLE_TICKS
                for offset in range(0, count, MAX_SAMPLES):
                    n = min(MAX_SAMPLES, count - offset)
                    actual = wav.readframes(n)
                    native = source.audio_window(begin+offset, n)
                    reference = base64.b64decode(native["pcm_base64"],validate=True)
                    if (len(actual) != 4*n or actual != reference or
                        native["take_document_sha256"] != seg["source_take_sha256"]):
                        raise RuntimeError("Edited soundtrack PCM differs from original source window")
            if wav.readframes(1):
                raise RuntimeError("Edited soundtrack has unexpected extra samples")
    if _read_edit(assembly, project_id, edit_id, edit_revision)[0]["document_sha256"] != edit["document_sha256"]:
        raise RuntimeError("Original committed edit changed during derivative verification")
    return {
        "status": "VERIFIED_EDITED_ORIGINAL_30S",
        "edit_sha256": edit["document_sha256"],
        "manifest_sha256": _file_sha256(manifest_path),
        "pictures": OUTPUT_FRAMES,
        "original_pcm_samples": AUDIO_SAMPLES,
        "source_takes_immutable": True,
        "single_file_master": False,
        "physical_production_render_verified": False,
    }
