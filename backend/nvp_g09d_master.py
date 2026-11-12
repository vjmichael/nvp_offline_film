"""G09-D native finishing DSP and honest color management.

A full SOURCE-MIX based BS.1770 K-weighted, gated integrated loudness
measurement underlies signed 16-bit 48kHz derived sound. Gain is constrained
by measured SAMPLE peak, never called certified dBTP. Silence is preserved.
Source PCM and original performance USD remain untouched.

Picture finishing operates on the real display-referred 8-bit G08 preview
render. It applies an explicit sRGB SDR finishing transform; it does not
pretend that an 8-bit display-referred JPEG contains recoverable HDR values
or can be treated as ACES scene-linear/OCIO output.
"""
from __future__ import annotations
from array import array
from io import BytesIO
import hashlib
import math
import struct
import sys

from PIL import Image,ImageEnhance

RATE=48000
CHANNELS=2
MAX_SECONDS=30
CHUNK=2000
PCM_FRAME_BYTES=4
# ITU-R BS.1770 48kHz reference K-weighting biquads.
HIGH_B=(1.53512485958697,-2.69169618940638,1.19839281085285)
HIGH_A=(1.,-1.69065929318241,.73248077421585)
PASS_B=(1.,-2.,1.)
PASS_A=(1.,-1.99004745483398,.99007225036621)


def _biquad(value,b,a,state):
    x1,x2,y1,y2=state
    y=b[0]*value+b[1]*x1+b[2]*x2-a[1]*y1-a[2]*y2
    state[:]=[value,x1,y,y1]
    return y


def _samples(raw):
    if type(raw) is not bytes or len(raw)%4 or len(raw)>MAX_SECONDS*RATE*4:
        raise ValueError("Original film mix must be bounded 48 kHz PCM stereo")
    pcm=array("h");pcm.frombytes(raw)
    if sys.byteorder!="little":pcm.byteswap()
    return pcm


def _integrated_loudness(pcm):
    count=len(pcm)//2
    if not count:return None
    # Entire programme is filtered, then 400ms / 100ms overlapping,
    # energy-gated as BS.1770 / EBU R128. Stereo channels weigh 1.0.
    states=[[0.,0.,0.,0.] for _ in range(4)]
    energies=array("d")
    for frame in range(count):
        power=0.
        for ch in (0,1):
            value=pcm[frame*2+ch]/32768.
            shelf=_biquad(value,HIGH_B,HIGH_A,states[ch*2])
            high=_biquad(shelf,PASS_B,PASS_A,states[ch*2+1])
            power+=high*high
        energies.append(power)
    window=RATE*4//10
    hop=RATE//10
    # For short movies a partially silent padded 400ms gate is still a
    # measurable programme, never an invented numerical LUFS on silence.
    if count<window:
        energies.extend([0.]*(window-count))
        count=window
    prefix=array("d",[0.])
    running=0.
    for item in energies:
        running+=item
        prefix.append(running)
    blocks=[]
    for start in range(0,count-window+1,hop):
        energy=(prefix[start+window]-prefix[start])/window
        if energy>0:
            level=-.691+10*math.log10(energy)
            if level>-70:blocks.append(energy)
    if not blocks:return None
    ungated=sum(blocks)/len(blocks)
    relative=-.691+10*math.log10(ungated)-10
    limit=10**((max(-70.,relative)+.691)/10)
    accepted=[v for v in blocks if v>=limit]
    if not accepted:return None
    return round(-.691+10*math.log10(sum(accepted)/len(accepted)),3)


def analyze_pcm(raw):
    samples=_samples(raw)
    loudness=_integrated_loudness(samples)
    peak=max((abs(v) for v in samples),default=0)
    return {"sample_rate":RATE,"channels":CHANNELS,
        "sample_count":len(samples)//2,
        "integrated_lufs":loudness,
        "sample_peak_dbfs":(
            round(20*math.log10(peak/32768.),3) if peak else None),
        "sample_peak_abs":peak,
        "measurement":"BS.1770 K-weighted gated integrated loudness, 48k stereo",
        "true_peak_measured":False,
        "professional_broadcast_certified":False}


