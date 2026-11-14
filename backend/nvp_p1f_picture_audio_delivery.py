"""P1-F independent original-picture PNG sequence + original-PCM WAV delivery.

Export requires a FULLY ACCEPTED finite source batch; no PNG or PCM comes
from an unaudited worker. This is not a video codec, muxed film, master,
2D generative upscale or sustained-production acceptance.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import struct
import wave

from backend.nvp_p1f_multishot_reel import P1FDurableShotReels

FORMAT="nvp.p1f.original_picture_pcm_segment.v1"
FRAME_SAMPLES=2000  # 48k stereo at exact 24fps
MAX_FRAME_BYTES=32*1024*1024


def _hash_file(file):
    h=sha256()
    with open(file,"rb") as handle:
        for part in iter(lambda:handle.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()


def _write_json(path,obj):
    raw=json.dumps(obj,sort_keys=True,separators=(",",":"),
                   ensure_ascii=True,allow_nan=False).encode("ascii")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return sha256(raw).hexdigest()


class P1FVerifiedSegmentDelivery:
    def __init__(self,journal:P1FDurableShotReels):
        if not isinstance(journal,P1FDurableShotReels):
            raise TypeError("Trusted durable original-frame journal required")
        self.journal=journal

    def deliver(self,batch_id):
        """Atomically publish a source-hashed 24fps picture sequence and WAV.

        The files are derived duplicates; FilmIndex originals and full-film
        master state are unchanged. A fresh review verifies each worker again.
        The caller cannot specify a path or replace previously published work.
        """
        verified=self.journal.verify(batch_id)
        if not verified["all_frames_verified"]:
            raise RuntimeError("No partly rendered source batch can be delivered")
        doc,state=self.journal._manifest(batch_id)
        if state!="FRAMES_VERIFIED":
            raise RuntimeError("Only the exact complete immutable batch is deliverable")
        frames=doc["source_frames"]
        if not frames or len(frames)>240:
            raise RuntimeError("Non-finite segment source frame count")
        root=self.journal.renderer.supervisor.root
        export_root=root/"p1f_verified_segments"
        if export_root.is_symlink():
            raise RuntimeError("Segment delivery root cannot be a link")
        export_root.mkdir(mode=0o700,exist_ok=True)
        # Batch ID is already checked by _manifest, and never supplied as a
        # relative/absolute filesystem path.
        destination=export_root/batch_id
        scratch=export_root/(batch_id+".partial")
        if (destination.exists() or destination.is_symlink() or
                scratch.exists() or scratch.is_symlink()):
            raise RuntimeError("Previously exported/recovered segment cannot be overwritten")
        scratch.mkdir(mode=0o700,exist_ok=False)
        images=[]
        sound_digest=sha256()
        dimensions=None
        global_previous=None
        try:
            sound_path=scratch/"original_actor_audio.wav"
            with wave.open(str(sound_path),"wb") as output_sound:
                output_sound.setnchannels(2)
                output_sound.setsampwidth(2)
                output_sound.setframerate(48000)
                for offset,item in enumerate(frames):
                    if (type(item["global_frame"]) is not int or
                            global_previous is not None and
                            item["global_frame"]!=global_previous+1):
                        raise RuntimeError("Original output film timeline is discontinuous")
                    global_previous=item["global_frame"]
                    receipt=self.journal.renderer.verify_delivered(
                        doc["project_id"],doc["plan_id"],item["job_id"])
                    if (receipt.get("format")!=
                            "nvp.p1f.independent_picture_audio_receipt.v1" or
                            receipt.get("passed") is not True or
                            receipt.get("plan_document_sha256")!=
                                doc["plan_document_sha256"] or
                            receipt.get("job_id")!=item["job_id"] or
                            receipt.get("entire_film_rendered") is not False):
                        raise RuntimeError("Native worker receipt does not match original segment")
                    source=self.journal.reels.picture_instant(
                        doc["project_id"],doc["plan_id"],
                        item["reel_index"],item["frame_offset"])
                    if (source["source_tick"]!=item["source_tick"] or
                            source["output_tick"]!=item["output_tick"] or
                            source["source_camera"]!=item["camera_path"] or
                            source["source_take_sha256"]!=item["take_sha256"] or
                            source["output_frame"]!=item["global_frame"]):
                        raise RuntimeError("Frozen Take or camera changed during picture assembly")
                    jobdir=root/item["job_id"]
                    pic=jobdir/"original_frame.png"
                    snd=jobdir/"original_pcm.wav"
                    if (pic.is_symlink() or snd.is_symlink() or
                            not pic.is_file() or not snd.is_file() or
                            not 256<=pic.stat().st_size<=MAX_FRAME_BYTES):
                        raise RuntimeError("Original picture/sound bytes missing or escaped")
                    if _hash_file(pic)!=receipt["original_picture"]["png_sha256"]:
                        raise RuntimeError("Original source picture SHA differs from worker audit")
                    width=receipt["original_picture"]["width"]
                    height=receipt["original_picture"]["height"]
                    if dimensions is None:
                        dimensions=[width,height]
                    elif dimensions!=[width,height]:
                        raise RuntimeError("Incompatible frame size in exact source segment")
                    with wave.open(str(snd),"rb") as frame_wav:
                        if (frame_wav.getnchannels()!=2 or
                                frame_wav.getframerate()!=48000 or
                                frame_wav.getsampwidth()!=2 or
                                frame_wav.getnframes()!=FRAME_SAMPLES):
                            raise RuntimeError("Original actor PCM WAV is not one exact film frame")
                        pcm=frame_wav.readframes(FRAME_SAMPLES)
                    if (len(pcm)!=FRAME_SAMPLES*4 or
                            sha256(pcm).hexdigest()!=
                                receipt["original_derived_audio"]["pcm_sha256"]):
                        raise RuntimeError("Authoritative actor audio changed before segment assembly")
                    output_sound.writeframesraw(pcm)
                    sound_digest.update(pcm)
                    target=scratch/("frame_%06d.png"%offset)
                    with pic.open("rb") as inp,target.open("xb") as out:
                        shutil.copyfileobj(inp,out,1024*1024)
                        out.flush()
                        os.fsync(out.fileno())
                    if _hash_file(target)!=receipt["original_picture"]["png_sha256"]:
                        raise RuntimeError("Picture changed on independently copied segment")
                    images.append({
                        "frame_index":offset,
                        "global_frame":item["global_frame"],
                        "original_take_sha256":item["take_sha256"],
                        "source_tick":item["source_tick"],
                        "output_tick":item["output_tick"],
                        "camera_path":item["camera_path"],
                        "picture_file":target.name,
                        "picture_sha256":_hash_file(target),
                        "actor_pcm_sha256":sha256(pcm).hexdigest(),
                    })
            with sound_path.open("rb") as handle:
                os.fsync(handle.fileno())
            with wave.open(str(sound_path),"rb") as joined:
                if (joined.getnframes()!=len(frames)*FRAME_SAMPLES or
                        joined.getframerate()!=48000 or
                        joined.getnchannels()!=2 or
                        joined.getsampwidth()!=2):
                    raise RuntimeError("Joined original sound timing changed")
                actual=sha256()
                while True:
                    chunk=joined.readframes(8192)
                    if not chunk:
                        break
                    actual.update(chunk)
                if actual.hexdigest()!=sound_digest.hexdigest():
                    raise RuntimeError("Joined original PCM differs from exact source frames")
            segment={
                "format":FORMAT,"batch_id":batch_id,
                "project_id":doc["project_id"],
                "plan_id":doc["plan_id"],
                "plan_document_sha256":doc["plan_document_sha256"],
                "batch_manifest_sha256":sha256(json.dumps(
                    doc,sort_keys=True,separators=(",",":"),
                    allow_nan=False,ensure_ascii=True).encode("ascii")).hexdigest(),
                "frame_rate":24,"audio_sample_rate":48000,
                "audio_channels":2,"audio_sample_width_bytes":2,
                "frame_count":len(images),
                "audio_sample_count_per_channel":len(images)*FRAME_SAMPLES,
                "picture_dimensions":dimensions,
                "audio_file":sound_path.name,
                "audio_sha256":_hash_file(sound_path),
                "pcm_sha256":actual.hexdigest(),
                "frames":images,
                "picture_audio_originals_modified":False,
                "muxed_movie_created":False,
                "whole_film_delivered":False,
                "final_master_approved":False,
            }
            _write_json(scratch/"delivery_manifest.json",segment)
            scratch.rename(destination)
            return {**segment,"status":"SOURCE_SEGMENT_DELIVERED",
                    "delivery_path":str(destination)}
        except BaseException:
            # Only this derivative staging path is owned by the exporter;
            # never delete the FilmIndex source, original Jobs or prior work.
            shutil.rmtree(scratch,ignore_errors=True)
            raise

    def verify_delivered(self,batch_id):
        """Cold-reopen all picture/audio bytes without running a new worker."""
        verified=self.journal.verify(batch_id)
        if not verified["all_frames_verified"]:
            raise RuntimeError("Native source batch no longer verified")
        root=self.journal.renderer.supervisor.root/"p1f_verified_segments"/batch_id
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError("Original delivered segment missing/linked")
        manifest=root/"delivery_manifest.json"
        if not manifest.is_file() or manifest.is_symlink():
            raise RuntimeError("Delivery manifest missing/linked")
        doc=json.loads(manifest.read_text("ascii"))
        if (doc.get("format")!=FORMAT or doc.get("batch_id")!=batch_id or
                doc.get("frame_count")!=verified["frame_count"] or
                doc.get("muxed_movie_created") is not False or
                doc.get("whole_film_delivered") is not False or
                doc.get("final_master_approved") is not False):
            raise RuntimeError("Verified segment identity/status changed")
        if len(doc["frames"])!=verified["frame_count"]:
            raise RuntimeError("Original picture sequence altered after delivery")
        if any(p.is_symlink() for p in root.iterdir()):
            raise RuntimeError("Derivative segment contains symlink")
        for index,frame in enumerate(doc["frames"]):
            expected="frame_%06d.png"%index
            if (frame["frame_index"]!=index or frame["picture_file"]!=expected or
                    _hash_file(root/expected)!=frame["picture_sha256"]):
                raise RuntimeError("Delivered original picture sequence changed")
        audio=root/"original_actor_audio.wav"
        if _hash_file(audio)!=doc["audio_sha256"]:
            raise RuntimeError("Delivered original WAV changed")
        with wave.open(str(audio),"rb") as f:
            if (f.getnframes()!=doc["frame_count"]*FRAME_SAMPLES or
                    f.getframerate()!=48000 or f.getnchannels()!=2 or
                    f.getsampwidth()!=2):
                raise RuntimeError("Delivered audio film clock changed")
            digest=sha256()
            for i in range(doc["frame_count"]):
                pcm=f.readframes(FRAME_SAMPLES)
                if sha256(pcm).hexdigest()!=doc["frames"][i]["actor_pcm_sha256"]:
                    raise RuntimeError("Original actor PCM frame was reordered or tampered")
                digest.update(pcm)
            if digest.hexdigest()!=doc["pcm_sha256"]:
                raise RuntimeError("Concatenated PCM manifest differs from film-time samples")
        return {**doc,"status":"SOURCE_SEGMENT_REVERIFIED"}
