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
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import wave

from backend.nvp_data_av_scene import FrozenSceneAV,MAX_SAMPLES
from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_temporal_ledger import (
    TICKS_PER_SECOND,tick_from_frame,frame_at_tick,_int)

FORMAT="nvp.final_2d.image_sequence_pcm.v1"
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
    if type(data) is not bytes or not 32<=len(data)<=MAX_PNG_BYTES:
        raise RuntimeError("Native raster renderer returned invalid PNG length")
    if data[:8]!=b"\x89PNG\r\n\x1a\n" or data[12:16]!=b"IHDR":
        raise RuntimeError("Native raster renderer did not return PNG")
    width,height=struct.unpack(">II",data[16:24])
    if not 1<=width<=4096 or not 1<=height<=2160 or width*height>MAX_PIXELS:
        raise RuntimeError("Unbounded or non-production PNG raster dimensions")
    return width,height


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
               fps_num=24,fps_den=1):
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
               "output_kind":"png_sequence_pcm_wav_not_single_file_master"}
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
                encoded=self.render(
                    scope=dict(scope),tick=tick,camera_path=camera,
                    source_snapshot=state)
                width,height=_png_header(encoded)
                if dimensions is None:
                    dimensions=(width,height)
                elif dimensions!=(width,height):
                    raise RuntimeError("Final presentation geometry changed raster dimensions")
                name=f"{i+1:07d}.png"
                with (pictures/name).open("xb") as sink:
                    sink.write(encoded);sink.flush();os.fsync(sink.fileno())
                receipt.append({"sample_index":i,
                                "source_tick":str(tick),
                                "camera_path":camera,
                                "png_file":name,
                                "sha256":sha256(encoded).hexdigest()})
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
                "format":FORMAT,"status":"DERIVED_2D_PACKAGE",
                "presentation_id":presentation_id,
                "original_project_id":project_id,
                "original_take_id":take_id,
                "original_take_sha256":expected_take_sha256,
                "film_duration_tick":str(duration),
                "fps_num":fps_num,"fps_den":fps_den,
                "output_picture_count":len(receipt),
                "picture_dimensions":dimensions,
                "pictures":receipt,
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
            os.replace(staged,target)
            return {"status":"DERIVED_2D_PACKAGE",
                    "directory":str(target),
                    "manifest_sha256":sha256(
                        (target/"manifest.json").read_bytes()).hexdigest(),
                    "take_sha256":expected_take_sha256,
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