def master_sound(original_raw,audio_settings,*,intent="working"):
    """Return (derived bytes, evidence) without mutating source or gain claims."""
    source=_samples(original_raw)
    if len(source)<2:raise ValueError("There is no film sound sample window")
    original=analyze_pcm(original_raw)
    sample_count=len(source)//2
    target=audio_settings["target_lufs"]
    ceiling=audio_settings["peak_ceiling_dbfs"]
    maximum=32767.*10**(ceiling/20)
    peak=original["sample_peak_abs"]
    loudness=original["integrated_lufs"]
    required_gain=(10**((target-loudness)/20)
                   if loudness is not None else 1.)
    # Never silently boost more than 12 dB or obliterate original dynamics.
    required_gain=min(required_gain,10**(12/20))
    max_gain=(maximum/peak if peak else 1.)
    gain=min(required_gain,max_gain)
    if not math.isfinite(gain) or gain<0:
        raise RuntimeError("The film sound cannot be mastered safely")
    fade_in=round(audio_settings["fade_in_seconds"]*RATE)
    fade_out=round(audio_settings["fade_out_seconds"]*RATE)
    if fade_in+fade_out>sample_count:
        raise ValueError("The requested sound fades overlap the original film")
    output=array("h")
    for frame in range(sample_count):
        envelope=1.
        if fade_in:
            envelope=min(envelope,frame/fade_in)
        if fade_out:
            envelope=min(envelope,(sample_count-1-frame)/fade_out)
        envelope=max(0.,envelope)
        for ch in (0,1):
            value=round(source[frame*2+ch]*gain*envelope)
            output.append(int(max(-32768,min(32767,value))))
    if sys.byteorder!="little":output.byteswap()
    derived=output.tobytes()
    after=analyze_pcm(derived)
    # A derived SDR review may be delivered at a lower-than-target level,
    # but must not present a false measured target or silent-clipping pass.
    deviation=(abs(after["integrated_lufs"]-target)
               if after["integrated_lufs"] is not None else None)
    is_review=(intent!="working")
    if is_review and (deviation is None or deviation>1.):
        raise RuntimeError(
            "This recording cannot meet the reviewed loudness target and "
            "safe peak ceiling together; adjust the target or edit the source.")
    if after["sample_peak_abs"]>maximum+1:
        raise RuntimeError("Mastered audio exceeds its selected peak ceiling")
    return derived,{"format":"nvp.g09d.native_pcm_master_receipt.v1",
        "original_mix_sha256":hashlib.sha256(original_raw).hexdigest(),
        "derived_master_sha256":hashlib.sha256(derived).hexdigest(),
        "original_sound_unchanged":True,
        "target_integrated_lufs":target,
        "measured_integrated_lufs":after["integrated_lufs"],
        "measured_sample_peak_dbfs":after["sample_peak_dbfs"],
        "max_sample_peak_dbfs":ceiling,
        "target_loudness_reached":deviation is not None and deviation<=1.,
        "source_integrated_lufs":loudness,
        "gain_db":round(20*math.log10(gain),3) if gain>0 else None,
        "fade_in_seconds":audio_settings["fade_in_seconds"],
        "fade_out_seconds":audio_settings["fade_out_seconds"],
        "sample_count":sample_count,
        "true_peak_measured":False,"dcp_cinema_audio_compliant":False,
        "pcm_format":"stereo_48000_s16le"}


def _srgb_lut(exposure,lift,warmth):
    import math
    a=2**exposure
    def convert(value,mult):
        u=value/255.
        linear=u/12.92 if u<=.04045 else ((u+.055)/1.055)**2.4
        linear=max(0.,linear*a*mult+lift)
        encoded=(12.92*linear if linear<=.0031308
                 else 1.055*linear**(1/2.4)-.055)
        return round(max(0.,min(1.,encoded))*255)
    return (
        [convert(x,1+warmth*.35) for x in range(256)],
        [convert(x,1.) for x in range(256)],
        [convert(x,1-warmth*.35) for x in range(256)]
    )


