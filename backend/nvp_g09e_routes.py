"""Director-only genuine native reel export; locked movies stay protected.

One user-confirmed operation creates a durable long-film job. Explicit
resume is the only way to continue interrupted work after restart. No
arbitrary local executable, source file, destination path or unreviewed
network service is exposed. Long exports of G03 encrypted films are
fail-closed pending encrypted worker/asset-custody acceptance.
"""
from __future__ import annotations
from fastapi import HTTPException,Request
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel,Field

from backend.nvp_g09e_delivery import G09ELongDelivery

class StartLongFilm(BaseModel):
    expected_revision:int=Field(ge=1,le=15000)
    director_confirmed:bool

class ConfirmLongFilm(BaseModel):
    director_confirmed:bool

def _safe(fn):
    try:return fn()
    except KeyError as e:
        raise HTTPException(404,detail="That saved film work is unavailable") from e
    except PermissionError as e:
        raise HTTPException(403,detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(422,detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(409,detail=str(e)) from e

def mount_g09e_routes(app,studio,film_access,live_films,cookie_name):
    handler=G09ELongDelivery(studio,access=film_access,
                              protected_movie=live_films)
    def token(request,*,download=False):
        if download:
            if request.headers.get("sec-fetch-site") not in (
                    None,"same-origin","none"):
                raise HTTPException(403,detail="Open your completed film in NVP")
        elif request.headers.get("x-nvp-director")!="1":
            raise HTTPException(403,detail="Open Export Film to manage rendering")
        return request.cookies.get(cookie_name)
    def route(method,tail,fn):
        # Same unlock/session middleware guards ordinary and live paths.
        # Live requests fail closed until encrypted long asset custody exists.
        for protected in (False,True):
            app.add_api_route(
                "/api/projects/{project_id}"+(
                    "/live" if protected else "")+
                "/long-film"+tail,fn,methods=[method],
                name="g09e_"+fn.__name__+
                    ("_sealed" if protected else "_ordinary"))

    def jobs(project_id:str,request:Request):
        return {"format":"nvp.g09e.long_film_jobs.v1",
            "jobs":_safe(lambda:handler.list(
                project_id,token(request)))}
    route("GET","",jobs)

    def start(project_id:str,request:Request,payload:StartLongFilm):
        if payload.director_confirmed is not True:
            raise HTTPException(422,detail="Review and choose to render the saved film yourself")
        return _safe(lambda:handler.start(
            project_id,payload.expected_revision,token(request)))
    route("POST","/start",start)

    def read(project_id:str,job_id:str,request:Request):
        return _safe(lambda:handler.read(
            project_id,job_id,token(request)))
    route("GET","/{job_id}",read)

    def resume(project_id:str,job_id:str,request:Request,
               payload:ConfirmLongFilm):
        if payload.director_confirmed is not True:
            raise HTTPException(422,detail="Choose Resume Film Render yourself")
        return _safe(lambda:handler.resume(
            project_id,job_id,token(request)))
    route("POST","/{job_id}/resume",resume)

    def cancel(project_id:str,job_id:str,request:Request,
               payload:ConfirmLongFilm):
        if payload.director_confirmed is not True:
            raise HTTPException(422,detail="Choose Stop Film Render yourself")
        return _safe(lambda:handler.cancel(
            project_id,job_id,token(request)))
    route("POST","/{job_id}/cancel",cancel)

    def manifest(project_id:str,job_id:str,request:Request):
        data=_safe(lambda:handler.manifest(
            project_id,job_id,token(request,download=True)))
        import json
        raw=json.dumps(data,sort_keys=True,separators=(",",":")).encode("utf8")
        return Response(raw,media_type="application/json",headers={
            "Cache-Control":"private, no-store, max-age=0",
            "Content-Disposition":(
                'attachment; filename="NVP-Film-Reels-'+job_id[:8]+'.json"'),
            "X-Content-Type-Options":"nosniff"})
    route("GET","/{job_id}/manifest",manifest)

    def reel(project_id:str,job_id:str,index:int,request:Request):
        source=_safe(lambda:handler.reel_path(
            project_id,job_id,index,token(request,download=True)))
        return FileResponse(source,media_type="video/x-msvideo",
            filename=f"NVP-Film-Reel-{index+1:05d}.avi",
            content_disposition_type="attachment",
            headers={"Cache-Control":"private, no-store, max-age=0",
                     "X-Content-Type-Options":"nosniff"})
    route("GET","/{job_id}/reels/{index}",reel)
    return handler
