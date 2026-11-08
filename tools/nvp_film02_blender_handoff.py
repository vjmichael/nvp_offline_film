"""FILM02-01: a complete ORIGINAL 30s FilmIndex edit -> immutable Blender handoff.

Source truth is the frozen edited OpenUSD/PCM production data. This file
does NOT render frames, synthesize sound, authorize a model to run Blender,
or make a 30-second finished film. The future Blender adapter receives
only this hash-bound source data through the existing supervised worker.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from tools.nvp_film01_original_30s import (
    FORMAT as ORIGINAL_FORMAT, FRAMES, FPS, SHOT_SECONDS, SOURCE_IDS,
    write_original_30s_source,
)

FORMAT = "nvp.film02.original_30s.blender_source_handoff.v1"
FRAME_TICK = TICKS_PER_SECOND // FPS
SHOT_FRAMES = SHOT_SECONDS * FPS
CUTS = (SHOT_FRAMES, 2 * SHOT_FRAMES)
REQUIRED = {
    "/World/RelayCore": "prop",
    "/World/ServiceCraft": "actor",
    "/World/Engineer": "actor",
    "/World/CrossingBox": "actor",
    "/World/PassingSphere": "actor",
    "/World/Camera": "camera",
    "/World/PracticalLight": "light",
}
ASSETS = frozenset(REQUIRED) - {"/World/Camera", "/World/PracticalLight"}
CHIRP = "BeaconSignalRestored"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def _digest(value):
    return sha256(_canonical(value)).hexdigest()


def validate_handoff(body, report):
    """Pure structural recheck independent of the manifest-producing loop."""
    if (type(body) is not dict or body.get("format") != FORMAT or
            body.get("source_edit_sha256") != report["edit_sha256"] or
            body.get("source_project_id") != report["project_id"] or
            body.get("duration_seconds") != 30 or
            body.get("frame_rate") != FPS or
            body.get("frame_count") != FRAMES or
            body.get("cut_output_frames") != list(CUTS) or
            body.get("source_takes_unchanged") is not True or
            body.get("test_only_source_fixture") is not True or
            body.get("production_creator_approval_obtained") is not False or
            body.get("picture_rendered") is not False or
            body.get("mixed_audio_exported") is not False):
        raise PermissionError("Not an original source-bound, unrendered FILM02 handoff")
    expected_digest = body.get("manifest_sha256")
    unsigned = {key: value for key, value in body.items()
                if key != "manifest_sha256"}
    if expected_digest != _digest(unsigned):
        raise PermissionError("Original frozen Blender handoff SHA changed")
    shots = body.get("shots")
    frames = body.get("frames")
    assets = body.get("assets")
    if (type(shots) is not list or len(shots) != 3 or
            type(frames) is not list or len(frames) != FRAMES or
            type(assets) is not dict or len(assets) != 5):
        raise RuntimeError("30-second edited source/camera/geometry coverage incomplete")
    for i, shot in enumerate(shots):
        expected = report["shots"][i]
        if (shot["take_id"] != SOURCE_IDS[i] or
                shot["take_sha256"] != expected["take_sha256"] or
                shot["scene_sha256"] != expected["scene_sha256"] or
                shot["timeline_sha256"] != expected["timeline_sha256"] or
                shot["sound_sha256"] != expected["sound_sha256"] or
                shot["start_output_frame"] != i * SHOT_FRAMES or
                shot["end_output_frame"] != (i + 1) * SHOT_FRAMES or
                shot["camera_path"] != "/World/Camera"):
            raise PermissionError("FilmIndex Take or 10-second edit cut changed")
    chirp_frames = []
    for i, frame in enumerate(frames):
        shot = shots[i // SHOT_FRAMES]
        local_frame = i % SHOT_FRAMES
        if (frame["output_frame_zero"] != i or
                frame["output_film_tick"] != str(i * FRAME_TICK) or
                frame["source_film_tick"] != str(local_frame * FRAME_TICK) or
                frame["segment_id"] != shot["segment_id"] or
                frame["source_take_sha256"] != shot["take_sha256"] or
                frame["scene_sha256"] != shot["scene_sha256"] or
                type(frame["snapshot_sha256"]) is not str or
                len(frame["snapshot_sha256"]) != 64 or
                set(frame["world_matrices"]) != set(REQUIRED) or
                type(frame["source_sound_event_ids"]) is not list):
            raise PermissionError("Cut, native tick or authored scene lost at frame " + str(i))
        for path, matrix in frame["world_matrices"].items():
            if (type(matrix) is not list or len(matrix) != 4 or
                    any(type(row) is not list or len(row) != 4 or
                        any(type(v) not in (int, float) or not math.isfinite(v)
                            for v in row) for row in matrix)):
                raise PermissionError("Nonfinite native USD transform at " + path)
        if CHIRP in frame["source_sound_event_ids"]:
            chirp_frames.append(i)
    if chirp_frames != list(range(624, 636)):
        raise RuntimeError("Original source chirp lost its 26.0-26.5s film clock")
    for path in ASSETS:
        if not any(path in asset["bound_scene_paths"] for asset in assets.values()):
            raise RuntimeError("A source object has no verified USD mesh/primitive")
    return {
        "format": FORMAT,
        "source_edit_sha256": report["edit_sha256"],
        "frame_count": len(frames),
        "cut_frames": list(CUTS),
        "chirp_start_frame": chirp_frames[0],
        "chirp_end_exclusive": chirp_frames[-1] + 1,
        "all_frames_source_bound": True,
        "render_acceptance": False,
        "creator_visual_approval": False,
    }


def build_handoff(source_root):
    """Read a previously frozen disposable source project, without changing it."""
    root = Path(source_root)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise PermissionError("A trusted absolute frozen source workspace is required")
    report_path = root / "original-source-report.json"
    original_report_bytes = report_path.read_bytes()
    report = json.loads(original_report_bytes)
    if (report.get("format") != ORIGINAL_FORMAT or
            report.get("target_frames") != FRAMES or
            report.get("shot_count") != 3 or
            report.get("hard_cuts") != 2 or
            report.get("source_takes_frozen_and_verified") is not True or
            report.get("creator_release_approved") is not False):
        raise PermissionError("Expected exact original three-shot frozen film")
    studio = Studio(root / "short.sqlite3")
    index = FilmIndex(studio)
    pid = report["project_id"]
    slate = DigitalSlateBranches(index, verify_editor_action=lambda *_: False)
    assembly = SlateSequenceAssembly(slate, verify_editor_action=lambda *_: False)
    edit = assembly.open_edit(pid, report["edit_id"], 1)
    if (edit["document_sha256"] != report["edit_sha256"] or
            edit["data"]["duration_tick"] != 30 * TICKS_PER_SECOND):
        raise PermissionError("The committed thirty-second editorial SHA changed")
    segments = edit["data"]["segments"]
    if len(segments) != 3:
        raise RuntimeError("This original handoff requires exactly three source Takes")
    registry = OpenUSDAssetRegistry(index)
    assets = {}
    shots = []
    frames = []
    for shot_no, segment in enumerate(segments):
        expected = report["shots"][shot_no]
        start, end = shot_no * SHOT_FRAMES, (shot_no + 1) * SHOT_FRAMES
        if (segment["source_take_id"] != SOURCE_IDS[shot_no] or
                segment["source_take_document_sha256"] != expected["take_sha256"] or
                segment["timeline_start_tick"] != start * FRAME_TICK or
                segment["timeline_end_tick"] != end * FRAME_TICK or
                segment["source_in_tick"] != 0 or
                segment["source_out_tick"] != SHOT_SECONDS * TICKS_PER_SECOND):
            raise PermissionError("Original FilmIndex editorial segment no longer matches source")
        for boundary in (start, end - 1):
            resolved = assembly.source_at(
                pid, report["edit_id"], 1,
                timeline_tick=boundary * FRAME_TICK,
                expected_edit_sha256=report["edit_sha256"])
            if (resolved["segment_id"] != segment["segment_id"] or
                    resolved["source_take_sha256"] != expected["take_sha256"] or
                    resolved["source_tick"] != str((boundary - start) * FRAME_TICK)):
                raise RuntimeError("Committed source projection failed at editorial cut")
        take = index.read_revision(pid, expected["take_id"], 1)
        sound = index.read_revision(pid, expected["sound_id"], 1)
        if (take["document_sha256"] != expected["take_sha256"] or
                sound["document_sha256"] != expected["sound_sha256"] or
                take["data"]["scene_document_sha256"] != expected["scene_sha256"] or
                take["data"]["timeline_document_sha256"] != expected["timeline_sha256"]):
            raise RuntimeError("Frozen Take, original sound or scene SHA changed")
        shot = {
            "shot": expected["shot"],
            "segment_id": segment["segment_id"],
            "take_id": expected["take_id"],
            "take_sha256": expected["take_sha256"],
            "scene_sha256": expected["scene_sha256"],
            "timeline_sha256": expected["timeline_sha256"],
            "sound_id": expected["sound_id"],
            "sound_sha256": expected["sound_sha256"],
            "start_output_frame": start,
            "end_output_frame": end,
            "camera_path": "/World/Camera",
            "practical_light_path": "/World/PracticalLight",
            "source_scene_revision": expected["scene_revision"],
        }
        shots.append(shot)
        native = FrozenSceneAV(
            index, pid, expected["take_id"],
            expected_take_sha256=expected["take_sha256"],
            listener_path="/World/Camera")
        try:
            for n in range(start, end):
                source_tick = (n - start) * FRAME_TICK
                snapshot = native.snapshot(source_tick)
                by_path = {row["path"]: row for row in snapshot["objects"]}
                if (set(by_path) != set(REQUIRED) or
                        snapshot["scene_document_sha256"] != shot["scene_sha256"] or
                        snapshot["timeline_document_sha256"] != shot["timeline_sha256"]):
                    raise RuntimeError("Native scene is not the expected frozen shot")
                transforms = {}
                for path, role in REQUIRED.items():
                    obj = by_path[path]
                    if obj["semantic_role"] != role:
                        raise PermissionError("Original camera, light or object actor role changed")
                    transforms[path] = obj["world_matrix"]
                    binding = obj["asset"]
                    if path in ASSETS:
                        if type(binding) is not dict or binding.get("asset_revision") != 1:
                            raise PermissionError("Missing source-bound original primitive")
                        asset_id = binding["asset_id"]
                        record, _ = registry.open(pid, asset_id, 1) if asset_id not in assets else (None, None)
                        if record is not None:
                            assets[asset_id] = {
                                "source_document_sha256": record["document_sha256"],
                                "source_data": record["data"],
                                "bound_scene_paths": [path],
                            }
                        else:
                            if path not in assets[asset_id]["bound_scene_paths"]:
                                assets[asset_id]["bound_scene_paths"].append(path)
                active_sound = sorted(row["event_id"] for row in snapshot["active_events"]
                                      if row["event_kind"] == "sound")
                frames.append({
                    "output_frame_zero": n,
                    "output_film_tick": str(n * FRAME_TICK),
                    "source_film_tick": str(source_tick),
                    "segment_id": shot["segment_id"],
                    "source_take_sha256": shot["take_sha256"],
                    "scene_sha256": shot["scene_sha256"],
                    "snapshot_sha256": snapshot["snapshot_sha256"],
                    "world_matrices": transforms,
                    "source_sound_event_ids": active_sound,
                })
        finally:
            native.close()
    body = {
        "format": FORMAT,
        "title": report["title"],
        "source_project_id": pid,
        "source_edit_sha256": report["edit_sha256"],
        "source_slate_sha256": report["slate_sha256"],
        "duration_seconds": 30,
        "frame_rate": FPS,
        "frame_count": FRAMES,
        "cut_output_frames": list(CUTS),
        "shots": shots,
        "assets": assets,
        "frames": frames,
        "source_takes_unchanged": True,
        "test_only_source_fixture": True,
        "production_creator_approval_obtained": False,
        "picture_rendered": False,
        "mixed_audio_exported": False,
        "renderer_handoff_pending": True,
        "source_pcm_reference_only": True,
    }
    body["manifest_sha256"] = _digest(body)
    validate_handoff(body, report)
    if report_path.read_bytes() != original_report_bytes:
        raise RuntimeError("Frozen original source report changed during handoff")
    for shot in shots:
        if index.read_revision(pid, shot["take_id"], 1)["document_sha256"] != shot["take_sha256"]:
            raise RuntimeError("Original Take changed after source evaluation")
    return body


def write_handoff(source_root, destination):
    path = Path(destination)
    if (not path.is_absolute() or not path.parent.is_dir() or
            path.exists() or path.is_symlink()):
        raise PermissionError("New absolute handoff output, outside original source, required")
    if path.is_relative_to(Path(source_root)):
        raise PermissionError("Derived worker handoff cannot overwrite source")
    body = build_handoff(source_root)
    with path.open("x", encoding="utf8") as output:
        json.dump(body, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")
    return body


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    cli.add_argument("--create-test-fixture", action="store_true")
    cli.add_argument("--consent", required=True)
    args = cli.parse_args()
    if args.consent != "I_APPROVE_DISPOSABLE_30S_SOURCE_HANDOFF_TEST":
        cli.error("Only explicitly approved CI source fixture handoff is allowed")
    source = args.source.resolve()
    if args.create_test_fixture:
        write_original_30s_source(source, approve_test_only=True)
    body = write_handoff(source, args.out.resolve())
    print(json.dumps({
        "format": FORMAT,
        "source_sha256": body["manifest_sha256"],
        "frames_verified": len(body["frames"]),
        "cuts_verified": body["cut_output_frames"],
        "rendered_movie_created": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
