"""Read-only finished DCP preview through the accepted Windows native authority.

The trusted host admits one revocable session. Picture and PCM come from
published MXF, not a proxy or the Take. No arbitrary executable, path or
command is accepted from a client. Preview is not a calibrated screening
or a continuous-real-time playback/production certification.
"""
from __future__ import annotations
from contextlib import contextmanager, ExitStack
from copy import deepcopy
from bisect import bisect_right
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import base64
import json
import ctypes
import os
import secrets
import threading
import time
import wave
from backend.nvp_film_index import FilmIndex
from backend.nvp_wo4_feature_journal import FeatureJournal,FRAME_TICKS
from backend.nvp_wo4_delivery_journal import CinemaDeliveryJournal
from backend.nvp_wo5_original_short import inspect_indexed_reel
from backend.nvp_wo5_original_feature import inspect_indexed_feature
from backend.nvp_wo3_native_codecs import common_codec_authority,_sha,MAX_STAGE_BYTES
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure,_linked_entry
from backend.nvp_wo3_j2k_audit import inspect_j2k_header,PROFILES
from backend.nvp_wo3_independent_essence import _ppm_header
from backend.nvp_wo4_pcm_master import CHANNEL_LAYOUTS
from backend.nvp_wo4_pcm_stream import _protected_path,_hash_stream
from backend.nvp_wo4_resource_budget import require_stage_space

FORMAT="nvp.wo5.finished_dcp_pcm24_picture_review.v1"
RATE=48000
FPS=24
SAMPLES_PER_FRAME=2000
PCM_CACHE_FRAMES=24
SESSION_SECONDS=7200
MAX_PREVIEW_WIDTH=1024
MAX_PNG_BYTES=3*1024*1024
MAX_J2K_BYTES=16*1024*1024
# One picture decode at a time; reserve all four compressed frames, one
# full-resolution 4K raster, audio and logs. Never raise the native stage cap.
STAGE_RESERVE=160*1024*1024

@dataclass(frozen=True)
class Reel:
    first:int
    frames:int
    picture:Path
    sound:Path
    picture_sha:str
    sound_sha:str
    picture_bytes:int
    sound_bytes:int
    job_id:str
    channels:tuple
    picture_shas:tuple
    wav:Path
    wav_sha:str
    wav_bytes:int
    pcm_sha:str
    receipt_sha:str

def locate_reel(reels,frame):
    """Global output Film Time -> exact published local MXF reel offset."""
    if (type(frame) is not int or frame < 0 or
            not reels or type(reels) is not tuple):
        raise ValueError("Exact nonnegative finished-film frame required")
    starts=[r.first for r in reels]
    index=bisect_right(starts,frame)-1
    if index<0 or frame>=reels[index].first+reels[index].frames:
        raise ValueError("Requested finished film frame outside indexed CPL")
    return index,frame-reels[index].first

