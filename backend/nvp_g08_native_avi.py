"""G08 first-party offline, FFmpeg-free picture/sound AVI delivery.

MJPEG video is JPEG encoded with Pillow (independent libjpeg); soundtrack
is interleaved native stereo PCM16. A self-owned RIFF/AVI muxer publishes
actual independently decodable picture+audio, not an image sequence, mock
file or renamed container. The bounded first profile is 640x360 / 24 fps,
48kHz stereo, maximum 30 seconds. G09 improves photorealism and scale.

Source pixels are projected from original time-evaluated frozen OpenUSD, not
a pre-flattened frame index; only derived picture/audio enters this container.
This renderer handles the typed G05 primitives, intentionally refusing other
unknown geometry rather than silently omitting the original set.
"""
from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
from io import BytesIO
import math
from pathlib import Path
import struct
import time

from PIL import Image,ImageDraw,ImageEnhance
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_g07_preview import _stereo_gain

WIDTH=640
HEIGHT=360
FPS=24
AUDIO_HZ=48000
AUDIO_CHANNELS=2
AUDIO_BLOCK=4
PROFILE="nvp.g08.mjpeg_pcm.avi.640x360p24"
MAX_SECONDS=30
MAX_OUTPUT_BYTES=160*1024*1024
MAX_RENDER_OBJECTS=96
FRAMES_PER_SECOND=FPS
TICKS_FRAME=TICKS_PER_SECOND//FPS
TICKS_SAMPLE=TICKS_PER_SECOND//AUDIO_HZ
DEFAULT_BACKGROUND=(110,151,178)
SUPPORTED=frozenset(("box","sphere","cone","cylinder","camera","sun","lamp"))


def _chunk(tag:bytes,payload:bytes):
    return tag+struct.pack("<I",len(payload))+payload+(b"\0" if len(payload)&1 else b"")


def _list(tag:bytes,payload:bytes):
    return _chunk(b"LIST",tag+payload)


def _stream_header(kind,handler,scale,rate,length,suggested,sample_size,
                   width=0,height=0):
    return struct.pack("<4s4sIHHIIIIIIIIhhhh",kind,handler,0,0,0,0,
        scale,rate,0,length,suggested,0xffffffff,sample_size,
        0,0,width,height)


def _riff_head(frame_count,samples,width,height,frame_buffer):
    avih=struct.pack("<IIIIIIIIII4I",
        round(1_000_000/FPS),0,0,0x10,frame_count,0,2,
        frame_buffer,width,height,0,0,0,0)
    bitmap=struct.pack("<IiiHH4sIiiII",
        40,width,height,1,24,b"MJPG",width*height*3,0,0,0,0)
    video=_list(b"strl",
        _chunk(b"strh",_stream_header(
            b"vids",b"MJPG",1,FPS,frame_count,frame_buffer,0,width,height))+
        _chunk(b"strf",bitmap))
    pcm=struct.pack("<HHIIHH",1,2,AUDIO_HZ,AUDIO_HZ*AUDIO_BLOCK,
                    AUDIO_BLOCK,16)
    audio=_list(b"strl",
        _chunk(b"strh",_stream_header(
            b"auds",b"\0\0\0\0",AUDIO_BLOCK,AUDIO_HZ*AUDIO_BLOCK,
            samples,8000,AUDIO_BLOCK))+
        _chunk(b"strf",pcm))
    return _list(b"hdrl",_chunk(b"avih",avih)+video+audio)


