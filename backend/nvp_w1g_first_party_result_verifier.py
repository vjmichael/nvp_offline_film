"""Independent original W1-G first-party native capability-slice verification.

Read only the original supervised worker's bounded inputs and produced bytes;
no subprocess, approval callback, model, device access or source mutation.
A claimed successful process exit or a self-written result.json cannot
establish a correct output. This verifies five CONSTRAINED capability slices,
not full native film, scene, audio or DCP workflow completion.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import math
import struct

ROLE_OPERATIONS={
    "original_capture":("capture.manifest","pcm16_verified_intake"),
    "scene_render":("render.ppm","bounded_native_math_picture"),
    "editorial":("edit.pcm","bounded_pcm_non_destructive_cut"),
    "audio":("mix.pcm","bounded_native_pcm_gain"),
    "delivery":("delivery.bundle","finite_native_media_bundle"),
}
MAX_SOURCE_BYTES=8*1024*1024


def _source(directory:Path,name:str)->bytes:
    file=directory/name
    if (file.is_symlink() or not file.is_file() or
        file.stat().st_size<=0 or file.stat().st_size>MAX_SOURCE_BYTES):
        raise RuntimeError("Missing, linked or unbounded native worker source: "+name)
    return file.read_bytes()


def _control(directory,name,maximum_a,maximum_b):
    parts=_source(directory,name).decode("ascii").split()
    if (len(parts)!=2 or any(not p.isdigit() or len(p)>10 for p in parts)):
        raise ValueError("Untrusted native worker numeric controls")
    a,b=map(int,parts)
    if a>maximum_a or b>maximum_b:
        raise ValueError("Native worker numeric controls outside acceptance bounds")
    return a,b


def _sha(data:bytes)->str:
    return sha256(data).hexdigest()


def expected_native_math_picture(width:int,height:int)->bytes:
    """Independent exact bounded raster oracle, not compiled worker output."""
    if (type(width) is not int or type(height) is not int or
        not 16<=width<=128 or not 16<=height<=128):
        raise PermissionError("Unbounded native raster dimensions")
    pixels=bytearray()
    radius=0.54
    for y in range(height):
        for x in range(width):
            nx=(float(x)+0.5)/width*2.0-1.0
            ny=1.0-(float(y)+0.5)/height*2.0
            radius_squared=nx*nx+ny*ny
            diffuse=0.0
            if radius_squared<radius*radius:
                nz=math.sqrt(radius*radius-radius_squared)/radius
                diffuse=max(0.0,nx*(-0.4)+ny*0.6+nz*0.75)
            pixels.extend((20+math.floor(205*diffuse+0.5),
                           20+math.floor(80*diffuse+0.5),
                           30+math.floor(60*diffuse+0.5)))
    return f"P6\\n{width} {height}\\n255\\n".encode("ascii")+bytes(pixels)


def verify_bounded_first_party_role(scope:dict,result:dict,directory:Path)->bool:
    """Checks exact immutable-plan scope, output shape, semantics, and digest.

    This function is mandatory alongside a calling host's own independent
    domain verifier, not a replacement for native Job/cgroup termination.
    """
    if (type(scope) is not dict or type(result) is not dict or
        type(directory) is not Path):
        raise PermissionError("Original trusted native worker scope missing")
    role=scope.get("role")
    if role not in ROLE_OPERATIONS:
        raise PermissionError("Unrecognized original compiled native worker capability")
    output_name,operation=ROLE_OPERATIONS[role]
    if set(result)!={"format","job_id","project_id","role","plan_sha256",
                      "output_name","output_sha256","operation","output_bytes",
                      "full_film_pipeline_accepted"}:
        raise PermissionError("Extra, missing or unbounded original native receipt fields")
    if (result["format"]!="nvp.w1g.native_worker_result.v1" or
        result["job_id"]!=scope.get("job_id") or
        result["project_id"]!=scope.get("project_id") or
        result["role"]!=role or
        result["plan_sha256"]!=scope.get("plan_sha256") or
        result["output_name"]!=output_name or
        result["operation"]!=operation or
        result["full_film_pipeline_accepted"] is not False):
        raise PermissionError("Original native worker result differs from sealed authorized role")
    produced=_source(directory,output_name)
    if (type(result["output_bytes"]) is not int or
        result["output_bytes"]!=len(produced) or
        result["output_sha256"]!=_sha(produced)):
        raise PermissionError("Original native output bytes differ from sealed result identity")

    if role=="original_capture":
        samples=_source(directory,"source.pcm")
        if len(samples)%2:
            raise PermissionError("Native capture source is not PCM16LE")
        values=struct.unpack("<"+"h"*(len(samples)//2),samples)
        manifest=("format=nvp.w1g.pcm_intake.v1\n"
                  f"samples={len(values)}\npeak={max(map(abs,values))}\n"
                  f"source_sha256={_sha(samples)}\n").encode("ascii")
        if produced!=manifest:
            raise PermissionError("Native PCM intake audit did not match actual original bytes")
    elif role=="scene_render":
        width,height=_control(directory,"scene.txt",128,128)
        if width<16 or height<16:
            raise PermissionError("Native scene dimensions below minimum")
        prefix=f"P6\n{width} {height}\n255\n".encode("ascii")
        if (not produced.startswith(prefix) or
            len(produced)!=len(prefix)+3*width*height):
            raise PermissionError("Native raster output is not a real bounded PPM image")
        if produced!=expected_native_math_picture(width,height):
            raise PermissionError("Native renderer pixels differ from independently computed scene")
    elif role=="editorial":
        original=_source(directory,"source.pcm")
        start,count=_control(directory,"edit.txt",4194304,4194304)
        if len(original)%2 or count==0 or start>=len(original)//2 or (
                count>len(original)//2-start):
            raise PermissionError("Edited source range is not an actual bounded PCM cut")
        if produced!=original[2*start:2*(start+count)]:
            raise PermissionError("Native editorial result changes immutable sample selection")
    elif role=="audio":
        original=_source(directory,"source.pcm")
        num,den=_control(directory,"gain.txt",8,8)
        if len(original)%2 or den==0:
            raise PermissionError("Native PCM gain source invalid")
        values=struct.unpack("<"+"h"*(len(original)//2),original)
        scaled=[max(-32768,min(32767,int(v*num/den))) for v in values]
        expected=struct.pack("<"+"h"*len(scaled),*scaled)
        if produced!=expected:
            raise PermissionError("Native audio result differs from exact rational PCM gain")
    else:
        picture=_source(directory,"render.ppm")
        audio=_source(directory,"mix.pcm")
        if len(audio)%2 or not picture.startswith(b"P6\n"):
            raise PermissionError("Native delivery source identities invalid")
        expected=(b"NVPW1G01"+
                  struct.pack("<QQ",len(picture),len(audio))+picture+audio)
        if produced!=expected:
            raise PermissionError("Native delivery result differs from original picture/PCM bytes")
    return True
