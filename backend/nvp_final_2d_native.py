"""DA-05: creator-approved flattened 2D picture/audio package, NO FFmpeg.

The original 3D OpenUSD Digital Take remains authoritative. Only after
native creator approval does a trusted image-render backend evaluate
specific derived output instants and return PNGs. A bounded reader yields
PCM16 windows from the SAME frozen Take and the Python wave writer emits
a separate derived soundtrack. The output is an exact-SHA PNG image
sequence + PCM WAV + provenance manifest, NOT a conventional encoded
single-file film/DCP or complete cinema mastering implementation.

A real tested native 3D raster renderer must be injected as render_png.
Without one, fail closed; never silently render generic cards/proxies.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import wave

from PIL import Image

from backend.nvp_data_av_scene import FrozenSceneAV,MAX_SAMPLES
from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_temporal_ledger import (
    TICKS_PER_SECOND,tick_from_frame,frame_at_tick,_int)

FORMAT="nvp.final_2d.image_sequence_pcm.v1"
FORMAT_EXR="nvp.final_2d.acescg_exr_sequence_pcm.v1"
MAX_FRAMES=7200
MAX_PNG_BYTES=24*1024*1024
SAMPLE_RATE=48000
SAMPLE_TICKS=TICKS_PER_SECOND//SAMPLE_RATE
MAX_PIXELS=4096*2160
OUTPUT_CADENCES=frozenset(((24,1),(25,1),(30,1),(60,1),
                          (24000,1001),(30000,1001)))


def _file_sha256(path):
    digest=sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()


def _png_header(data):
    """Reject corrupt, truncated or polyglot image bytes before publication.

    A PNG magic number and forged IHDR alone do not prove valid output.
    Validate chunk CRCs and decoded bounded pixels; a creator-approved
    2D derivative must never contain unreadable picture files.
    """
    if type(data) is not bytes or not 32<=len(data)<=MAX_PNG_BYTES:
        raise RuntimeError("Native raster renderer returned invalid PNG length")
    if data[:8]!=b"\x89PNG\r\n\x1a\n" or data[12:16]!=b"IHDR":
        raise RuntimeError("Native raster renderer did not return PNG")
    width,height=struct.unpack(">II",data[16:24])
    if not 1<=width<=4096 or not 1<=height<=2160 or width*height>MAX_PIXELS:
        raise RuntimeError("Unbounded or non-production PNG raster dimensions")
    # IEND is fixed by the PNG specification. Trailing data (which many
    # image readers ignore) is not part of an approved PNG image.
    if data[-12:]!=bytes.fromhex("0000000049454e44ae426082"):
        raise RuntimeError("Truncated or trailing native PNG output")
    try:
        with Image.open(BytesIO(data)) as image:
            if (image.format!="PNG" or image.mode not in ("RGB","RGBA")
                    or image.size!=(width,height)):
                raise RuntimeError("Unsupported native PNG pixel format")
            image.verify()  # Validate PNG chunk framing and CRCs.
        with Image.open(BytesIO(data)) as image:
            image.load()  # Confirm the bounded pixels actually decompress.
    except (OSError,ValueError,SyntaxError) as exc:
        raise RuntimeError("Corrupted native PNG raster data") from exc
    return width,height

def _publish_no_replace(staged,target):
    """Atomically publish a completed film package without clobbering one.

    The earlier exists()/is_symlink() check is helpful for quick error
    reporting but is NOT enough: two independent exporters can pass it
    concurrently. Both supported native operating systems must enforce
    no-replace at the actual directory rename, not with a Python mutex.
    """
    if os.name=="nt":
        # Windows MoveFileEx without REPLACE_EXISTING, as used by os.rename,
        # refuses an existing destination (even an empty directory).
        os.rename(staged,target)
    elif sys.platform.startswith("linux"):
        # renameat2 RENAME_NOREPLACE=1 is an atomic filesystem operation;
        # os.replace would overwrite an empty existing destination directory.
        import ctypes
        try:
            fn=ctypes.CDLL(None,use_errno=True).renameat2
        except AttributeError as exc:
            raise RuntimeError("Atomic no-clobber output publication unavailable") from exc
        fn.argtypes=(ctypes.c_int,ctypes.c_char_p,
                     ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
        fn.restype=ctypes.c_int
        if fn(-100,os.fsencode(staged),-100,os.fsencode(target),1)!=0:
            err=ctypes.get_errno()
            raise OSError(err,os.strerror(err),os.fspath(target))
    else:
        raise RuntimeError("No verified atomic no-replace output on this OS")


class Approved2DPackage:
    def __init__(self,index:FilmIndex,*,native_creator_approval,render_png):
        if (not isinstance(index,FilmIndex) or
            not callable(native_creator_approval) or
            not callable(render_png)):
            raise TypeError("Trusted FilmIndex, creator approval, native raster renderer required")
        self.index=index
        self.approve=native_creator_approval
        self.render=render_png

    def export(self,project_id,take_id,expected_take_sha256,
               presentation_id,output_parent,*,listener_path,
               fps_num=24,fps_den=1,color_grade=None,
               aces_color_grade=None,linear_exr_grade=None):
        _require_pid(project_id)
        _id(take_id,"original Digital Take")
        _id(presentation_id,"unique final presentation identity")
        _sha(expected_take_sha256)
        if type(listener_path) is not str or not listener_path.startswith("/World/"):
            raise ValueError("Creator must select a virtual 3D listener for export")
        if (type(fps_num) is not int or type(fps_den) is not int or
            (fps_num,fps_den) not in OUTPUT_CADENCES):
            raise ValueError("Unsupported native output sampling cadence")
        original=self.index.read_revision(project_id,take_id,1)
        if original["document_sha256"]!=expected_take_sha256:
            raise RuntimeError("Final 2D package source Take SHA changed")
        data=original["data"]
        if (original["kind"]!="take" or data.get("frozen") is not True or
            data.get("format")!="nvp.digital_take.openusd_temporal.v1"):
            raise RuntimeError("Cannot flatten an old frame-proxy or unfrozen source")
        if sum(mode is not None for mode in (
                color_grade,aces_color_grade,linear_exr_grade))>1:
            raise ValueError("Cannot mix display SDR, ACES2 and ACEScg EXR grades")
        aces=None
        exr=None
        if linear_exr_grade is not None:
            if type(linear_exr_grade) is not dict or set(linear_exr_grade)!={
                    "grade_id","revision","document_sha256","config_sha256"}:
                raise ValueError("Native linear EXR requires exact saved grade/config")
            from backend.nvp_native_color_decisions import NativeColorDecisions
            from backend.nvp_native_aces_color import policy
            info,_=policy()
            _sha(linear_exr_grade["config_sha256"])
            if info["configuration_sha256"]!=linear_exr_grade["config_sha256"]:
                raise RuntimeError("Native ACEScg source interchange config changed")
            _id(linear_exr_grade["grade_id"],"frozen source grade")
            _sha(linear_exr_grade["document_sha256"])
            previous=NativeColorDecisions(self.index).read(
                project_id,linear_exr_grade["grade_id"],
                linear_exr_grade["revision"])
            if (previous["document_sha256"]!=
                    linear_exr_grade["document_sha256"] or
                previous["take_id"]!=take_id or
                previous["take_sha256"]!=expected_take_sha256):
                raise RuntimeError("EXR source grade does not match original Take")
            exr={
                "grade_id":previous["grade_id"],
                "revision":previous["revision"],
                "document_sha256":previous["document_sha256"],
                "config_sha256":info["configuration_sha256"],
                "working_space":"ACEScg",
                "output_encoding":"RGB32_FLOAT_OPENEXR",
                "professional_calibration_accepted":False,
                "master_approved":False,
            }
        if aces_color_grade is not None:
            if type(aces_color_grade) is not dict or set(aces_color_grade)!={
                    "grade_id","revision","document_sha256","config_sha256"}:
                raise ValueError("ACES source output needs exact grade/config pins")
            from backend.nvp_native_color_decisions import NativeColorDecisions
            from backend.nvp_native_aces_color import policy
            info,_=policy()
            _sha(aces_color_grade["config_sha256"])
            if info["configuration_sha256"]!=aces_color_grade["config_sha256"]:
                raise RuntimeError("Pinned native ACES2 config changed")
            _id(aces_color_grade["grade_id"],"original source grade")
            _sha(aces_color_grade["document_sha256"])
            plan=NativeColorDecisions(self.index).read(
                project_id,aces_color_grade["grade_id"],
                aces_color_grade["revision"])
            if (plan["document_sha256"]!=aces_color_grade["document_sha256"] or
                plan["take_id"]!=take_id or
                plan["take_sha256"]!=expected_take_sha256):
                raise RuntimeError("Original ACES grade source Take is not verified")
            aces={
                "grade_id":plan["grade_id"],
                "revision":plan["revision"],
                "document_sha256":plan["document_sha256"],
                "config_sha256":info["configuration_sha256"],
                "configuration":info["configuration"],
                "display":info["output_display"],
                "view":info["output_view"],
                "output_encoding":"RGB16_PNG_SDR",
                "professional_calibration_accepted":False,
                "master_approved":False,
            }
        grade=None
        if color_grade is not None:
            if (type(color_grade) is not dict or
                    set(color_grade)!={"grade_id","revision","document_sha256"}):
                raise ValueError("Only exact immutable color revision pins accepted")
            from backend.nvp_native_color_decisions import NativeColorDecisions
            from backend.nvp_film_index import _id as _color_id
            _color_id(color_grade["grade_id"],"native color decision")
            _sha(color_grade["document_sha256"])
            plan=NativeColorDecisions(self.index).read(
                project_id,color_grade["grade_id"],color_grade["revision"])
            if (plan["document_sha256"]!=color_grade["document_sha256"] or
                    plan["take_id"]!=take_id or
                    plan["take_sha256"]!=expected_take_sha256):
                raise RuntimeError("Derived grade not bound to immutable original Take")
            grade={"grade_id":plan["grade_id"],
                   "revision":plan["revision"],
                   "document_sha256":plan["document_sha256"],
                   "parameters":plan["parameters"],
                   "processing_profile":"display_referred_preview_only"}
        duration=data["duration_tick"]
        count=frame_at_tick(duration,fps_num,fps_den,rounding="ceil")
        if count<=0 or count>MAX_FRAMES:
            raise ValueError("Selected final presentation exceeds bounded output chunk")
        samples=duration//SAMPLE_TICKS
        # This is an explicitly approved DERIVATIVE, never a new authoritative Take.
        scope={"project_id":project_id,"take_id":take_id,
               "take_document_sha256":expected_take_sha256,
               "presentation_id":presentation_id,
               "fps_num":fps_num,"fps_den":fps_den,
               "frame_count":count,"audio_samples":samples,
               "original_data_immutable":True,"no_ffmpeg":True,
               "listener_path":listener_path,
               "scene_document_sha256":data["scene_document_sha256"],
               "timeline_document_sha256":data["timeline_document_sha256"],
               "output_kind":(
                    "acescg_openexr_pcm_wav_not_single_file_master" if exr
                    else "png_sequence_pcm_wav_not_single_file_master"),
               "color_pipeline":(
                    "ocio_scene_linear_acescg_exr32_unmastered" if exr
                    else "ocio_aces2_scene_linear_png16_unmastered" if aces
                    else "display_linearized_srgb_png8_review"),
               "color_grade_sha256":(
                    exr["document_sha256"] if exr else
                    aces["document_sha256"] if aces else
                    grade["document_sha256"] if grade else None),
               "aces_config_sha256":(
                    exr["config_sha256"] if exr else
                    aces["config_sha256"] if aces else None)}
        if self.approve(dict(scope)) is not True:
            raise PermissionError("Creator did not authorize exact final 2D sample projection")
        if self.index.read_revision(
            project_id,take_id,1)["document_sha256"]!=expected_take_sha256:
            raise RuntimeError("Frozen original changed during final authorization")
        # output_parent is selected by trusted native host; NEVER browser JSON.
        parent=Path(output_parent)
        if parent.is_symlink() or not parent.is_dir():
            raise RuntimeError("Native output parent must be an existing trusted directory")
        parent=parent.resolve()
        target=parent/("NVP2D_"+presentation_id)
        if target.exists() or target.is_symlink():
            raise FileExistsError("Never overwrite a previous 2D film presentation")
        source=FrozenSceneAV(self.index,project_id,take_id,
            expected_take_sha256=expected_take_sha256,
            listener_path=self._listener(project_id,data,listener_path))
        staged=Path(tempfile.mkdtemp(prefix=".nvp-2d-",dir=parent))
        try:
            pictures=staged/"pictures"
            pictures.mkdir()
            receipt=[]
            dimensions=None
            grade_channels_clipped=0
            grade_channels_seen=0
            aces_source_pins=[]
            exr_source_pins=[]
            if exr:
                from backend.nvp_native_scene_linear_exr import NativeSceneLinearEXR
                exr_renderer=NativeSceneLinearEXR(self.index)
            if aces:
                from backend.nvp_native_aces_color import NativeACESColor
                aces_renderer=NativeACESColor(self.index)
            for i in range(count):
                tick=tick_from_frame(i,fps_num,fps_den)
                if tick>=duration:
                    break
                state=source.snapshot(tick)
                # An active scene camera event observes the SAME world.
                active=source.timeline.events_at(
                    project_id,data["timeline_id"],data["timeline_revision"],
                    tick=tick,event_kind="camera",limit=2)
                if len(active)>1:
                    raise RuntimeError("Multiple simultaneous camera views cannot be flattened")
                camera=(active[0]["payload"].get("usd_prim_path")
                        if active else None)
                if camera is not None and source.roles.get(camera)!="camera":
                    raise RuntimeError("Output camera is not native OpenUSD scene camera")
                # Gaps are real Film Time; a trusted renderer emits an actual
                # blank picture for camera=None, never fabricates scene data.
                if exr:
                    from backend.nvp_native_scene_linear_exr import (
                        write_authored_camera_gap_exr)
                    name=f"{i+1:07d}.exr"
                    dest=pictures/name
                    if camera is None:
                        source_receipt=write_authored_camera_gap_exr(
                            dest,
                            take_sha256=expected_take_sha256,
                            grade_sha256=exr["document_sha256"],
                            ocio_config_sha256=exr["config_sha256"],
                            source_snapshot_sha256=state["snapshot_sha256"],
                            film_time_tick=tick)
                    else:
                        source_receipt=exr_renderer.write(
                            project_id,take_id,expected_take_sha256,
                            exr["grade_id"],exr["revision"],
                            exr["document_sha256"],tick=tick,
                            camera_path=camera,
                            expected_config_sha256=exr["config_sha256"],
                            output_file=dest,
                            source_session=source,source_snapshot=state)
                        if (source_receipt["scene_snapshot_sha256"]!=
                                state["snapshot_sha256"] or
                            source_receipt["grade_sha256"]!=
                                exr["document_sha256"]):
                            raise RuntimeError("Authored source EXR provenance changed")
                    width,height=source_receipt["width"],source_receipt["height"]
                    exr_source_pins.append(source_receipt)
                    receipt.append({
                        "sample_index":i,"source_tick":str(tick),
                        "camera_path":camera,"exr_file":name,
                        "sha256":source_receipt["output_exr_sha256"],
                        "pixel_type":"FLOAT32",
                        "working_space":"ACEScg",
                        "original_scene_snapshot_sha256":
                            state["snapshot_sha256"],
                    })
                elif aces:
                    if camera is None:
                        # Actual gap has no source camera. Explicitly
                        # blank rather than fabricate one for a color grade.
                        from backend.nvp_native_aces_color import png16_rgb
                        import numpy as np
                        encoded=png16_rgb(np.zeros((360,640,3),dtype=np.uint16))
                        source_receipt={
                            "scene_snapshot_sha256":state["snapshot_sha256"],
                            "camera_path":None,"black_camera_gap":True,
                            "clipped_channels":0,
                            "color_channel_count":360*640*3,
                        }
                    else:
                        encoded,processed=aces_renderer.process_verified_usd_scene(
                            project_id,take_id,expected_take_sha256,
                            aces["grade_id"],aces["revision"],
                            aces["document_sha256"],
                            tick=tick,camera_path=camera,
                            expected_config_sha256=aces["config_sha256"],
                            source_session=source,source_snapshot=state)
                        original_source=processed["scene_linear_source"]
                        if (original_source["scene_snapshot_sha256"]!=
                                state["snapshot_sha256"] or
                            original_source["scene_document_sha256"]!=
                                state["scene_document_sha256"] or
                            processed["grade_sha256"]!=aces["document_sha256"]):
                            raise RuntimeError("Source ACES output changed before publication")
                        source_receipt={
                            "scene_snapshot_sha256":state["snapshot_sha256"],
                            "camera_path":camera,"black_camera_gap":False,
                            "clipped_channels":processed["clipped_channels"],
                            "color_channel_count":processed["width"]*
                                                   processed["height"]*3,
                            "scene_linear_rgba_sha256":original_source[
                                "scene_linear_rgba_sha256"],
                        }
                    if encoded[24:26]!=bytes((16,2)):
                        raise RuntimeError("Native ACES picture lost RGB16 bit-depth")
                    grade_channels_clipped+=source_receipt["clipped_channels"]
                    grade_channels_seen+=source_receipt["color_channel_count"]
                    aces_source_pins.append(source_receipt)
                else:
                    encoded=self.render(
                        scope=dict(scope),tick=tick,camera_path=camera,
                        source_snapshot=state)
                    _png_header(encoded)
                    if grade:
                        from backend.nvp_native_color_eval import apply_display_grade
                        encoded,audit=apply_display_grade(
                            encoded,grade["parameters"],return_audit=True)
                        grade_channels_clipped+=audit["channels_clipped"]
                        grade_channels_seen+=audit["color_channel_count"]
                if not exr:
                    width,height=_png_header(encoded)
                    name=f"{i+1:07d}.png"
                    with (pictures/name).open("xb") as sink:
                        sink.write(encoded);sink.flush();os.fsync(sink.fileno())
                    receipt.append({"sample_index":i,
                                    "source_tick":str(tick),
                                    "camera_path":camera,
                                    "png_file":name,
                                    "sha256":sha256(encoded).hexdigest(),
                                    **({"original_scene_snapshot_sha256":
                                        state["snapshot_sha256"],
                                        "pixel_bit_depth":16}
                                       if aces else {})})
                if dimensions is None:
                    dimensions=(width,height)
                elif dimensions!=(width,height):
                    raise RuntimeError("Final presentation geometry changed raster dimensions")
            if len(receipt)!=count:
                raise RuntimeError("Native image output cadence incomplete")
            wav_path=staged/"soundtrack.wav"
            with wave.open(str(wav_path),"wb") as track:
                track.setnchannels(2);track.setsampwidth(2)
                track.setframerate(SAMPLE_RATE)
                for first in range(0,samples,MAX_SAMPLES):
                    n=min(MAX_SAMPLES,samples-first)
                    result=source.audio_window(first,n)
                    import base64
                    pcm=base64.b64decode(result["pcm_base64"],validate=True)
                    if len(pcm)!=n*4:
                        raise RuntimeError("Native scene sound device sample count changed")
                    track.writeframesraw(pcm)
            with wave.open(str(wav_path),"rb") as inspected:
                if inspected.getnframes()!=samples:
                    raise RuntimeError("Derived audio film duration does not match original")
            # Producer-owned receipts preserve original source SHA/provenance
            # alongside output digests, even if exported assets are later moved.
            manifest={
                "format":FORMAT_EXR if exr else FORMAT,
                "status":"DERIVED_2D_PACKAGE",
                "presentation_id":presentation_id,
                "original_project_id":project_id,
                "original_take_id":take_id,
                "original_take_sha256":expected_take_sha256,
                "film_duration_tick":str(duration),
                "fps_num":fps_num,"fps_den":fps_den,
                "output_picture_count":len(receipt),
                "picture_dimensions":dimensions,
                "pictures":receipt,
                "color_grade":grade,
                "aces_color_grade":aces,
                "linear_exr_grade":exr,
                "color_pipeline":scope["color_pipeline"],
                "picture_format":"exr" if exr else "png",
                "pixel_bit_depth":32 if exr else 16 if aces else 8,
                "aces_source_receipts":aces_source_pins if aces else None,
                "acescg_source_receipts":exr_source_pins if exr else None,
                "derived_scene_linear_aces_audit":({
                    "processor_config_sha256":aces["config_sha256"],
                    "grade_sha256":aces["document_sha256"],
                    "color_channel_count":grade_channels_seen,
                    "clipped_channel_count":grade_channels_clipped,
                    "clip_fraction":(
                        grade_channels_clipped/grade_channels_seen
                        if grade_channels_seen else 0),
                    "rendered_from_original_usd":True,
                    "original_scene_color_calibrated":False,
                    "cinema_master_approved":False,
                } if aces else None),
                "derived_display_color_audit":({
                    "profile":"linearized_srgb_sdr_review_not_aces",
                    "color_channel_count":grade_channels_seen,
                    "clipped_channel_count":grade_channels_clipped,
                    "clip_fraction":grade_channels_clipped/grade_channels_seen,
                    "professional_color_managed_master":False,
                } if grade else None),
                "audio_file":"soundtrack.wav",
                "audio_sample_rate":SAMPLE_RATE,
                "audio_samples":samples,
                "audio_sha256":_file_sha256(wav_path),
                "original_data_modified":False,
                "source_frames_authoritative":False,
                "ffmpeg_used":False,
                "conventional_single_file_master":False,
            }
            with (staged/"manifest.json").open("x",encoding="utf8") as f:
                json.dump(manifest,f,sort_keys=True,separators=(",",":"))
                f.flush();os.fsync(f.fileno())
            _publish_no_replace(staged,target)
            return {"status":"DERIVED_2D_PACKAGE",
                    "directory":str(target),
                    "manifest_sha256":sha256(
                        (target/"manifest.json").read_bytes()).hexdigest(),
                    "take_sha256":expected_take_sha256,
                    "color_grade_sha256":(
                        exr["document_sha256"] if exr else
                        aces["document_sha256"] if aces else
                        grade["document_sha256"] if grade else None),
                    "color_pipeline":scope["color_pipeline"],
                    "pixel_bit_depth":32 if exr else 16 if aces else 8,
                    "picture_format":"exr" if exr else "png",
                    "ffmpeg_used":False,
                    "single_file_master":False}
        finally:
            source.close()
            if staged.exists():
                shutil.rmtree(staged)

    def _listener(self,project_id,take,selected):
        scene=self.index.read_revision(project_id,take["scene_id"],
                                      take["scene_revision"])
        # A source camera is one explicit output observation reference.
        cameras=sorted(p for p,role in scene["data"]["prim_roles"].items()
                       if role=="camera")
        if selected not in cameras:
            raise ValueError("Final presentation listener must be an authored camera")
        return selected
