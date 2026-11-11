"""Host-gated G07 editing routes. Only presentation decisions, sampled previews
and disposable sound envelopes are exposed to the Post-Production UI."""
from __future__ import annotations

from fastapi import HTTPException,Request
from fastapi.responses import Response
from pydantic import BaseModel,Field

from backend.nvp_g07_edit import G07Editor
from backend.nvp_g07_preview import picture,audio_window


class EditChange(BaseModel):
    expected_revision:int=Field(ge=0,le=15000)
    operation:str=Field(min_length=2,max_length=32)
    details:dict


class Restore(BaseModel):
    expected_revision:int=Field(ge=0,le=15000)
    source_revision:int=Field(ge=1,le=15000)


def _safe(task):
    try:
        return task()
    except PermissionError as exc:
        raise HTTPException(403,detail="This film action is not authorized") from exc
    except KeyError as exc:
        raise HTTPException(404,detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409,detail=str(exc)) from exc


def mount_g07_routes(app,studio,live_films,cookie_name):
    def editor(project_id,request):
        if request.headers.get("x-nvp-director")!="1":
            raise HTTPException(403,detail="Open the film editing workspace")
        secured=live_films().exists(project_id)
        return G07Editor(studio,live=live_films() if secured else None,
            token=request.cookies.get(cookie_name) if secured else None)

    def routes(method,tail,handler):
        for prefix,tag in (("edit","plain"),("live/edit","protected")):
            app.add_api_route(
                "/api/projects/{project_id}/"+prefix+tail,
                handler,methods=[method],
                name="g07_"+handler.__name__+"_"+tag)

    def view(project_id:str,request:Request):
        return _safe(lambda:editor(project_id,request).view(project_id))
    routes("GET","",view)

    def change(project_id:str,request:Request,payload:EditChange):
        return _safe(lambda:editor(project_id,request).mutate(
            project_id,payload.expected_revision,
            payload.operation,payload.details))
    routes("POST","/change",change)

    def restore(project_id:str,request:Request,payload:Restore):
        return _safe(lambda:editor(project_id,request).restore(
            project_id,payload.source_revision,payload.expected_revision))
    routes("POST","/restore",restore)

    def sample(project_id:str,request:Request,seconds:str="0"):
        service=editor(project_id,request)
        return _safe(lambda:picture(service,project_id,seconds))
    routes("GET","/picture",sample)

    def listen(project_id:str,request:Request,
               start_seconds:str="0",duration_seconds:str="3"):
        service=editor(project_id,request)
        data=_safe(lambda:audio_window(service,project_id,
            start_seconds,duration_seconds))
        return Response(content=data,media_type="audio/wav",headers={
            "Cache-Control":"private, no-store, max-age=0",
            "X-Content-Type-Options":"nosniff",
            "Content-Disposition":"inline"})
    routes("GET","/sound",listen)
