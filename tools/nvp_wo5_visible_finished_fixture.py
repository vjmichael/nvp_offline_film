"""WO5 installed visible WebView2 proof fixture, NOT a production FilmIndex feature.

This CI-only bridge predecodes an ACTUAL finished SMPTE DCP's MXF tracks
with the installed hash-pinned native CineCert/OpenJPEG toolchain, then
offers a bounded immutable packet cache to NVP's unmodified real React
FinishedFilmPlaybackPanel over real pywebview IPC. The real WebAudio
device clock and Canvas presentation run in a visible installed NVP.exe.
It avoids masking an underpowered decoder as a failed audio clock; native
decoder sustained throughput is measured separately.

The fixture intentionally has no original authoring Take lineage and is
not a director-authorized FilmIndex feature. NEVER expose it from the
ordinary installed application or mark cinema/creative approval.
"""
from __future__ import annotations
import base64
from hashlib import sha256
from pathlib import Path
import secrets
from tempfile import TemporaryDirectory
import wave

from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo3_j2k_audit import PROFILES, inspect_j2k_header
from backend.nvp_wo3_native_codecs import digest_file
from backend.nvp_wo3_independent_essence import _ppm_header
from backend.nvp_wo4_feature_journal import FRAME_TICKS
from backend.nvp_wo5_finished_playback import (
    _display_png, _stereo_pcm16, _fingerprint, FORMAT, MAX_J2K_BYTES,
    SAMPLES_PER_FRAME, RATE)
from backend.nvp_supervised_codec_process import run_supervised_codec

CI_FORMAT="nvp.wo5.ci_installed_real_final_mxf_visible_av.v1"
CI_FEATURE="NVP_WO5_REAL_PUBLISHED_MXF_CI_ONLY"
CI_SESSION="NVP_WO5_CI_ACTUAL_DCP_DISPLAY"
MIN_CI_FRAMES=24
# Reopen at most one genuine second of published MXF essence per codec
# invocation; four-frame launch churn caused 180 repeated native process pairs
# for a 720-frame rehearsal. This stays disk-bounded and preserves ALL frames.
MAX_UNWRAP_FRAMES=24

