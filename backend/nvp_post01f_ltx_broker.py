"""POST-01F R4: fixed installed LTX Layout-to-Render broker entrypoint.

To be packaged as an independently pinned, installed Windows executable;
never launch this file as an unsandboxed substitute for AppContainer custody.
No network, no arbitrary commands and no original scene/PCM/project keys.

This module is REAL source for the broker: calls the installed ltx-pipelines
Python entrypoint in-process, then a separately checksum-pinned external-media
FFmpeg/ffprobe pair to remove generated audio and the one derived pad frame.
It is NOT proof that any Windows build, license, checkpoint or GPU works.
"""
from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from backend.nvp_post01f_ltx_native_handoff import (
    WIRE, RESULT, MAX_PLAN, MAX_PICTURE, MAX_LAYOUT, MAX_LOOK,
    MAX_CONDITIONING, _canonical, _sha, digest_file, validate_intent,
    _write_new,
)
from backend.nvp_post01f_ltx_native_command import build_layout_to_render_argv
from backend.nvp_post01f_scm_lowbox_guard import require_current_scm_lowbox_job

LOCK_FORMAT = "nvp.post01f.installed_ltx_runtime_lock.v1"
LOCK_NAME = "nvp_ltx_runtime.lock.json"
# Asset hash verification is intentionally NOT skipped based on mtimes or filenames.
ASSET_FILES = ("python", "checkpoint", "spatial_upsampler", "lora", "ffmpeg", "ffprobe")
ASSET_DIRS = ("gemma_root", "ltx_package")
ALLOW_EXTRA = frozenset(("picture.native.mp4",))
MAX_LOCK = 65536
MAX_NATIVE = 1024 * 1024 * 1024
MAX_PROBE = 256 * 1024
MAX_MODEL_FILES = 2048


def _read_json(path: Path, limit: int) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > limit or path.stat().st_size < 2:
        raise PermissionError("Missing or unbounded native LTX JSON")
    raw = path.read_bytes()
    if len(raw) > limit:
        raise PermissionError("Native LTX JSON grew during read")
    value = json.loads(raw)
    if type(value) is not dict:
        raise ValueError("Native LTX JSON object required")
    return value


def _inside(file: Path, base: Path) -> Path:
    if not file.is_absolute() or file.is_symlink():
        raise PermissionError("Only a real absolute installed path is permitted")
    target = file.resolve(strict=True)
    if not target.is_relative_to(base):
        raise PermissionError("Installed asset escapes the reviewed code root")
    return target


def _asset_tree(path: Path, *, maximum_files: int = MAX_MODEL_FILES) -> dict[str, str]:
    """Hash every reviewed file, refusing reparse points and new/unlisted files."""
    if path.is_symlink() or not path.is_dir():
        raise PermissionError("Reviewed model/package tree must exist without symlink")
    files = {}
    for file in sorted(path.rglob("*")):
        if file.is_symlink():
            raise PermissionError("Installed model/package subtree contains linked asset")
        if file.is_dir():
            continue
        if not file.is_file() or len(files) >= maximum_files:
            raise PermissionError("Unreviewed or unbounded installed asset tree")
        name = file.relative_to(path).as_posix()
        files[name] = digest_file(file, 80*1024*1024*1024)
    if not files:
        raise PermissionError("Unpopulated installed runtime asset directory")
    return files


