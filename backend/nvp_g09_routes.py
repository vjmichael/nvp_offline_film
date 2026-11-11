"""Director-facing G09-A scene finishing, no technical asset/worker surface."""
from __future__ import annotations
from fastapi import HTTPException,Request
from fastapi.responses import Response
from pydantic import BaseModel,Field
from backend.nvp_g09_environment import G09Environment


class LookChange(BaseModel):
    expected_revision:int=Field(ge=0,le=3000)
    operation:str=Field(min_length=3,max_length=32)
    details:dict


class LookApprove(BaseModel):
    expected_revision:int=Field(ge=1,le=3000)


class LookKit(BaseModel):
    expected_revision:int=Field(ge=1,le=3000)
    name:str=Field(min_length=1,max_length=80)


def _safe(job):
    try:return job()
    except PermissionError as exc:
        raise HTTPException(403,detail="This movie is not unlocked") from exc
    except KeyError as exc:
        raise HTTPException(404,detail="This scene or saved set was not found") from exc
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409,detail=str(exc)) from exc


def mount_g09_routes(app,studio,live_films,cookie_name):
    def service(pid,request):
        if request.headers.get("x-nvp-director")!="1":
            raise HTTPException(403,detail="Open your movie's editing room")
        secured=live_films().exists(pid)
        return G09Environment(studio,live_films() if secured else None,
            request.cookies.get(cookie_name) if secured else None)

    def routes(method,tail,fn):
        app.add_api_route(
            "/api/projects/{project_id}/production/looks/"+tail,
            fn,methods=[method],name="g09_"+fn.__name__+"_ordinary")
        app.add_api_route(
            "/api/projects/{project_id}/live/production/looks/"+tail,
            fn,methods=[method],name="g09_"+fn.__name__+"_secured")

    def look(project_id:str,take_id:str,request:Request):
        return _safe(lambda:service(project_id,request).view(project_id,take_id))
    routes("GET","{take_id}",look)

    def preview(project_id:str,take_id:str,request:Request):
        picture=_safe(lambda:service(project_id,request).preview(
            project_id,take_id))
        return Response(picture,media_type="image/jpeg",headers={
            "Cache-Control":"private, no-store, max-age=0",
            "X-Content-Type-Options":"nosniff"})
    routes("GET","{take_id}/preview",preview)

    def change(project_id:str,take_id:str,request:Request,payload:LookChange):
        return _safe(lambda:service(project_id,request).edit(
            project_id,take_id,payload.expected_revision,
            payload.operation,payload.details))
    routes("POST","{take_id}/change",change)

    def approve(project_id:str,take_id:str,request:Request,payload:LookApprove):
        return _safe(lambda:service(project_id,request).approve(
            project_id,take_id,payload.expected_revision))
    routes("POST","{take_id}/approve",approve)

    def save_kit(project_id:str,take_id:str,request:Request,payload:LookKit):
        return _safe(lambda:service(project_id,request).save_kit(
            project_id,take_id,payload.name,payload.expected_revision))
    routes("POST","{take_id}/save-set",save_kit)