def _display_png(xyz12,profile):
    """Derived screen preview only: DCI gamma2.6 XYZ -> approximate sRGB.

    DCP essence is unchanged. Screen white/brightness and auditorium
    appearance are not certified; use real color-managed theater QC.
    """
    import numpy as np
    from PIL import Image
    width,height,_=PROFILES[profile]
    if type(xyz12) is not bytes or len(xyz12)!=width*height*6:
        raise PermissionError("Invalid exact decoded DCDM 12-bit raster")
    # Select bounded pixels BEFORE expensive floating point transforms.
    stride=max(1,(width+MAX_PREVIEW_WIDTH-1)//MAX_PREVIEW_WIDTH)
    raw=np.frombuffer(xyz12,dtype=">u2").reshape(height,width,3)
    # Authenticate the numeric range of the ENTIRE decoded DCP image before
    # constructing a lower-resolution preview. A bad XYZ12 word at a pixel
    # skipped by downsampling must not be silently accepted as valid essence.
    # max() scans the contiguous full-resolution array without allocating
    # a second full-resolution boolean mask.
    if int(raw.max())>4095:
        raise PermissionError("Out-of-range delivered cinema XYZ12 values")
    sample=raw[::stride,::stride,:]
    xyz=np.power(sample.astype(np.float32)/4095.0,2.6)
    matrix=np.array([[3.2406,-1.5372,-0.4986],
                     [-0.9689,1.8758,0.0415],
                     [0.0557,-0.2040,1.0570]],dtype=np.float32)
    linear=np.maximum(xyz@matrix.T,0.0)
    rgb=np.where(linear<=0.0031308,12.92*linear,
                 1.055*np.power(linear,1/2.4)-0.055)
    rgb8=np.rint(np.clip(rgb,0,1)*255).astype(np.uint8)
    buffer=BytesIO()
    Image.fromarray(rgb8,"RGB").save(buffer,format="PNG",compress_level=3)
    data=buffer.getvalue()
    if len(data)>MAX_PNG_BYTES:
        raise PermissionError("Decoded picture exceeds bounded native preview")
    return data, (rgb8.shape[1],rgb8.shape[0])

def _stereo_pcm16(pcm24,channel_order):
    """Exact delivered PCM24 samples -> labelled stereo preview downmix.

    This does not change the actual 6/8-channel master. It is headphone/
    desktop monitoring, not cinema calibration or verified surround playback.
    """
    import numpy as np
    channels=len(channel_order)
    if tuple(channel_order) not in CHANNEL_LAYOUTS.values():
        raise PermissionError("Unapproved cinema channel sequence")
    if type(pcm24) is not bytes or len(pcm24)!=SAMPLES_PER_FRAME*channels*3:
        raise PermissionError("Delivered PCM24 did not cover exact picture frame")
    triplets=np.frombuffer(pcm24,dtype=np.uint8).reshape(SAMPLES_PER_FRAME,channels,3)
    vals=(triplets[:,:,0].astype(np.int32) |
          (triplets[:,:,1].astype(np.int32)<<8) |
          (triplets[:,:,2].astype(np.int32)<<16))
    signed=np.where(vals & 0x800000,vals-0x1000000,vals)
    samples=signed.astype(np.float32)/(2**23)
    left=samples[:,0].copy()
    right=samples[:,1].copy()
    if channels>=6:
        # Downmix for *preview*, never for derived master:
        # L/R + (-3 dB center/surround), LFE at -12 dB;
        # conservative normalization avoids overflow on multi-channel scenes.
        left=(left+0.70710678*samples[:,2]+0.25*samples[:,3]+
              0.70710678*samples[:,4]) / 2.66421356
        right=(right+0.70710678*samples[:,2]+0.25*samples[:,3]+
               0.70710678*samples[:,5]) / 2.66421356
        if channels==8:
            left=(left*2.66421356+0.70710678*samples[:,6])/3.37132034
            right=(right*2.66421356+0.70710678*samples[:,7])/3.37132034
    stereo=np.column_stack((left,right))
    return np.rint(np.clip(stereo,-1,1)*32767).astype("<i2").tobytes()


def _identity(path):
    path=Path(path)
    if (not path.is_absolute() or len(path.drive)!=2 or path.drive[1]!=":" or
        any(part in (".","..") or ":" in part for part in path.parts[1:]) or
        any(_linked_entry(x) for x in (path,*path.parents)) or not path.is_file()):
        raise PermissionError("Exact native local media path required")
    st=path.stat()
    return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)


@contextmanager
def _locked_media(path):
    """Windows read handle denies cooperating and non-cooperating file writers
    and replacement while selected media is admitted. No worker gets the
    original inode. No Linux/stdlib fallback to an unlocked file.
    """
    import win32file
    import win32con
    import msvcrt
    path=Path(path)
    original=_identity(path)
    handle=win32file.CreateFile(str(path),win32con.GENERIC_READ,win32con.FILE_SHARE_READ,
                 None,win32con.OPEN_EXISTING,win32con.FILE_ATTRIBUTE_NORMAL,None)
    raw=handle.Detach()
    try:
        fd=msvcrt.open_osfhandle(raw,os.O_RDONLY|os.O_BINARY)
    except BaseException:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(raw))
        raise
    with os.fdopen(fd,"rb") as stream:
        st=os.fstat(stream.fileno())
        if (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)!=original or _identity(path)!=original:
            raise PermissionError("Source media changed on locked open")
        yield stream,original
        if _identity(path)!=original:
            raise PermissionError("Source media replaced during read lease")


