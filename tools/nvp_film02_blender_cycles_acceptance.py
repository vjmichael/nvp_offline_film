"""FILM02-02 — supervised real Blender/Cycles source-locked 30s shot render.

The actual NVP BlenderWorkerSupervisor, ApprovedBlenderDispatcher and TaskLedger
own every process and permission decision. This CI fixture uses a *test-only*
trusted-host approval callback; never expose it to an AI model or browser.
Each 10-second shot is independently checkpointed in up to 24-frame native
Cycles jobs, then its 240 original Film Time pictures are SHA re-verified.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw

from backend.nvp_approved_blender_dispatch import ApprovedBlenderDispatcher
from backend.nvp_blender_worker import BlenderOperation, BlenderWorkerSupervisor, sha_file
from backend.nvp_render_source_stage import _write_exclusive
from backend.nvp_resource_ledger import TaskLedger
from tools.nvp_film02_blender_handoff import (
    FRAMES, FPS, SHOT_FRAMES, _canonical, _digest, build_handoff,
    validate_handoff,
)

PACKET_FORMAT = "nvp.film02.cycles.original_shot_chunk.v1"
RECEIPT_FORMAT = "nvp.film02.cycles.native_chunk_render.v1"
SHOT_FORMAT = "nvp.film02.cycles.original_240_frame_shot.v1"
SCRIPT = "trusted_film02_cycles.py"
MANIFEST = "source.json"
BATCH = 24
OUT_FIELDS = {"scene.blend": "blend", "audit.json": "json_audit",
              "preview.png": "png"}


def source_packet(plan, shot_no, first, stop):
    """No invented camera, asset or pose: all data comes from FILM02-01."""
    if (type(shot_no) is not int or shot_no not in (0, 1, 2) or
            type(first) is not int or type(stop) is not int or
            not shot_no * SHOT_FRAMES <= first < stop <= (shot_no + 1) * SHOT_FRAMES or
            stop - first > BATCH):
        raise ValueError("Only bounded 1..24 frame chunks inside one original shot")
    shot = plan["shots"][shot_no]
    frames = plan["frames"][first:stop]
    if (len(frames) != stop-first or
            any(row["output_frame_zero"] != i or
                row["source_take_sha256"] != shot["take_sha256"] or
                row["segment_id"] != shot["segment_id"]
                for i, row in enumerate(frames, first))):
        raise PermissionError("Source projection crossed an edit cut")
    source = {
        "parent_manifest_sha256": plan["manifest_sha256"],
        "source_project_id": plan["source_project_id"],
        "source_edit_sha256": plan["source_edit_sha256"],
        "source_title": plan["title"],
        "shot_number": shot_no,
        "segment_id": shot["segment_id"],
        "take_sha256": shot["take_sha256"],
        "scene_sha256": shot["scene_sha256"],
        "sound_sha256": shot["sound_sha256"],
        "first_frame": first,
        "stop_frame": stop,
        "frames": frames,
        "assets": plan["assets"],
        "creator_approved_for_release": False,
    }
    return {"format": PACKET_FORMAT, "source": source,
            "source_sha256": _digest(source)}


def validate_packet(plan, packet):
    if (type(packet) is not dict or packet.get("format") != PACKET_FORMAT or
            type(packet.get("source")) is not dict or
            packet.get("source_sha256") != _digest(packet["source"]) or
            packet["source"].get("parent_manifest_sha256") != plan["manifest_sha256"] or
            packet["source"].get("source_edit_sha256") != plan["source_edit_sha256"] or
            packet["source"].get("source_project_id") != plan["source_project_id"] or
            packet["source"].get("creator_approved_for_release") is not False):
        raise PermissionError("Unreviewed, changed or untrusted Blender source")
    s = packet["source"]
    # Reconstruct from the original parent manifest. A packet with a new,
    # internally consistent SHA cannot silently replace selected source.
    exact = source_packet(plan, s["shot_number"], s["first_frame"], s["stop_frame"])
    if packet != exact:
        raise PermissionError("Chunk differs from original FilmIndex source")
    return s


def stage_chunk(plan, worker, shot_no, first, stop):
    if not isinstance(worker, BlenderWorkerSupervisor):
        raise TypeError("FILM02 must use the established contained Blender worker")
    packet = source_packet(plan, shot_no, first, stop)
    validate_packet(plan, packet)
    job_id = "film02_s%d_f%04d_" % (shot_no, first) + plan["manifest_sha256"][:16]
    job = worker.root / job_id
    script = Path(__file__).with_name("nvp_film02_blender_cycles_worker.py")
    if not script.is_file() or script.is_symlink():
        raise PermissionError("Reviewed first-party Blender bpy adapter unavailable")
    script_bytes = script.read_bytes()
    packet_bytes = _canonical(packet)
    resumed = job.exists() or job.is_symlink()
    if resumed:
        if (job.is_symlink() or
                not (job / MANIFEST).is_file() or
                (job / MANIFEST).read_bytes() != packet_bytes or
                not (job / SCRIPT).is_file() or
                (job / SCRIPT).read_bytes() != script_bytes):
            raise PermissionError("Prior shot batch cannot be trusted or resumed")
    else:
        job.mkdir(mode=0o700, exist_ok=False)
        _write_exclusive(job, MANIFEST, packet_bytes)
        _write_exclusive(job, SCRIPT, script_bytes)
    op = BlenderOperation(
        job_id=job_id,
        script=SCRIPT,
        script_sha256=sha_file(job / SCRIPT),
        inputs={MANIFEST: sha_file(job / MANIFEST)},
        outputs=dict(OUT_FIELDS),
        arguments={"--manifest": MANIFEST, "--output": "scene.blend",
                   "--audit": "audit.json", "--out": "frames"},
        timeout_seconds=600, memory_limit_mb=3072,
        require_linux_cgroup_v2=False, gpu_memory_mb=0,
    )
    if not resumed:
        worker._validate(op)
    return op, packet, job, resumed


def inspect_chunk(plan, worker, op, packet, job):
    """Independent exact PNG and source verification before admitting pixels."""
    status = worker.verify_completed(op.job_id)
    if status["state"] != "SUCCEEDED":
        raise RuntimeError("Only fully verified contained Blender jobs are accepted")
    source = validate_packet(plan, packet)
    audit_path = job / "audit.json"
    if audit_path.is_symlink():
        raise PermissionError("Blender native audit cannot be a symlink")
    audit = json.loads(audit_path.read_text("utf8"))
    if (audit.get("passed") is not True or
            audit.get("format") != RECEIPT_FORMAT or
            audit.get("engine") != "CYCLES" or
            audit.get("device") != "CPU" or
            audit.get("samples", 0) < 8 or
            audit.get("glossy_bounces", 0) < 4 or
            audit.get("original_source_modified") is not False or
            audit.get("picture_rendered_in_genuine_cycles") is not True or
            audit.get("original_audio_rendered") is not False or
            audit.get("creator_visual_approval") is not False or
            audit.get("source_parent_manifest_sha256") != plan["manifest_sha256"] or
            audit.get("source_edit_sha256") != plan["source_edit_sha256"] or
            audit.get("source_take_sha256") != source["take_sha256"] or
            audit.get("shot_number") != source["shot_number"] or
            audit.get("first_frame") != source["first_frame"] or
            audit.get("stop_frame") != source["stop_frame"] or
            audit.get("blend_sha256") != sha_file(job / "scene.blend")):
        raise RuntimeError("Original-shot native Blender audit mismatched frozen project")
    rows = audit.get("rendered_frame_rows")
    if type(rows) is not list or len(rows) != source["stop_frame"] - source["first_frame"]:
        raise RuntimeError("Native Cycles chunk is missing picture frames")
    for i, (row, orig) in enumerate(zip(rows, source["frames"]), source["first_frame"]):
        png = job / "frames" / f"frame_{i:04d}.png"
        if (row.get("frame_zero") != i or
                row.get("output_film_tick") != orig["output_film_tick"] or
                row.get("source_film_tick") != orig["source_film_tick"] or
                row.get("source_take_sha256") != orig["source_take_sha256"] or
                row.get("snapshot_sha256") != orig["snapshot_sha256"] or
                row.get("original_sound_event_ids") != orig["source_sound_event_ids"] or
                png.is_symlink() or not png.is_file() or
                row.get("png_sha256") != sha_file(png) or
                row.get("png_bytes") != png.stat().st_size):
            raise PermissionError("Native Cycles pixels/source/time altered at frame " + str(i))
        with Image.open(png) as image:
            image.load()
            if image.format != "PNG" or image.size != (640, 360):
                raise RuntimeError("Only original full 640x360 native Cycles PNGs")
    if (sha_file(job / "preview.png") !=
            rows[0]["png_sha256"]):
        raise RuntimeError("Blender independently declared preview differs from frame")
    return rows


def _copy_verified(png, dest):
    if dest.exists() or dest.is_symlink():
        if (dest.is_symlink() or not dest.is_file() or
                sha_file(dest) != sha_file(png)):
            raise PermissionError("Existing completed frame cannot be overwritten")
    else:
        shutil.copy2(png, dest)


def run_original_shot(source_root, manifest_path, out, blender, *,
                      shot_no, ci_test_consent=False):
    if not ci_test_consent:
        raise PermissionError("Only explicitly approved disposable CI test may render")
    source_root = Path(source_root).resolve(strict=True)
    manifest_path = Path(manifest_path).resolve(strict=True)
    out = Path(out).resolve()
    if (out == source_root or out.is_relative_to(source_root) or
            source_root.is_relative_to(out) or out.is_symlink()):
        raise PermissionError("Native derived render workspace cannot contain original source")
    report = json.loads((source_root / "original-source-report.json").read_text("utf8"))
    plan = json.loads(manifest_path.read_text("utf8"))
    validate_handoff(plan, report)
    # This reopens the SAME source data and exact Take SHA on every runner.
    # Three shots cannot each secretly use their own newly created project.
    current = build_handoff(source_root)
    if current != plan:
        raise PermissionError("Downloaded handoff differs from actual frozen FilmIndex source")
    if type(shot_no) is not int or shot_no not in (0, 1, 2):
        raise ValueError("Only one of the three original source shots")
    executable = Path(shutil.which(str(blender)) or blender).resolve()
    if not executable.is_file():
        raise FileNotFoundError("Only real reviewed Blender native binary")
    version = subprocess.run(
        [str(executable), "-b", "--version"],
        capture_output=True, text=True, check=True, timeout=25).stdout.splitlines()[0]
    if not version.startswith("Blender "):
        raise PermissionError("Not the real approved Blender binary")
    out.mkdir(parents=True, exist_ok=True)
    ledger = TaskLedger(out / "activity")
    worker = BlenderWorkerSupervisor(
        out / "native_blender_worker",
        blender_executable=executable,
        blender_sha256=sha_file(executable),
        blender_version=version,
        activity_ledger=ledger)
    permissions = {}
    def approval_check(approval_id, digest, document):
        spec = document.get("operation", {})
        expected = permissions.get(approval_id)
        return bool(expected and spec == json.loads(expected.canonical()))
    dispatcher = ApprovedBlenderDispatcher(
        worker, ledger, approval_check=approval_check)
    review = out / "review" / f"shot_{shot_no}"
    frames_dir = review / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    all_rows, chunks, scene_samples = [], [], []
    start = shot_no * SHOT_FRAMES
    stop = start + SHOT_FRAMES
    for first in range(start, stop, BATCH):
        end = min(first + BATCH, stop)
        op, packet, job, resumed = stage_chunk(
            plan, worker, shot_no, first, end)
        if resumed:
            # Journals are never replayed or silently declared recovered.
            if worker.inspect(op.job_id)["state"] != "SUCCEEDED":
                raise RuntimeError("Interrupted/failed Blender chunk requires separate reviewed retry")
            worker.verify_completed(op.job_id)
        else:
            approval_id = "CI_ONLY_FILM02_" + op.job_id
            permissions[approval_id] = op
            if not dispatcher.enqueue(op, approval_id=approval_id, lane="standard"):
                raise RuntimeError("Trusted native Blender resource claim not queued")
            outcome = dispatcher.run_next()
            if not outcome or outcome.get("state") != "SUCCEEDED":
                raise RuntimeError("Contained approved native Blender chunk failed: " + str(outcome))
        rows = inspect_chunk(plan, worker, op, packet, job)
        if first in (start, stop - BATCH):
            samples = review / "source_scene_samples"
            samples.mkdir(parents=True, exist_ok=True)
            scene_path = samples / f"frame_{first:04d}.blend"
            source_path = samples / f"frame_{first:04d}.source.json"
            _copy_verified(job / "scene.blend", scene_path)
            _copy_verified(job / "source.json", source_path)
            scene_samples.append({
                "first_frame": first,
                "scene_file": scene_path.name,
                "scene_sha256": sha_file(scene_path),
                "source_file": source_path.name,
                "source_sha256": sha_file(source_path),
            })
        for item in rows:
            n = item["frame_zero"]
            _copy_verified(job / "frames" / f"frame_{n:04d}.png",
                           frames_dir / f"frame_{n:04d}.png")
        all_rows.extend(rows)
        chunks.append({
            "job_id": op.job_id, "first_frame": first, "stop_frame": end,
            "worker_state": "SUCCEEDED", "script_sha256": op.script_sha256,
            "source_packet_sha256": packet["source_sha256"],
            "audit_sha256": sha_file(job / "audit.json"),
            "scene_blend_sha256": sha_file(job / "scene.blend"),
            "reverified_completed_job": resumed,
        })
    if (len(all_rows) != SHOT_FRAMES or
            [r["frame_zero"] for r in all_rows] != list(range(start, stop))):
        raise RuntimeError("Native Blender source original shot missing pictures")
    contact = Image.new("RGB", (3*640 + 4*12, 400), (20, 22, 26))
    pen = ImageDraw.Draw(contact)
    for i, frame in enumerate((start, start+120, stop-1)):
        with Image.open(frames_dir / f"frame_{frame:04d}.png") as img:
            img.load()
            x = 12 + i * 652
            contact.paste(img.convert("RGB"), (x, 12))
        pen.text((x, 376), f"REAL Cycles FILM02 shot {shot_no} output frame {frame}",
                 fill=(234, 237, 241))
    contact_path = review / "three_original_Cycles_moments.png"
    if contact_path.exists():
        if sha_file(contact_path) != sha256(_image_bytes(contact)).hexdigest():
            # Re-review is deterministic only when original accepted files match.
            raise RuntimeError("Previously accepted source contact was changed")
    else:
        contact.save(contact_path, format="PNG")
    receipt = {
        "format": SHOT_FORMAT, "passed": True,
        "original_project_id": plan["source_project_id"],
        "source_manifest_sha256": plan["manifest_sha256"],
        "source_edit_sha256": plan["source_edit_sha256"],
        "source_take_sha256": plan["shots"][shot_no]["take_sha256"],
        "source_original_sound_sha256": plan["shots"][shot_no]["sound_sha256"],
        "shot_number": shot_no, "first_frame": start, "stop_frame": stop,
        "rendered_frame_count": SHOT_FRAMES, "fps": FPS,
        "genuine_blender_cycles": True,
        "blender_version": version,
        "blender_binary_sha256": sha_file(executable),
        "chunks": chunks, "frames": all_rows,
        "saved_native_blender_scene_samples": scene_samples,
        "contact_sha256": sha_file(contact_path),
        "all_native_job_and_image_SHA_verified": True,
        "original_take_and_edit_unchanged": True,
        "continuous_30s_movie_muxed": False,
        "real_creator_artistic_approval": False,
        "2k_cinema_master_or_DCP": False,
    }
    receipt_path = review / "shot_receipt.json"
    if receipt_path.exists():
        old = json.loads(receipt_path.read_text("utf8"))
        # The resumed flags are run-local; validate immutable critical fields.
        for key in ("source_manifest_sha256", "source_edit_sha256",
                    "source_take_sha256", "frames", "contact_sha256"):
            if old[key] != receipt[key]:
                raise PermissionError("Previously accepted completed shot changed")
    else:
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return receipt


def _image_bytes(image):
    from io import BytesIO
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", required=True, type=Path)
    cli.add_argument("--handoff", required=True, type=Path)
    cli.add_argument("--out", required=True, type=Path)
    cli.add_argument("--blender", required=True)
    cli.add_argument("--shot", required=True, type=int, choices=(0, 1, 2))
    cli.add_argument("--consent", required=True)
    args = cli.parse_args()
    if args.consent != "I_APPROVE_DISPOSABLE_FILM02_NATIVE_CYCLES_RENDER":
        cli.error("Real Blender render requires an explicit trusted CI fixture grant")
    result = run_original_shot(
        args.source, args.handoff, args.out, args.blender,
        shot_no=args.shot, ci_test_consent=True)
    print(json.dumps({
        "shot": result["shot_number"], "native_frames": result["rendered_frame_count"],
        "original_source_manifest_sha256": result["source_manifest_sha256"],
        "all_verified": result["all_native_job_and_image_SHA_verified"],
        "complete_movie": result["continuous_30s_movie_muxed"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
