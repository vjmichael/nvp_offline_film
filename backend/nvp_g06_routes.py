"""G06 trusted host routes. Imported by NVP's director API after its normal
project/cookie gate has been installed. No rendering worker permissions here."""
from __future__ import annotations

from fastapi import HTTPException,Request
from fastapi.responses import Response
from pydantic import BaseModel,Field

from backend.nvp_g06_filming import G06Filming
from backend.nvp_g06_native_recorder import G06NativeRecorder

RECORDER=G06NativeRecorder()


class Version(BaseModel):
    expected_revision:int=Field(ge=0,le=1000000)


class Duration(Version):
    seconds:str=Field(min_length=1,max_length=30)


class Event(Version):
    kind:str=Field(min_length=3,max_length=40)
    object_id:str|None=Field(default=None,max_length=40)
    start_seconds:str=Field(min_length=1,max_length=30)
    end_seconds:str=Field(min_length=1,max_length=30)
    target_position:list[float]|None=None
    intensity:float|None=Field(default=None,ge=0,le=10)
    note:str=Field(default="",max_length=1000)


class Retake(Version):
    reason:str=Field(default="retake",max_length=160)

class NoteIdea(BaseModel):
    object_id:str|None=Field(default=None,max_length=40)
    at_seconds:str=Field(min_length=1,max_length=30)
    instructions:str=Field(default="",max_length=750)

class NoteReview(Version):
    decision:str=Field(min_length=6,max_length=6)
    edited_note:str|None=Field(default=None,max_length=400)


class Freeze(Version):
    clip_ids:list[str]=Field(default_factory=list,max_length=32)
    clip_starts:dict[str,str]=Field(default_factory=dict)


class MicrophoneStart(BaseModel):
    actor_id:str|None=Field(default=None,max_length=40)


class MicrophoneSession(BaseModel):
    session_id:str=Field(min_length=32,max_length=32)


class Camera(Version):
    view_index:int=Field(ge=0,le=2)
    focal_mm:float=Field(ge=12,le=180)
    position:list[float]=Field(min_length=3,max_length=3)
    look_at:list[float]=Field(min_length=3,max_length=3)


def _safe(action):
    try:
        return action()
    except KeyError as exc:
        raise HTTPException(404,detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403,detail="This action was not authorized") from exc
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409,detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(503,detail="A required filmmaking component is unavailable") from exc
    except Exception as exc:
        from backend.nvp_idea_pipeline import LocalModelUnavailable
        if isinstance(exc,LocalModelUnavailable):
            raise HTTPException(503,detail="AI assistance is unavailable right now") from exc
        raise


