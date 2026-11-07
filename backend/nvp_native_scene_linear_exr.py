"""Batch 3: unmastered true scene-linear ACEScg FLOAT32 OpenEXR derivative.

This intentionally does NOT run a display-view transform: EXR holds
creative source-linear RGB in ACEScg for future mastering. A separately
approved SDR PNG16/DCP output is downstream, not an alternate capture.

Only a verified frozen original USD Take, source-authored camera at exact
Film Time, immutable grade revision, and pinned native OpenColorIO config
can produce images. Files go exclusively to native approved staging.
There is no FFmpeg, external executable, 8-bit source frame or arbitrary
asset resolver anywhere in this route.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import math

from backend.nvp_native_color_decisions import NativeColorDecisions
from backend.nvp_native_aces_color import (
    _deps,CONFIG_URI,SOURCE,grade_scene_linear,policy)
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster
from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_temporal_ledger import _int

FORMAT="nvp.native_ocio.source_acescg_float32_exr.v1"
DEST="ACEScg"
MAX_EXR_BYTES=32*1024*1024


class NativeSceneLinearEXR:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Original verified FilmIndex is required")
        self.index=index

    def write(self,project_id,take_id,take_sha256,grade_id,grade_revision,
              grade_sha256,*,tick,camera_path,expected_config_sha256,
              output_file,source_session=None,source_snapshot=None):
        _require_pid(project_id)
        _id(take_id,"frozen original USD Take")
        _id(grade_id,"non-destructive color grade")
        for sha_value in (take_sha256,grade_sha256,expected_config_sha256):
            _sha(sha_value)
        _int(tick,"exact Film Time scene-linear picture tick")
        grade=NativeColorDecisions(self.index).read(
            project_id,grade_id,grade_revision)
        if (grade["take_id"]!=take_id or grade["take_sha256"]!=take_sha256 or
            grade["document_sha256"]!=grade_sha256):
            raise RuntimeError("Original source grade revision is not pinned")
        info,_=policy()
        if info["configuration_sha256"]!=expected_config_sha256:
            raise RuntimeError("Native ACEScg transform config is not pinned")
        ocio,np=_deps()
        config=ocio.Config.CreateFromBuiltinConfig(CONFIG_URI)
        if config.getColorSpace(DEST) is None:
            raise RuntimeError("Native OCIO ACEScg float scene-linear space is missing")
        transform=ocio.ColorSpaceTransform(src=SOURCE,dst=DEST)
        cpu=config.getProcessor(transform).getDefaultCPUProcessor()
        rgba,original=NativeSceneLinearRaster(self.index).render(
            project_id,take_id,take_sha256,tick=tick,camera_path=camera_path,
            source_session=source_session,source_snapshot=source_snapshot)
        source_sha=sha256(rgba.tobytes()).hexdigest()
        graded=grade_scene_linear(rgba,grade["parameters"],np)
        cpu.applyRGBA(graded)
        if (not np.isfinite(graded).all() or
            not np.allclose(graded[:,:,3],1.,rtol=0,atol=1e-6) or
            graded.dtype!=np.float32):
            raise RuntimeError("OCIO ACEScg source-linear conversion invalid")
        rgb=np.ascontiguousarray(graded[:,:,:3],dtype=np.float32)
        dest=Path(output_file)
        if (dest.suffix.lower()!=".exr" or
            dest.is_symlink() or dest.exists() or
            dest.parent.is_symlink() or not dest.parent.is_dir()):
            raise PermissionError("Only a newly staged trusted native EXR destination")
        try:
            import OpenEXR
        except ImportError as exc:
            raise RuntimeError("Pinned native OpenEXR package absent; no external codec fallback") from exc
        if not str(getattr(OpenEXR,"__version__","")).startswith("3.4.17"):
            raise RuntimeError("Installed native OpenEXR version not approved")
        hdr={
            "type":OpenEXR.scanlineimage,
            "compression":OpenEXR.ZIP_COMPRESSION,
            "nvpOriginalTakeSha":take_sha256,
            "nvpOriginalSceneSha":original["scene_document_sha256"],
            "nvpOriginalSnapshotSha":original["scene_snapshot_sha256"],
            "nvpSavedGradeSha":grade_sha256,
            "nvpOCIOConfigSha":expected_config_sha256,
            "nvpColorSpace":DEST,
            "nvpFilmTimeTick":str(tick),
            "nvpCinemaMasterStatus":"unmastered",
        }
        try:
            with OpenEXR.File(hdr,{"RGB":rgb}) as outfile:
                outfile.write(str(dest))
            if dest.stat().st_size>MAX_EXR_BYTES:
                raise RuntimeError("Original source EXR exceeds resource bound")
            with OpenEXR.File(str(dest)) as opened:
                source=opened.channels()["RGB"].pixels
                if (source.dtype!=np.float32 or source.shape!=rgb.shape or
                    not np.array_equal(source,rgb) or
                    opened.header()["nvpOriginalTakeSha"]!=take_sha256 or
                    opened.header()["nvpOCIOConfigSha"]!=expected_config_sha256):
                    raise RuntimeError("Native EXR source validation failed")
            if sha256(rgba.tobytes()).hexdigest()!=source_sha:
                raise RuntimeError("Original scene-linear pixel buffer was modified")
            if self.index.read_revision(
                project_id,take_id,1)["document_sha256"]!=take_sha256:
                raise RuntimeError("Frozen Take changed while authoring EXR")
            receipt={
                "format":FORMAT,"status":"UNMASTERED_SOURCE_LINEAR_ACESCG_EXR",
                "source_tick":str(tick),"camera_path":camera_path,
                "take_sha256":take_sha256,
                "grade_sha256":grade_sha256,
                "ocio_config_sha256":expected_config_sha256,
                "original_float_rgba_sha256":source_sha,
                "output_exr_sha256":_sha_file(dest),
                "working_space":DEST,
                "scene_snapshot_sha256":original["scene_snapshot_sha256"],
                "width":int(rgb.shape[1]),"height":int(rgb.shape[0]),
                "components":3,"float_bits_per_component":32,
                "source_camera_colorimetry_calibrated":False,
                "source_usd_light_transport_calibrated":False,
                "professional_master_approved":False,
                "original_modified":False,"ffmpeg_used":False,
            }
            return receipt
        except BaseException:
            dest.unlink(missing_ok=True)
            raise


def _sha_file(path):
    digest=sha256()
    with Path(path).open("rb") as f:
        while data:=f.read(1024*1024):digest.update(data)
    return digest.hexdigest()
