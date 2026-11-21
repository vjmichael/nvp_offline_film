"""POST-01F: R1 documented Python IC-LoRA CLI, for a reviewed installed broker.

Builds argv only; never launches Python, downloads weights, reads project
secrets or proves inference. Broker must validate exact installed pins and
remove native-generated audio before producing the picture-only result.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.nvp_post01f_ltx_native_handoff import WIRE, validate_intent
from backend.nvp_diffusion_music_prompt import compose_diffusion_prompt


def build_layout_to_render_argv(plan: dict, *, job_root: Path,
                                installed: dict) -> list[str]:
    if not isinstance(plan, dict) or plan.get("format") != WIRE:
        raise ValueError("Versioned POST-01F LTX plan required")
    intent = {k:v for k,v in plan.items() if k not in ("format","job_id")}
    validate_intent(intent)
    root = Path(job_root)
    if not root.is_dir() or root.is_symlink():
        raise PermissionError("Existing protected per-job stage required")
    if not isinstance(installed, dict) or set(installed) != {
            "python", "checkpoint", "spatial_upsampler", "gemma_root", "lora", "install_root"}:
        raise ValueError("Exact reviewed runtime role roster required")
    base = Path(installed["install_root"]).resolve(strict=True)
    if not base.is_dir() or base.is_symlink() or base == root.resolve(strict=True):
        raise PermissionError("Disjoint pinned model code root required")
    resolved = {}
    for name in ("python", "checkpoint", "spatial_upsampler", "lora", "gemma_root"):
        item = Path(installed[name])
        if not item.is_absolute() or item.is_symlink() or not item.exists():
            raise PermissionError("Unreviewed model/runtime path")
        item = item.resolve(strict=True)
        if not item.is_relative_to(base):
            raise PermissionError("LTX runtime asset escapes reviewed install root")
        if name != "gemma_root" and not item.is_file():
            raise PermissionError("Pinned LTX file is absent")
        if name == "gemma_root" and not item.is_dir():
            raise PermissionError("Pinned Gemma model directory is absent")
        resolved[name] = str(item)
    guide = root/"conditioning.json"
    if guide.is_symlink() or not guide.is_file() or guide.stat().st_size > 16*1024:
        raise PermissionError("Bounded native conditioning missing")
    data = json.loads(guide.read_text("utf-8"))
    standard_fields = {"positive_prompt", "take_sha256", "camera_id"}
    if (not isinstance(data,dict) or set(data) not in (standard_fields, standard_fields|{"no_background_music"}) or
        data["take_sha256"] != intent["take_sha256"] or
        data["camera_id"] != intent["camera_id"] or
        type(data["positive_prompt"]) is not str or
        type(data.get("no_background_music",False)) is not bool):
        raise ValueError("Frozen Take/shot prompt does not match structured conditioning")
    final_prompt = compose_diffusion_prompt(data["positive_prompt"],
                        no_background_music=data.get("no_background_music",False))
    return [resolved["python"],"-m","ltx_pipelines.ic_lora",
        "--distilled-checkpoint-path",resolved["checkpoint"],
        "--spatial-upsampler-path",resolved["spatial_upsampler"],
        "--gemma-root",resolved["gemma_root"],
        "--lora",resolved["lora"],
        "--video-conditioning",str((root/"layout.mp4").resolve(strict=True)),"1.0",
        "--stage-2-ic-lora",
        "--image",str((root/"look.png").resolve(strict=True)),"-1","1.0",
        "--prompt",final_prompt,"--seed",str(intent["seed"]),
        "--height",str(intent["height"]),"--width",str(intent["width"]),
        "--num-frames",str(intent["model_frames"]),
        "--frame-rate","24",
        "--output-path",str(root/"picture.native.mp4")]
