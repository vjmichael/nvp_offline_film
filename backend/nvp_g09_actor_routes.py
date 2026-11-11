"""Filmmaker-only G09-B ActorID performance and original-voice review routes.

No model or browser endpoint can mint an ActorID, synthesize voice, attach
arbitrary sound, mutate a Take, launch external engines or change approvals.
Only the reviewed source-bound human movie access path is accepted.
"""
from __future__ import annotations

from fastapi import HTTPException,Request
from fastapi.responses import Response
from pydantic import BaseModel,Field

from backend.nvp_g09_actor import G09Actors


class ActorChange(BaseModel):
    expected_revision:int=Field(ge=0,le=3000)
    actor_id:str=Field(min_length=8,max_length=100)
    operation:str=Field(min_length=3,max_length=32)
    details:dict


class ActorReview(BaseModel):
    expected_revision:int=Field(ge=1,le=3000)


class ActorRestore(ActorReview):
    source_revision:int=Field(ge=1,le=3000)


def _safe(work):
    try:return work()
    except PermissionError as exc:
        raise HTTPException(403,detail="Unlock this movie before working with actors") from exc
    except KeyError as exc:
        raise HTTPException(404,detail="The requested actor or recording was not found") from exc
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409,detail=str(exc)) from exc


def mount_g09_actor_routes(app,studio,live_films,cookie_name):
    def studio_for(pid,request):
        if request.headers.get("x-nvp-director")!="1":
            raise HTTPException(403,detail="Open your film's acting room")
        secured=live_films().exists(pid)
        return G09Actors(studio,live_films() if secured else None,
            request.cookies.get(cookie_name) if secured else None)

    def route(method,tail,handler):
        for prefix,name in (
            ("production/actors","ordinary"),
            ("live/production/actors","protected")):
            app.add_api_route("/api/projects/{project_id}/"+prefix+"/"+tail,
                              handler,methods=[method],
                              name="g09b_"+handler.__name__+"_"+name)

    def read(project_id:str,take_id:str,request:Request):
        return _safe(lambda:studio_for(project_id,request).view(
            project_id,take_id))
    route("GET","{take_id}",read)

    def change(project_id:str,take_id:str,request:Request,payload:ActorChange):
        return _safe(lambda:studio_for(project_id,request).change(
            project_id,take_id,payload.actor_id,payload.expected_revision,
            payload.operation,payload.details))
    route("POST","{take_id}/change",change)

    def approve(project_id:str,take_id:str,request:Request,payload:ActorReview):
        return _safe(lambda:studio_for(project_id,request).approve(
            project_id,take_id,payload.expected_revision))
    route("POST","{take_id}/approve",approve)

    def restore(project_id:str,take_id:str,request:Request,payload:ActorRestore):
        return _safe(lambda:studio_for(project_id,request).restore(
            project_id,take_id,payload.source_revision,payload.expected_revision))
    route("POST","{take_id}/restore",restore)

    def picture(project_id:str,take_id:str,request:Request,seconds:str="0"):
        raw=_safe(lambda:studio_for(project_id,request).picture_preview(
            project_id,take_id,seconds))
        return Response(content=raw,media_type="image/jpeg",headers={
            "Cache-Control":"private, no-store, max-age=0",
            "X-Content-Type-Options":"nosniff"})
    route("GET","{take_id}/preview",picture)

    def voice(project_id:str,take_id:str,clip_id:str,request:Request):
        raw=_safe(lambda:studio_for(project_id,request).voice_preview(
            project_id,take_id,clip_id))
        return Response(content=raw,media_type="audio/wav",headers={
            "Cache-Control":"private, no-store, max-age=0",
            "X-Content-Type-Options":"nosniff",
            "Content-Disposition":"inline"})
    route("GET","{take_id}/voice/{clip_id}",voice)