def _copy_published(source,target,expected,size,cancel):
    _sha(expected)
    if type(size) is not int or not 128<=size<=MAX_STAGE_BYTES-STAGE_RESERVE:
        raise PermissionError("Published asset exceeds protected playback budget")
    _protected_path(target.parent,directory=True)
    source.seek(0)
    digest=sha256()
    total=0
    with target.open("xb") as out:
        identity=_protected_path(target)
        info=os.fstat(out.fileno())
        if (info.st_dev,info.st_ino)!=identity:
            raise PermissionError("Protected playback destination replaced")
        while block:=source.read(1024*1024):
            if cancel():raise InterruptedError("Playback staging cancelled")
            total+=len(block)
            if total>size:raise PermissionError("Published asset exceeds approved bytes")
            digest.update(block);out.write(block)
        out.flush();os.fsync(out.fileno())
    if total!=size or digest.hexdigest()!=expected or _hash_stream(target)!=(expected,size):
        raise PermissionError("Published MXF changed before protected decode")


def _read_verified_pcm24(wavfile,channel_order,frames=1):
    if type(frames) is not int or not 1<=frames<=PCM_CACHE_FRAMES:
        raise ValueError("Bounded exact native sound region required")
    identity=_protected_path(Path(wavfile))
    with Path(wavfile).open("rb") as stream, wave.open(stream,"rb") as inp:
        st=os.fstat(stream.fileno())
        if (st.st_dev,st.st_ino)!=identity or inp.getnchannels()!=len(channel_order) or
            inp.getframerate()!=RATE or inp.getsampwidth()!=3 or
            inp.getcomptype()!="NONE" or inp.getnframes()!=frames*SAMPLES_PER_FRAME):
            raise PermissionError("Unwrapped finished PCM does not match approved Film Time")
        pcm=inp.readframes(frames*SAMPLES_PER_FRAME)
    if len(pcm)!=frames*SAMPLES_PER_FRAME*3*len(channel_order) or _protected_path(Path(wavfile))!=identity:
        raise PermissionError("Incomplete native delivered sound")
    return pcm


def _region_ledger(stream,reel,cancel):
    """Stream the approved EFS WAV once; retain at most 300 digests per reel,
    not the whole soundtrack or any independently asserted chunk hash.
    """
    stream.seek(0)
    full=sha256()
    size=0
    while block:=stream.read(1024*1024):
        if cancel():raise InterruptedError("Playback master verification cancelled")
        size+=len(block)
        if size>reel.wav_bytes:raise PermissionError("Approved WAV grew")
        full.update(block)
    if full.hexdigest()!=reel.wav_sha or size!=reel.wav_bytes:
        raise PermissionError("Approved master WAV differs")
    stream.seek(0)
    ledger={}
    pcm=sha256()
    with wave.open(stream,"rb") as reader:
        if (reader.getnchannels()!=len(reel.channels) or reader.getframerate()!=RATE or
            reader.getsampwidth()!=3 or reader.getcomptype()!="NONE" or
            reader.getnframes()!=reel.frames*SAMPLES_PER_FRAME):
            raise PermissionError("Source PCM timeline differs")
        for first in range(0,reel.frames,PCM_CACHE_FRAMES):
            if cancel():raise InterruptedError("Playback master verification cancelled")
            count=min(PCM_CACHE_FRAMES,reel.frames-first)
            data=reader.readframes(count*SAMPLES_PER_FRAME)
            if len(data)!=count*SAMPLES_PER_FRAME*3*len(reel.channels):
                raise PermissionError("Approved PCM region truncated")
            pcm.update(data)
            ledger[first]=(count,sha256(data).hexdigest())
    if pcm.hexdigest()!=reel.pcm_sha:
        raise PermissionError("Approved source PCM SHA differs")
    return ledger