class InstalledPublishedDCPFixture:
    """Bounded native rehearsal cache: every frame read from final MXF."""

    def __init__(self,root,codec_provider,*,max_frames=720,progress=None):
        if not callable(codec_provider):
            raise RuntimeError("Release-pinned installed decoder not available")
        if progress is not None and not callable(progress):
            raise TypeError("Native progress observer must be host-supplied")
        self.progress=progress
        self.unwrap,self.decode=codec_provider()
        self.root=Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise PermissionError("Test-only DCP requires exact local path")
        self.audit=inspect_dcp_structure(self.root)
        if self.audit["status"]!="STRUCTURE_AND_SHA_VERIFIED":
            raise PermissionError("Real finished DCP SHA audit failed")
        if self.audit["reel_count"]<2:
            raise PermissionError("Visible CI requires two actual SMPTE reels")
        self.profile="2K_FLAT_24"
        tracks=self.audit["tracks"]
        if len(tracks)!=self.audit["reel_count"]*2:
            raise PermissionError("Real published picture and sound required")
        self.reels=[]
        cursor=0
        for i,frames in enumerate(self.audit["reel_durations"]):
            kinds={t["kind"]:t for t in tracks[2*i:2*i+2]}
            if set(kinds)!={"picture","sound"}:
                raise PermissionError("Native SMPTE reel track type missing")
            image=self.root/kinds["picture"]["filename"]
            sound=self.root/kinds["sound"]["filename"]
            for asset in (image,sound):
                if asset.is_symlink() or asset.resolve(strict=True).parent!=(
                        self.root.resolve(strict=True)):
                    raise PermissionError("Published track outside verified final DCP")
            self.reels.append({
                "first":cursor,"frames":frames,"picture":image,"sound":sound,
                "picture_sha":digest_file(image),"sound_sha":digest_file(sound),
                "picture_stat":_fingerprint(image),
                "sound_stat":_fingerprint(sound),
            })
            cursor+=frames
        self.total=cursor
        if (not MIN_CI_FRAMES<=self.total<=max_frames or
                not self.total%24==0):
            raise PermissionError("Test must have real 24fps, >=1s published DCP")
        self.frames=[None]*self.total
        self._picture_cache={}
        self._granted=None
        self.decode_calls=0
        self.picture_unique_hashes=set()
        self._prepared=False

    def _checked_asset(self,reel):
        for kind in ("picture","sound"):
            asset=reel[kind]
            if (asset.is_symlink() or not asset.is_file() or
                    _fingerprint(asset)!=reel[kind+"_stat"] or
                    digest_file(asset)!=reel[kind+"_sha"]):
                raise PermissionError("Final SMPTE DCP track modified during native rehearsal")

    def prepare(self):
        """Pre-roll EXACT real MXF frames using bounded <=24-frame native unwrap workers.

        This is cache-ahead playback acceptance, NOT native decode throughput.
        A repeated-source 30s fixture has only six unique codestreams;
        it cannot represent a unique-frame feature film.
        """
        if self._prepared:
            raise PermissionError("Fixture decoder preparation is one-shot")
        for ri,reel in enumerate(self.reels):
            self._checked_asset(reel)
            for local in range(0,reel["frames"],MAX_UNWRAP_FRAMES):
                count=min(MAX_UNWRAP_FRAMES,reel["frames"]-local)
                if self.progress is not None:
                    self.progress(ri,local,count,self.total)
                with TemporaryDirectory(prefix="nvp-real-visible-mxf-") as temp:
                    work=Path(temp)
                    run_supervised_codec(self.unwrap,
                        ["-f",str(local),"-d",str(count),
                         "-b",str(MAX_J2K_BYTES),str(reel["picture"]),"p_"],
                        workdir=work,check_cancel=lambda:False,timeout=240)
                    run_supervised_codec(self.unwrap,
                        ["-f",str(local),"-d",str(count),
                         str(reel["sound"]),"snd"],
                        workdir=work,check_cancel=lambda:False,timeout=240)
                    with wave.open(str(work/"snd"),"rb") as wav:
                        if (wav.getframerate()!=RATE or
                            wav.getnchannels()!=2 or
                            wav.getsampwidth()!=3 or
                            wav.getnframes()!=count*SAMPLES_PER_FRAME):
                            raise PermissionError("Final mastered PCM24 has incorrect clock/sample count")
                        sound=wav.readframes(count*SAMPLES_PER_FRAME)
                    if len(sound)!=count*SAMPLES_PER_FRAME*6:
                        raise PermissionError("Native final sound sample window incomplete")
                    for n in range(count):
                        file=work/f"p_{local+n:06d}.j2c"
                        if (file.is_symlink() or not file.is_file() or
                                file.stat().st_size>MAX_J2K_BYTES):
                            raise PermissionError("Native finished picture frame missing")
                        j2k=file.read_bytes()
                        digest=sha256(j2k).hexdigest()
                        inspect_j2k_header(j2k,self.profile)
                        if digest not in self._picture_cache:
                            dest=f"review_{local+n:06d}.ppm"
                            run_supervised_codec(self.decode,
                                ["-i",file.name,"-o",dest],
                                workdir=work,check_cancel=lambda:False,timeout=240)
                            rgb=_ppm_header(work/dest,
                                width=PROFILES[self.profile][0],
                                height=PROFILES[self.profile][1])
                            preview,(width,height)=_display_png(rgb,self.profile)
                            self._picture_cache[digest]=(
                                base64.b64encode(preview).decode("ascii"),
                                width,height)
                            self.decode_calls+=1
                        picture,w,h=self._picture_cache[digest]
                        self.picture_unique_hashes.add(digest)
                        part=sound[n*SAMPLES_PER_FRAME*6:
                                   (n+1)*SAMPLES_PER_FRAME*6]
                        stereo=_stereo_pcm16(part,("L","R"))
                        absolute=reel["first"]+local+n
                        self.frames[absolute]={
                            "format":FORMAT,
                            "status":"DECODED_PUBLISHED_FINAL_FRAME",
                            "frame_index":absolute,
                            "reel_index":ri,
                            "reel_frame_index":local+n,
                            "picture_24fps_film_time_tick":absolute*FRAME_TICKS,
                            "audio_start_sample":absolute*SAMPLES_PER_FRAME,
                            "audio_samples":SAMPLES_PER_FRAME,
                            "picture_png_base64":picture,
                            "picture_width":w,"picture_height":h,
                            "stereo_pcm16_base64":base64.b64encode(stereo).decode("ascii"),
                            "source_j2k_sha256":digest,
                            "picture_and_sound_from_final_published_mxf":True,
                            "screen_display_calibrated":False,
                            "original_multichannel_master_preserved":True,
                            "finished_film_complete_viewing_verified":False,
                            "production_accepted":False,
                        }
            self._checked_asset(reel)
        if any(f is None for f in self.frames):
            raise RuntimeError("Published DCP pictures/audio incomplete")
        self._prepared=True
        return {
            "format":CI_FORMAT,"source":"REAL_PUBLISHED_DCP_PICTURE_AND_SOUND_MXF",
            "frames":self.total,"reels":len(self.reels),
            "unique_j2k_codestreams":len(self.picture_unique_hashes),
            "native_openjpeg_decodes":self.decode_calls,
            "all_sound_windows_from_final_pcm24":True,
            "cache_decoded_before_webview_play":True,
            "uninterrupted_playback_verified":False,
            "native_decode_sustained_24fps_verified":False,
            "director_creative_approval":False,
        }

    def begin(self,project_id,feature_id,approved_project_id):
        if not self._prepared or project_id!=approved_project_id or feature_id!=CI_FEATURE:
            raise PermissionError("Only this installed CI published DCP rehearsal")
        if self._granted:
            raise PermissionError("One native finished-film presentation session")
        self._granted=secrets.token_urlsafe(24)
        return {
            "format":FORMAT,"status":"FINISHED_DCP_READONLY_READY",
            "session_id":self._granted,"fps":24,"sound_rate":RATE,
            "sound_samples_per_frame":SAMPLES_PER_FRAME,
            "frame_count":self.total,
            "native_picture_and_sound_from_published_mxf":True,
            "continuous_real_time_playback_verified":False,
            "original_scene_custody_verified":False,
            "installed_ci_fixture_cache_ahead":True,
            "production_accepted":False,
        }

    def window(self,session,first,count):
        if not self._granted or session!=self._granted:
            raise PermissionError("No admitted native finished-film test session")
        if (type(first) is not int or type(count) is not int or
                not 0<=first<self.total or not 1<=count<=4):
            raise ValueError("Exact bounded native finished-film fixture window")
        ri=next((i for i,r in enumerate(self.reels)
                 if r["first"]<=first<r["first"]+r["frames"]),None)
        if ri is None:raise PermissionError("Reel not indexed in published DCP")
        reel=self.reels[ri]
        count=min(count,reel["first"]+reel["frames"]-first)
        return {
            "format":FORMAT,"status":"DECODED_PUBLISHED_FINAL_WINDOW",
            "start_frame":first,"frame_count":count,
            "frames":self.frames[first:first+count],
            "reel_index":ri,"no_reel_crossing":True,
            "whole_film_in_memory":True,  # CI rehearsal only; NOT a production decoder
            "native_decoded_before_play":True,
            "production_accepted":False,"ffmpeg_used":False,
        }

    def stop(self,ticket):
        if not self._granted or ticket!=self._granted:
            raise PermissionError("Native CI session already revoked")
        self._granted=None
        return {"status":"STOPPED","source_modified":False}

    def close(self):
        self._granted=None
        self.frames=[]
        self._picture_cache.clear()
