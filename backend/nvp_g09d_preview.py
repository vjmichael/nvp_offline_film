"""G09-D disposable finishing audition from authoritative original movie data.

Neither still nor sound window is stored as a new Take/master. The preview
opens source USD/PCM in the same unlocked host, then evaluates the CURRENT
director draft at the requested exact Film Time. Preview cannot certify an
OCIO/ACES or cinema deliverable.
"""
from __future__ import annotations
from io import BytesIO
import wave
from backend.nvp_g07_edit import _sec
from backend.nvp_g08_native_avi import (
    TICKS_FRAME,TICKS_SAMPLE,render_picture,_audio_frame)
from backend.nvp_g09d_finishing import G09DFinishing
from backend.nvp_g09d_master import finish_picture,master_sound
from backend.nvp_g09c_playback import _worlds
from backend.nvp_g09c_native_audio import SpatialFilmMixer

MAX_AUDITION_SECONDS=4

def _material(editor,pid):
    finishing=G09DFinishing(editor.filming.g05.g04.studio,
        editor.filming.g05.g04.live,
        editor.filming.g05.g04.token)
    # Avoid deriving identity from caller-controlled HTTP params.
    review=finishing.view(pid)
    if review["source_changed"]:
        raise RuntimeError("Finishing refers to an older film; update it before audition")
    assembly=editor.native_assembly(pid,review["current_film_source"]["edit_revision"])
    return review["draft"],assembly

def preview_picture(editor,pid,seconds="0"):
    decision,assembly=_material(editor,pid)
    tick=_sec(seconds)
    if tick>=assembly["duration_tick"]:
        raise ValueError("Choose a point inside the saved movie")
    # The picture's frame clock remains 24fps even when the director
    # enters arbitrary original Film Time on the preview playhead.
    tick=(tick//TICKS_FRAME)*TICKS_FRAME
    worlds=_worlds(assembly,actors=True)
    if assembly.get("production_looks") or assembly.get("actor_performances"):
        from backend.nvp_g09_render import render_production_picture
        jpeg=render_production_picture(assembly,worlds,tick)
    else:jpeg=render_picture(assembly,worlds,tick)
    finished,receipt=finish_picture(jpeg,decision["color"])
    return finished

def preview_sound(editor,pid,at_seconds="0",duration_seconds="3"):
    decision,assembly=_material(editor,pid)
    from backend.nvp_g07_edit import _sec
    start=_sec(at_seconds);duration=_sec(duration_seconds,limit=MAX_AUDITION_SECONDS)
    if (duration<=0 or duration>4*7056000000 or
        start%TICKS_SAMPLE or duration%TICKS_SAMPLE or
        start>=assembly["duration_tick"]):
        raise ValueError("Listen to a short sound moment from the saved movie")
    # Full programme loudness normalization must be based on the ACTUAL
    # whole G07 source soundtrack, never on a three-second excerpt.
    original=bytearray()
    sources=assembly["original_takes"]
    if assembly.get("acoustic_looks"):
        mixer=SpatialFilmMixer(assembly,_worlds(assembly))
    else:mixer=None
    count=(assembly["duration_tick"]+TICKS_SAMPLE-1)//TICKS_SAMPLE
    for sample in range(0,count,48000):
        n=min(48000,count-sample)
        original.extend(
            mixer.window(sample,n)[0] if mixer else
            _audio_frame(assembly,sources,sample,n))
    finished,receipt=master_sound(bytes(original),decision["audio"],
        intent=decision["finishing_intent"])
    first=start//TICKS_SAMPLE
    last=min(count,first+duration//TICKS_SAMPLE)
    with BytesIO() as memory:
        with wave.open(memory,"wb") as wav:
            wav.setnchannels(2);wav.setsampwidth(2)
            wav.setframerate(48000)
            wav.writeframes(finished[first*4:last*4])
        return memory.getvalue(),receipt