def mount_g06_routes(app,studio,live_films,cookie_name):
    """One native filmmaker surface for encrypted and ordinary projects."""

    def service(pid,request):
        if request.headers.get("x-nvp-director")!="1":
            raise HTTPException(403,detail="Open this action in your film workspace")
        secured=live_films().exists(pid)
        return G06Filming(studio,
            live=live_films() if secured else None,
            token=request.cookies.get(cookie_name) if secured else None)

    # Define one logical operation and register both project storage shapes;
    # the existing middleware makes locked encrypted projects inaccessible.
    def routes(method,tail,fn):
        app.add_api_route(
            "/api/projects/{project_id}/film/"+tail,
            fn,methods=[method],name="g06_"+fn.__name__+"_ordinary")
        app.add_api_route(
            "/api/projects/{project_id}/live/film/"+tail,
            fn,methods=[method],name="g06_"+fn.__name__+"_secured")

    def scene(project_id:str,scene_id:str,request:Request):
        return _safe(lambda:service(project_id,request).view(project_id,scene_id))
    routes("GET","scene/{scene_id}",scene)

    def duration(project_id:str,scene_id:str,request:Request,payload:Duration):
        return _safe(lambda:service(project_id,request).set_duration(
            project_id,scene_id,payload.seconds,payload.expected_revision))
    routes("POST","scene/{scene_id}/duration",duration)

    def event(project_id:str,scene_id:str,request:Request,payload:Event):
        return _safe(lambda:service(project_id,request).add_event(
            project_id,scene_id,
            expected_revision=payload.expected_revision,
            kind=payload.kind,object_id=payload.object_id,
            start_seconds=payload.start_seconds,
            end_seconds=payload.end_seconds,
            target_position=payload.target_position,
            intensity=payload.intensity,note=payload.note))
    routes("POST","scene/{scene_id}/events",event)

    def remove(project_id:str,scene_id:str,event_id:str,request:Request,
               expected_revision:int):
        return _safe(lambda:service(project_id,request).remove_event(
            project_id,scene_id,event_id,expected_revision))
    routes("DELETE","scene/{scene_id}/events/{event_id}",remove)

    def ask_note(project_id:str,scene_id:str,request:Request,payload:NoteIdea):
        return _safe(lambda:service(project_id,request).ask_performance_note(
            project_id,scene_id,object_id=payload.object_id,
            at_seconds=payload.at_seconds,instructions=payload.instructions))
    routes("POST","scene/{scene_id}/notes/suggest",ask_note)

    def review_note(project_id:str,scene_id:str,note_id:str,request:Request,
                    payload:NoteReview):
        return _safe(lambda:service(project_id,request).review_performance_note(
            project_id,scene_id,note_id,payload.decision,payload.expected_revision,
            payload.edited_note))
    routes("POST","scene/{scene_id}/notes/{note_id}/decision",review_note)

    def retake(project_id:str,scene_id:str,request:Request,payload:Retake):
        return _safe(lambda:service(project_id,request).restart_scene(
            project_id,scene_id,payload.expected_revision,payload.reason))
    routes("POST","scene/{scene_id}/retake",retake)

    def mic_start(project_id:str,scene_id:str,request:Request,
                  payload:MicrophoneStart):
        current=_safe(lambda:service(project_id,request).view(project_id,scene_id))
        if payload.actor_id is not None and payload.actor_id not in {
                obj["actor_id"] for obj in current["stage_objects"]
                if obj["role"]=="actor"}:
            raise HTTPException(422,detail="Choose a performer in this scene")
        return _safe(lambda:RECORDER.begin(
            project_id,scene_id,payload.actor_id,request.cookies.get(cookie_name)))
    routes("POST","scene/{scene_id}/microphone/start",mic_start)

    def mic_finish(project_id:str,scene_id:str,request:Request,
                   payload:MicrophoneSession):
        # Bound to the same cookie/session that started the recording.
        return _safe(lambda:RECORDER.finish(
            project_id,payload.session_id,request.cookies.get(cookie_name),
            service(project_id,request)))
    routes("POST","scene/{scene_id}/microphone/finish",mic_finish)

    def mic_cancel(project_id:str,scene_id:str,request:Request,
                   payload:MicrophoneSession):
        return _safe(lambda:RECORDER.cancel(
            project_id,payload.session_id,request.cookies.get(cookie_name)))
    routes("POST","scene/{scene_id}/microphone/cancel",mic_cancel)

    def listen(project_id:str,scene_id:str,clip_id:str,request:Request):
        original=_safe(lambda:service(project_id,request).original_preview(
            project_id,scene_id,clip_id))
        return Response(content=original,media_type="audio/wav",
            headers={"Cache-Control":"private, no-store, max-age=0",
                     "X-Content-Type-Options":"nosniff"})
    routes("GET","scene/{scene_id}/originals/{clip_id}/listen",listen)

    def freeze(project_id:str,scene_id:str,request:Request,payload:Freeze):
        return _safe(lambda:service(project_id,request).freeze_take(
            project_id,scene_id,payload.expected_revision,payload.clip_ids,
        payload.clip_starts))
    routes("POST","scene/{scene_id}/takes",freeze)

    def take(project_id:str,scene_id:str,take_id:str,request:Request):
        return _safe(lambda:service(project_id,request).read_take(
            project_id,scene_id,take_id))
    routes("GET","scene/{scene_id}/takes/{take_id}",take)

    def camera(project_id:str,scene_id:str,take_id:str,request:Request,
               payload:Camera):
        return _safe(lambda:service(project_id,request).change_camera(
            project_id,scene_id,take_id,payload.expected_revision,
            payload.view_index,payload.focal_mm,
            payload.position,payload.look_at))
    routes("PUT","scene/{scene_id}/takes/{take_id}/camera",camera)


def revoke_recording(project_id):
    RECORDER.cancel_project(project_id)
