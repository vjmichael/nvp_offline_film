"""G09-F distribution, portable film library and continuous verified playback.

All endpoints are bound to the existing project lock gate. No arbitrary
host path, shell command, untrusted executable, network download or extra
model authority. Import accepts ONLY a director-selected streamed file.
A film is not advertised as available until all archive reels validate.
"""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import re
from zipfile import BadZipFile

from fastapi import HTTPException,Request
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel
from backend.nvp_g09f_distribution import G09FDistribution
from backend.nvp_g09f_package import MAX_PACKAGE_BYTES

class DirectorConfirmation(BaseModel):
    director_confirmed:bool

def _safe(fn):
    try:return fn()
    except KeyError as exc:
        raise HTTPException(404,detail="The selected finished film was not found") from exc
    except PermissionError as exc:
        raise HTTPException(403,detail=str(exc)) from exc
    except (ValueError,BadZipFile) as exc:
        raise HTTPException(422,detail=str(exc)) from exc
    except (RuntimeError,OSError) as exc:
        raise HTTPException(409,detail=str(exc)) from exc

def mount_g09f_routes(app,long_delivery,studio,film_access,live_films,
                      cookie_name):
    service=G09FDistribution(long_delivery,studio,access=film_access,
        protected_movie=live_films)
    reader=service.reader

    def owner(project_id,request,*,download=False):
        if download:
            if request.headers.get("sec-fetch-site") not in (
                None,"same-origin","none"):
                raise HTTPException(403,detail="Open your distributed film in NVP")
        elif request.headers.get("x-nvp-director")!="1":
            raise HTTPException(403,detail="Open your film distribution workspace")
        token=request.cookies.get(cookie_name)
        _safe(lambda:service._auth(project_id,token))
        return token

    def add(method,tail,fn):
        # For protected movie routes, the existing API allowlist admits
        # only 'live/...' paths. The service independently refuses plaintext
        # publication from any G03-protected film even with an unlock token.
        for protected in (False,True):
            prefix="/api/projects/{project_id}"+(
                "/live" if protected else "")
            app.add_api_route(prefix+tail,fn,methods=[method],
                name="g09f_"+fn.__name__+
                    ("_live" if protected else "_ordinary"))

    def packages(project_id:str,job_id:str,request:Request):
        token=owner(project_id,request)
        return _safe(lambda:service.status(project_id,job_id,token))
    add("GET","/long-film/{job_id}/package",packages)

    def package_start(project_id:str,job_id:str,request:Request,
                      payload:DirectorConfirmation):
        if payload.director_confirmed is not True:
            raise HTTPException(422,detail="Choose Package Film yourself")
        token=owner(project_id,request)
        return _safe(lambda:service.start(project_id,job_id,token))
    add("POST","/long-film/{job_id}/package",package_start)

    def package_stop(project_id:str,job_id:str,request:Request,
                     payload:DirectorConfirmation):
        if payload.director_confirmed is not True:
            raise HTTPException(422,detail="Choose Stop Packaging yourself")
        token=owner(project_id,request)
        return _safe(lambda:service.cancel(project_id,job_id,token))
    add("POST","/long-film/{job_id}/package/stop",package_stop)

    def package_download(project_id:str,job_id:str,request:Request):
        token=owner(project_id,request,download=True)
        path=_safe(lambda:service.file(project_id,job_id,token))
        return FileResponse(path,media_type="application/octet-stream",
            filename="NVP-Film-"+job_id[:8]+".nvpfilm",
            content_disposition_type="attachment",
            headers={"Cache-Control":"private, no-store, max-age=0",
                     "X-Content-Type-Options":"nosniff"})
    add("GET","/long-film/{job_id}/package/file",package_download)

    def library_list(project_id:str,request:Request):
        token=owner(project_id,request)
        return {"format":"nvp.g09f.film_library.v1",
            "films":_safe(lambda:service.library(project_id,token))}
    add("GET","/film-library",library_list)

    async def import_film(project_id:str,request:Request):
        token=owner(project_id,request)
        if request.headers.get("content-type","").split(";")[0].strip().lower()!=(
                "application/x-nvpfilm"):
            raise HTTPException(415,detail="Select a genuine .nvpfilm package")
        incoming_length=request.headers.get("content-length")
        if incoming_length is not None:
            try:size=int(incoming_length)
            except ValueError:raise HTTPException(
                422,detail="The selected film has no valid file length")
            if not 1024<=size<=MAX_PACKAGE_BYTES:
                raise HTTPException(413,detail="Film package is outside size limits")
        target=_safe(lambda:service.upload_target(project_id,token))
        copied=0
        try:
            with open(target,"xb",buffering=0) as sink:
                async for part in request.stream():
                    if not part:continue
                    copied+=len(part)
                    if copied>MAX_PACKAGE_BYTES:
                        raise HTTPException(413,detail="Imported film exceeds its original media budget")
                    if not film_access().permitted(
                            project_id,token,renew=False):
                        raise HTTPException(423,detail="Film was locked during import")
                    # ASGI chunk size is not a trusted memory bound.
                    # Split even an oversized provided chunk into fixed 1MiB
                    # slices and write synchronously to the owned temp file.
                    for offset in range(0,len(part),1024*1024):
                        sink.write(part[offset:offset+1024*1024])
                sink.flush();os.fsync(sink.fileno())
            if copied<1024:
                raise HTTPException(422,detail="The selected film package is incomplete")
            # Import/re-hash is performed off the event-loop. If the browser
            # goes away, unverified staged bytes are never published.
            result=await asyncio.to_thread(service.import_uploaded,
                project_id,token,target)
            return result
        finally:
            if target.exists() and not target.is_symlink():
                target.unlink()
    add("POST","/film-library/import",import_film)

    def _completed(project_id,job_id,request):
        token=owner(project_id,request)
        return _safe(lambda:service.completed_source(project_id,job_id,token))
    def _imported(project_id,film_id,request):
        token=owner(project_id,request)
        return _safe(lambda:service.library_source(project_id,film_id,token))

    def _timeline(folder,manifest):
        return _safe(lambda:reader.timeline(folder,manifest))

    def original_timeline(project_id:str,job_id:str,request:Request):
        folder,manifest=_completed(project_id,job_id,request)
        return _timeline(folder,manifest)
    add("GET","/long-film/{job_id}/watch/timeline",original_timeline)

    def imported_timeline(project_id:str,film_id:str,request:Request):
        folder,manifest=_imported(project_id,film_id,request)
        return _timeline(folder,manifest)
    add("GET","/film-library/{film_id}/watch/timeline",imported_timeline)

    def _pictures(folder,manifest,start_frame,count):
        return _safe(lambda:reader.pictures(folder,manifest,start_frame,count))
    def original_frames(project_id:str,job_id:str,request:Request,
                        start_frame:int=0,count:int=12):
        folder,manifest=_completed(project_id,job_id,request)
        return _pictures(folder,manifest,start_frame,count)
    add("GET","/long-film/{job_id}/watch/frames",original_frames)

    def imported_frames(project_id:str,film_id:str,request:Request,
                        start_frame:int=0,count:int=12):
        folder,manifest=_imported(project_id,film_id,request)
        return _pictures(folder,manifest,start_frame,count)
    add("GET","/film-library/{film_id}/watch/frames",imported_frames)

    def _sound(folder,manifest,start_sample,count):
        wav,receipt=_safe(lambda:reader.sound(
            folder,manifest,start_sample,count))
        return Response(content=wav,media_type="audio/wav",
            headers={"Cache-Control":"private, no-store, max-age=0",
                "X-Content-Type-Options":"nosniff",
                "X-NVP-Audio-Start-Sample":str(receipt["start_sample"]),
                "X-NVP-Audio-Samples":str(receipt["sample_count"]),
                "X-NVP-Source-SHA256":receipt["source_sha256"]})
    def original_sound(project_id:str,job_id:str,request:Request,
                       start_sample:int=0,count:int=24000):
        folder,manifest=_completed(project_id,job_id,request)
        return _sound(folder,manifest,start_sample,count)
    add("GET","/long-film/{job_id}/watch/sound",original_sound)

    def imported_sound(project_id:str,film_id:str,request:Request,
                       start_sample:int=0,count:int=24000):
        folder,manifest=_imported(project_id,film_id,request)
        return _sound(folder,manifest,start_sample,count)
    add("GET","/film-library/{film_id}/watch/sound",imported_sound)
    return service