def read_pinned_install(installed_executable: Path, expected_lock_sha256: str) -> dict:
    """Immutable reviewed manifest adjacent to the installed broker; no job paths."""
    exe = Path(installed_executable)
    if not exe.is_absolute() or exe.is_symlink() or not exe.is_file():
        raise PermissionError("Only an installed reviewed LTX broker is allowed")
    base = exe.resolve(strict=True).parent
    lock = base / LOCK_NAME
    if digest_file(lock, MAX_LOCK) != _sha(expected_lock_sha256):
        raise PermissionError("Installed LTX runtime/model manifest changed")
    obj = _read_json(lock, MAX_LOCK)
    if set(obj) != {"format", "install_root", "upstream_commit", "files", "directories"} or obj["format"] != LOCK_FORMAT or (
        type(obj["upstream_commit"]) is not str or
        not re.fullmatch(r"[a-f0-9]{40}", obj["upstream_commit"])):
        raise PermissionError("Unreviewed LTX pipeline revision/manifest shape")
    root = _inside(Path(obj["install_root"]), base)
    if not root.is_dir() or not isinstance(obj["files"], dict) or set(obj["files"]) != set(ASSET_FILES) or (
        not isinstance(obj["directories"], dict) or set(obj["directories"]) != set(ASSET_DIRS)):
        raise PermissionError("Incomplete pinned LTX model/runtime stack")
    resolved = {"install_root": str(root)}
    for role in ASSET_FILES:
        item = obj["files"][role]
        if type(item) is not dict or set(item) != {"path", "sha256"}:
            raise PermissionError("Incomplete installed binary/model pin")
        path = _inside(Path(item["path"]), root)
        if not path.is_file() or digest_file(path, 80*1024*1024*1024) != _sha(item["sha256"]):
            raise PermissionError("Pinned runtime/model file did not match installed bytes")
        resolved[role] = str(path)
    for role in ASSET_DIRS:
        item = obj["directories"][role]
        if type(item) is not dict or set(item) != {"path", "files"} or not isinstance(item["files"], dict):
            raise PermissionError("Incomplete installed model directory receipt")
        path = _inside(Path(item["path"]), root)
        actual = _asset_tree(path)
        if not item["files"] or set(actual) != set(item["files"]) or any(
            actual[k] != _sha(v) for k,v in item["files"].items()):
            raise PermissionError("Pinned model/package tree drifted")
        resolved[role] = str(path)
    if Path(resolved["python"]).resolve() != exe.resolve():
        raise PermissionError("Reviewed Python execution entry must be the installed broker itself")
    return resolved


def validate_broker_job(stage: Path, *, installed_executable: Path, expected_lock_sha256: str) -> tuple[dict, dict]:
    """Repeat hashes *inside* the installed worker; host repeats them after exit."""
    root = Path(stage)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.parent.is_symlink():
        raise PermissionError("Broker requires a trusted existing protected source stage")
    plan = _read_json(root / "plan.json", MAX_PLAN)
    if set(plan) != {"format", "job_id", *validate_intent({k:v for k,v in plan.items() if k not in ("format", "job_id")})} or plan["format"] != WIRE or (
        type(plan["job_id"]) is not str or not re.fullmatch(r"ltx_[0-9a-f]{24}", plan["job_id"]) or
        root.name != plan["job_id"]):
        raise PermissionError("Foreign or unbounded LTX job identity")
    if plan["model_stack_sha256"] != _sha(expected_lock_sha256):
        raise PermissionError("Job requested an unreviewed model stack")
    allowed = {"journal.json", "plan.json", "layout.mp4", "look.png", "conditioning.json", "stdout.log", "stderr.log"}
    if set(p.name for p in root.iterdir()) != allowed or any(p.is_symlink() or not p.is_file() for p in root.iterdir()):
        raise PermissionError("Native broker stage contains unreviewed input/sidecars")
    for name, key, limit in (
        ("layout.mp4", "layout_sha256", MAX_LAYOUT),
        ("look.png", "look_sha256", MAX_LOOK),
        ("conditioning.json", "conditioning_sha256", MAX_CONDITIONING)):
        if digest_file(root/name, limit) != plan[key]:
            raise PermissionError("Mutable original-derived conditioning rejected")
    from backend.nvp_w1g_encrypted_source import verify_efs_inputs
    verify_efs_inputs(root, ("journal.json", "plan.json", "layout.mp4", "look.png", "conditioning.json"))
    installed = read_pinned_install(installed_executable, expected_lock_sha256)
    return plan, installed


