"""G09-C native-source synchronized picture/audio playback.

Every frame comes from immutable G06 OpenUSD + approved G09/A/B decisions
at the exact G07 film time. Each stereo sound sample comes from verified
G06 original PCM, optionally processed by an approved G09-C acoustic look.
A client may consume 12 images (500ms at 24fps) and 48k samples (1s) per
bounded request, without producing a substitute intermediate source video.
Playback is synced in the WebAudio renderer to the *audio device clock*.
"""
from __future__ import annotations
from base64 import b64encode
from hashlib import sha256
from io import BytesIO
from decimal import Decimal,InvalidOperation
import json
import math
import wave

from backend.nvp_g07_edit import G07Editor,_sec
from backend.nvp_g08_native_avi import (
    FPS,TICKS_FRAME,TICKS_SAMPLE,SourceWorld,render_picture,_audio_frame)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_g09c_native_audio import SpatialFilmMixer

MAX_IMAGE_FRAMES=12
MAX_AUDIO_SAMPLES=48000
MAX_TAKES=60
MAX_SCENES=60

def _assembly(editor,pid,revision):
    # Keep every read guarded by the existing film session access. Even for
    # a changed draft, original source must be reopened and independently
    # checked. No source bytes go to the UI.
    assembly=editor.native_assembly(pid,revision)
    if assembly["edit_revision"]!=revision:
        raise RuntimeError("The film edit changed; reopen the listening room")
    if not assembly["segments"] or assembly["duration_tick"]<=0:
        raise ValueError("Add a recorded Take to start playback")
    if len(assembly["original_takes"])>MAX_TAKES:
        raise ValueError("This playback scene exceeds its source budget")
    return assembly

def _worlds(assembly,*,actors=False):
    worlds={take_id:SourceWorld(original)
            for take_id,original in assembly["original_takes"].items()}
    if actors and assembly.get("actor_performances"):
        from backend.nvp_g09_actor_rig import ActorFrameEvaluator
        for take_id,approved in assembly["actor_performances"].items():
            if take_id not in worlds:
                raise RuntimeError("Actor performance references a missing Take")
            worlds[take_id].actor_frame_evaluator=ActorFrameEvaluator(
                assembly["original_takes"][take_id],approved)
    return worlds

def frames(editor,pid,revision,start_frame,count):
    if (type(revision) is not int or revision<1 or
        type(start_frame) is not int or start_frame<0 or
        type(count) is not int or not 1<=count<=MAX_IMAGE_FRAMES):
        raise ValueError("Choose a bounded picture playback window")
    assembly=_assembly(editor,pid,revision)
    total=(assembly["duration_tick"]+TICKS_FRAME-1)//TICKS_FRAME
    if start_frame>=total:
        raise ValueError("The selected picture begins after the film")
    actual=min(count,total-start_frame)
    worlds=_worlds(assembly,actors=True)
    enhanced=bool(assembly.get("production_looks") or
                  assembly.get("actor_performances"))
    if enhanced:
        from backend.nvp_g09_render import render_production_picture
    output=[]
    for n in range(actual):
        frame=start_frame+n
        tick=min(assembly["duration_tick"]-1,frame*TICKS_FRAME)
        raw=(render_production_picture(assembly,worlds,tick)
             if enhanced else render_picture(assembly,worlds,tick))
        if not raw.startswith(b"\xff\xd8") or not raw.endswith(b"\xff\xd9"):
            raise RuntimeError("Source picture did not evaluate as native JPEG")
        output.append({"frame":frame,"at_tick":tick,
            "picture_base64":b64encode(raw).decode("ascii")})
    return {"format":"nvp.g09c.picture_frames.v1",
        "edit_revision":revision,
        "edit_sha256":assembly["edit_document_sha256"],
        "actor_sha256":assembly["actor_performances_sha256"],
        "look_sha256":assembly["production_looks_sha256"],
        "fps":FPS,"start_frame":start_frame,"frames":output,
        "total_frames":total,
        "original_source_preserved":True,
        "picture_is_source_evaluated":True}

def sound(editor,pid,revision,start_sample,count):
    if (type(revision) is not int or revision<1 or
        type(start_sample) is not int or start_sample<0 or
        type(count) is not int or not 1<=count<=MAX_AUDIO_SAMPLES):
        raise ValueError("Choose at most one second of original-source sound")
    assembly=_assembly(editor,pid,revision)
    if start_sample*TICKS_SAMPLE>=assembly["duration_tick"]:
        raise ValueError("The requested sound begins after the film")
    count=min(count,math.ceil(assembly["duration_tick"]/TICKS_SAMPLE)-start_sample)
    originals=assembly["original_takes"]
    if assembly.get("acoustic_looks"):
        mixer=SpatialFilmMixer(assembly,_worlds(assembly))
        pcm,receipt=mixer.window(start_sample,count)
    else:
        # Preserve the G08 original-source interpretation exactly if no
        # director approved an acoustic/environment processing change.
        pcm=_audio_frame(assembly,originals,start_sample,count)
        receipt={"start_sample":start_sample,"sample_count":count,
            "sample_rate":48000,"output_channels":2,
            "source_pcm_rewritten":False}
    if len(pcm)!=count*4:
        raise RuntimeError("Playback audio and the film clock have diverged")
    stream=BytesIO()
    with wave.open(stream,"wb") as wav:
        wav.setnchannels(2);wav.setsampwidth(2)
        wav.setframerate(48000);wav.writeframes(pcm)
    return stream.getvalue(),{"format":"nvp.g09c.source_audio.v1",
        "edit_revision":revision,
        "source_edit_sha256":assembly["edit_document_sha256"],
        "acoustics_sha256":assembly["acoustic_looks_sha256"],
        **receipt,"native_clock_ticks_per_second":TICKS_PER_SECOND}

def timeline(editor,pid,revision):
    if type(revision) is not int or revision<1:
        raise ValueError("Save an edit to play this film")
    assembly=_assembly(editor,pid,revision)
    total=assembly["duration_tick"]
    return {"format":"nvp.g09c.playback.v1",
        "edit_revision":revision,
        "edit_sha256":assembly["edit_document_sha256"],
        "look_sha256":assembly["production_looks_sha256"],
        "actor_sha256":assembly["actor_performances_sha256"],
        "acoustics_sha256":assembly["acoustic_looks_sha256"],
        "duration_tick":total,
        "duration_seconds":total/TICKS_PER_SECOND,
        "sample_rate":48000,"channels":2,"frames_per_second":24,
        "picture_frames":math.ceil(total/TICKS_FRAME),
        "audio_samples":math.ceil(total/TICKS_SAMPLE),
        "source_originals_preserved":True,
        "uses_audio_device_clock":True,"long_form_playback_accepted":False}
