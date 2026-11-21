"""NVP B10: production-resolution safety policy for genuine frozen EXR renders.

Profiles are deliberately conservative on a household RAM/disk budget. This
does not claim pixels are photorealistic or OCIO/ACES-managed; that requires
independent B10 color conversion, render/asset quality checks and film review.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

MIB=1024*1024
GIB=1024*MIB


@dataclass(frozen=True)
class ResolutionProfile:
    name: str
    width: int
    height: int
    max_chunk_frames: int
    minimum_ram_mb: int
    estimated_rgba_f32_frame_bytes: int


def profile_for(width:int,height:int)->ResolutionProfile:
    if type(width) is not int or type(height) is not int:
        raise ValueError("Render dimensions must be integer")
    if not 64<=width<=3840 or not 64<=height<=2160:
        raise ValueError("Render output exceeds bounded 4K UHD policy")
    if width%2 or height%2:
        raise ValueError("Film frames require even pixel dimensions")
    area=width*height
    raw=area*4*4
    if area<=640*360:
        return ResolutionProfile("previsualization",width,height,8,1024,raw)
    if area<=1280*720:
        return ResolutionProfile("HD",width,height,2,2048,raw)
    if area<=1920*1080:
        return ResolutionProfile("full_HD",width,height,1,3072,raw)
    if area<=3840*2160:
        return ResolutionProfile("UHD_4K",width,height,1,8192,raw)
    raise ValueError("Unsupported rendering dimensions")


def validate_full_render(width:int,height:int,chunk_size:int,ram_mb:int,
                         frames:int,*,worker_root:Path,archive_root:Path):
    preset=profile_for(width,height)
    # The B9 Workbench backend requests gpu_memory_mb=0. On a real
    # Windows/AMD workstation that does NOT prove a UHD GPU render uses no
    # VRAM. Keep 4K as an explicit capacity profile but forbid execution
    # until native measured device admission is wired into its worker spec.
    if preset.name=="UHD_4K":
        raise RuntimeError(
            "UHD/4K render is planning-only until native GPU VRAM "
            "admission and a device-scoped resource ticket are implemented")
    if (type(chunk_size) is not int or
        not 1<=chunk_size<=preset.max_chunk_frames):
        raise ValueError("Frame batch size exceeds approved profile memory bounds")
    if (type(ram_mb) is not int or ram_mb<preset.minimum_ram_mb or
        ram_mb>65536):
        raise ValueError("Insufficient approved native RAM for output resolution")
    if type(frames) is not int or not 1<=frames<=14400:
        raise ValueError("Invalid bounded frame count")
    # Conservative worst-case uncompressed linear RGBA32; staging and content
    # addressed publishing duplicate source bytes while writing atomically.
    projected=2*frames*preset.estimated_rgba_f32_frame_bytes+GIB
    for root in (Path(worker_root),Path(archive_root)):
        if not root.is_dir() or root.is_symlink():
            raise RuntimeError("Trusted native render/archive path missing or symlinked")
        free=shutil.disk_usage(root).free
        if free<projected:
            raise RuntimeError(
                "Insufficient disk capacity for complete native EXR sequence")
    return {"profile":preset.name,"width":width,"height":height,
            "max_chunk_frames":preset.max_chunk_frames,
            "minimum_ram_mb":preset.minimum_ram_mb,
            "frames":frames,
            "expected_uncompressed_frame_bytes":preset.estimated_rgba_f32_frame_bytes,
            "required_available_disk_bytes":projected,
            "ready_for_resource_admission":True}