def _probe_media(ffprobe: Path, path: Path) -> dict:
    """External MEDIA boundary only; the original core never invokes FFmpeg."""
    cmd = [str(ffprobe), "-v", "error", "-count_frames", "-show_entries",
           "stream=nb_read_frames,index,codec_type,width,height,avg_frame_rate",
           "-of", "json", str(path)]
    require_current_scm_lowbox_job()
    completed = subprocess.run(cmd, cwd=str(path.parent), stdin=subprocess.DEVNULL,
                               capture_output=True, shell=False, timeout=90, check=True)
    if len(completed.stdout) > MAX_PROBE:
        raise PermissionError("Unbounded native media probe")
    result = json.loads(completed.stdout)
    streams = result.get("streams")
    if type(streams) is not list or not streams:
        raise ValueError("No native media stream metadata")
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if len(videos) != 1 or len(streams) != len(videos) + len(audio):
        raise ValueError("Unexpected native data, subtitle or multi-video streams")
    stream = videos[0]
    try:
        n = int(stream["nb_read_frames"])
        fps = Fraction(stream["avg_frame_rate"])
        width, height = stream["width"], stream["height"]
    except (KeyError, ValueError, ZeroDivisionError) as exc:
        raise PermissionError("Native decoder did not expose an exact frame count") from exc
    if type(width) is not int or type(height) is not int:
        raise ValueError("Native picture dimensions absent")
    return {"frames":n,"fps":fps,"width":width,"height":height,"audio_streams":len(audio)}


