"""WO5 installed-NVP.exe real external codec/essence throughput probe.

Only invoked from NVP.exe --smoke-finished-playback on an isolated CI-owned
real SMPTE DCP fixture; never an HTTP/JS or authoring endpoint. Reopens real
MXF/JPEG2000/PCM from the installed exe using the *installer's* pinned
decoder+notices. This measures actual native codec throughput and faults,
NOT a complete original film viewed in a WebView/physical cinema.
"""
from __future__ import annotations
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time
import tracemalloc
import wave

from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo3_j2k_audit import inspect_j2k_header, PROFILES
from backend.nvp_wo3_independent_essence import _ppm_header
from backend.nvp_wo3_native_codecs import digest_file
from backend.nvp_supervised_codec_process import run_supervised_codec
from backend.nvp_wo5_finished_playback import _display_png, _stereo_pcm16
from backend.nvp_wo5_codec_binding import desktop_finished_decoder_provider
from backend.nvp_wo4_pcm_master import CHANNEL_LAYOUTS

FORMAT="nvp.wo5.installed_real_codec_sustained_throughput.v1"
FRAME_SAMPLES=2000
MAX_FRAMES_PER_BATCH=4

def run_installed_finished_probe(*,bundle_root,dcp_dir,seconds=20,
                                 min_fps=24):
    if type(seconds) not in (int,float) or not 1<=seconds<=120 or (
            type(min_fps) not in (int,float) or not 1<=min_fps<=120):
        raise ValueError("Explicit bounded installed decoder test duration")
    root=Path(dcp_dir)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise PermissionError("Trusted test-selected published DCP folder required")
    provider=desktop_finished_decoder_provider(bundle_root)
    if not callable(provider):
        raise RuntimeError("Installed NVP executable lacks release-pinned licensed codecs")
    unwrap,decode=provider()
    audit=inspect_dcp_structure(root)
    if (audit["status"]!="STRUCTURE_AND_SHA_VERIFIED" or
            audit["reel_count"]<2):
        raise PermissionError("Actual published two-reel SMPTE DCP sample required")
    tracks=audit["tracks"]
    if len(tracks)!=audit["reel_count"]*2:
        raise PermissionError("Every real reel needs picture and sound")
    root=root.resolve(strict=True)
    profile="2K_FLAT_24"  # Source test fixture is explicitly 2K Flat.
    reels=[]
    for r in range(audit["reel_count"]):
        part={x["kind"]:x for x in tracks[r*2:r*2+2]}
        if set(part)!={"picture","sound"}:
            raise PermissionError("Real final picture/sound sequence missing")
        pic=root/part["picture"]["filename"]
        snd=root/part["sound"]["filename"]
        if (pic.is_symlink() or snd.is_symlink() or
                pic.resolve(strict=True).parent!=root or
                snd.resolve(strict=True).parent!=root):
            raise PermissionError("Published DCP MXF escaped the package")
        reels.append((pic,snd,audit["reel_durations"][r]))
    report={
        "format":FORMAT,
        "status":"IN_PROGRESS_NOT_WATCHED",
        "real_installed_codec_sha256":{
            "unwrap":unwrap.sha256,"openjpeg":decode.sha256},
        "real_smpte_dcp_structure_reopened":True,
        "source_immutable":True,
        "uncalibrated_monitor_preview_only":True,
        "uses_ffmpeg":False,
        "original_30_minute_film_watched":False,
        "external_projection_passed":False,
    }
    tracemalloc.start()
    decoded=0
    bytes_output=0
    start=time.monotonic()
    reel_index=0
    while time.monotonic()-start<seconds:
        pic,snd,nframes=reels[reel_index]
        # The same real six-frame sample is recycled to probe sustained
        # decoder work; this IS NOT a varied original-film acceptance.
        n=min(MAX_FRAMES_PER_BATCH,nframes)
        with tempfile.TemporaryDirectory(prefix="nvp-installed-decoder-") as tmp:
            work=Path(tmp)
            cancel=lambda:False
            run_supervised_codec(unwrap,["-f","0","-d",str(n),
                "-b",str(16*1024*1024),str(pic),"p_"],
                workdir=work,check_cancel=cancel,timeout=240)
            run_supervised_codec(unwrap,["-f","0","-d",str(n),
                str(snd),"snd"],workdir=work,
                check_cancel=cancel,timeout=240)
            with wave.open(str(work/"snd"),"rb") as wav:
                channels=wav.getnchannels()
                if (channels!=2 or wav.getsampwidth()!=3 or
                    wav.getframerate()!=48000 or
                    wav.getnframes()!=n*FRAME_SAMPLES):
                    raise RuntimeError("Real installed sound MXF unwrapped with wrong timing")
                audio=wav.readframes(n*FRAME_SAMPLES)
            if len(audio)!=n*FRAME_SAMPLES*channels*3:
                raise RuntimeError("Native decoded PCM24 samples missing")
            for frame in range(n):
                j2c=work/f"p_{frame:06d}.j2c"
                if j2c.is_symlink() or not j2c.is_file():
                    raise RuntimeError("Missing real published native MXF picture")
                j2k=j2c.read_bytes()
                inspect_j2k_header(j2k,profile)
                out=f"review_{frame:06d}.ppm"
                run_supervised_codec(decode,
                    ["-i",j2c.name,"-o",out],
                    workdir=work,check_cancel=cancel,timeout=240)
                pixels=_ppm_header(work/out,
                    width=PROFILES[profile][0],
                    height=PROFILES[profile][1])
                png,_=_display_png(pixels,profile)
                stereo=_stereo_pcm16(
                    audio[frame*FRAME_SAMPLES*channels*3:
                          (frame+1)*FRAME_SAMPLES*channels*3],
                    CHANNEL_LAYOUTS["stereo"])
                if len(stereo)!=FRAME_SAMPLES*2*2:
                    raise RuntimeError("Real sound monitor output lost samples")
                bytes_output+=len(png)+len(stereo)
                decoded+=1
        reel_index=(reel_index+1)%len(reels)
    elapsed=time.monotonic()-start
    _,peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    fps=decoded/elapsed
    report.update({
        "status":("THROUGHPUT_TARGET_MET_NOT_GUI_ACCEPTED" if
                  fps>=min_fps else "THROUGHPUT_BELOW_TARGET"),
        "repeated_original_sample":True,
        "real_native_picture_and_pcm_windows":decoded,
        "real_codec_elapsed_seconds":round(elapsed,3),
        "picture_decode_frames_per_second":round(fps,3),
        "target_frames_per_second":min_fps,
        "throughput_target_met":fps>=min_fps,
        "decoded_review_bytes":bytes_output,
        "python_tracemalloc_peak_bytes":peak,
        "real_device_av_sync_verified":False,
        "installed_visible_webview_playback_verified":False,
        "production_film_accepted":False,
    })
    return report

def smoke_from_installed_bundle(bundle_root):
    selection=os.environ.get("NVP_WO5_SMOKE_DCP_DIR","")
    if not selection:
        raise RuntimeError("Host must provide genuine published DCP test path")
    report=run_installed_finished_probe(
        bundle_root=bundle_root,dcp_dir=Path(selection),
        seconds=float(os.environ.get("NVP_WO5_SMOKE_SECONDS","20")))
    print("NVP_WO5_INSTALLED_CODEC_EVIDENCE="+
          json.dumps(report,sort_keys=True),flush=True)
    destination=os.environ.get("NVP_WO5_SMOKE_REPORT")
    if destination:
        file=Path(destination)
        if (not file.is_absolute() or file.exists() or file.is_symlink()
                or not file.parent.is_dir()):
            raise PermissionError("Fresh trusted CI-only report path required")
        file.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                        encoding="utf8")
    # Throughput failure is an explicit release blocker, not a green smoke.
    if not report["throughput_target_met"]:
        raise RuntimeError("Installed native decoder below 24fps; see report")
    return 0
