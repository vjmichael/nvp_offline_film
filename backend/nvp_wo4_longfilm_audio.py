"""Source-approved PCM24 reel-set candidate, not a cinema master or worker grant.

Classic RIFF per reel; total raw source may exceed 4 GiB. Ordered bounded
receipt lines and a compact root bind the exact 24 fps / 48 kHz clock.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import uuid

from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_wo4_pcm_master import CHANNEL_LAYOUTS, MAX_FRAMES, MIN_24, MAX_24, _round_away
from backend.nvp_wo4_pcm_stream import _protected_path, HEX_SHA, MAX_RIFF_PCM_BYTES, FRAMES_PER_BLOCK
from backend.nvp_wo4_resource_budget import require_stage_space
from backend.nvp_wo3_atomic_publish import atomic_publish_directory, _fsync_directory

FORMAT = "nvp.wo4.partitioned_pcm24_candidate.v1"
RATE = 48000
SAMPLES_PER_FRAME = 2000
DEFAULT_REEL_FRAMES = 7200
MAX_TOTAL_FRAMES = (2**53-1)//(TICKS_PER_SECOND//24)
MAX_ROOT_BYTES = 16384
MAX_LINE_BYTES = 4096


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _sha(value):
    if type(value) is not str or not HEX_SHA.fullmatch(value):
        raise PermissionError("Exact original audio or manifest SHA required")
    return value


def _check(cancelled):
    if cancelled():
        raise InterruptedError("Creator cancelled partitioned audio candidate")


class AudioReels:
    """O(1) exact clock layout with balanced, never sub-three-frame reels."""
    def __init__(self, frames, layout, max_reel_frames=DEFAULT_REEL_FRAMES):
        if layout not in CHANNEL_LAYOUTS:
            raise ValueError("Explicit original speaker layout required")
        if (type(frames) is not int or not 3 <= frames <= MAX_TOTAL_FRAMES or
                type(max_reel_frames) is not int or not 3 <= max_reel_frames <= MAX_FRAMES):
            raise ValueError("Exact bounded cinema-frame address required")
        self.frames = frames
        self.layout = layout
        self.labels = CHANNEL_LAYOUTS[layout]
        self.stride = len(self.labels)*3
        self.maximum = min(max_reel_frames, MAX_RIFF_PCM_BYTES//(SAMPLES_PER_FRAME*self.stride))
        self.count = (frames+self.maximum-1)//self.maximum
        self.base, self.extra = divmod(frames, self.count)
        if self.base < 3:
            raise ValueError("Requested reel limit cannot cover whole film with three-frame minimum")
        self.source_bytes = frames*SAMPLES_PER_FRAME*self.stride

    def at(self, index):
        if type(index) is not int or not 0 <= index < self.count:
            raise IndexError("Audio reel outside approved clock")
        first = index*self.base+min(index,self.extra)
        count = self.base+int(index < self.extra)
        return {"reel_index":index,"first_frame":first,"frame_count":count,
                "first_sample":first*SAMPLES_PER_FRAME,"sample_count":count*SAMPLES_PER_FRAME,
                "filename":f"PCM24_{index:06d}.wav"}

    def descriptor(self):
        return {"frame_count":self.frames,"channel_layout":self.layout,
                "channel_order":list(self.labels),"sample_rate":RATE,"sample_width_bytes":3,
                "sample_count":self.frames*SAMPLES_PER_FRAME,"source_bytes":self.source_bytes,
                "max_reel_frames":self.maximum,"reel_count":self.count,
                "container":"partitioned_classic_riff_wave"}


def _header(samples, stride):
    size = samples*stride
    if size > MAX_RIFF_PCM_BYTES:
        raise ValueError("Single reel would exceed classic RIFF size")
    return struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF",36+size,b"WAVE",b"fmt ",16,
                       1,stride//3,RATE,RATE*stride,stride,24,b"data",size)


def _identity(stream, expected):
    info=os.fstat(stream.fileno())
    if (info.st_dev,info.st_ino)!=expected:
        raise PermissionError("Protected audio file changed at open")
    return info


def _hash_source(source, identity, size, cancelled):
    digest=sha256()
    with source.open("rb") as inp:
        if _identity(inp,identity).st_size!=size:
            raise PermissionError("Original PCM duration differs from approved film clock")
        remaining=size
        while remaining:
            _check(cancelled)
            packet=inp.read(min(remaining,1024*1024))
            if not packet:
                raise PermissionError("Original PCM truncated")
            remaining-=len(packet);digest.update(packet)
        if inp.read(1) or _protected_path(source)!=identity:
            raise PermissionError("Original PCM changed during read")
    return digest.hexdigest()


def _write_protected(path, data):
    with path.open("xb") as out:
        _identity(out,_protected_path(path))
        out.write(data);out.flush();os.fsync(out.fileno())


def _read_root(folder, expected_sha):
    root=folder/"manifest.json"
    identity=_protected_path(root)
    with root.open("rb") as inp:
        _identity(inp,identity);raw=inp.read(MAX_ROOT_BYTES+1)
    if len(raw)>MAX_ROOT_BYTES or sha256(raw).hexdigest()!=_sha(expected_sha):
        raise PermissionError("Partitioned PCM root identity differs")
    doc=json.loads(raw)
    if _canon(doc)!=raw or doc.get("format")!=FORMAT:
        raise RuntimeError("Invalid partitioned PCM root")
    layout=AudioReels(doc["frame_count"],doc["channel_layout"],doc["max_reel_frames"])
    if any(doc.get(k)!=v for k,v in layout.descriptor().items()):
        raise RuntimeError("Partitioned PCM root has inconsistent exact clock")
    if any(doc.get(k) is not False for k in ("source_modified","production_audio_accepted","ffmpeg_used")):
        raise RuntimeError("Audio candidate cannot authorize a master")
    for key in ("source_pcm_sha256","original_take_sha256","master_pcm_sha256","reels_sha256"):
        _sha(doc[key])
    return doc,layout


def _packets(folder, expected_sha, cancelled, on_reel=None):
    """Yield only bounded verified-layout packets; exhaust to validate full receipt.

    Consumers must not publish/accept anything until successful exhaustion.
    """
    folder=Path(folder)
    folder_id=_protected_path(folder,directory=True)
    doc,layout=_read_root(folder,expected_sha)
    manifest=folder/"reels.jsonl";mid=_protected_path(manifest)
    rows_hash=sha256();master=sha256()
    with manifest.open("rb") as rows:
        _identity(rows,mid)
        for i in range(layout.count):
            _check(cancelled)
            raw=rows.readline(MAX_LINE_BYTES+1)
            if not raw.endswith(b"\n") or len(raw)>MAX_LINE_BYTES:
                raise RuntimeError("Incomplete or oversized reel receipt")
            row=json.loads(raw);slot=layout.at(i)
            if (_canon(row)+b"\n"!=raw or set(row)!=set(slot)|{"wav_sha256","pcm_sha256","source_pcm_sha256","wav_bytes"} or
                    any(row.get(k)!=v for k,v in slot.items())):
                raise RuntimeError("Reel receipt gap, overlap or wrong identity")
            _sha(row["source_pcm_sha256"]);rows_hash.update(raw)
            path=folder/slot["filename"];fid=_protected_path(path)
            header=_header(slot["sample_count"],layout.stride)
            remaining=slot["sample_count"]*layout.stride
            if row["wav_bytes"]!=remaining+len(header):
                raise RuntimeError("Reel byte count differs from exact clock")
            wav_hash=sha256(header);pcm=sha256()
            with path.open("rb") as inp:
                if _identity(inp,fid).st_size!=row["wav_bytes"] or inp.read(len(header))!=header:
                    raise PermissionError("Wrong RIFF format or exact reel duration")
                while remaining:
                    _check(cancelled)
                    size=min(remaining,FRAMES_PER_BLOCK*layout.stride)
                    packet=inp.read(size)
                    if len(packet)!=size:
                        raise RuntimeError("Reel PCM truncated")
                    remaining-=size;wav_hash.update(packet);pcm.update(packet);master.update(packet)
                    yield packet
                if inp.read(1) or _protected_path(path)!=fid:
                    raise PermissionError("Reel grew or changed during read")
            if (wav_hash.hexdigest()!=_sha(row["wav_sha256"]) or
                    pcm.hexdigest()!=_sha(row["pcm_sha256"])):
                raise PermissionError("Reel PCM or WAV SHA differs from receipt")
            if on_reel is not None:
                on_reel(row)
        if rows.read(1) or _protected_path(manifest)!=mid:
            raise RuntimeError("Unexpected extra reel receipts")
    if rows_hash.hexdigest()!=doc["reels_sha256"] or master.hexdigest()!=doc["master_pcm_sha256"]:
        raise PermissionError("Full reel-set manifest or PCM SHA differs")
    if _protected_path(folder,directory=True)!=folder_id or _read_root(folder,expected_sha)[0]!=doc:
        raise PermissionError("Published reel root changed during verification")
    # Reject unexpected files without constructing a directory-sized set.
    count=0
    for path in folder.iterdir():
        if path.name not in ("manifest.json","reels.jsonl"):
            name=path.name
            if not name.startswith("PCM24_") or not name.endswith(".wav") or not name[6:-4].isascii() or not name[6:-4].isdigit():
                raise RuntimeError("Unexpected reel-set entry")
            index=int(name[6:-4])
            if not 0<=index<layout.count or layout.at(index)["filename"]!=name:
                raise RuntimeError("Unexpected reel file identity")
        count+=1
        if count>layout.count+2:
            raise RuntimeError("Unexpected additional reel-set entries")
    if count!=layout.count+2:
        raise RuntimeError("Incomplete reel set")
    _check(cancelled)


def verify_partitioned_pcm24(receipt, *, cancelled=lambda:False):
    if receipt.get("format")!=FORMAT or receipt.get("status")!="PARTITIONED_PCM24_CANDIDATE_PUBLISHED":
        raise PermissionError("Trusted partitioned PCM candidate receipt required")
    folder=Path(receipt["destination"]);expected=receipt["manifest_sha256"]
    _protected_path(folder,directory=True)
    doc,layout=_read_root(folder,expected)
    for _ in _packets(folder,expected,cancelled):
        pass
    return {"manifest_sha256":expected,"frame_count":layout.frames,
            "sample_count":layout.frames*SAMPLES_PER_FRAME,"reel_count":layout.count,
            "master_pcm_sha256":doc["master_pcm_sha256"],"production_audio_accepted":False}


def master_partitioned_pcm24(source_path, *, source_sha256, original_take_sha256,
                             cinema_frames, channel_layout, output_root, approve,
                             max_reel_frames=DEFAULT_REEL_FRAMES, gain_numerator=1,
                             gain_denominator=1, cancelled=lambda:False):
    if not callable(approve) or not callable(cancelled):
        raise PermissionError("Trusted creator approval and cancellation required")
    _sha(source_sha256);_sha(original_take_sha256)
    layout=AudioReels(cinema_frames,channel_layout,max_reel_frames)
    if (type(gain_numerator) is not int or not 0<=gain_numerator<=16 or
            type(gain_denominator) is not int or not 1<=gain_denominator<=16):
        raise ValueError("Bounded rational mastering gain required")
    gain=Fraction(gain_numerator,gain_denominator)
    if gain>4:
        raise ValueError("Unsafe mastering gain")
    source=Path(source_path);root=Path(output_root)
    sid=_protected_path(source);rid=_protected_path(root,directory=True)
    source=source.resolve(strict=True);root=root.resolve(strict=True)
    if _hash_source(source,sid,layout.source_bytes,cancelled)!=source_sha256:
        raise PermissionError("Original PCM SHA mismatch")
    scope={"operation":"nvp.wo4.master_partitioned_original_pcm24.v1","format":FORMAT,
           **layout.descriptor(),"source_sha256":source_sha256,"original_take_sha256":original_take_sha256,
           "source_path":str(source),"output_root":str(root),"gain":[gain.numerator,gain.denominator],
           "encrypted_at_rest_required":True,"source_modified":False,"production_audio_accepted":False}
    _check(cancelled)
    if approve(deepcopy(scope)) is not True:
        return {"format":FORMAT,"status":"DENIED","source_modified":False}
    if _protected_path(source)!=sid or _protected_path(root,directory=True)!=rid:
        raise PermissionError("Approved audio paths changed during consent")
    _check(cancelled)
    require_stage_space(root,layout.source_bytes+layout.count*(44+MAX_LINE_BYTES)+MAX_ROOT_BYTES)
    stage=Path(tempfile.mkdtemp(prefix=".nvp-pcm-reels-",dir=root));stage_id=None
    target=root/("PCM24_REELS_"+uuid.uuid4().hex)
    raw=sha256();master=sha256();rows_hash=sha256();peak=0
    try:
        stage_id=_protected_path(stage,directory=True)
        with source.open("rb") as inp,(stage/"reels.jsonl").open("xb") as rows:
            _identity(inp,sid);_identity(rows,_protected_path(stage/"reels.jsonl"))
            for i in range(layout.count):
                _check(cancelled);slot=layout.at(i);remaining=slot["sample_count"]*layout.stride
                header=_header(slot["sample_count"],layout.stride);wav_sha=sha256(header);pcm_sha=sha256();source_reel=sha256()
                path=stage/slot["filename"]
                with path.open("xb") as out:
                    _identity(out,_protected_path(path));out.write(header)
                    while remaining:
                        _check(cancelled);size=min(remaining,FRAMES_PER_BLOCK*layout.stride)
                        packet=inp.read(size)
                        if len(packet)!=size:
                            raise PermissionError("Original PCM truncated during mastering")
                        remaining-=size;raw.update(packet);source_reel.update(packet)
                        scaled=bytearray(size)
                        for offset in range(0,size,3):
                            value=int.from_bytes(packet[offset:offset+3],"little",signed=True)
                            value=_round_away(value*gain.numerator,gain.denominator)
                            if not MIN_24<=value<=MAX_24:
                                raise ValueError("Mastering gain clips the original PCM")
                            peak=max(peak,abs(value));scaled[offset:offset+3]=value.to_bytes(3,"little",signed=True)
                        out.write(scaled);pcm_sha.update(scaled);wav_sha.update(scaled);master.update(scaled)
                    out.flush();os.fsync(out.fileno())
                row={**slot,"wav_sha256":wav_sha.hexdigest(),"pcm_sha256":pcm_sha.hexdigest(),
                     "source_pcm_sha256":source_reel.hexdigest(),
                     "wav_bytes":len(header)+slot["sample_count"]*layout.stride}
                line=_canon(row)+b"\n"
                if len(line)>MAX_LINE_BYTES:
                    raise RuntimeError("Reel receipt exceeds bounded line")
                rows.write(line);rows_hash.update(line)
            if inp.read(1) or raw.hexdigest()!=source_sha256:
                raise PermissionError("Original PCM changed after approval")
            rows.flush();os.fsync(rows.fileno())
        doc={"format":FORMAT,**layout.descriptor(),"source_pcm_sha256":source_sha256,
             "original_take_sha256":original_take_sha256,"master_pcm_sha256":master.hexdigest(),
             "reels_sha256":rows_hash.hexdigest(),"gain":[gain.numerator,gain.denominator],
             "peak_output_absolute":peak,"source_modified":False,"production_audio_accepted":False,
             "ffmpeg_used":False}
        root_bytes=_canon(doc);root_sha=sha256(root_bytes).hexdigest()
        _write_protected(stage/"manifest.json",root_bytes)
        for _ in _packets(stage,root_sha,cancelled):
            pass
        if (_protected_path(source)!=sid or _protected_path(root,directory=True)!=rid or
                _protected_path(stage,directory=True)!=stage_id):
            raise PermissionError("Approved audio paths changed before publication")
        _check(cancelled);_fsync_directory(stage)
        atomic_publish_directory(stage,target)
        # An error after promotion leaves an orphan for explicit review, never an approved receipt.
        if _protected_path(target,directory=True)!=stage_id:
            raise PermissionError("Published audio set identity differs")
        receipt={"format":FORMAT,"status":"PARTITIONED_PCM24_CANDIDATE_PUBLISHED",
                 "destination":str(target),"manifest_sha256":root_sha,**doc,
                 "whole_track_loaded_into_ram":False,"encrypted_at_rest_verified":True}
        verify_partitioned_pcm24(receipt,cancelled=cancelled)
        return receipt
    finally:
        if stage.exists() and stage_id is not None and _protected_path(stage,directory=True)==stage_id:
            shutil.rmtree(stage)


def measure_partitioned_pcm24_loudness(receipt, *, cancelled=lambda:False):
    from backend.nvp_wo4_loudness_stream import measure_bounded_packets
    if receipt.get("format")!=FORMAT or receipt.get("status")!="PARTITIONED_PCM24_CANDIDATE_PUBLISHED":
        raise PermissionError("Trusted partitioned PCM candidate receipt required")
    folder=Path(receipt["destination"]);expected=receipt["manifest_sha256"]
    _protected_path(folder,directory=True)
    doc,layout=_read_root(folder,expected)
    return measure_bounded_packets(lambda:_packets(folder,expected,cancelled),layout.labels,
                                   layout.frames*SAMPLES_PER_FRAME,doc["master_pcm_sha256"])


def finite_reel_candidate(receipt, reel_index, *, expected_first_frame, expected_frame_count,
                          cancelled=lambda:False):
    """Read-only bridge to the original finite sound wrapper. No worker grant.

    The original delivery journal must still compare exact source, mastered
    PCM, gain, Take identity and picture interval to its approved decision.
    """
    from backend.nvp_wo4_pcm_stream import FORMAT as SINGLE_FORMAT
    if receipt.get("format")!=FORMAT or receipt.get("status")!="PARTITIONED_PCM24_CANDIDATE_PUBLISHED":
        raise PermissionError("Trusted partitioned PCM candidate receipt required")
    folder=Path(receipt["destination"]);expected=receipt["manifest_sha256"]
    _protected_path(folder,directory=True)
    doc,layout=_read_root(folder,expected);slot=layout.at(reel_index)
    if (type(expected_first_frame) is not int or type(expected_frame_count) is not int or
            slot["first_frame"]!=expected_first_frame or slot["frame_count"]!=expected_frame_count or
            slot["frame_count"]>DEFAULT_REEL_FRAMES):
        raise PermissionError("Selected audio must match exact finite picture reel interval")
    selected=None
    def remember(row):
        nonlocal selected
        if row["reel_index"]==reel_index:
            selected=row
    for _ in _packets(folder,expected,cancelled,remember):
        pass
    if selected is None:
        raise RuntimeError("Missing verified source reel")
    return {"format":SINGLE_FORMAT,"status":"STREAMED_PCM24_CANDIDATE_PUBLISHED",
            "destination":str(folder/slot["filename"]),"wav_file_sha256":selected["wav_sha256"],
            "wav_file_bytes":selected["wav_bytes"],"master_pcm_sha256":selected["pcm_sha256"],
            "source_pcm_sha256":selected["source_pcm_sha256"],"original_take_sha256":doc["original_take_sha256"],
            "frame_count":slot["frame_count"],"first_frame":slot["first_frame"],
            "channel_order":doc["channel_order"],"sample_rate":RATE,"sample_width_bytes":3,
            "gain":doc["gain"],"partitioned_manifest_sha256":expected,"source_modified":False,
            "production_audio_accepted":False,"ffmpeg_used":False,"whole_reel_loaded_into_ram":False,
            "encrypted_at_rest_verified":True,"classic_riff_under_4gib":True}
