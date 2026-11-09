"""USD-FILM-01R reviewed draft/final Cycles profiles (not browser scripts).

Low-fi source visualization uses native USD geometry without rendering
pixels. These profiles apply only to the actual source-selected 01Q
Blender/Cycles pictures and are bound into source+view cache keys, OS job IDs,
user authorization and worker output size verification.
"""
from __future__ import annotations
from hashlib import sha256
import json

FORMAT="nvp.usd_film01r.reviewed_cycles_quality_profile.v1"
PROFILES={
    "technical_smoke":(320,180,8,600,2048),
    "draft_360p":(640,360,16,900,3072),
    "final_720p":(1280,720,48,1800,6144),
    "final_1080p":(1920,1080,96,3600,12288),
}

def reviewed_quality(name):
    if type(name) is not str or name not in PROFILES:
        raise ValueError("Only fixed first-party film quality profiles allowed")
    w,h,s,seconds,ram=PROFILES[name]
    return {
        "format":FORMAT,"name":name,
        "engine":"BLENDER_CYCLES",
        "device":"CPU",
        "resolution_x":w,"resolution_y":h,"samples":s,
        "timeout_seconds":seconds,"max_worker_ram_mb":ram,
        "original_actor_performance_must_not_change":True,
        "final_cinema_picture_approval":False}

def quality_hash(profile):
    return sha256(json.dumps(profile,sort_keys=True,
        separators=(",",":"),ensure_ascii=True,
        allow_nan=False).encode("ascii")).hexdigest()

def verify_quality(profile):
    if not isinstance(profile,dict):
        raise TypeError("Reviewed source quality record required")
    result=reviewed_quality(profile.get("name"))
    if result!=profile:
        raise PermissionError("Unreviewed renderer profile or resources")
    return result