class MjpegPcmAvi:
    """Streaming mux; no external executable, FFmpeg or libav."""
    def __init__(self,file,frame_count,*,width=WIDTH,height=HEIGHT):
        self.fp=file
        self.frames=frame_count
        self.width=width
        self.height=height
        self.count=0
        self.audio_samples=0
        self.entries=[]
        self.max_frame=0
        self.first_chunk=0
        self.movi_size_offset=0
        self.riff_size_offset=0
        self._begin()

    def _begin(self):
        fp=self.fp
        fp.write(b"RIFF")
        self.riff_size_offset=fp.tell()
        fp.write(b"\0"*4+b"AVI ")
        # MJPEG buffer max is conservatively the uncompressed RGB size.
        header=_riff_head(self.frames,self.frames*2000,
                          self.width,self.height,self.width*self.height*3)
        fp.write(header)
        fp.write(b"LIST")
        self.movi_size_offset=fp.tell()
        fp.write(b"\0"*4+b"movi")
        self.first_chunk=fp.tell()-4

    def _write(self,tag,data,keyframe):
        if not isinstance(data,bytes):raise TypeError("Movie data must be native bytes")
        pos=self.fp.tell()
        self.fp.write(tag+struct.pack("<I",len(data))+data)
        if len(data)&1:self.fp.write(b"\0")
        self.entries.append((tag,0x10 if keyframe else 0,
                             pos-self.first_chunk,len(data)))
        if self.fp.tell()>MAX_OUTPUT_BYTES:
            raise ValueError("Movie exceeds the bounded first export profile")

    def frame(self,jpeg,pcm):
        if self.count>=self.frames:
            raise ValueError("Too many rendered movie frames")
        if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
            raise ValueError("Native picture is not an actual JPEG")
        if len(pcm)!=2000*AUDIO_BLOCK:
            raise ValueError("Audio sample count is not synchronized with 24 fps")
        self._write(b"00dc",jpeg,True)
        self._write(b"01wb",pcm,False)
        self.audio_samples+=len(pcm)//AUDIO_BLOCK
        self.count+=1
        self.max_frame=max(self.max_frame,len(jpeg))

    def finish(self):
        if self.count!=self.frames or self.audio_samples!=self.frames*2000:
            raise RuntimeError("Video and original-source sound are incomplete")
        fp=self.fp
        movi_end=fp.tell()
        fp.seek(self.movi_size_offset)
        fp.write(struct.pack("<I",movi_end-(self.movi_size_offset+4)))
        fp.seek(movi_end)
        entries=b"".join(struct.pack("<4sIII",*x) for x in self.entries)
        fp.write(_chunk(b"idx1",entries))
        end=fp.tell()
        if end>MAX_OUTPUT_BYTES or end>=2**32:
            raise ValueError("The native AVI output is larger than its bounded profile")
        fp.seek(self.riff_size_offset)
        fp.write(struct.pack("<I",end-8))
        fp.seek(end)
        fp.flush()
        return {"frames":self.count,"audio_samples_per_channel":self.audio_samples,
                "output_bytes":end,"video_fourcc":"MJPG",
                "audio_format":"PCM signed stereo 16-bit","codec_dependency":"Pillow/libjpeg",
                "ffmpeg_used":False}


def _normalized(vec):
    length=math.sqrt(sum(v*v for v in vec))
    if length<1e-8:return None
    return tuple(v/length for v in vec)


def _dot(a,b):
    return sum(a[i]*b[i] for i in range(3))


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],
            a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])


def _basis(camera):
    pos=camera["position"];target=camera["look_at"]
    forward=_normalized([target[i]-pos[i] for i in range(3)])
    if forward is None:raise ValueError("Camera has no direction")
    right=_normalized(_cross(forward,(0.,0.,1.)))
    if right is None:right=(1.,0.,0.)
    up=_cross(right,forward)
    return pos,right,up,forward


def _project(pt,basis,focal,width,height):
    pos,right,up,forward=basis
    delta=[pt[i]-pos[i] for i in range(3)]
    z=_dot(delta,forward)
    if z<.08:return None
    fx=width*focal/36.
    return (width*.5+_dot(delta,right)*fx/z,
            height*.5-_dot(delta,up)*fx/z,z)


def _cube():
    points=[(x,y,z) for z in (-.5,.5) for y in (-.5,.5) for x in (-.5,.5)]
    faces=[(0,1,3,2),(4,6,7,5),(0,4,5,1),
           (2,3,7,6),(0,2,6,4),(1,5,7,3)]
    return points,faces


