"""Filmmaker-facing G08 delivery routes, preserving the existing G03 lock gate.

No arbitrary destination path, shell/process API or unreviewed artifact can be
provided through these routes. Only a completed second-process-verified native
film receives an NVP-owned read-only download link.
"""
from __future__ import annotations

from fastapi import HTTPException,Request
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field

from backend.nvp_g08_export import G08MovieExporter


class StartFilm(BaseModel):
    expected_revision:int=Field(ge=1,le=15000)
    director_confirmed:bool


def _safe(action):
    try:return action()
    except KeyError as exc:
        raise HTTPException(404,detail="Movie or export was not found") from exc
    except PermissionError as exc:
        raise HTTPException(403,detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409,detail=str(exc)) from exc


def mount_g08_routes(app,studio,film_access,live_films,cookie_name):
    exporter=G08MovieExporter(
        studio,access=film_access,protected_movie=live_films)

    def auth(request):
        if request.headers.get("x-nvp-director")!="1":
            raise HTTPException(403,detail="Open Export Film in your movie workspace")
        return request.cookies.get(cookie_name)

    def routes(method,suffix,handler):
        app.add_api_route("/api/projects/{project_id}/export"+suffix,
                          handler,methods=[method],
                          name="g08_"+handler.__name__+"_ordinary")
        app.add_api_route("/api/projects/{project_id}/live/export"+suffix,
                          handler,methods=[method],
                          name="g08_"+handler.__name__+"_protected")

    def jobs(project_id:str,request:Request):
        return {"format":"nvp.g08.delivery.v1",
                "exports":_safe(lambda:exporter.list(
                    project_id,auth(request)))}
    routes("GET","",jobs)

    def start(project_id:str,request:Request,payload:StartFilm):
        if payload.director_confirmed is not True:
            raise HTTPException(422,detail="Choose Export Film yourself to begin")
        token=auth(request)
        return _safe(lambda:exporter.prepare(
            project_id,payload.expected_revision,token))
    routes("POST","/start",start)

    def progress(project_id:str,job_id:str,request:Request):
        return _safe(lambda:exporter.read(
            project_id,job_id,auth(request)))
    routes("GET","/{job_id}",progress)

    def cancel(project_id:str,job_id:str,request:Request):
        return _safe(lambda:exporter.cancel(
            project_id,job_id,auth(request)))
    routes("POST","/{job_id}/cancel",cancel)

    def movie(project_id:str,job_id:str,request:Request):
        path=_safe(lambda:exporter.movie_path(
            project_id,job_id,auth(request)))
        # FileResponse handles byte-range requests for browser and native
        # media players. No file path is disclosed in the JSON project API.
        return FileResponse(path,media_type="video/x-msvideo",
            filename="NVP-Film-"+job_id[:8]+".avi",
            content_disposition_type="attachment",
            headers={"Cache-Control":"private, no-store, max-age=0",
                     "X-Content-Type-Options":"nosniff"})
    routes("GET","/{job_id}/movie",movie)
    return exporter