def conform_picture_only(*, stage: Path, plan: dict, installed: dict) -> dict:
    """Decode/re-encode bounded model clip as 120-frame, video-only artifact.

    The output is re-encoded to avoid temporal dependence on the dropped final
    frame. Exact PTS/stream acceptance remains the INDEPENDENT host's job.
    """
    root = Path(stage)
    source, picture = root / "picture.native.mp4", root / "picture.mp4"
    if picture.exists() or picture.is_symlink():
        raise PermissionError("Refuse replacement of an existing picture")
    digest_file(source, MAX_NATIVE)
    native = _probe_media(Path(installed["ffprobe"]), source)
    if (native["frames"] != plan["model_frames"] or native["fps"] != Fraction(24,1)
        or native["width"] != plan["width"] or native["height"] != plan["height"]):
        raise PermissionError("Native generation does not match 8k+1 frame layout")
    command = [installed["ffmpeg"], "-nostdin", "-hide_banner", "-loglevel", "error",
        "-protocol_whitelist", "file", "-i", str(source),
        "-map", "0:v:0", "-an", "-sn", "-dn", "-frames:v", str(plan["display_frames"]),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", "-n", str(picture)]
    require_current_scm_lowbox_job()
    subprocess.run(command, cwd=str(root), stdin=subprocess.DEVNULL, capture_output=True,
                   shell=False, timeout=600, check=True)
    # Original model mp4 may have generated audio. It must never persist after
    # the picture-only derivative exists, even in an encrypted sidecar.
    if source.is_symlink() or not source.is_file():
        raise PermissionError("Native intermediate disappeared")
    source.unlink()
    final = _probe_media(Path(installed["ffprobe"]), picture)
    if (final["frames"] != plan["display_frames"] or final["fps"] != Fraction(24,1)
        or final["width"] != plan["width"] or final["height"] != plan["height"]
        or final["audio_streams"] != 0):
        raise PermissionError("Derived picture still contains audio, missing frames or incorrect timing")
    picture_sha = digest_file(picture, MAX_PICTURE)
    from backend.nvp_w1g_encrypted_source import verify_efs_inputs
    verify_efs_inputs(root, ("picture.mp4",))
    return {"sha":picture_sha, "frames":final["frames"], "audio_streams":0}


def verify_derived_inputs_before_generation(*, stage: Path, plan: dict, installed: dict) -> dict:
    """Decode the *derived* layout before inference; do not infer 8k+1 from its filename.

    A 120-frame Film Time interval must be compiled to a 121-frame guide by
    the trusted NVP source compiler before invoking LTX. Raw 120 frames would
    otherwise be snapped down by the upstream temporal frame grid.
    """
    root = Path(stage)
    layout = _probe_media(Path(installed["ffprobe"]),root/"layout.mp4")
    if (layout["frames"] != plan["model_frames"] or layout["fps"] != Fraction(24,1)
        or layout["width"] != plan["width"] or layout["height"] != plan["height"]
        or layout["audio_streams"] != 0):
        raise PermissionError("Low-poly guide lacks exact derived 8k+1 frame grid/zero audio")
    still = root/"look.png"
    if still.is_symlink() or not still.is_file() or still.stat().st_size > MAX_LOOK:
        raise PermissionError("Missing approved bounded art-directed first frame")
    with still.open("rb") as source:
        header = source.read(24)
    if (header[:8] != b"\x89PNG\r\n\x1a\n" or
        header[12:16] != b"IHDR" or len(header) != 24):
        raise PermissionError("Approved look is not a recognized PNG with an IHDR")
    width,height = int.from_bytes(header[16:20],"big"),int.from_bytes(header[20:24],"big")
    if width != plan["width"] or height != plan["height"]:
        raise PermissionError("Art-directed look still does not match the source camera canvas")
    return {"model_guide_frames":layout["frames"],"fps":24,
            "original_source_remains_authoritative":True}


def _run_real_ltx(argv: list[str], installed: dict, stage: Path) -> None:
    """Run pinned upstream IC-LoRA in this AppContainer, never a subprocess."""
    # This is set to suppress package downloads, not as a replacement for WFP.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    if argv[1:3] != ["-m", "ltx_pipelines.ic_lora"] or argv[0] != installed["python"]:
        raise PermissionError("Installed LTX CLI mismatch")
    package = importlib.import_module("ltx_pipelines.ic_lora")
    location = Path(package.__file__)
    if not location.resolve(strict=True).is_relative_to(Path(installed["ltx_package"])):
        raise PermissionError("Imported LTX implementation is outside pinned package")
    original = sys.argv
    try:
        sys.argv = ["ltx_pipelines.ic_lora", *argv[3:]]
        package.main()  # Actual model inference only on the provisioned Windows host.
    finally:
        sys.argv = original


def run_installed_broker(*, stage: Path, installed_executable: Path,
                         expected_lock_sha256: str) -> dict:
    """Actual installed entrypoint; exits nonzero on any missing native proof."""
    if os.name != "nt":
        raise PermissionError("Installed LTX broker is Windows AppContainer-only")
    plan, installed = validate_broker_job(stage,
        installed_executable=installed_executable,
        expected_lock_sha256=expected_lock_sha256)
    argv = build_layout_to_render_argv(plan, job_root=Path(stage), installed={
        name: installed[name] for name in
        ("install_root", "python", "checkpoint", "spatial_upsampler", "gemma_root", "lora")})
    verify_derived_inputs_before_generation(stage=Path(stage),plan=plan,installed=installed)
    _run_real_ltx(argv, installed, Path(stage))
    out = conform_picture_only(stage=Path(stage), plan=plan, installed=installed)
    for name in ("layout.mp4", "look.png", "conditioning.json"):
        if digest_file(Path(stage)/name, {
            "layout.mp4":MAX_LAYOUT,"look.png":MAX_LOOK,"conditioning.json":MAX_CONDITIONING}[name]) != plan[{
            "layout.mp4":"layout_sha256", "look.png":"look_sha256", "conditioning.json":"conditioning_sha256"}[name]]:
            raise PermissionError("Model execution mutated source conditioning")
    if set(p.name for p in Path(stage).iterdir()) != {
        "journal.json", "plan.json", "layout.mp4", "look.png", "conditioning.json",
        "stdout.log", "stderr.log", "picture.mp4"}:
        raise PermissionError("Native model produced unapproved extra files")
    response = {"format":RESULT,"job_id":plan["job_id"],"project_id":plan["project_id"],
        "plan_sha256":digest_file(Path(stage)/"plan.json", MAX_PLAN),
        "model_stack_sha256":plan["model_stack_sha256"], "picture_sha256":out["sha"],
        "picture_frames":plan["display_frames"],"fps":24,"width":plan["width"],
        "height":plan["height"],"audio_generated":False}
    _write_new(Path(stage)/"result.json", _canonical(response))
    from backend.nvp_w1g_encrypted_source import verify_efs_inputs
    verify_efs_inputs(Path(stage), ("result.json", "picture.mp4"))
    return response


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--nvp-ltx-job":
        raise SystemExit("Use reviewed --nvp-ltx-job <trusted existing plan.json> only")
    job = Path(sys.argv[2])
    if job.name != "plan.json" or not job.is_absolute() or job.is_symlink():
        raise PermissionError("Worker may only open a host-staged, absolute job plan")
    exe = Path(sys.executable).resolve(strict=True)
    lock = exe.parent / LOCK_NAME
    expected_sha = digest_file(lock, MAX_LOCK)
    run_installed_broker(stage=job.parent,installed_executable=exe,
                         expected_lock_sha256=expected_sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
