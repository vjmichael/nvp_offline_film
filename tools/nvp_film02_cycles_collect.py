"""FILM02-02 — independently audit all three genuine Cycles shot artifacts.

Receives ONE frozen FilmIndex source manifest and three individually
supervised, completed 240-frame shot output folders. Validates 720 actual
PNG files, hard cuts, original Film Time, native scene readback and SHA.
Only then creates a non-theatrical director review contact sheet and a
truthful 720-frame picture-only completion receipt. No model-made frames.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from PIL import Image, ImageDraw

from tools.nvp_film02_blender_handoff import (
    FRAMES, FPS, SHOT_FRAMES, validate_handoff, CHIRP,
)
from tools.nvp_film02_blender_cycles_acceptance import (
    SHOT_FORMAT, sha_file,
)

FORMAT = "nvp.film02.cycles.three_shot_verified_original_picture.v1"
SAMPLE_FRAMES = (0, 120, 239, 240, 360, 479, 480, 600, 719)


def verify_three_shots(plan, report, shot_root):
    validate_handoff(plan, report)
    root = Path(shot_root).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise PermissionError("Three genuine shot artifact folders required")
    complete = []
    shot_proofs = []
    for shot in range(3):
        folder = root / f"shot_{shot}"
        if folder.is_symlink() or not folder.is_dir():
            raise RuntimeError("Missing independent original film shot " + str(shot))
        path = folder / "shot_receipt.json"
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Missing immutable Blender shot receipt")
        doc = json.loads(path.read_text("utf8"))
        start = shot * SHOT_FRAMES
        end = start + SHOT_FRAMES
        expected_shot = plan["shots"][shot]
        if (doc.get("format") != SHOT_FORMAT or
                doc.get("passed") is not True or
                doc.get("original_project_id") != plan["source_project_id"] or
                doc.get("source_manifest_sha256") != plan["manifest_sha256"] or
                doc.get("source_edit_sha256") != plan["source_edit_sha256"] or
                doc.get("source_take_sha256") != expected_shot["take_sha256"] or
                doc.get("source_original_sound_sha256") != expected_shot["sound_sha256"] or
                doc.get("shot_number") != shot or
                doc.get("first_frame") != start or
                doc.get("stop_frame") != end or
                doc.get("rendered_frame_count") != SHOT_FRAMES or
                doc.get("fps") != FPS or
                doc.get("genuine_blender_cycles") is not True or
                doc.get("all_native_job_and_image_SHA_verified") is not True or
                doc.get("original_take_and_edit_unchanged") is not True or
                doc.get("continuous_30s_movie_muxed") is not False or
                doc.get("real_creator_artistic_approval") is not False or
                doc.get("2k_cinema_master_or_DCP") is not False):
            raise PermissionError("An original film shot does not share the same edit")
        chunks = doc.get("chunks")
        rows = doc.get("frames")
        if (type(chunks) is not list or len(chunks) != 10 or
                type(rows) is not list or len(rows) != SHOT_FRAMES or
                [c["first_frame"] for c in chunks] != list(range(start, end, 24)) or
                any(c.get("stop_frame") != c["first_frame"]+24 or
                    c.get("worker_state") != "SUCCEEDED"
                    for c in chunks)):
            raise RuntimeError("Missing original journaled Cycles render chunks")
        samples = doc.get("saved_native_blender_scene_samples")
        if (type(samples) is not list or len(samples) != 2 or
                [s.get("first_frame") for s in samples] != [start, end-24]):
            raise RuntimeError("Original source Blender scene samples missing")
        for sample in samples:
            sample_dir = folder / "source_scene_samples"
            for extension, name_key, sha_key in (
                ("blend", "scene_file", "scene_sha256"),
                ("source.json", "source_file", "source_sha256")):
                expected_name = f"frame_{sample['first_frame']:04d}.{extension}"
                path = sample_dir / expected_name
                if (sample.get(name_key) != expected_name or
                        path.is_symlink() or not path.is_file() or
                        sha_file(path) != sample.get(sha_key)):
                    raise RuntimeError("Original native Blender scene sample changed")
        for start_chunk in (start, end - 24):
            reopen_path = folder / f"independent_blend_reopen_{start_chunk:04d}.json"
            if reopen_path.is_symlink() or not reopen_path.is_file():
                raise RuntimeError("Second Blender .blend readback evidence missing")
            reread = json.loads(reopen_path.read_text("utf8"))
            row = next(c for c in chunks if c["first_frame"] == start_chunk)
            if (reread.get("passed") is not True or
                    reread.get("genuine_separate_native_blender_readback") is not True or
                    reread.get("source_packet_sha256") != row["source_packet_sha256"] or
                    reread.get("parent_source_manifest_sha256") != plan["manifest_sha256"] or
                    reread.get("source_edit_sha256") != plan["source_edit_sha256"] or
                    reread.get("shot_number") != shot or
                    reread.get("first_frame") != start_chunk or
                    reread.get("stop_frame") != start_chunk+24 or
                    reread.get("source_bound_scene_object_count") != 7):
                raise RuntimeError("Independent original Blender scene reopening failed")
        folder_frames = folder / "frames"
        if folder_frames.is_symlink() or not folder_frames.is_dir():
            raise RuntimeError("Original individual Cycles frame directory missing")
        if len(list(folder_frames.glob("frame_*.png"))) != SHOT_FRAMES:
            raise RuntimeError("Native shot contains missing or unexpected picture files")
        for i, (row, original) in enumerate(
                zip(rows, plan["frames"][start:end]), start):
            png = folder_frames / f"frame_{i:04d}.png"
            if (row.get("frame_zero") != i or
                    row.get("output_film_tick") != original["output_film_tick"] or
                    row.get("source_film_tick") != original["source_film_tick"] or
                    row.get("source_take_sha256") != original["source_take_sha256"] or
                    row.get("snapshot_sha256") != original["snapshot_sha256"] or
                    row.get("original_sound_event_ids") != original["source_sound_event_ids"] or
                    png.is_symlink() or not png.is_file() or
                    row.get("png_sha256") != sha_file(png) or
                    row.get("png_bytes") != png.stat().st_size):
                raise PermissionError("Unverified real Cycles original film pixel at " + str(i))
            with Image.open(png) as image:
                image.load()
                if image.format != "PNG" or image.size != (640, 360):
                    raise RuntimeError("Original Cycles frame is not native RGB PNG")
            complete.append({"frame_zero": i,
                             "png_sha256": row["png_sha256"],
                             "take_sha256": row["source_take_sha256"]})
        contact = folder / "three_original_Cycles_moments.png"
        if not contact.is_file() or contact.is_symlink() or sha_file(contact) != doc["contact_sha256"]:
            raise RuntimeError("Original per-shot director sample contact changed")
        shot_proofs.append({
            "shot": shot, "take_sha256": doc["source_take_sha256"],
            "frame_count": len(rows), "all_chunks_native_success": True,
            "native_blender_version": doc["blender_version"],
            "contact_sha256": doc["contact_sha256"],
        })
    if (len(complete) != FRAMES or
            [item["frame_zero"] for item in complete] != list(range(FRAMES)) or
            any(complete[i]["take_sha256"] ==
                complete[i-1]["take_sha256"] for i in (240, 480))):
        raise RuntimeError("Three original distinct scenes did not make 720 pictures")
    return complete, shot_proofs


def publish_review(plan, report, shot_root, destination):
    frames, shots = verify_three_shots(plan, report, shot_root)
    dest = Path(destination)
    if not dest.is_absolute() or dest.is_symlink() or dest.exists():
        raise PermissionError("Director review must be published to a fresh folder")
    dest.mkdir(parents=True, mode=0o700)
    src = Path(shot_root)
    contact = Image.new("RGB", (3 * 640 + 4 * 12, 3 * 390 + 4 * 12), (21, 23, 28))
    pen = ImageDraw.Draw(contact)
    for i, frame in enumerate(SAMPLE_FRAMES):
        path = src / f"shot_{frame//SHOT_FRAMES}" / "frames" / f"frame_{frame:04d}.png"
        with Image.open(path) as image:
            image.load()
            x = 12 + (i % 3) * 652
            y = 12 + (i // 3) * 390
            contact.paste(image.convert("RGB"), (x, y))
        pen.text((x, y+365), f"Cycles original film {frame/FPS:.2f}s   frame {frame}",
                 fill=(235, 236, 240))
    contact_path = dest / "FILM02_30sec_nine_real_Cycles_frames.png"
    contact.save(contact_path, format="PNG")
    receipt = {
        "format": FORMAT, "passed": True, "frame_count": len(frames),
        "fps": FPS, "film_duration_seconds": 30,
        "original_project_id": plan["source_project_id"],
        "original_edit_sha256": plan["source_edit_sha256"],
        "original_source_manifest_sha256": plan["manifest_sha256"],
        "source_cut_frames": [240, 480],
        "original_beacon_cue_frames": [624, 636],
        "three_real_Cycles_source_shots": shots,
        "contact_sha256": sha_file(contact_path),
        "original_per_frame_picture_sha256": frames,
        "source_sound_only_not_mastered_audio": True,
        "continuous_sound_picture_movie_created": False,
        "director_viewed_or_approved": False,
        "physical_installed_windows": False,
        "theatrical_DCP_or_DCI_acceptance": False,
    }
    (dest / "FILM02_30sec_verified_native_Cycles_receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", "utf8")
    return receipt


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--handoff", type=Path, required=True)
    cli.add_argument("--original-report", type=Path, required=True)
    cli.add_argument("--shots", type=Path, required=True)
    cli.add_argument("--out", type=Path, required=True)
    args = cli.parse_args()
    plan = json.loads(args.handoff.read_text("utf8"))
    report = json.loads(args.original_report.read_text("utf8"))
    result = publish_review(plan, report, args.shots, args.out.resolve())
    print(json.dumps({
        "full_source_picture": "VERIFIED_REAL_BLENDER_CYCLES",
        "frames": result["frame_count"], "original_edit_sha256":
        result["original_edit_sha256"],
        "audio_movie": "NOT_YET_CREATED",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