def finish_picture(jpeg,color_settings):
    """Real display-referred 8-bit sRGB finishing, no spurious HDR claim."""
    if type(jpeg) is not bytes or not jpeg.startswith(b"\xff\xd8"):
        raise ValueError("Filmed picture must be an independently rendered JPEG")
    with Image.open(BytesIO(jpeg)) as source:
        if source.format!="JPEG" or source.size!=(640,360):
            raise RuntimeError("Finishing received a different cinema picture profile")
        img=source.convert("RGB")
    if (color_settings["exposure"]==0 and
        color_settings["contrast"]==1 and
        color_settings["saturation"]==1 and
        color_settings["lift"]==0 and
        color_settings["warmth"]==0):
        return jpeg,{"color_edited":False,"input_color":"sRGB_8bit",
                     "output_color":"sRGB_8bit","aces_transform_applied":False}
    r,g,b=img.split()
    rl,gl,bl=_srgb_lut(color_settings["exposure"],
                       color_settings["lift"],color_settings["warmth"])
    img=Image.merge("RGB",(r.point(rl),g.point(gl),b.point(bl)))
    if color_settings["contrast"]!=1:
        img=ImageEnhance.Contrast(img).enhance(color_settings["contrast"])
    if color_settings["saturation"]!=1:
        img=ImageEnhance.Color(img).enhance(color_settings["saturation"])
    sink=BytesIO()
    img.save(sink,format="JPEG",quality=91,subsampling=0,
             optimize=False)
    return sink.getvalue(),{"color_edited":True,
        "input_color":"sRGB_8bit","output_color":"sRGB_8bit",
        "aces_transform_applied":False}



def verify_completed_movie_sound(movie_bytes,finished=None):
    """Measure ACTUAL delivered AVI PCM; never trust a render-worker claim.

    Caller must first run the existing fully independent G08 movie verifier,
    which decodes every MJPEG frame and validates the RIFF index. This
    extracts only the audio chunks of that already-verified exact byte stream.
    """
    from backend.nvp_g08_native_avi import MAX_OUTPUT_BYTES
    if (type(movie_bytes) is not bytes or
        not 0<len(movie_bytes)<=MAX_OUTPUT_BYTES):
        raise ValueError("Finished source movie is invalid")
    start=movie_bytes.find(b"movi")
    end=movie_bytes.rfind(b"idx1")
    if start<0 or end<=start:
        raise RuntimeError("The final movie contains no audio-bearing film media")
    at=start+4
    result=bytearray()
    count=0
    while at<end:
        if at+8>end:raise RuntimeError("A sound chunk was truncated")
        kind=movie_bytes[at:at+4]
        size=struct.unpack_from("<I",movie_bytes,at+4)[0]
        stop=at+8+size
        if stop>end:raise RuntimeError("AVI sound chunk extends beyond the verified movie")
        if kind==b"01wb":
            if size!=8000:
                raise RuntimeError("Finished source sound lost its 24fps/48k alignment")
            result.extend(movie_bytes[at+8:stop]);count+=1
        elif kind!=b"00dc":
            raise RuntimeError("Unexpected native movie stream")
        at=stop+(size&1)
    if at!=end or not count or len(result)!=count*8000:
        raise RuntimeError("The verified movie sound is not contiguous")
    raw=bytes(result)
    measured=analyze_pcm(raw)
    ceiling=None;deviation=None;accepted=None
    if finished is not None:
        settings=finished["finishing"]["audio"]
        intent=finished["finishing"]["finishing_intent"]
        ceiling=settings["peak_ceiling_dbfs"]
        measured_peak=measured["sample_peak_dbfs"]
        if measured_peak is not None and measured_peak>ceiling+.01:
            raise RuntimeError("The completed sound exceeded its selected peak ceiling")
        observed=measured["integrated_lufs"]
        deviation=(abs(observed-settings["target_lufs"])
                   if observed is not None else None)
        accepted=deviation is not None and deviation<=1.
        if intent!="working" and not accepted:
            raise RuntimeError("This finished movie does not meet its reviewed loudness target")
    return {
        "format":"nvp.g09d.independent_sound_readback.v1",
        "rendered_pcm_sha256":sha256(raw).hexdigest(),
        "sample_count":measured["sample_count"],
        "integrated_lufs":measured["integrated_lufs"],
        "sample_peak_dbfs":measured["sample_peak_dbfs"],
        "approved_peak_ceiling_dbfs":ceiling,
        "approved_review_loudness_met":accepted,
        "original_recordings_preserved":True,
        "verified_pcm_in_real_avi":True,
        "true_peak_or_cinema_audio_certified":False}
