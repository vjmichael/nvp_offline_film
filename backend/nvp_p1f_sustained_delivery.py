"""P1-F: finite source-accurate picture + sound delivery over long edits.

One original-time segment, at most one second / 24 frames, is rendered per
separately authorized chunk. There is NO unlimited render queue or concurrent
worker privilege. Original OpenUSD Take, shot, audio and P1-D director review
are rechecked before/after staging, and independent filesystem verification
precedes a single final directory rename. Unfinished .nvp-p1f-* stages are
never accepted as rendered film after a restart.

A trusted host supplies the supervised renderer and the output directory.
This module never starts an unsupervised Blender, FFmpeg or device producer.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import wave

from backend.nvp_data_av_scene import FrozenSceneAV,MAX_SAMPLES,TICKS_PER_SAMPLE
from backend.nvp_final_2d_native import _png_header,_file_sha256
from backend.nvp_film_index import _id,_require_pid,_sha
from backend.nvp_p1d_editorial_continuity import NativeEditorialContinuity
from backend.nvp_p1e_actor_spatial_bus import NativeActorSpatialBus
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_temporal_ledger import TICKS_PER_SECOND,_int,tick_from_frame

FORMAT="nvp.p1f.immutable_picture_sound_chunk.v1"
FPS=24
FRAME_TICKS=tick_from_frame(1,FPS,1)
AUDIO_PER_FRAME=48000//FPS
MAX_CHUNK_FRAMES=24
MAX_PNG_BYTES=48*1024*1024


def _canon(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _digest(value):
    return hashlib.sha256(_canon(value)).hexdigest()


class NativeSustainedPictureSound:
    def __init__(self,assembly:SlateSequenceAssembly,
                 continuity:NativeEditorialContinuity, *,
                 native_creator_approval,render_png,
                 cancelled=lambda:False):
        if (not isinstance(assembly,SlateSequenceAssembly) or
            not isinstance(continuity,NativeEditorialContinuity) or
            continuity.index is not assembly.index or
            not callable(native_creator_approval) or
            not callable(render_png) or not callable(cancelled)):
            raise TypeError("Native source editor, approved renderer and host grant required")
        self.assembly=assembly
        self.continuity=continuity
        self.index=assembly.index
        self.approve=native_creator_approval
        self.render_png=render_png
        self.cancelled=cancelled

    def preflight(self,project_id,continuity_id,revision, *,
                  first_frame,frame_count,listener_path,
                  camera_path,actor_mix_id=None,actor_mix_revision=None):
        _require_pid(project_id)
        _id(continuity_id,"director continuity source")
        first=_int(first_frame,"first output frame")
        count=_int(frame_count,"finite picture-sound chunk frames",
                   minimum=1,maximum=MAX_CHUNK_FRAMES)
        if (type(listener_path) is not str or
            not listener_path.startswith("/World/") or
            len(listener_path)>240 or type(camera_path) is not str or
            not camera_path.startswith("/World/") or len(camera_path)>240):
            raise ValueError("Native output requires exact authored listener and camera")
        if (actor_mix_id is None)!=(actor_mix_revision is None):
            raise ValueError("Actor-owned audio requires exact mix ID and revision")
        review=self.continuity.open(project_id,continuity_id,revision)
        doc=review["data"]
        if doc["review_status"]!="READY_FOR_SEPARATE_EXPORT_AUTHORIZATION":
            raise PermissionError("Director has not accepted every cut and original audio policy")
        duration=doc["duration_tick"]
        if duration%FRAME_TICKS or first+count>duration//FRAME_TICKS:
            raise ValueError("Original edit cannot be silently retimed to 24 fps")
        source=self.continuity.at(project_id,continuity_id,revision,
                                  first*FRAME_TICKS)
        final=self.continuity.at(project_id,continuity_id,revision,
                                (first+count)*FRAME_TICKS-1)
        if (source["director_cue"]!=final["director_cue"] or
            source["source_take_sha256"]!=final["source_take_sha256"] or
            source["source_shot_sha256"]!=final["source_shot_sha256"] or
            final["source_tick"]-source["source_tick"]!=count*FRAME_TICKS-1):
            raise ValueError("Finite chunk crosses a cut; split at the actual edit boundary")
        take=self.index.read_revision(project_id,source["source_take_id"],1)
        if take["document_sha256"]!=source["source_take_sha256"]:
            raise RuntimeError("Selected original Digital Take SHA changed")
        av=FrozenSceneAV(self.index,project_id,source["source_take_id"],
            expected_take_sha256=take["document_sha256"],listener_path=listener_path)
        try:
            if av.roles.get(camera_path)!="camera":
                raise ValueError("Picture camera is not one authored USD camera")
            if (source["source_tick"]%TICKS_PER_SAMPLE or
                (source["source_tick"]+count*FRAME_TICKS)>av.duration):
                raise ValueError("Original audio and picture frame boundaries do not agree")
        finally:
            av.close()
        mix_sha=None
        if actor_mix_id is not None:
            _id(actor_mix_id,"original ActorID mix")
            mix=NativeActorSpatialBus(
                self.index,verify_director_action=lambda *_:False).open(
                project_id,actor_mix_id,actor_mix_revision)
            if (mix["data"]["take_document_sha256"]!=take["document_sha256"] or
                mix["data"]["listener_path"]!=listener_path):
                raise RuntimeError("Selected ActorID bus does not belong to original Take/listener")
            mix_sha=mix["document_sha256"]
        return {
            "format":FORMAT,"project_id":project_id,
            "continuity_id":continuity_id,"continuity_revision":revision,
            "continuity_document_sha256":review["document_sha256"],
            "edit_id":doc["edit_id"],"edit_revision":doc["edit_revision"],
            "edit_document_sha256":doc["edit_document_sha256"],
            "source_take_id":source["source_take_id"],
            "source_take_sha256":source["source_take_sha256"],
            "source_shot_id":source["source_shot_id"],
            "source_shot_revision":source["source_shot_revision"],
            "source_shot_sha256":source["source_shot_sha256"],
            "first_frame":first,"frame_count":count,
            "output_start_tick":str(first*FRAME_TICKS),
            "source_start_tick":str(source["source_tick"]),
            "duration_tick":str(count*FRAME_TICKS),
            "listener_path":listener_path,"camera_path":camera_path,
            "actor_mix_id":actor_mix_id,"actor_mix_revision":actor_mix_revision,
            "actor_mix_document_sha256":mix_sha,
            "audio_policy":"actor_only" if mix_sha else "full_original_scene",
            "fps":FPS,"audio_rate":48000,"stereo_pcm16le":True,
            "render_approved":False,"output_frames_generated":False,
            "full_film_master_approved":False,"original_source_mutated":False,
        }

    def _fresh(self,plan):
        current=self.preflight(
            plan["project_id"],plan["continuity_id"],plan["continuity_revision"],
            first_frame=plan["first_frame"],frame_count=plan["frame_count"],
            listener_path=plan["listener_path"],camera_path=plan["camera_path"],
            actor_mix_id=plan["actor_mix_id"],
            actor_mix_revision=plan["actor_mix_revision"])
        if current!=plan:
            raise RuntimeError("Immutable source/chunk changed since native approval")

    def export_chunk(self,project_id,continuity_id,revision,chunk_id,
                     output_parent,*,first_frame,frame_count,
                     listener_path,camera_path,actor_mix_id=None,
                     actor_mix_revision=None):
        _id(chunk_id,"unique original-time export chunk")
        plan=self.preflight(
            project_id,continuity_id,revision,
            first_frame=first_frame,frame_count=frame_count,
            listener_path=listener_path,camera_path=camera_path,
            actor_mix_id=actor_mix_id,actor_mix_revision=actor_mix_revision)
        parent=Path(output_parent)
        if parent.is_symlink() or not parent.is_dir():
            raise RuntimeError("Native host output directory is not an existing plain directory")
        parent=parent.resolve()
        target=parent/("P1F_"+chunk_id)
        if target.exists() or target.is_symlink():
            raise FileExistsError("Chunk identity already published or occupied")
        intent={"operation":"nvp.p1f.authorize_original_finite_chunk.v1",
                "project_id":project_id,"chunk_id":chunk_id,
                "plan_sha256":_digest(plan),
                "output_directory":str(target),
                "frames":plan["frame_count"],
                "full_film_master_approved":False,
                "source_mutation_allowed":False}
        if self.approve(dict(intent)) is not True:
            raise PermissionError("Creator refused exact source-bounded picture/sound chunk")
        self._fresh(plan)
        if self.cancelled():
            raise InterruptedError("Native creator cancelled before picture worker")
        staged=Path(tempfile.mkdtemp(prefix=".nvp-p1f-",dir=parent))
        try:
            pictures=staged/"pictures"
            pictures.mkdir()
            av=FrozenSceneAV(self.index,project_id,plan["source_take_id"],
                expected_take_sha256=plan["source_take_sha256"],
                listener_path=listener_path)
            try:
                entries=[]
                dims=None
                first_tick=int(plan["source_start_tick"])
                for step in range(plan["frame_count"]):
                    if self.cancelled():
                        raise InterruptedError("Native director cancelled picture generation")
                    source_tick=first_tick+step*FRAME_TICKS
                    original=av.snapshot(source_tick)
                    if plan["source_shot_id"] is not None:
                        from backend.nvp_int02_shot_composition import compose_shot_snapshot
                        original=compose_shot_snapshot(
                            self.index,project_id,
                            take_id=plan["source_take_id"],
                            take_sha256=plan["source_take_sha256"],
                            shot_id=plan["source_shot_id"],
                            shot_revision=plan["source_shot_revision"],
                            shot_sha256=plan["source_shot_sha256"],
                            tick=source_tick,source_snapshot=original,
                            listener_path=listener_path)
                    render_scope={**plan,"operation":intent["operation"],
                                  "chunk_id":chunk_id,
                                  "approved_plan_sha256":intent["plan_sha256"],
                                  "source_tick":source_tick}
                    raw=self.render_png(
                        scope=render_scope,tick=source_tick,
                        camera_path=camera_path,source_snapshot=original)
                    if type(raw) is not bytes or not 0<len(raw)<=MAX_PNG_BYTES:
                        raise RuntimeError("Supervised native renderer did not return bounded PNG bytes")
                    size=_png_header(raw)
                    if dims is None:dims=list(size)
                    if size!=tuple(dims):
                        raise RuntimeError("Original source cameras changed output dimensions")
                    name=f"{step+1:06d}.png"
                    with (pictures/name).open("xb") as fd:
                        fd.write(raw);fd.flush();os.fsync(fd.fileno())
                    entries.append({"index":step,
                                    "output_frame":first_frame+step,
                                    "source_tick":str(source_tick),
                                    "filename":name,"sha256":hashlib.sha256(raw).hexdigest()})
                samples=plan["frame_count"]*AUDIO_PER_FRAME
                first_source_sample=first_tick//TICKS_PER_SAMPLE
                with wave.open(str(staged/"soundtrack.wav"),"wb") as wav:
                    wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(48000)
                    actor_bus=None
                    if plan["actor_mix_id"] is not None:
                        actor_bus=NativeActorSpatialBus(
                            self.index,verify_director_action=lambda *_:False)
                    for offset in range(0,samples,MAX_SAMPLES):
                        if self.cancelled():
                            raise InterruptedError("Creator cancelled finite original PCM derivation")
                        count=min(MAX_SAMPLES,samples-offset)
                        if actor_bus is None:
                            piece=av.audio_window(first_source_sample+offset,count)
                            if piece["take_document_sha256"]!=plan["source_take_sha256"]:
                                raise RuntimeError("Source PCM Take changed during export")
                            data=base64.b64decode(piece["pcm_base64"],validate=True)
                            if hashlib.sha256(data).hexdigest()!=piece["audio_sha256"]:
                                raise RuntimeError("Original stereo PCM SHA changed")
                        else:
                            piece=actor_bus.window(
                                project_id,plan["actor_mix_id"],plan["actor_mix_revision"],
                                first_sample=first_source_sample+offset,count=count)
                            if piece["mix_document_sha256"]!=plan["actor_mix_document_sha256"]:
                                raise RuntimeError("Authoritative ActorID mix changed")
                            data=piece["original_pcm_bytes"]
                            if hashlib.sha256(data).hexdigest()!=piece["stereo_sha256"]:
                                raise RuntimeError("Actor-owned source PCM SHA changed")
                        if len(data)!=count*4:
                            raise RuntimeError("Native sound bus emitted incorrect PCM sample count")
                        wav.writeframesraw(data)
            finally:
                av.close()
            manifest={"format":FORMAT,"status":"SOURCE_BOUNDED_PICTURE_PCM_CHUNK",
                      "chunk_id":chunk_id,"plan":plan,"plan_sha256":_digest(plan),
                      "picture_dimensions":dims,"frames":entries,
                      "audio_file":"soundtrack.wav",
                      "audio_sha256":_file_sha256(staged/"soundtrack.wav"),
                      "audio_samples":samples,"source_modified":False,
                      "ffmpeg_used":False,"conventional_master_approved":False,
                      "native_worker_receipts_embedded":False}
            with (staged/"manifest.json").open("x",encoding="utf8") as fd:
                fd.write(_canon(manifest).decode("ascii"))
                fd.flush();os.fsync(fd.fileno())
            self.verify_chunk(project_id,staged,expected_plan=plan)
            if self.cancelled():
                raise InterruptedError("Creator cancelled before native chunk publication")
            self._fresh(plan)
            if target.exists() or target.is_symlink():
                raise FileExistsError("Original chunk output identity became occupied")
            os.replace(staged,target)
            return self.verify_chunk(project_id,target,expected_plan=plan)
        finally:
            if staged.exists():shutil.rmtree(staged)

    def verify_chunk(self,project_id,folder,*,expected_plan=None):
        _require_pid(project_id)
        root=Path(folder)
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError("Untrusted or absent output directory")
        manifest_file=root/"manifest.json"
        if (manifest_file.is_symlink() or not manifest_file.is_file()
                or manifest_file.stat().st_size>2*1024*1024):
            raise RuntimeError("Chunk lacks bounded independent manifest")
        manifest=json.loads(manifest_file.read_bytes())
        if (type(manifest) is not dict or
            manifest.get("format")!=FORMAT or
            manifest.get("status")!="SOURCE_BOUNDED_PICTURE_PCM_CHUNK" or
            manifest.get("source_modified") is not False or
            manifest.get("conventional_master_approved") is not False or
            manifest.get("ffmpeg_used") is not False):
            raise RuntimeError("Not a valid immutable original-sound chunk")
        plan=manifest["plan"]
        if (plan["project_id"]!=project_id or
            manifest["plan_sha256"]!=_digest(plan) or
            (expected_plan is not None and plan!=expected_plan)):
            raise RuntimeError("Published picture/sound chunk plan mismatch")
        self._fresh(plan)
        frames=manifest["frames"]
        if (type(frames) is not list or len(frames)!=plan["frame_count"] or
            type(manifest["picture_dimensions"]) is not list or
            len(manifest["picture_dimensions"])!=2):
            raise RuntimeError("Missing original source frame samples")
        pic_dir=root/"pictures"
        if pic_dir.is_symlink() or not pic_dir.is_dir():
            raise RuntimeError("Rendered picture directory missing or linked")
        for i,pic in enumerate(frames):
            name=f"{i+1:06d}.png"
            if (pic.get("filename")!=name or pic.get("index")!=i or
                pic.get("output_frame")!=plan["first_frame"]+i or
                pic.get("source_tick")!=str(
                    int(plan["source_start_tick"])+i*FRAME_TICKS)):
                raise RuntimeError("Original film frame clock/identity changed")
            file=pic_dir/name
            if file.is_symlink() or not file.is_file():
                raise RuntimeError("Original output picture missing or linked")
            payload=file.read_bytes()
            if (len(payload)>MAX_PNG_BYTES or
                hashlib.sha256(payload).hexdigest()!=pic["sha256"] or
                list(_png_header(payload))!=manifest["picture_dimensions"]):
                raise RuntimeError("Rendered original picture digest/dimensions changed")
        if len(list(pic_dir.iterdir()))!=len(frames):
            raise RuntimeError("Unexpected files in verified picture set")
        wav_path=root/"soundtrack.wav"
        if wav_path.is_symlink() or not wav_path.is_file() or (
                _file_sha256(wav_path)!=manifest["audio_sha256"]):
            raise RuntimeError("Original source audio derivative changed")
        with wave.open(str(wav_path),"rb") as wav:
            if (wav.getnchannels()!=2 or wav.getsampwidth()!=2 or
                wav.getframerate()!=48000 or
                wav.getnframes()!=plan["frame_count"]*AUDIO_PER_FRAME or
                wav.getnframes()!=manifest["audio_samples"]):
                raise RuntimeError("Stereo original sound has incomplete 48kHz samples")
        if {x.name for x in root.iterdir()}!={"manifest.json","soundtrack.wav","pictures"}:
            raise RuntimeError("Unrecognized files in authoritative finite source package")
        return {"format":FORMAT,"status":"INDEPENDENT_SOURCE_CHUNK_VERIFIED",
                "chunk_id":manifest["chunk_id"],
                "first_frame":plan["first_frame"],
                "frame_count":plan["frame_count"],
                "plan_sha256":manifest["plan_sha256"],
                "manifest_sha256":_file_sha256(manifest_file),
                "audio_sha256":manifest["audio_sha256"],
                "source_edit_sha256":plan["edit_document_sha256"],
                "source_take_sha256":plan["source_take_sha256"],
                "file_path":str(root.resolve()),
                "original_source_modified":False,
                "full_film_master_approved":False}

    @staticmethod
    def abandoned_stages(output_parent):
        """Report crash leftovers; NEVER promote them to an accepted chunk."""
        parent=Path(output_parent)
        if not parent.is_dir() or parent.is_symlink():
            raise RuntimeError("Native output parent not trusted")
        return sorted(x.name for x in parent.iterdir()
                      if x.name.startswith(".nvp-p1f-"))
