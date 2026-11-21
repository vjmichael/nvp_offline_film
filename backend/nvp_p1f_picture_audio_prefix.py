"""P1-F independent, bounded-memory picture/audio source-prefix assembly.

Consumes ONLY complete, independently reverified 24-fps PNG+48k PCM segments
from the original durable journal. Each frame is rehashed after derivative
copy; the stereo WAV is written sequentially, frame-by-frame, with exact
2000 samples per picture. A partial prefix can be reviewed without pretending
to be a finished film, muxing a codec, changing original Takes or granting
production worker access. Failures retain a .partial marker and never resume
or overwrite after restart. No FFmpeg, downloaded code, model-selected path.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import wave

from backend.nvp_film_index import _require_pid,_id
from backend.nvp_p1f_picture_audio_delivery import (
    P1FVerifiedSegmentDelivery,FRAME_SAMPLES,_hash_file)
from backend.nvp_p1f_p2_verified_coverage import P1FVerifiedFilmCoverage
from backend.nvp_p1f_multishot_reel import P1FDurableShotReels

FORMAT="nvp.p1f.source_sequence_png_pcm_prefix.v1"
MAX_SOURCE_FRAMES=259200


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False)


def _digest(value):
    return sha256(_json(value).encode("ascii")).hexdigest()


def _write(path,value):
    raw=_json(value).encode("ascii")
    with Path(path).open("xb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    return sha256(raw).hexdigest()


class P1FVerifiedPictureAudioPrefix:
    def __init__(self,journal:P1FDurableShotReels):
        if not isinstance(journal,P1FDurableShotReels):
            raise TypeError("Only original source-bound durable Blender journal accepted")
        self.journal=journal
        self.delivery=P1FVerifiedSegmentDelivery(journal)
        self.coverage=P1FVerifiedFilmCoverage(self.delivery)
        self.root=journal.renderer.supervisor.root/"p1f_picture_audio_prefixes"

    def review(self,pid,plan_id):
        _require_pid(pid);_id(plan_id,"original source film plan")
        coverage=self.coverage.verify_coverage(pid,plan_id)
        if coverage["gap_or_overlap"]:
            raise RuntimeError("Original picture/audio source coverage has a gap or overlap")
        frames=coverage["verified_frames"]
        if type(frames) is not int or not 1<=frames<=MAX_SOURCE_FRAMES:
            raise RuntimeError("No independently verified nonempty original film prefix")
        # A fixed count alone cannot authorize substitution of a different
        # source segment under the same output-frame interval. Bind each
        # original independently reopened source manifest SHA in order.
        with self.coverage._connect() as db:
            rows=db.execute("""SELECT batch_id,first_frame,frame_count,
                       source_manifest_sha256 FROM verified_segments
                       WHERE project_id=? AND plan_id=?
                       ORDER BY first_frame,batch_id""",(pid,plan_id)).fetchall()
        manifest_chain=_digest([
            {"batch_id":bid,"first_frame":first,"frame_count":count,
             "source_manifest_sha256":digest}
            for bid,first,count,digest in rows])
        doc={
            "format":FORMAT,
            "status":"REVIEW_ONLY_NOT_EXPORTED",
            "project_id":pid,
            "plan_id":plan_id,
            "plan_document_sha256":coverage["plan_document_sha256"],
            "source_frames":frames,
            "source_segment_manifest_chain_sha256":manifest_chain,
            "original_audio_samples_per_channel":frames*FRAME_SAMPLES,
            "complete_source_film":coverage["all_source_frames_verified"],
            "ready_to_publish_master":False,
            "film_master_created":False,
        }
        return {**doc,"review_sha256":_digest(doc)}

    def assemble(self,pid,plan_id,sequence_id,*,expected_review_sha256,
                 approve_export,creator_event):
        _require_pid(pid);_id(plan_id,"original source plan")
        _id(sequence_id,"one-use independent picture/audio prefix")
        if not callable(approve_export):
            raise TypeError("Only independent creator approval permits derived prefix")
        review=self.review(pid,plan_id)
        if (type(expected_review_sha256) is not str or
                expected_review_sha256!=review["review_sha256"]):
            raise RuntimeError("Source coverage changed after reviewed picture/audio scope")
        approval={
            "operation":"nvp.p1f.export_verified_picture_audio_prefix.v1",
            "project_id":pid,"plan_id":plan_id,
            "plan_document_sha256":review["plan_document_sha256"],
            "verified_frame_count":review["source_frames"],
            "review_sha256":expected_review_sha256,
            "sequence_id":sequence_id,
        }
        if approve_export(creator_event,dict(approval)) is not True:
            raise PermissionError("Creator refused independently reviewed picture/audio prefix")
        # Only safe stable IDs are used, never caller-provided output paths.
        root=self.root
        if root.is_symlink():
            raise RuntimeError("Independent source prefix root may not be a symlink")
        root.mkdir(mode=0o700,parents=False,exist_ok=True)
        prefix=root/sequence_id
        scratch=root/(sequence_id+".partial")
        if (prefix.exists() or prefix.is_symlink() or
                scratch.exists() or scratch.is_symlink()):
            raise RuntimeError("A previously approved prefix cannot be replayed/overwritten")
        scratch.mkdir(mode=0o700,exist_ok=False)
        complete=review["source_frames"]
        copied=0
        picture_chain=sha256()
        pcm_chain=sha256()
        try:
            source_segments=self.coverage._connect()
            # Snapshot only the immutable original registered source order;
            # verify_coverage already independently reread each entire segment.
            with source_segments as db:
                entries=db.execute("""SELECT batch_id,first_frame,frame_count
                    FROM verified_segments WHERE project_id=? AND plan_id=?
                    ORDER BY first_frame,batch_id""",(pid,plan_id)).fetchall()
            frame_index=scratch/"frame_sources.jsonl"
            audio=scratch/"original_actor_audio.wav"
            with frame_index.open("xb") as manifest, wave.open(str(audio),"wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                for batch_id,first,count in entries:
                    if copied>=complete:
                        break
                    if first!=copied or first+count>complete:
                        raise RuntimeError("Frozen source segment frame clocks are discontinuous")
                    segment=self.delivery.verify_delivered(batch_id)
                    if (segment["project_id"]!=pid or
                            segment["plan_id"]!=plan_id or
                            segment["plan_document_sha256"]!=
                                review["plan_document_sha256"] or
                            segment["frame_count"]!=count):
                        raise RuntimeError("Segment source moved during prefix assembly")
                    segment_root=self.journal.renderer.supervisor.root/(
                        "p1f_verified_segments")/batch_id
                    with wave.open(str(segment_root/"original_actor_audio.wav"),"rb") as src_audio:
                        if (src_audio.getframerate()!=48000 or
                                src_audio.getnchannels()!=2 or
                                src_audio.getsampwidth()!=2 or
                                src_audio.getnframes()!=count*FRAME_SAMPLES):
                            raise RuntimeError("Original segment PCM sample clock changed")
                        for frame in segment["frames"]:
                            from backend.nvp_temporal_ledger import TICKS_PER_SECOND
                            if (frame["global_frame"]!=copied or
                                    frame["output_tick"]!=copied*(TICKS_PER_SECOND//24)):
                                raise RuntimeError("Original picture frame or Film Time order changed")
                            origin=segment_root/frame["picture_file"]
                            if origin.is_symlink() or not origin.is_file():
                                raise RuntimeError("Original source PNG missing or linked")
                            if _hash_file(origin)!=frame["picture_sha256"]:
                                raise RuntimeError("Original PNG changed since independent source review")
                            dest=scratch/("frame_%06d.png"%copied)
                            with origin.open("rb") as inp,dest.open("xb") as out:
                                shutil.copyfileobj(inp,out,1024*1024)
                                out.flush()
                                os.fsync(out.fileno())
                            copied_sha=_hash_file(dest)
                            if copied_sha!=frame["picture_sha256"]:
                                raise RuntimeError("Copied original PNG differs from source")
                            picture_chain.update(bytes.fromhex(copied_sha))
                            pcm=src_audio.readframes(FRAME_SAMPLES)
                            if (len(pcm)!=FRAME_SAMPLES*4 or
                                    sha256(pcm).hexdigest()!=frame["actor_pcm_sha256"]):
                                raise RuntimeError("Original independently verified actor PCM changed")
                            wav.writeframesraw(pcm)
                            pcm_chain.update(pcm)
                            line={
                                "global_frame":copied,
                                "source_batch_id":batch_id,
                                "original_take_sha256":frame["original_take_sha256"],
                                "source_tick":frame["source_tick"],
                                "output_tick":frame["output_tick"],
                                "camera_path":frame["camera_path"],
                                "picture_file":dest.name,
                                "picture_sha256":copied_sha,
                                "actor_pcm_sha256":frame["actor_pcm_sha256"],
                            }
                            manifest.write((_json(line)+"\n").encode("ascii"))
                            copied+=1
                manifest.flush()
                os.fsync(manifest.fileno())
            with audio.open("r+b") as fd:
                fd.flush()
                os.fsync(fd.fileno())
            if copied!=complete:
                raise RuntimeError("Not all independently verified original frames assembled")
            with wave.open(str(audio),"rb") as joined:
                if (joined.getnframes()!=complete*FRAME_SAMPLES or
                        joined.getframerate()!=48000 or
                        joined.getnchannels()!=2 or joined.getsampwidth()!=2):
                    raise RuntimeError("Continuous stereo PCM output sample count differs")
                actual=sha256()
                while data:=joined.readframes(8192):
                    actual.update(data)
                if actual.digest()!=pcm_chain.digest():
                    raise RuntimeError("Assembled continuous source PCM does not match original segments")
            if self.review(pid,plan_id)["review_sha256"]!=expected_review_sha256:
                raise RuntimeError("Verified original source coverage changed during assembly")
            summary={
                "format":FORMAT,"status":"VERIFIED_SOURCE_PREFIX_NOT_MASTER",
                "project_id":pid,"plan_id":plan_id,
                "sequence_id":sequence_id,
                "plan_document_sha256":review["plan_document_sha256"],
                "source_segment_manifest_chain_sha256":
                    review["source_segment_manifest_chain_sha256"],
                "source_frames":complete,
                "source_audio_samples_per_channel":complete*FRAME_SAMPLES,
                "picture_sha256_chain":picture_chain.hexdigest(),
                "pcm_sha256":pcm_chain.hexdigest(),
                "wav_sha256":_hash_file(audio),
                "frame_index_sha256":_hash_file(frame_index),
                "complete_source_film":review["complete_source_film"],
                "portable_movie_created":False,
                "final_film_approved":False,
                "master_created":False,
            }
            _write(scratch/"sequence_manifest.json",summary)
            scratch.rename(prefix)
            return {**summary,"sequence_path":str(prefix)}
        except BaseException:
            # Leave '.partial' intact for independent failure/cancellation
            # investigation. Never treat it as a completed source prefix.
            raise

    def verify(self,pid,plan_id,sequence_id):
        _require_pid(pid);_id(plan_id,"original film source plan")
        _id(sequence_id,"original one-use source sequence")
        root=self.root/sequence_id
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError("No verified original source picture/audio prefix")
        manifest=root/"sequence_manifest.json"
        if manifest.is_symlink() or not manifest.is_file():
            raise RuntimeError("No durable picture/audio prefix receipt")
        summary=json.loads(manifest.read_text("ascii"))
        if (summary.get("format")!=FORMAT or
                summary.get("status")!="VERIFIED_SOURCE_PREFIX_NOT_MASTER" or
                summary.get("project_id")!=pid or
                summary.get("plan_id")!=plan_id or
                summary.get("sequence_id")!=sequence_id or
                summary.get("portable_movie_created") is not False or
                summary.get("final_film_approved") is not False or
                summary.get("master_created") is not False):
            raise RuntimeError("Source prefix receipt cannot claim completed film")
        original=self.review(pid,plan_id)
        if (original["plan_document_sha256"]!=summary["plan_document_sha256"] or
                original["source_frames"]!=summary["source_frames"] or
                original["source_segment_manifest_chain_sha256"]!=
                    summary["source_segment_manifest_chain_sha256"]):
            raise RuntimeError("Source prefix coverage changed after assembly")
        index=root/"frame_sources.jsonl"
        if index.is_symlink() or _hash_file(index)!=summary["frame_index_sha256"]:
            raise RuntimeError("Source picture frame index changed")
        picture_chain=sha256()
        with index.open("r",encoding="ascii") as inp:
            for n,line in enumerate(inp):
                frame=json.loads(line)
                target=root/("frame_%06d.png"%n)
                if (frame["global_frame"]!=n or
                        frame["picture_file"]!=target.name or
                        target.is_symlink() or
                        _hash_file(target)!=frame["picture_sha256"]):
                    raise RuntimeError("Source sequence PNG order/integrity changed")
                picture_chain.update(bytes.fromhex(frame["picture_sha256"]))
        if (n+1!=summary["source_frames"] or
                picture_chain.hexdigest()!=summary["picture_sha256_chain"]):
            raise RuntimeError("Source sequence missing/tampered picture frames")
        audio=root/"original_actor_audio.wav"
        if audio.is_symlink() or _hash_file(audio)!=summary["wav_sha256"]:
            raise RuntimeError("Source sequence WAV changed since committed audit")
        with wave.open(str(audio),"rb") as data:
            if (data.getnframes()!=summary["source_audio_samples_per_channel"] or
                    data.getframerate()!=48000 or
                    data.getnchannels()!=2 or data.getsampwidth()!=2):
                raise RuntimeError("Original audio sample clock changed")
            pcm=sha256()
            while block:=data.readframes(8192):
                pcm.update(block)
            if pcm.hexdigest()!=summary["pcm_sha256"]:
                raise RuntimeError("Original sound samples differ after restart")
        return {**summary,"reopened_and_verified":True}