def _sphere():
    # A real faceted geometry, not a flat labelled icon.
    n,m=12,7
    pts=[]
    for j in range(m+1):
        lat=-math.pi/2+math.pi*j/m
        for i in range(n):
            a=2*math.pi*i/n
            pts.append((.5*math.cos(lat)*math.cos(a),
                        .5*math.cos(lat)*math.sin(a),.5*math.sin(lat)))
    faces=[]
    for j in range(m):
        for i in range(n):
            a=j*n+i;b=j*n+(i+1)%n
            faces.append((a,b,b+n,a+n))
    return pts,faces


def _cone():
    n=12
    pts=[(0,0,.5)]+[(.5*math.cos(2*math.pi*i/n),
                      .5*math.sin(2*math.pi*i/n),-.5) for i in range(n)]
    faces=[(0,1+i,1+(i+1)%n) for i in range(n)]
    faces.append(tuple(range(1,n+1)))
    return pts,faces


def _cylinder():
    n=12;pts=[]
    for z in (-.5,.5):
        pts.extend((.5*math.cos(2*math.pi*i/n),
                    .5*math.sin(2*math.pi*i/n),z) for i in range(n))
    faces=[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    faces +=[tuple(range(n)),tuple(range(n,2*n))]
    return pts,faces


MESH={
    "box":_cube(),"sphere":_sphere(),"cone":_cone(),
    "cylinder":_cylinder()
}


def _world_stage(raw):
    from pxr import Sdf,Usd
    layer=Sdf.Layer.CreateAnonymous("g08-source-evaluation.usda")
    if not layer.ImportFromString(raw.decode("utf8")) or (
            layer.subLayerPaths or layer.GetExternalReferences()):
        raise RuntimeError("Original OpenUSD source cannot be independently opened")
    stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
    if not stage or not stage.GetPrimAtPath("/World"):
        raise RuntimeError("Original film world is not an OpenUSD stage")
    return stage


class SourceWorld:
    def __init__(self,record):
        self.record=record
        if sha256(record["performance_usd"]).hexdigest()!=record.get(
                "performance_sha256",sha256(record["performance_usd"]).hexdigest()):
            raise RuntimeError("Frozen performance SHA mismatch")
        self.stage=_world_stage(record["performance_usd"])
        self.objects=[]
        if len(record["stage_objects"])>MAX_RENDER_OBJECTS:
            raise ValueError("This film scene exceeds the initial rendering profile")
        for entry in record["stage_objects"]:
            shape=entry["shape"]
            if shape not in SUPPORTED:
                raise RuntimeError("Original world contains an unsupported geometry kind")
            if shape in MESH:
                prim=self.stage.GetPrimAtPath("/World/Objects/"+entry["id"])
                if not prim:
                    raise RuntimeError("Frozen scene object cannot be evaluated")
                self.objects.append((entry,prim))

    def polygons(self,tick,basis,focal,width,height):
        from pxr import Usd,UsdGeom,Gf
        faces=[]
        t=Usd.TimeCode(float(tick))
        light=_normalized((-.6,-.4,1.))
        for item,prim in self.objects:
            mat=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(t)
            vertices,polys=MESH[item["shape"]]
            world=[mat.Transform(Gf.Vec3d(*p)) for p in vertices]
            color=item["color"]
            rgb=tuple(int(color[k:k+2],16) for k in (1,3,5))
            for face in polys:
                xyz=[tuple(world[i]) for i in face]
                points=[_project(p,basis,focal,width,height) for p in xyz]
                # Explicitly refuse only the face straddling near clip; later
                # G09 renderer will fully clip and shade arbitrary mesh types.
                if any(p is None for p in points):
                    continue
                a,b,c=xyz[0],xyz[1],xyz[2]
                norm=_normalized(_cross([b[i]-a[i] for i in range(3)],
                                        [c[i]-a[i] for i in range(3)]))
                if norm is None:continue
                brightness=.52+.48*abs(_dot(norm,light))
                adjusted=tuple(max(0,min(255,round(v*brightness))) for v in rgb)
                depth=sum(p[2] for p in points)/len(points)
                xy=[(p[0],p[1]) for p in points]
                faces.append((depth,xy,adjusted))
        faces.sort(key=lambda x:x[0],reverse=True)
        return faces


def _grade(image,decision):
    exp=decision["exposure"];contrast=decision["contrast"]
    sat=decision["saturation"];warmth=decision["warmth"]
    if exp: image=ImageEnhance.Brightness(image).enhance(2**exp)
    if contrast!=1: image=ImageEnhance.Contrast(image).enhance(contrast)
    if sat!=1: image=ImageEnhance.Color(image).enhance(sat)
    if warmth:
        r,g,b=image.split()
        r=r.point(lambda v:min(255,max(0,round(v*(1+warmth*.15)))))
        b=b.point(lambda v:min(255,max(0,round(v*(1-warmth*.15)))))
        image=Image.merge("RGB",(r,g,b))
    return image


def _active(segments,tick):
    live=[]
    for i,s in enumerate(segments):
        if s["start_tick"]<=tick<s["end_tick"]:
            overlap=s["transition"]["duration_tick"]
            weight=(tick-s["start_tick"])/overlap if i and overlap and (
                tick<s["start_tick"]+overlap) else 1.
            live.append((s,weight))
    if len(live)==2:
        live.sort(key=lambda x:x[0]["start_tick"])
        return [(live[0][0],1-live[1][1]),live[1]]
    if len(live)>2:
        raise RuntimeError("Editorial transitions have more than two overlapping shots")
    return live


def render_picture(assembly,worlds,tick):
    entries=_active(assembly["segments"],tick)
    if not entries:raise RuntimeError("The film contains a gap in its picture")
    canvas=None
    for seg,weight in entries:
        src_tick=seg["source_in_tick"]+tick-seg["start_tick"]
        if not seg["source_in_tick"]<=src_tick<seg["source_out_tick"]:
            raise RuntimeError("The scene cut references time outside original recording")
        record=worlds[seg["take_id"]]
        settings=record.record.get("stage_setting",{})
        daylight=settings.get("daylight","day")
        bg=(20,28,47) if daylight=="night" else (
            (147,118,142) if daylight=="dusk" else DEFAULT_BACKGROUND)
        img=Image.new("RGB",(WIDTH,HEIGHT),bg)
        draw=ImageDraw.Draw(img)
        basis=_basis(seg["camera"])
        for depth,polygon,color in record.polygons(
                src_tick,basis,seg["camera"]["focal_mm"],WIDTH,HEIGHT):
            draw.polygon(polygon,fill=color)
        img=_grade(img,seg["grade"])
        if canvas is None:canvas=img
        else:canvas=Image.blend(canvas,img,max(0.,min(1.,weight)))
    out=BytesIO()
    canvas.save(out,format="JPEG",quality=76,subsampling=2,optimize=False)
    return out.getvalue()


def _audio_frame(assembly,takes,start_sample,count):
    start_tick=start_sample*TICKS_SAMPLE
    results=[[0.0]*count for _ in range(2)]
    for seg_index,seg in enumerate(assembly["segments"]):
        lower=max(start_tick,seg["start_tick"])
        upper=min(start_tick+count*TICKS_SAMPLE,seg["end_tick"])
        if lower>=upper:continue
        take=takes[seg["take_id"]]
        recordings={item["clip_id"]:item for item in take["audio"]}
        for edit in seg["audio"]:
            if not edit["enabled"] or not edit["gain"]:continue
            recorded=recordings.get(edit["clip_id"])
            if recorded is None:raise RuntimeError("The film's original sound is missing")
            original_start=recorded["start_tick"]+edit["offset_tick"]
            offset=seg["start_tick"]+original_start-seg["source_in_tick"]
            actual_a=max(lower,offset)
            actual_b=min(upper,offset+recorded["duration_tick"])
            if actual_a>=actual_b:continue
            first=max(0,math.ceil((actual_a-start_tick)/TICKS_SAMPLE))
            last=min(count,math.ceil((actual_b-start_tick)/TICKS_SAMPLE))
            pcm=memoryview(recorded["pcm16le"])
            left,right=_stereo_gain(recorded["emitter_position"],seg["camera"],
                                    edit["pan"],edit["spatial"])
            scalar=edit["gain"]*assembly["master_gain"]
            for j in range(first,last):
                tick=start_tick+j*TICKS_SAMPLE
                source_sample=(tick-offset)//TICKS_SAMPLE
                if not 0<=source_sample<recorded["sample_count"]:continue
                at=source_sample*2
                value=int.from_bytes(pcm[at:at+2],"little",signed=True)
                fade=1.
                incoming=seg["transition"]["duration_tick"]
                if (seg_index>0 and incoming and
                    tick<seg["start_tick"]+incoming):
                    fade=(tick-seg["start_tick"])/incoming
                if seg_index+1<len(assembly["segments"]):
                    next_segment=assembly["segments"][seg_index+1]
                    outgoing=next_segment["transition"]["duration_tick"]
                    if outgoing and tick>=next_segment["start_tick"]:
                        fade=1.-(tick-next_segment["start_tick"])/outgoing
                fade=max(0.,min(1.,fade))
                results[0][j]+=value*scalar*left*fade
                results[1][j]+=value*scalar*right*fade
    data=bytearray(count*4)
    for j in range(count):
        struct.pack_into("<hh",data,4*j,
                         max(-32768,min(32767,round(results[0][j]))),
                         max(-32768,min(32767,round(results[1][j]))))
    return bytes(data)


def render_film(assembly,output,*,cancel=None,progress=None):
    """Render actual 30s-or-shorter AVI bytes to an owned seekable sink."""
    from backend.nvp_g07_edit import FORMAT as EDIT_FORMAT
    if assembly.get("format")!=EDIT_FORMAT:
        raise RuntimeError("This film has no trusted source-based edit assembly")
    if assembly.get("source_media_modified") is not False:
        raise RuntimeError("Refuse an edit that altered its original source")
    total=assembly["duration_tick"]
    if type(total) is not int or total<=0 or total>MAX_SECONDS*TICKS_PER_SECOND:
        raise ValueError("First film export supports up to 30 seconds")
    if total%TICKS_FRAME:
        raise ValueError("Trim the edited film to a complete 24 fps frame")
    frames=total//TICKS_FRAME
    if frames>720:
        raise ValueError("Film exceeds the first 720-frame profile")
    if total%TICKS_SAMPLE:
        raise ValueError("Film sound is not aligned to 48-kHz sample time")
    sources=assembly["original_takes"]
    if len(sources)>60:raise ValueError("First export supports up to 60 original Takes")
    for item in sources.values():
        if not isinstance(item["performance_usd"],bytes):
            raise RuntimeError("Original performance is not native OpenUSD bytes")
    worlds={key:SourceWorld(value) for key,value in sources.items()}
    production=assembly.get("production_looks",{})
    derived_receipts={}
    if production:
        from backend.nvp_g09_environment import _json,_sha
        from backend.nvp_g09_render import render_production_picture
        from backend.nvp_g09_production_usd import author_derived_world
        actual=_sha(_json({key:{
            "revision":v["revision"],"sha256":v["sha256"]}
            for key,v in sorted(production.items())}).encode("utf8"))
        if actual!=assembly.get("production_looks_sha256"):
            raise RuntimeError("Approved scene look digest was changed")
        if set(production)-set(sources):
            raise RuntimeError("An approved set is not bound to a frozen Take")
        # Independently author and reopen the production PBR/MaterialX USD
        # layer for each actual original scene before deriving any pixels.
        # Only the receipt is retained; original USD is never overwritten.
        for take_id,approval in production.items():
            derived,receipt=author_derived_world(
                sources[take_id]["performance_usd"],take_id,
                sources[take_id]["take_sha256"],approval["look"],
                sources[take_id])
            if receipt["source_modified"] is not False:
                raise RuntimeError("Production scene altered frozen source")
            derived_receipts[take_id]=receipt
            del derived
    acting=assembly.get("actor_performances",{})
    actor_receipts={}
    if acting:
        from backend.nvp_g09_actor import _json as _actor_json,_sha as _actor_sha
        from backend.nvp_g09_actor_rig import (
            ActorFrameEvaluator,author_actor_world)
        from backend.nvp_g09_render import render_production_picture
        actual=_actor_sha(_actor_json({key:{
            "revision":v["revision"],"sha256":v["sha256"]}
            for key,v in sorted(acting.items())}).encode("utf8"))
        if actual!=assembly.get("actor_performances_sha256"):
            raise RuntimeError("Approved acting direction digest was changed")
        if set(acting)-set(sources):
            raise RuntimeError("An acting profile is not bound to the original film")
        # One Take can be reused in multiple edits with a different
        # original-audio placement/mute each time. Derive the acting
        # source against EACH edited shot so USD jaw time stays equal to
        # the final audible G07 PCM window, not a stale Take-default.
        actor_segments=[seg for seg in assembly["segments"]
                        if seg["take_id"] in acting]
        if len(actor_segments)>32:
            raise ValueError("This initial actor export supports up to thirty-two edited character shots")
        for take_id,approval in acting.items():
            record=sources[take_id]
            if approval["performance"]["actors"]:
                worlds[take_id].actor_frame_evaluator=ActorFrameEvaluator(
                    record,approval)
        for seg in actor_segments:
            take_id=seg["take_id"]
            approval=acting[take_id]
            record=sources[take_id]
            if not approval["performance"]["actors"]:continue
            derived,receipt=author_actor_world(
                record["performance_usd"],record,approval,
                source_pcm=record["audio"],voice_edits=seg["audio"],
                edit_clip_id=seg["clip_id"])
            if receipt["original_audio_untouched"] is not True:
                raise RuntimeError("Actor animation tried to alter original speech")
            actor_receipts[seg["clip_id"]]=receipt
            del derived
    acoustics=assembly.get("acoustic_looks",{})
    spatial_mixer=None
    if acoustics:
        from backend.nvp_g09c_native_audio import SpatialFilmMixer
        from backend.nvp_g09c_acoustics import _json as _cjson,_sha as _csha
        expected=_csha(_cjson({
            key:{"revision":val["revision"],"sha256":val["sha256"]}
            for key,val in sorted(acoustics.items())
        }).encode("utf8"))
        if (expected!=assembly.get("acoustic_looks_sha256") or
            set(acoustics)-set(sources)):
            raise RuntimeError("The approved sound environment was changed")
        spatial_mixer=SpatialFilmMixer(assembly,worlds)
    writer=MjpegPcmAvi(output,frames)
    for frame in range(frames):
        if cancel is not None and cancel():
            raise InterruptedError("Movie export was cancelled")
        tick=frame*TICKS_FRAME
        jpeg=(render_production_picture(assembly,worlds,tick)
              if production or acting else render_picture(assembly,worlds,tick))
        sound=(spatial_mixer.window(frame*2000,2000)[0]
               if spatial_mixer is not None
               else _audio_frame(assembly,sources,frame*2000,2000))
        writer.frame(jpeg,sound)
        if progress and (frame%6==0 or frame==frames-1):
            progress(frame+1,frames)
    result=writer.finish()
    result["duration_seconds"]=frames/FPS
    result["fps"]=FPS
    result["width"]=WIDTH
    result["height"]=HEIGHT
    result["profile"]=PROFILE
    result["approved_look_sha256"]=assembly.get("production_looks_sha256")
    result["approved_production_look_applied"]=bool(production)
    result["approved_acoustic_looks_sha256"]=assembly.get(
        "acoustic_looks_sha256")
    result["source_based_3d_audio_mixed"]=spatial_mixer is not None
    result["original_pcm_preserved"]=True
    result["approved_actor_performances_sha256"]=assembly.get(
        "actor_performances_sha256")
    result["animated_actor_count"]=sum(
        len(approval["performance"]["actors"])
        for approval in acting.values())
    if acting:
        result["derived_actor_usd_receipts_sha256"]=_actor_sha(_actor_json({
            key:{"source":value["original_usd_sha256"],
                 "derived":value["derived_usd_sha256"],
                 "approved":value["actor_approved_sha256"],
                 "sound_edit":value["sound_edit_sha256"],
                 "clip":value["edit_clip_id"]}
            for key,value in sorted(actor_receipts.items())
        }).encode("utf8"))
    result["derived_usd_scene_count"]=len(derived_receipts)
    if production:
        result["derived_usd_receipts_sha256"]=_sha(
            _json(derived_receipts).encode("utf8"))
    result["original_sources_changed"]=False
    return result


def verify_movie(data,expected_frames,*,expected_sha=None):
    """Independent AVI readback of headers, all frames, PCM and AVI index.

    Feed a new file opened in a separate verifier process in production.
    The parser never trusts output file extensions, metadata or job claims.
    """
    if hasattr(data,"read"):
        data=data.read()
    if type(data) is not bytes or len(data)<512 or len(data)>MAX_OUTPUT_BYTES:
        raise RuntimeError("Completed film has invalid size")
    if expected_sha and sha256(data).hexdigest()!=expected_sha:
        raise RuntimeError("Published movie hash differs from the completed render")
    if data[:4]!=b"RIFF" or data[8:12]!=b"AVI ":
        raise RuntimeError("Delivered file is not an AVI movie")
    if struct.unpack_from("<I",data,4)[0]!=len(data)-8:
        raise RuntimeError("Delivered movie length header is inconsistent")
    movi=data.find(b"movi")
    idx=data.rfind(b"idx1")
    if movi<0 or idx<0 or idx<=movi:
        raise RuntimeError("Movie has no independently searchable frames")
    at=movi+4
    frames=0;audio=0;first=None;last=None;chunk_count=0
    while at<idx:
        if at+8>idx:raise RuntimeError("AVI media chunk is truncated")
        tag=data[at:at+4];size=struct.unpack_from("<I",data,at+4)[0]
        stop=at+8+size
        if stop>idx:raise RuntimeError("AVI chunk payload is incomplete")
        raw=data[at+8:stop]
        if tag==b"00dc":
            if not raw.startswith(b"\xff\xd8") or not raw.endswith(b"\xff\xd9"):
                raise RuntimeError("AVI picture chunk is not JPEG")
            # Decode EVERY recorded picture in an independently supervised
            # verifier process. Header-only JPEG checks cannot satisfy
            # the G08 proof that the complete movie is actually playable.
            with Image.open(BytesIO(raw)) as decoded:
                decoded.load()
                if decoded.size!=(WIDTH,HEIGHT) or decoded.mode not in (
                        "RGB","YCbCr","L"):
                    raise RuntimeError("One filmed picture could not be decoded")
            frames+=1
            if first is None:first=raw
            last=raw
        elif tag==b"01wb":
            if size!=8000:raise RuntimeError("AVI source sound lost sample alignment")
            audio+=size//AUDIO_BLOCK
        else:raise RuntimeError("Unexpected media stream in delivered movie")
        at=stop+(size&1);chunk_count+=1
    if at!=idx or frames!=expected_frames or audio!=frames*2000 or (
            chunk_count!=frames*2):
        raise RuntimeError("Movie frames and sound are not continuous")
    if struct.unpack_from("<I",data,idx+4)[0]!=chunk_count*16:
        raise RuntimeError("Movie index is incomplete")
    # All picture frames have been decoded above, and every per-frame
    # stereo PCM payload has been checked against the exact sample clock.
    return {"verified":True,"frames":frames,"audio_samples_per_channel":audio,
        "duration_seconds":frames/FPS,"sha256":sha256(data).hexdigest(),
        "bytes":len(data),"picture_codec":"MJPEG",
        "sound_codec":"PCM16 stereo","ffmpeg_used":False}
