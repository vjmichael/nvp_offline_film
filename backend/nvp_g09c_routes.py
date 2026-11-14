"""G09-C bounded native A/V preview and approved room-sound director routes.

Same ordinary/encrypted film unlock boundary as G07/G09-A/B. Only trusted
reviewed fixed operations, never arbitrary audio input, editable original
USD, microphone upload, script, device path, executable or raw PCM source.
"""
from __future__ import annotations

import json
from fastapi import HTTPException,Request
from fastapi.responses import Response
from pydantic import BaseModel,Field

from backend.nvp_g07_edit import G07Editor
from backend.nvp_g09c_acoustics import G09CAcoustics
from backend.nvp_g09c_playback import frames,sound,timeline


class SoundChange(BaseModel):
    expected_revision:int=Field(ge=0,le=2000)
    operation:str=Field(min_length=3,max_length=24)
    details:dict

class SoundReview(BaseModel):
    expected_revision:int=Field(ge=1,le=2000)

class SoundRestore(BaseModel):
    expected_revision:int=Field(ge=0,le=2000)
    source_revision:int=Field(ge=1,le=2000)

def _safe(fn):
    try:return fn()
    except PermissionError as e:
        raise HTTPException(403,detail="Unlock this movie to review its sound") from e
    except KeyError as e:
        raise HTTPException(404,detail="The selected source was not found") from e
    except ValueError as e:
        raise HTTPException(422,detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(409,detail=str(e)) from e

def mount_g09c_routes(app,studio,live_films,cookie_name):
    def services(pid,request):
        if request.headers.get("x-nvp-director")!="1":
            raise HTTPException(403,detail="Open Film Editing to review sound and picture")
        encrypted=live_films().exists(pid)
        live=live_films() if encrypted else None
        token=request.cookies.get(cookie_name) if encrypted else None
        return G09CAcoustics(studio,live,token),G07Editor(studio,live,token)

    def route(method,suffix,fn,kind):
        for protected in (False,True):
            path="/api/projects/{project_id}"+(
                "/live" if protected else "")+"/"+kind+suffix
            app.add_api_route(path,fn,methods=[method],
                name="g09c_"+fn.__name__+("_protected" if protected else "_ordinary"))

    def room(project_id:str,take_id:str,request:Request):
        acoustic,_=services(project_id,request)
        return _safe(lambda:acoustic.view(project_id,take_id))
    route("GET","/{take_id}",room,"production/sound")

    def change(project_id:str,take_id:str,request:Request,payload:SoundChange):
        acoustic,_=services(project_id,request)
        return _safe(lambda:acoustic.change(project_id,take_id,
            payload.expected_revision,payload.operation,payload.details))
    route("POST","/{take_id}/change",change,"production/sound")

    def approve(project_id:str,take_id:str,request:Request,payload:SoundReview):
        acoustic,_=services(project_id,request)
        return _safe(lambda:acoustic.approve(project_id,take_id,
            payload.expected_revision))
    route("POST","/{take_id}/approve",approve,"production/sound")

    def restore(project_id:str,take_id:str,request:Request,payload:SoundRestore):
        acoustic,_=services(project_id,request)
        return _safe(lambda:acoustic.restore(project_id,take_id,
            payload.source_revision,payload.expected_revision))
    route("POST","/{take_id}/restore",restore,"production/sound")

    def av_timeline(project_id:str,request:Request,revision:int=0):
        _,edit=services(project_id,request)
        return _safe(lambda:timeline(edit,project_id,revision))
    route("GET","/timeline",av_timeline,"av")

    def picture_frames(project_id:str,request:Request,revision:int=0,
                       start_frame:int=0,count:int=12):
        _,edit=services(project_id,request)
        return _safe(lambda:frames(edit,project_id,revision,start_frame,count))
    route("GET","/frames",picture_frames,"av")

    def sound_window(project_id:str,request:Request,revision:int=0,
                     start_sample:int=0,count:int=24000):
        _,edit=services(project_id,request)
        pcm,proof=_safe(lambda:sound(
            edit,project_id,revision,start_sample,count))
        # Proof contains only non-sensitive clock/codec metadata. Source
        # voice content is already contained in authenticated no-store WAV.
        return Response(content=pcm,media_type="audio/wav",headers={
            "Cache-Control":"private, no-store, max-age=0",
            "X-Content-Type-Options":"nosniff",
            "X-NVP-Audio-Start-Sample":str(proof["start_sample"]),
            "X-NVP-Audio-Samples":str(proof["sample_count"]),
            "X-NVP-Audio-Edit-Revision":str(proof["edit_revision"])})
    route("GET","/sound",sound_window,"av")
