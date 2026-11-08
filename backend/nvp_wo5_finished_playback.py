"""WO5-04 FFmpeg-free finished-film review of *published* DCP picture and PCM.

Read-only native desktop session. Reopens exact indexed, hash-checked
multi-reel DCP, then extracts ONE published MXF frame and its paired 48 kHz
PCM24 audio frame using approved native CineCert asdcplib. Decodes published
JPEG2000 with approved native OpenJPEG, and converts XYZ12 to a bounded
uncalibrated 8-bit sRGB screen preview. This is NOT original Take audition:
the pixels and samples come from the final picture/sound MXF tracks.

A source-window helper never produces a master, modifies an original, launches
an independent supervisor or claims Bv2.1 or calibrated projection. The GUI
may buffer; it must not silently skip a frame or present unplayed footage as
a watched movie.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import base64
from bisect import bisect_right
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import secrets
import threading
import time
import wave

from backend.nvp_film_index import FilmIndex
from backend.nvp_wo4_feature_journal import FeatureJournal, FRAME_TICKS
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary, digest_file
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo3_j2k_audit import inspect_j2k_header, PROFILES
from backend.nvp_wo3_independent_essence import _ppm_header
from backend.nvp_supervised_codec_process import run_supervised_codec
from backend.nvp_wo4_pcm_master import CHANNEL_LAYOUTS
from backend.nvp_wo5_original_feature import inspect_original_feature_readiness

FORMAT="nvp.wo5.finished_dcp_pcm24_picture_review.v1"
RATE=48000
FPS=24
SAMPLES_PER_FRAME=RATE//FPS
PCM_CACHE_FRAMES=24  # At most one actual finished-MXF sound second.
SESSION_SECONDS=7200
MAX_PREVIEW_WIDTH=1024
MAX_PNG_BYTES=3*1024*1024
MAX_SESSIONS=1
MAX_J2K_BYTES=16*1024*1024

@dataclass(frozen=True)
class Reel:
    first:int
    frames:int
    picture:Path
    sound:Path
    picture_sha:str
    sound_sha:str
    job_id:str
    channels:tuple[str,...]
    picture_stat:tuple[int,int,int,int]
    sound_stat:tuple[int,int,int,int]

def _fingerprint(path):
    st=path.stat()
    return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)

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
    sample=raw[::stride,::stride,:]
    if np.any(sample>4095):
        raise PermissionError("Out-of-range delivered cinema XYZ12 values")
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

def _read_verified_pcm24(wavfile,channel_order):
    if wavfile.is_symlink() or not wavfile.is_file():
        raise PermissionError("Native MXF did not produce original PCM WAV")
    with wave.open(str(wavfile),"rb") as inp:
        if (inp.getnchannels()!=len(channel_order) or
                inp.getframerate()!=RATE or
                inp.getsampwidth()!=3 or
                inp.getcomptype()!="NONE" or
                inp.getnframes()!=SAMPLES_PER_FRAME):
            raise PermissionError("Unwrapped finished PCM does not match 24fps/48k")
        pcm=inp.readframes(SAMPLES_PER_FRAME)
    if len(pcm)!=SAMPLES_PER_FRAME*3*len(channel_order):
        raise PermissionError("Incomplete native delivered sound")
    return pcm

def load_published_reels(index,journal,project_id,feature_id):
    """Fully rehash and pin final CPL, final MXF and original FilmIndex."""
    audited=inspect_original_feature_readiness(index,journal,project_id,feature_id)
    f,manifest,folder,_=journal._recheck_feature(feature_id)
    if (f["state"]!="INDEXED" or
            audited["filmindex_feature_receipt_sha256"]!=f["filmindex_sha256"]):
        raise PermissionError("Published delivered feature not FilmIndex indexed")
    struct=inspect_dcp_structure(folder)
    tracks=struct["tracks"]
    ordered=manifest["ordered_reel_job_ids"]
    if (len(tracks)!=2*len(ordered) or
            struct["reel_durations"]!=[r["frames"] for r in manifest["reels"]]):
        raise PermissionError("Final delivered SMPTE CPL does not match reel schedule")
    result=[]
    cursor=0
    folder=folder.resolve(strict=True)
    for i,(job_id,part) in enumerate(zip(ordered,manifest["reels"])):
        pair=tracks[2*i:2*i+2]
        by_kind={x["kind"]:x for x in pair}
        if set(by_kind)!={"picture","sound"}:
            raise PermissionError("Expected picture and sound on every final reel")
        files={}
        for kind in ("picture","sound"):
            track=by_kind[kind]
            if (track["asset_id"]!=part[kind]["asset_uuid"] or
                    track["duration_frames"]!=part["frames"]):
                raise PermissionError("CPL track references unrelated source reel")
            file=folder/track["filename"]
            if (file.is_symlink() or not file.is_file() or
                    file.resolve(strict=True).parent!=folder or
                    digest_file(file)!=part[kind]["file_sha256"]):
                raise PermissionError("Final picture/sound track changed after publication")
            files[kind]=file
        reel=journal.reel(job_id)
        decision=index.read_revision(project_id,reel["decision_id"],1)
        channels=tuple(decision["data"]["channel_order"])
        if channels not in CHANNEL_LAYOUTS.values():
            raise PermissionError("Mastered DCP cinema channels unrecognized")
        if part["start_tick"]!=cursor*FRAME_TICKS:
            raise PermissionError("Final video has a gap or overlapping reel")
        result.append(Reel(cursor,part["frames"],
                           files["picture"],files["sound"],
                           part["picture"]["file_sha256"],
                           part["sound"]["file_sha256"],job_id,channels,
                           _fingerprint(files["picture"]),
                           _fingerprint(files["sound"])))
        cursor+=part["frames"]
    if cursor!=audited["frame_count"]:
        raise PermissionError("Final film CPL duration not equal to approved Film Time")
    return audited,tuple(result),manifest["profile"]

def _expected_frame_sha(journal,job_id,offset):
    with journal._read() as db:
        row=db.execute("""SELECT s.position,s.state,f.file_sha256
                FROM production_segments s JOIN production_cinema_frames f
                ON s.job_id=f.job_id AND s.position=f.position
                WHERE s.job_id=? AND s.position=?""",(job_id,offset)).fetchone()
    if row is None or row["position"]!=offset or row["state"]!="VERIFIED":
        raise PermissionError("Approved picture frame was not indexed")
    return row["file_sha256"]

class FinishedFilmPlayer:
    """One host-owned native session, strictly bounded and independently revocable.

    Operations are synchronous at IPC boundary. The React player prebuffers
    decoded frame+sound windows and owns the WebAudio timeline; if the
    native codecs are too slow, it MUST report buffering/underflow, not
    pretend to play smooth film.
    """
    def __init__(self,index,journal,*,unwrap,decoder,private_root,
                 native_window,ask_native):
        if (not isinstance(index,FilmIndex) or
            not isinstance(journal,FeatureJournal) or
            not isinstance(unwrap,ApprovedCodecBinary) or
            unwrap.product!="ASDCP-asdcp_unwrap" or
            not isinstance(decoder,ApprovedCodecBinary) or
            decoder.product!="OpenJPEG-opj_decompress" or
            not callable(native_window) or not callable(ask_native)):
            raise PermissionError("Trusted native finished-film player requires real pinned codecs")
        root=Path(private_root)
        if not root.is_absolute() or root.is_symlink():
            raise PermissionError("Only host-owned absolute native scratch path")
        root.mkdir(parents=True,exist_ok=True)
        if root.is_symlink():
            raise PermissionError("Native playback scratch redirected")
        self.index=index
        self.journal=journal
        self.unwrap=unwrap
        self.decoder=decoder
        self.root=root.resolve(strict=True)
        self.native_window=native_window
        self.ask_native=ask_native
        self._lock=threading.RLock()
        self._decode_lock=threading.Lock()
        self._state=None
        self._pcm_cache=None
        self._closed=False

    def begin(self,project_id,feature_id):
        self.native_window()
        with self._lock:
            if self._closed or self._state:
                raise PermissionError("Stop previous finished-film session first")
        audit,reels,profile=load_published_reels(
            self.index,self.journal,project_id,feature_id)
        scope={
            "operation":"nvp.wo5.approve_readonly_finished_mxf_playback.v1",
            "project_id":project_id,"feature_id":feature_id,
            "feature_filmindex_sha256":audit["filmindex_feature_receipt_sha256"],
            "picture_custody_sha256":audit["ordered_picture_custody_sha256"],
            "frames":audit["frame_count"],
            "unwrap_binary_sha256":self.unwrap.sha256,
            "openjpeg_binary_sha256":self.decoder.sha256,
            "read_only":True,
            "playback_not_dci_or_cinema_certification":True,
        }
        if self.ask_native(scope) is not True:
            return {"format":FORMAT,"status":"DENIED","source_modified":False}
        self.native_window()
        self.unwrap.check()
        self.decoder.check()
        with self._lock:
            if self._state or self._closed:
                raise PermissionError("Playback changed during native confirmation")
            ticket=secrets.token_urlsafe(32)
            self._pcm_cache=None
            self._state={"ticket":ticket,"project_id":project_id,
                         "feature_id":feature_id,"reels":reels,
                         "profile":profile,"audit":audit,
                         "created":time.monotonic(),"cancelled":False}
            return {"format":FORMAT,"status":"FINISHED_DCP_READONLY_READY",
                    "session_id":ticket,
                    "frame_count":audit["frame_count"],
                    "reel_count":len(reels),"fps":FPS,
                    "sound_rate":RATE,"sound_samples_per_frame":SAMPLES_PER_FRAME,
                    "screen_preview_max_width":MAX_PREVIEW_WIDTH,
                    "native_picture_and_sound_from_published_mxf":True,
                    "screen_preview_uncalibrated_xyz_to_srgb":True,
                    "sound_stereo_downmix_not_original_surround_output":True,
                    "continuous_real_time_playback_verified":False,
                    "smpte_bv21_certified":False,
                    "production_accepted":False,"ffmpeg_used":False}

    def _get(self,ticket):
        self.native_window()
        with self._lock:
            s=self._state
            if (self._closed or not s or type(ticket) is not str or
                    not secrets.compare_digest(ticket,s["ticket"]) or
                    s["cancelled"] or
                    time.monotonic()-s["created"]>SESSION_SECONDS):
                raise PermissionError("Native finished-film playback session revoked")
            return s

    def _cancelled(self,ticket):
        with self._lock:
            return (self._closed or not self._state or
                    self._state["cancelled"] or
                    self._state["ticket"]!=ticket)

    def _pcm24_window(self,ticket,reel,reel_index,local,count,work,cancel):
        """Read verified real sound essence with a bounded 24-frame cache.

        The first use of each one-second/reel region invokes the approved
        native MXF unwrap; adjacent frames reuse those SAME published PCM24
        samples. No synthetic sound, transcoded source, or complete-reel
        audio is retained. Caller holds _decode_lock and checks MXF identity.
        """
        if (type(local) is not int or type(count) is not int or
                not 0<=local<reel.frames or
                not 1<=count<=4 or local+count>reel.frames):
            raise ValueError("Exact reel-local mastered sound window required")
        segment=(local//PCM_CACHE_FRAMES)*PCM_CACHE_FRAMES
        frames=min(PCM_CACHE_FRAMES,reel.frames-segment)
        key=(ticket,reel_index,segment,frames,reel.sound_sha,reel.sound_stat)
        bytes_per_frame=SAMPLES_PER_FRAME*3*len(reel.channels)
        cache=self._pcm_cache
        if cache is None or cache["key"]!=key:
            run_supervised_codec(self.unwrap,
                ["-f",str(segment),"-d",str(frames),str(reel.sound),"snd"],
                workdir=work,check_cancel=cancel,
                timeout=150+frames*10)
            sound=work/"snd"
            if sound.is_symlink() or not sound.is_file():
                raise PermissionError("Native final DCP sound region missing")
            with wave.open(str(sound),"rb") as wav:
                if (wav.getnchannels()!=len(reel.channels) or
                    wav.getframerate()!=RATE or wav.getsampwidth()!=3 or
                    wav.getcomptype()!="NONE" or
                    wav.getnframes()!=frames*SAMPLES_PER_FRAME):
                    raise PermissionError("Published PCM24 region misaligned")
                pcm=wav.readframes(frames*SAMPLES_PER_FRAME)
            if len(pcm)!=frames*bytes_per_frame:
                raise PermissionError("Incomplete mastered PCM24 source region")
            self._get(ticket)  # Reject revoked playback before caching.
            cache={"key":key,"pcm":pcm}
            self._pcm_cache=cache
        start=(local-segment)*bytes_per_frame
        selected=cache["pcm"][start:start+count*bytes_per_frame]
        if len(selected)!=count*bytes_per_frame:
            raise PermissionError("Published PCM24 selection omitted samples")
        return selected

    def frame(self,ticket,global_frame):
        """Decode exact FINAL published picture/PCM for one 24fps frame.

        Clients may request arbitrary seek positions. Each call is bounded
        and serialized; no complete film, full reel or codec output persists.
        """
        s=self._get(ticket)
        if type(global_frame) is not int:
            raise ValueError("Exact integer output picture frame required")
        reel_index,local=locate_reel(s["reels"],global_frame)
        reel=s["reels"][reel_index]
        expected=_expected_frame_sha(self.journal,reel.job_id,local)
        with self._decode_lock:
            s=self._get(ticket)
            # Native process cancellation checks the same revocable grant.
            cancel=lambda:self._cancelled(ticket)
            for file,stamp in ((reel.picture,reel.picture_stat),
                               (reel.sound,reel.sound_stat)):
                if (not file.is_file() or file.is_symlink() or
                        file.resolve(strict=True).parent!=reel.picture.parent or
                        _fingerprint(file)!=stamp):
                    raise PermissionError("Final delivered MXF changed during viewing")
            # Every MXF asset was SHA-256 hashed at admission and is now
            # stat-pinned; picture codestream is SHA-verified per frame.
            # Never rehash 5-minute multi-GB tracks at 24fps: that would
            # make sustained playback impossible. A hostile same-size,
            # forged-mtime modification requires protected file ownership
            # or per-chunk authenticated PCM hashes in a later release.
            with TemporaryDirectory(prefix="nvp-finished-window-",dir=self.root) as tmp:
                work=Path(tmp)
                args=["-f",str(local),"-d","1","-b",str(MAX_J2K_BYTES),
                      str(reel.picture),"p_"]
                run_supervised_codec(self.unwrap,args,workdir=work,
                                     timeout=120,check_cancel=cancel)
                path=work/("p_"+f"{local:06d}"+".j2c")
                if (not path.is_file() or path.is_symlink() or
                        not 80<=path.stat().st_size<=MAX_J2K_BYTES):
                    raise PermissionError("Published MXF did not yield exact J2K")
                j2k=path.read_bytes()
                if sha256(j2k).hexdigest()!=expected:
                    raise PermissionError("Decoded FINAL MXF J2K differs from approved source")
                inspect_j2k_header(j2k,s["profile"])
                run_supervised_codec(self.decoder,
                                     ["-i",path.name,"-o","actual.ppm"],
                                     workdir=work,timeout=180,check_cancel=cancel)
                pixels=_ppm_header(work/"actual.ppm",
                                   width=PROFILES[s["profile"]][0],
                                   height=PROFILES[s["profile"]][1])
                png,(width,height)=_display_png(pixels,s["profile"])
                pcm24=self._pcm24_window(
                    ticket,reel,reel_index,local,1,work,cancel)
                audio=_stereo_pcm16(pcm24,reel.channels)
            self._get(ticket)
            return {
                "format":FORMAT,"status":"DECODED_PUBLISHED_FINAL_FRAME",
                "frame_index":global_frame,"reel_index":reel_index,
                "reel_frame_index":local,
                "picture_24fps_film_time_tick":global_frame*FRAME_TICKS,
                "audio_start_sample":global_frame*SAMPLES_PER_FRAME,
                "audio_samples":SAMPLES_PER_FRAME,
                "picture_png_base64":base64.b64encode(png).decode("ascii"),
                "picture_width":width,"picture_height":height,
                "stereo_pcm16_base64":base64.b64encode(audio).decode("ascii"),
                "source_j2k_sha256":expected,
                "picture_and_sound_from_final_published_mxf":True,
                "screen_display_calibrated":False,
                "original_multichannel_master_preserved":True,
                "finished_film_complete_viewing_verified":False,
                "production_accepted":False,
            }


    def window(self,ticket,first_frame,count=4):
        """Bounded final-MXF essence batch, clipped at one reel boundary.

        Reuses ONE native picture unwrap, ONE sound unwrap and at most four
        pinned OpenJPEG decodes, not three native process launches for every
        single frame. Never crosses a CPL reel without reauthorizing the
        next pinned track at its own exact local source position.
        """
        s=self._get(ticket)
        if (type(first_frame) is not int or type(count) is not int or
                not 1<=count<=4):
            raise ValueError("Bounded exact finished DCP picture/sound window required")
        reel_index,local=locate_reel(s["reels"],first_frame)
        reel=s["reels"][reel_index]
        count=min(count,reel.frames-local)
        if count<1:
            raise PermissionError("Finished DCP window is empty")
        expected=[_expected_frame_sha(self.journal,reel.job_id,local+n)
                  for n in range(count)]
        with self._decode_lock:
            self._get(ticket)
            cancel=lambda:self._cancelled(ticket)
            for file,stamp in ((reel.picture,reel.picture_stat),
                               (reel.sound,reel.sound_stat)):
                if (not file.is_file() or file.is_symlink() or
                        file.resolve(strict=True).parent!=reel.picture.parent or
                        _fingerprint(file)!=stamp):
                    raise PermissionError("Published final MXF changed before playback batch")
            with TemporaryDirectory(prefix="nvp-finished-batch-",dir=self.root) as temp:
                work=Path(temp)
                run_supervised_codec(self.unwrap,
                    ["-f",str(local),"-d",str(count),
                     "-b",str(MAX_J2K_BYTES),str(reel.picture),"p_"],
                    workdir=work,check_cancel=cancel,
                    timeout=150+count*25)
                pcm=self._pcm24_window(
                    ticket,reel,reel_index,local,count,work,cancel)
                bytes_per_picture_sound=SAMPLES_PER_FRAME*3*len(reel.channels)
                # The published J2K codestreams and PCM window have already
                # been independently SHA-verified. Separate read-only native
                # OpenJPEG workers can decode at most four different pictures
                # concurrently; output order remains exact Film Time order.
                # Each codec subprocess still owns its own supervised
                # Windows Job Object/Linux process group and cancellation.
                def decode_one_published_picture(n):
                    local_frame=local+n
                    file=work/("p_"+f"{local_frame:06d}"+".j2c")
                    if (file.is_symlink() or not file.is_file() or
                            not 80<=file.stat().st_size<=MAX_J2K_BYTES):
                        raise PermissionError("Published picture batch omitted a frame")
                    raw=file.read_bytes()
                    if sha256(raw).hexdigest()!=expected[n]:
                        raise PermissionError("Published J2K batch differs from FilmIndex")
                    inspect_j2k_header(raw,s["profile"])
                    dest="actual_"+f"{local_frame:06d}"+".ppm"
                    run_supervised_codec(self.decoder,
                        ["-i",file.name,"-o",dest],
                        workdir=work,check_cancel=cancel,timeout=180)
                    pixels=_ppm_header(work/dest,
                        width=PROFILES[s["profile"]][0],
                        height=PROFILES[s["profile"]][1])
                    png,(width,height)=_display_png(pixels,s["profile"])
                    audio=_stereo_pcm16(pcm[
                        n*bytes_per_picture_sound:
                        (n+1)*bytes_per_picture_sound],reel.channels)
                    frame_index=first_frame+n
                    result={
                        "format":FORMAT,
                        "status":"DECODED_PUBLISHED_FINAL_FRAME",
                        "frame_index":frame_index,
                        "reel_index":reel_index,
                        "reel_frame_index":local_frame,
                        "picture_24fps_film_time_tick":frame_index*FRAME_TICKS,
                        "audio_start_sample":frame_index*SAMPLES_PER_FRAME,
                        "audio_samples":SAMPLES_PER_FRAME,
                        "picture_png_base64":base64.b64encode(png).decode("ascii"),
                        "picture_width":width,"picture_height":height,
                        "stereo_pcm16_base64":base64.b64encode(audio).decode("ascii"),
                        "source_j2k_sha256":expected[n],
                        "picture_and_sound_from_final_published_mxf":True,
                        "screen_display_calibrated":False,
                        "original_multichannel_master_preserved":True,
                        "finished_film_complete_viewing_verified":False,
                        "production_accepted":False,
                    }
                    file.unlink()
                    (work/dest).unlink()
                    return result
                with ThreadPoolExecutor(max_workers=min(4,count)) as pool:
                    results=list(pool.map(
                        decode_one_published_picture,range(count)))
                self._get(ticket)
                return {
                    "format":FORMAT,
                    "status":"DECODED_PUBLISHED_FINAL_WINDOW",
                    "start_frame":first_frame,
                    "frame_count":count,
                    "reel_index":reel_index,
                    "frames":results,
                    "no_reel_crossing":True,
                    "whole_film_in_memory":False,
                    "production_accepted":False,
                    "ffmpeg_used":False,
                }

    def stop(self,ticket):
        self.native_window()
        with self._lock:
            s=self._get(ticket)
            s["cancelled"]=True
            self._state=None
            self._pcm_cache=None
        return {"format":FORMAT,"status":"STOPPED",
                "production_accepted":False}

    def close(self):
        with self._lock:
            self._closed=True
            self._pcm_cache=None
            if self._state:
                self._state["cancelled"]=True
                self._state=None
