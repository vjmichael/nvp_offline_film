"""G09-D director-controlled picture/audio finishing and delivery readiness.

No browser/AI command may approve its own finished film or request unreviewed
codecs. The existing G03 movie unlock gate and per-project director access
remain authoritative. Cinema-preflight is a genuine fail-closed diagnostic,
not a DCP encoder.
"""
from __future__ import annotations
from fastapi import HTTPException,Request
from pydantic import BaseModel,Field

from backend.nvp_g09d_finishing import G09DFinishing

class FinishChange(BaseModel):
    expected_revision:int=Field(ge=0,le=2500)
    section:str=Field(min_length=5,max_length=12)
    details:dict

class FinishReview(BaseModel):
    expected_revision:int=Field(ge=1,le=2500)

class FinishRestore(BaseModel):
    expected_revision:int=Field(ge=0,le=2500)
    source_revision:int=Field(ge=1,le=2500)

def _safe(job):
    try:return job()
    except PermissionError as exc:
        raise HTTPException(403,detail="Unlock your movie to finish it") from exc
    except KeyError as exc:
        raise HTTPException(404,detail="That finishing version is unavailable") from exc
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409,detail=str(exc)) from exc

def _dcp_gate():
    # An actual SMPTE DCP Bv2.1 must have independently verified
    # cinema XYZ J2K/MXF picture, PCM MXF, CPL/PKL/ASSETMAP/VOLINDEX
    # and a validated approved compliance profile. Native AVI cannot
    # satisfy these merely by renaming it or emitting XML placeholders.
    return {"format":"nvp.g09d.dcp_gate.v1",
        "status":"not_available","can_export_dcp":False,
        "independent_dcp_compliance_verified":False,
        "working_movie_profile":"640x360_24fps_srgb_mjpeg_pcm16",
        "missing":[
            "Genuine cinema XYZ 12-bit JPEG2000 picture frames",
            "SMPTE-compliant picture and sound MXF wrapping",
            "24-bit calibrated cinema audio mastering and channel layout",
            "Correct CPL, PKL, ASSETMAP, VOLINDEX and intrinsic asset hashes",
            "SMPTE DCP Bv2.1 packaging and independent DcpDoctor review",
            "Calibrated projector playback, cinema loudness and human approval"
        ],
        "source_media_preserved":True,
        "never_mislabel_an_avi_as_a_cinema_package":True}

def mount_g09d_routes(app,studio,live_films,cookie_name):
    def service(pid,request):
        if request.headers.get("x-nvp-director")!="1":
            raise HTTPException(403,detail="Open Export Film to finish your movie")
        secured=live_films().exists(pid)
        return G09DFinishing(studio,live_films() if secured else None,
            request.cookies.get(cookie_name) if secured else None)

    def route(method,tail,handler):
        for protected,namespace in ((False,"finish"),(True,"live/finish")):
            app.add_api_route(
                "/api/projects/{project_id}/"+namespace+tail,
                handler,methods=[method],
                name="g09d_"+handler.__name__+
                ("_protected" if protected else "_ordinary"))

    def view(project_id:str,request:Request):
        return _safe(lambda:service(project_id,request).view(project_id))
    route("GET","",view)

    def change(project_id:str,request:Request,payload:FinishChange):
        return _safe(lambda:service(project_id,request).change(
            project_id,payload.expected_revision,
            payload.section,payload.details))
    route("POST","/change",change)

    def approve(project_id:str,request:Request,payload:FinishReview):
        return _safe(lambda:service(project_id,request).approve(
            project_id,payload.expected_revision))
    route("POST","/approve",approve)

    def restore(project_id:str,request:Request,payload:FinishRestore):
        return _safe(lambda:service(project_id,request).restore(
            project_id,payload.expected_revision,payload.source_revision))
    route("POST","/restore",restore)

    def dcp(project_id:str,request:Request):
        # Check locked project/session before even explaining its
        # export capabilities; do not leak private movie existence.
        _safe(lambda:service(project_id,request).view(project_id))
        return _dcp_gate()
    route("GET","/cinema-readiness",dcp)