def _pcm_region_window(local,count,frames,read_region,bytes_per_frame):
    if (type(local) is not int or type(count) is not int or not 0<=local<frames or
            not 1<=count<=4 or local+count>frames):
        raise ValueError("Exact reel-local mastered sound window required")
    blocks=[]
    pos=local
    end=local+count
    while pos<end:
        first=(pos//PCM_CACHE_FRAMES)*PCM_CACHE_FRAMES
        length=min(PCM_CACHE_FRAMES,frames-first)
        pcm=read_region(first,length)
        if type(pcm) is not bytes or len(pcm)!=length*bytes_per_frame:
            raise PermissionError("Native region sample count differs")
        stop=min(end,first+length)
        blocks.append(pcm[(pos-first)*bytes_per_frame:(stop-first)*bytes_per_frame])
        pos=stop
    return b"".join(blocks)


def load_published_reels(index,journal,project_id,feature_id,*,single_reel=False):
    """Internal-only result includes validated paths; never expose it via IPC."""
    if (not isinstance(index,FilmIndex) or not isinstance(journal,CinemaDeliveryJournal)
            or type(single_reel) is not bool):
        raise PermissionError("Actual native project and production journal required")
    if single_reel:
        review=inspect_indexed_reel(index,journal,project_id,feature_id)
        folder,files=journal._check_published(feature_id)
        jobs=[feature_id]
        profile=review["profile"]
        receipt=review["source_filmindex_dcp_receipt_sha256"]
    else:
        if not isinstance(journal,FeatureJournal):
            raise PermissionError("Trusted native feature journal required")
        review=inspect_indexed_feature(index,journal,project_id,feature_id)
        f,m,folder,files=journal._recheck_feature(feature_id)
        receipt=review["filmindex_feature_receipt_sha256"]
        if f["filmindex_sha256"]!=receipt or f["state"]!="INDEXED":
            raise PermissionError("Feature publication changed")
        jobs=m["ordered_reel_job_ids"]
        profile=m["profile"]
    audit=inspect_dcp_structure(folder)
    if (audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or audit["reel_count"]!=len(jobs)
        or len(audit["tracks"])!=2*len(jobs) or audit["cpl_uuid"]!=review["cpl_uuid"]):
        raise PermissionError("Published CPL track schedule differs")
    reels=[]
    first=0
    for i,uid in enumerate(jobs):
        src=inspect_indexed_reel(index,journal,project_id,uid)
        d=journal.delivery(uid); rr=journal.reel(uid)
        count=src["frame_count"]
        if src["profile"]!=profile or audit["reel_durations"][i]!=count:
            raise PermissionError("Exact indexed reel profile and duration required")
        pair={x["kind"]:x for x in audit["tracks"][2*i:2*i+2]}
        if set(pair)!={"picture","sound"}:
            raise PermissionError("Exact published track pair required")
        tracks=[]
        for kind,assetid,digest,size in (("picture",rr["picture_uuid"],rr["track_sha256"],rr["track_bytes"]),
                                        ("sound",d["sound_uuid"],d["sound_sha256"],d["sound_bytes"])):
            track=pair[kind]
            path=folder/track["filename"]
            if (track["asset_id"]!=assetid or track["duration_frames"]!=count or
                files.get(path.name)!=digest or audit["assets"][assetid]["sha256"]!=digest or
                audit["assets"][assetid]["bytes"]!=size or _identity(path)[2]!=size):
                raise PermissionError("Final MXF differs from indexed source track")
            tracks.append((path,digest,size))
        if tracks[0][2]+tracks[1][2]+STAGE_RESERVE>MAX_STAGE_BYTES:
            raise PermissionError("Reel exceeds protected stage budget; smaller source reels required")
        wav=journal.approved_sound_candidate(uid)
        channels=tuple(src["channel_order"])
        if channels not in CHANNEL_LAYOUTS.values():
            raise PermissionError("Unrecognized original cinema channels")
        reels.append(Reel(first,count,tracks[0][0],tracks[1][0],tracks[0][1],tracks[1][1],
            tracks[0][2],tracks[1][2],uid,channels,tuple(x["j2k_sha256"] for x in src["frame_receipts"]),
            Path(wav["destination"]),wav["wav_file_sha256"],wav["wav_file_bytes"],
            wav["master_pcm_sha256"],src["source_filmindex_dcp_receipt_sha256"]))
        first+=count
    if first!=review["frame_count"]:
        raise PermissionError("Published Film Time differs")
    # Only small exact XML files are rehashed per window. Active native
    # track handles are write/delete denied, and stage hashes are checked by
    # the existing codec authority at every process launch.
    metadata={folder/name:digest for name,digest in files.items() if name.lower().endswith(".xml")}
    if not metadata:
        raise PermissionError("Missing committed cinema XML metadata")
    return receipt,tuple(reels),profile,metadata


class FinishedFilmPlayer:
    """One trusted host-owned revocable session, synchronous bounded windows.

    begin allows single-reel or feature identities. Codec factory must bind
    the *same* cancel closure to actual ProtectedCodecAuthority. No client
    path, code, approval boolean or decoder executable is accepted.
    """
    def __init__(self,index,journal,*,codec_factory,native_window,ask_native,host_revoked):
        if (not isinstance(index,FilmIndex) or not isinstance(journal,CinemaDeliveryJournal) or
            not all(callable(x) for x in (codec_factory,native_window,ask_native,host_revoked))):
            raise PermissionError("Trusted native finished-film host required")
        self.index,self.journal=index,journal
        self.codec_factory,self.native_window,self.ask_native=codec_factory,native_window,ask_native
        self.host_revoked=host_revoked
        self._lock=threading.RLock()
        self._decode_lock=threading.RLock()
        self._state=None
        self._active=None
        self._pcm_cache=None
        self._closed=False

    def _require_window(self):
        if self.native_window() is False or self.host_revoked():
            raise PermissionError("Native window/project grant revoked")

    def begin(self,project_id,feature_id,*,single_reel=False):
        self._require_window()
        with self._decode_lock:
            with self._lock:
                if self._closed or self._state:
                    raise PermissionError("Stop previous finished-film session first")
            receipt,reels,profile,metadata=load_published_reels(
                self.index,self.journal,project_id,feature_id,single_reel=single_reel)
            ticket=secrets.token_urlsafe(32)
            cancelled=threading.Event()
            expires=time.monotonic()+SESSION_SECONDS
            def cancel():
                return cancelled.is_set() or self._closed or time.monotonic()>expires or self.host_revoked()
            codecs=self.codec_factory(project_id,cancel)
            if (type(codecs) not in (tuple,list) or len(codecs)!=2 or
                tuple(c.product for c in codecs)!=("ASDCP-asdcp_unwrap","OpenJPEG-opj_decompress")):
                raise PermissionError("Trusted decoder pair required")
            unwrap,decoder=codecs
            authority=common_codec_authority(unwrap,decoder)
            if authority.project_id!=project_id or authority.cancel is not cancel:
                raise PermissionError("Playback native project/cancellation scope differs")
            scope={"operation":"nvp.wo5.approve_readonly_finished_mxf_playback.v1",
                   "project_id":project_id,"feature_id":feature_id,"single_reel":single_reel,
                   "filmindex_sha256":receipt,"frames":sum(r.frames for r in reels),
                   "ordered_reel_receipts":[r.receipt_sha for r in reels],
                   "codec_manifest_sha256":authority.pin,"unwrap_binary_sha256":unwrap.sha256,
                   "openjpeg_binary_sha256":decoder.sha256,"read_only":True,
                   "playback_not_dci_or_cinema_certification":True}
            if self.ask_native(deepcopy(scope)) is not True:
                return {"format":FORMAT,"status":"DENIED","source_modified":False}
            self._require_window()
            if load_published_reels(self.index,self.journal,project_id,feature_id,
                                    single_reel=single_reel)!=(receipt,reels,profile,metadata):
                raise PermissionError("Approved playback scope changed during consent")
            with self._lock:
                if self._closed or self._state or cancel():
                    raise PermissionError("Playback changed during creator confirmation")
                self._state={"ticket":ticket,"cancel":cancel,"event":cancelled,"reels":reels,
                    "receipt":receipt,"profile":profile,"metadata":metadata,"codecs":tuple(codecs),
                    "pid":project_id,"target":feature_id,"single":single_reel,"next_frame":None}
            return {"format":FORMAT,"status":"FINISHED_DCP_READONLY_READY","session_id":ticket,
                "frame_count":scope["frames"],"reel_count":len(reels),"fps":FPS,"sound_rate":RATE,
                "sound_samples_per_frame":SAMPLES_PER_FRAME,"screen_preview_max_width":MAX_PREVIEW_WIDTH,
                "native_picture_and_sound_from_published_mxf":True,
                "screen_preview_uncalibrated_xyz_to_srgb":True,
                "sound_stereo_downmix_not_original_surround_output":True,
                "continuous_real_time_playback_verified":False,"production_accepted":False,
                "smpte_bv21_certified":False,"ffmpeg_used":False}

    def _get(self,ticket):
        self._require_window()
        with self._lock:
            s=self._state
            if (not s or self._closed or type(ticket) is not str or
                not secrets.compare_digest(ticket,s["ticket"]) or s["cancel"]()):
                raise PermissionError("Native finished-film playback session revoked")
            return s

    def _assert_current(self,s):
        if s["cancel"]():raise InterruptedError("Playback revoked")
        if s["single"]:
            d=self.journal.delivery(s["target"])
            j=self.journal.status(s["target"])
            if (j["project_id"]!=s["pid"] or j["state"]!="DCP_INDEXED" or j["cancel_requested"] or
                d["phase"]!="INDEXED" or d["filmindex_sha256"]!=s["receipt"]):
                raise PermissionError("Indexed delivery changed")
        else:
            f=self.journal.feature(s["target"])
            if (f["project_id"]!=s["pid"] or f["state"]!="INDEXED" or f["cancel_requested"] or
                f["filmindex_sha256"]!=s["receipt"]):
                raise PermissionError("Indexed feature changed")
        if s["single"]:
            presentation_id="WO3DCP_"+d["cpl_uuid"].replace("-","")
        else:
            manifest=json.loads(f["manifest_json"])
            presentation_id="WO4FEATURE_"+manifest["ids"]["cpl"].replace("-","")
        presentation=self.index.read_revision(s["pid"],presentation_id,1)
        if (presentation["kind"]!="presentation" or presentation["document_sha256"]!=s["receipt"]):
            raise PermissionError("Current indexed finished presentation changed")
        for path,digest in s["metadata"].items():
            with _locked_media(path) as (stream,stamp):
                if stamp[2]>16*1024*1024 or sha256(stream.read(16*1024*1024+1)).hexdigest()!=digest:
                    raise PermissionError("Published cinema XML changed")

    @contextmanager
    def _reel_stage(self,s,reel):
        unwrap,_=s["codecs"]
        cancel=s["cancel"]
        with ExitStack() as stack:
            picture,pstamp=stack.enter_context(_locked_media(reel.picture))
            sound,sstamp=stack.enter_context(_locked_media(reel.sound))
            wav,wstamp=stack.enter_context(_locked_media(reel.wav))
            if (pstamp[:2]==sstamp[:2] or _protected_path(reel.wav)!=wstamp[:2] or
                pstamp[2]!=reel.picture_bytes or sstamp[2]!=reel.sound_bytes):
                raise PermissionError("Aliased or changed approved media")
            ledger=_region_ledger(wav,reel,cancel)
            root=stack.enter_context(unwrap.stage(reel.receipt_sha,playback_inputs={
                "picture.mxf":reel.picture_sha,"sound.mxf":reel.sound_sha,
                "frames":reel.frames,"picture_sha256":reel.picture_shas}))
            _protected_path(root,directory=True)
            require_stage_space(root,reel.picture_bytes+reel.sound_bytes+STAGE_RESERVE)
            _copy_published(picture,root/"picture.mxf",reel.picture_sha,reel.picture_bytes,cancel)
            _copy_published(sound,root/"sound.mxf",reel.sound_sha,reel.sound_bytes,cancel)
            yield {"root":root,"ledger":ledger,"stamps":((reel.picture,pstamp),(reel.sound,sstamp),(reel.wav,wstamp))}
            # Only after all synchronous native calls closed and outputs were
            # checked, remove our verified encrypted *copies*. Keep native
            # journal/logs. An exceptional exit preserves original evidence.
            from backend.nvp_w1g_release_gate import inspect_original_process_journals
            inspect_original_process_journals()
            for path,digest,size in ((root/"picture.mxf",reel.picture_sha,reel.picture_bytes),
                                      (root/"sound.mxf",reel.sound_sha,reel.sound_bytes)):
                if _hash_stream(path)!=(digest,size):
                    raise PermissionError("Unexpected protected playback input mutation")
                path.unlink()

    def _release_stage(self,exc=None):
        active,self._active=self._active,None
        self._pcm_cache=None
        if active:
            ctx=active["ctx"]
            if exc is None:
                ctx.__exit__(None,None,None)
            else:
                ctx.__exit__(type(exc),exc,exc.__traceback__)

    def _ensure_stage(self,s,reel,index):
        d=self.journal.delivery(reel.job_id)
        status=self.journal.status(reel.job_id)
        source=self.index.read_revision(s["pid"],"WO3DCP_"+d["cpl_uuid"].replace("-",""),1)
        if (status["project_id"]!=s["pid"] or status["state"]!="DCP_INDEXED" or status["cancel_requested"] or
            d["phase"]!="INDEXED" or d["filmindex_sha256"]!=reel.receipt_sha or
            source["document_sha256"]!=reel.receipt_sha):
            raise PermissionError("Source reel lost its indexed authority")
        if self._active is None or self._active["index"]!=index:
            self._release_stage()
            ctx=self._reel_stage(s,reel)
            value=ctx.__enter__()
            self._active={**value,"index":index,"ctx":ctx}
        for path,stamp in self._active["stamps"]:
            if _identity(path)!=stamp:
                raise PermissionError("Locked playback source identity changed")
        return self._active

    def _pcm24_window(self,s,reel,index,local,count,active):
        unwrap,_=s["codecs"]
        root=active["root"]
        def read_region(first,length):
            key=(s["ticket"],index,first,length,reel.sound_sha)
            if self._pcm_cache is not None and self._pcm_cache["key"]==key:
                return self._pcm_cache["pcm"]
            if s["cancel"]():raise InterruptedError("Playback cancelled")
            unwrap.run(["-f",str(first),"-d",str(length),"sound.mxf","audio"],cwd=root,timeout=180)
            out=root/"audio"
            pcm=_read_verified_pcm24(out,reel.channels,length)
            if active["ledger"].get(first)!=(length,sha256(pcm).hexdigest()):
                raise PermissionError("Native PCM differs from approved original master region")
            out.unlink()
            self._pcm_cache={"key":key,"pcm":pcm}
            return pcm
        return _pcm_region_window(local,count,reel.frames,read_region,SAMPLES_PER_FRAME*3*len(reel.channels))

    def frame(self,ticket,global_frame):
        return self.window(ticket,global_frame,1)["frames"][0]

    def window(self,ticket,first_frame,count=4):
        s=self._get(ticket)
        if type(first_frame) is not int or type(count) is not int or not 1<=count<=4:
            raise ValueError("Bounded exact finished DCP window required")
        index,local=locate_reel(s["reels"],first_frame)
        reel=s["reels"][index]
        count=min(count,reel.frames-local)
        with self._decode_lock:
            s=self._get(ticket)
            try:
                self._assert_current(s)
                if s["next_frame"]!=first_frame:self._pcm_cache=None
                active=self._ensure_stage(s,reel,index)
                root=active["root"];unwrap,decoder=s["codecs"]
                unwrap.run(["-f",str(local),"-d",str(count),"-b",str(MAX_J2K_BYTES),"picture.mxf","p_"],
                           cwd=root,timeout=250)
                pcm=self._pcm24_window(s,reel,index,local,count,active)
                bpf=SAMPLES_PER_FRAME*3*len(reel.channels)
                frames=[]
                for n in range(count):
                    if s["cancel"]():raise InterruptedError("Playback cancelled")
                    pos=local+n
                    file=root/f"p_{pos:06d}.j2c"
                    _protected_path(file)
                    if not 80<=file.stat().st_size<=MAX_J2K_BYTES:
                        raise PermissionError("Published native codestream exceeds bound")
                    raw=file.read_bytes()
                    expected=reel.picture_shas[pos]
                    if sha256(raw).hexdigest()!=expected:
                        raise PermissionError("Published codestream differs from indexed frame")
                    inspect_j2k_header(raw,s["profile"])
                    dest=f"xyz_{pos:06d}.ppm"
                    decoder.run(["-i",file.name,"-o",dest],cwd=root,timeout=240)
                    decoded=root/dest
                    _protected_path(decoded)
                    pixels=_ppm_header(decoded,width=PROFILES[s["profile"]][0],height=PROFILES[s["profile"]][1])
                    png,(width,height)=_display_png(pixels,s["profile"])
                    native_pcm=pcm[n*bpf:(n+1)*bpf]
                    audio=_stereo_pcm16(native_pcm,reel.channels)
                    frame_index=first_frame+n
                    frames.append({"format":FORMAT,"status":"DECODED_PUBLISHED_FINAL_FRAME",
                        "frame_index":frame_index,"reel_index":index,"reel_frame_index":pos,
                        "picture_24fps_film_time_tick":frame_index*FRAME_TICKS,
                        "audio_start_sample":frame_index*SAMPLES_PER_FRAME,"audio_samples":SAMPLES_PER_FRAME,
                        "picture_png_base64":base64.b64encode(png).decode("ascii"),
                        "picture_width":width,"picture_height":height,
                        "stereo_pcm16_base64":base64.b64encode(audio).decode("ascii"),
                        "source_j2k_sha256":expected,"decoded_xyz12_sha256":sha256(pixels).hexdigest(),
                        "source_pcm24_sha256":sha256(native_pcm).hexdigest(),
                        "picture_and_sound_from_final_published_mxf":True,"screen_display_calibrated":False,
                        "original_multichannel_master_preserved":True,"production_accepted":False,
                        "finished_film_complete_viewing_verified":False})
                    file.unlink();decoded.unlink()
                self._assert_current(s)
                self._ensure_stage(s,reel,index)
                for path,stamp in active["stamps"]:
                    if _identity(path)!=stamp:raise PermissionError("Playback source identity changed")
                self._get(ticket)
                s["next_frame"]=first_frame+count
                return {"format":FORMAT,"status":"DECODED_PUBLISHED_FINAL_WINDOW",
                    "start_frame":first_frame,"frame_count":count,"reel_index":index,"frames":frames,
                    "no_reel_crossing":True,"whole_film_in_memory":False,"production_accepted":False,
                    "continuous_real_time_playback_verified":False,"ffmpeg_used":False}
            except BaseException as exc:
                s["event"].set()
                with self._lock:self._state=None
                self._release_stage(exc)
                raise

    def stop(self,ticket):
        self._require_window()
        with self._lock:
            s=self._state
            if not s or type(ticket) is not str or not secrets.compare_digest(ticket,s["ticket"]):
                raise PermissionError("Unknown native playback session")
            s["event"].set()
        with self._decode_lock:
            with self._lock:
                if self._state is not None and self._state is not s:
                    return {"format":FORMAT,"status":"STOPPED","production_accepted":False}
                if self._state is s:self._state=None
            self._release_stage()
            from backend.nvp_w1g_release_gate import inspect_original_process_journals
            inspect_original_process_journals()
        return {"format":FORMAT,"status":"STOPPED","production_accepted":False}

    def close(self):
        with self._lock:
            self._closed=True
            if self._state:self._state["event"].set()
        with self._decode_lock:
            with self._lock:self._state=None
            self._release_stage()


