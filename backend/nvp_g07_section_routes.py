"""Existing director session/CSRF boundary for immutable G07 section decisions."""
from typing import Annotated, Literal
from fastapi import Request, HTTPException, Query, Path
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from backend.nvp_g07_edit import G07Editor
from backend.nvp_g07_sections import EditorialSections
from backend.nvp_g03_live_store import LiveFilmError
from backend.nvp_g03_windows_vault import VaultError

Sha = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$', strict=True)]
Id = Annotated[str, Field(pattern=r'^[a-f0-9]{32}$', strict=True)]
Revision = Annotated[int, Field(ge=1, le=15000, strict=True)]

class Exact(BaseModel):
    model_config=ConfigDict(extra='forbid')

class EditRef(Exact):
    kind: Literal['edit']
    revision: Revision
    digest: Sha

class EditSlice(EditRef):
    first: int=Field(ge=0,le=249,strict=True)
    count: int=Field(ge=1,le=250,strict=True)

class SectionRef(Exact):
    kind: Literal['section']
    section_id: Id
    digest: Sha

class SceneRef(Exact):
    kind: Literal['scene']
    scene_id: str=Field(pattern=r'^(SC_[a-f0-9]{12}|IDEA_[0-9]{3})$',strict=True)
    revision: Revision
    digest: Sha

class Page(Exact):
    selection: EditSlice|EditRef|SectionRef|SceneRef
    after: Id|None=None
    first: int=Field(default=0,ge=0,le=250,strict=True)
    limit: int=Field(default=32,ge=1,le=64,strict=True)

class Composition(Exact):
    title: str=Field(min_length=1,max_length=120,strict=True)
    children: list[Annotated[EditSlice|SectionRef,Field(discriminator='kind')]]=Field(min_length=1,max_length=64)

class Publish(Composition):
    digest: Sha

class Activation(Exact):
    section_id: Id
    digest: Sha
    expected_revision: int=Field(ge=0,le=15000,strict=True)

class Activate(Activation):
    approval_digest: Sha


class ActivePage(Exact):
    revision: Revision
    digest: Sha
    first: int=Field(default=0,ge=0,le=64**3*250-1,strict=True)
    limit: int=Field(default=32,ge=1,le=64,strict=True)


class RecoveryRequest(Exact):
    section_id: Id
    revision: Revision

class MediaScope(Exact):
    revision: Revision
    digest: Sha

class FeatureOperation(MediaScope):
    operation_id: Id

class FeatureStop(Exact):
    operation_id: Id

class PictureRequest(MediaScope):
    tick: str=Field(pattern=r'^(0|[1-9][0-9]{0,18})$',strict=True)

class ClipRequest(MediaScope):
    first_frame: int=Field(ge=0,le=259199,strict=True)
    frame_count: int=Field(ge=1,le=240,strict=True)

class ClipCopy(MediaScope):
    reel_id: Id

class SoundRequest(MediaScope):
    start_tick: str=Field(pattern=r'^(0|[1-9][0-9]{0,18})$',strict=True)
    duration_tick: str=Field(pattern=r'^[1-9][0-9]{0,10}$',strict=True)


def mount_section_routes(app, get_studio, live_films, film_access, cookie_name):
    def service(pid,request):
        if request.headers.get('x-nvp-director')!='1':raise HTTPException(403,'Open this action in your film workspace')
        live=live_films();secured=live.exists(pid)
        native_path='/live/edit/sections' in request.url.path
        if native_path!=secured:raise HTTPException(403,'Use the correct film workspace')
        token=request.cookies.get(cookie_name)
        def guard():
            if not film_access().permitted(pid,token):raise HTTPException(423,'Movie locked')
        guard()
        # Protected content is never opened through the shared Studio index.
        return EditorialSections(G07Editor(get_studio(),live=live if secured else None,token=token if secured else None),access_guard=guard)

    def respond(pid,request,action):
        try:
            result=action(service(pid,request))
            if not film_access().permitted(pid,request.cookies.get(cookie_name)):raise HTTPException(423,'Movie locked')
            if isinstance(result,Response):return result
            if isinstance(result,bytes):
                return Response(content=result,media_type='audio/wav',headers={'Cache-Control':'private, no-store, max-age=0','X-Content-Type-Options':'nosniff','Content-Disposition':'inline'})
            return JSONResponse(result,headers={'Cache-Control':'private, no-store, max-age=0'})
        except (LiveFilmError,VaultError,PermissionError) as exc:raise HTTPException(403,'This film action was not authorized') from exc
        except KeyError as exc:raise HTTPException(404,'The selected original was not found') from exc
        except ValueError as exc:raise HTTPException(422,'The selected section is not supported') from exc
        except RuntimeError as exc:raise HTTPException(409,'The original edit or section has changed. Reopen it.') from exc
        except OSError as exc:raise HTTPException(409,'The selected local storage is not available. Existing movie data was preserved.') from exc

    def directory(project_id:str,request:Request,family:Literal['scenes','takes','edits','sections'],after:str|None=Query(default=None,max_length=40),limit:int=Query(default=32,ge=1,le=64)):
        if family=='edits' and after is not None:
            if not after.isascii() or not after.isdecimal() or len(after)>5:raise HTTPException(422,'Invalid page')
            after=int(after)
        return respond(project_id,request,lambda s:s.directory(project_id,family,after,limit))
    def page(project_id:str,request:Request,payload:Page):
        return respond(project_id,request,lambda s:s.page(project_id,payload.selection.model_dump(),payload.first,payload.limit,payload.after))
    def preview(project_id:str,request:Request,payload:Composition):
        return respond(project_id,request,lambda s:s.preview(project_id,payload.title,[x.model_dump() for x in payload.children]))
    def publish(project_id:str,request:Request,payload:Publish):
        return respond(project_id,request,lambda s:s.publish(project_id,payload.title,[x.model_dump() for x in payload.children],payload.digest))
    def preview_activation(project_id:str,request:Request,payload:Activation):
        return respond(project_id,request,lambda s:s.preview_activation(project_id,payload.section_id,payload.digest,payload.expected_revision))
    def activate(project_id:str,request:Request,payload:Activate):
        return respond(project_id,request,lambda s:s.activate(project_id,payload.section_id,payload.digest,payload.expected_revision,payload.approval_digest))
    def preview_paged(project_id:str,request:Request,payload:Activation):
        return respond(project_id,request,lambda s:s.preview_paged(project_id,payload.section_id,payload.digest,payload.expected_revision))
    def activate_paged(project_id:str,request:Request,payload:Activate):
        return respond(project_id,request,lambda s:s.activate_paged(project_id,payload.section_id,payload.digest,payload.expected_revision,payload.approval_digest))
    def active_page(project_id:str,request:Request,payload:ActivePage):
        return respond(project_id,request,lambda s:s.active_page(project_id,payload.revision,payload.digest,payload.first,payload.limit))
    def picture(project_id:str,request:Request,payload:PictureRequest):
        from backend.nvp_g07_preview import paged_picture
        return respond(project_id,request,lambda s:paged_picture(s,project_id,payload.revision,payload.digest,int(payload.tick)))
    def sound(project_id:str,request:Request,payload:SoundRequest):
        from backend.nvp_g07_preview import paged_sound
        return respond(project_id,request,lambda s:paged_sound(s,project_id,payload.revision,payload.digest,int(payload.start_tick),int(payload.duration_tick)))
    def delivery_review(project_id:str,request:Request,payload:MediaScope):
        from backend.nvp_g07_paged_media import delivery_plan
        return respond(project_id,request,lambda s:delivery_plan(s,project_id,payload.revision,payload.digest))
    def storage_review(project_id:str,request:Request,after:Id|None=None):
        from backend.nvp_g07_storage_migration import storage_status
        return respond(project_id,request,lambda s:storage_status(s,project_id,after))
    def recover(project_id:str,request:Request,payload:RecoveryRequest):
        from backend.nvp_g07_recovery_dialog import recover_with_dialog
        # A normal loopback webpage cannot nominate an arbitrary filesystem
        # path or approve recovery; the installed native dialog owns both.
        origin=request.headers.get('origin')
        if request.headers.get('sec-fetch-site')!='same-origin' or origin!=f"{request.url.scheme}://{request.url.netloc}" or request.url.hostname!='127.0.0.1':
            raise HTTPException(403,'Open the installed protected movie workspace')
        dialog=getattr(request.app.state,'nvp_editorial_recovery_dialog',None)
        return respond(project_id,request,lambda s:recover_with_dialog(s,project_id,payload.section_id,payload.revision,origin,dialog))
    def native_origin(request):
        origin=request.headers.get('origin')
        if request.headers.get('sec-fetch-site')!='same-origin' or origin!=f"{request.url.scheme}://{request.url.netloc}" or request.url.hostname!='127.0.0.1':raise HTTPException(403,'Open the installed protected workspace')
        return origin,getattr(request.app.state,'nvp_editorial_recovery_dialog',None)
    def review_clip(project_id:str,request:Request,payload:ClipRequest):
        from backend.nvp_g07_recovery_dialog import review_clip_with_dialog
        origin,dialog=native_origin(request)
        return respond(project_id,request,lambda s:review_clip_with_dialog(s,project_id,payload.revision,payload.digest,payload.first_frame,payload.frame_count,origin,dialog))
    def clips(project_id:str,request:Request,payload:MediaScope,after:Id|None=None):
        from backend.nvp_g07_review_reels import list_reels
        return respond(project_id,request,lambda s:list_reels(s,project_id,payload.revision,payload.digest,after))
    def backup(project_id:str,request:Request):
        from backend.nvp_g07_recovery_dialog import backup_with_dialog
        origin,dialog=native_origin(request)
        return respond(project_id,request,lambda s:backup_with_dialog(s,project_id,origin,dialog))
    def restore_copy(project_id:str,request:Request):
        from backend.nvp_g07_recovery_dialog import backup_with_dialog
        origin,dialog=native_origin(request)
        return respond(project_id,request,lambda s:backup_with_dialog(s,project_id,origin,dialog,restore=True))
    def copy_clip(project_id:str,request:Request,payload:ClipCopy):
        from backend.nvp_g07_recovery_dialog import copy_clip_with_dialog
        origin,dialog=native_origin(request)
        return respond(project_id,request,lambda s:copy_clip_with_dialog(s,project_id,payload.revision,payload.digest,payload.reel_id,origin,dialog))
    def optimize(project_id:str,request:Request):
        from backend.nvp_g07_recovery_dialog import optimize_recording_with_dialog
        origin,dialog=native_origin(request)
        return respond(project_id,request,lambda s:optimize_recording_with_dialog(s,project_id,origin,dialog))
    def optimize_edits(project_id:str,request:Request):
        from backend.nvp_g07_recovery_dialog import optimize_payloads_with_dialog
        origin,dialog=native_origin(request)
        return respond(project_id,request,lambda s:optimize_payloads_with_dialog(s,project_id,origin,dialog,'edl'))
    def optimize_scenes(project_id:str,request:Request):
        from backend.nvp_g07_recovery_dialog import optimize_payloads_with_dialog
        origin,dialog=native_origin(request)
        return respond(project_id,request,lambda s:optimize_payloads_with_dialog(s,project_id,origin,dialog,'take'))
    def feature_step(project_id:str,request:Request,payload:FeatureOperation):
        from backend.nvp_g07_recovery_dialog import feature_step_with_dialog
        origin,dialog=native_origin(request)
        return respond(project_id,request,lambda s:feature_step_with_dialog(s,project_id,payload.revision,payload.digest,payload.operation_id,origin,dialog))
    def feature_stop(project_id:str,request:Request,payload:FeatureStop):
        from backend.nvp_g07_recovery_dialog import NativeRecoveryDialog
        origin,dialog=native_origin(request)
        if type(dialog) is not NativeRecoveryDialog or request.headers.get('x-nvp-director')!='1':raise HTTPException(403,'Open the installed protected movie workspace')
        token=request.cookies.get(cookie_name)
        def guard():
            if not film_access().permitted(project_id,token):raise HTTPException(423,'Movie locked')
        return JSONResponse({'project_id':project_id,'operation_id':payload.operation_id,'stop_requested':dialog.stop_feature(project_id,origin,guard,token,payload.operation_id)},headers={'Cache-Control':'private, no-store, max-age=0'})
    def feature_status(project_id:str,request:Request,payload:FeatureStop):
        from backend.nvp_g07_recovery_dialog import NativeRecoveryDialog
        origin,dialog=native_origin(request)
        if type(dialog) is not NativeRecoveryDialog or request.headers.get('x-nvp-director')!='1':raise HTTPException(403,'Open the installed protected movie workspace')
        token=request.cookies.get(cookie_name)
        def guard():
            if not film_access().permitted(project_id,token):raise HTTPException(423,'Movie locked')
        return JSONResponse({'project_id':project_id,'operation_id':payload.operation_id,**dialog.feature_status(project_id,origin,guard,token,payload.operation_id)},headers={'Cache-Control':'private, no-store, max-age=0'})
    def playback_access(pid,request,s):
        from backend.nvp_g07_recovery_dialog import NativeRecoveryDialog
        origin=f"{request.url.scheme}://{request.url.netloc}"
        dialog=getattr(request.app.state,'nvp_editorial_recovery_dialog',None)
        if (type(dialog) is not NativeRecoveryDialog or request.url.hostname!='127.0.0.1' or
            request.headers.get('sec-fetch-site')!='same-origin' or request.headers.get('origin',origin)!=origin):
            raise HTTPException(403,'Open the installed protected movie workspace')
        previous=s.access_guard
        s.access_guard=lambda:dialog._check(pid,origin,previous)
        s.access_guard()
        return s
    def playback_timeline(project_id:str,revision:Annotated[int,Path(ge=1,le=15000)],digest:Sha,job:Sha,request:Request):
        from backend.nvp_g07_feature_playback import timeline
        return respond(project_id,request,lambda s:timeline(playback_access(project_id,request,s),project_id,revision,digest,job))
    def playback_frames(project_id:str,revision:Annotated[int,Path(ge=1,le=15000)],digest:Sha,job:Sha,request:Request,start_frame:int=Query(ge=0,le=259199),count:int=Query(ge=1,le=12)):
        from backend.nvp_g07_feature_playback import pictures
        return respond(project_id,request,lambda s:pictures(playback_access(project_id,request,s),project_id,revision,digest,job,start_frame,count))
    def playback_sound(project_id:str,revision:Annotated[int,Path(ge=1,le=15000)],digest:Sha,job:Sha,request:Request,start_sample:int=Query(ge=0,le=518399999),count:int=Query(ge=1,le=24000)):
        from backend.nvp_g07_feature_playback import sound
        def action(s):
            raw,headers=sound(playback_access(project_id,request,s),project_id,revision,digest,job,start_sample,count)
            return Response(raw,media_type='audio/wav',headers={**headers,'Cache-Control':'private, no-store, max-age=0','X-Content-Type-Options':'nosniff'})
        return respond(project_id,request,action)
    def playback_paired(project_id:str,revision:Annotated[int,Path(ge=1,le=15000)],digest:Sha,job:Sha,request:Request,start_sample:int=Query(ge=0,le=518399999),count:int=Query(ge=1,le=24000)):
        from backend.nvp_g07_feature_playback import paired
        return respond(project_id,request,lambda s:paired(playback_access(project_id,request,s),project_id,revision,digest,job,start_sample,count))
    def inventory_page(project_id:str,request:Request,family:Literal['takes','recordings'],after:Id|None=None,limit:int=Query(default=32,ge=1,le=64)):
        from backend.nvp_g07_feature_playback import inventory
        return respond(project_id,request,lambda s:inventory(playback_access(project_id,request,s),project_id,family,after,limit))
    for suffix,handler in [('timeline',playback_timeline),('frames',playback_frames),('sound',playback_sound),('paired',playback_paired)]:
        app.add_api_route('/api/projects/{project_id}/live/edit/sections/playback/{revision}/{digest}/{job}/'+suffix,handler,methods=['GET'],name='perf03g_'+handler.__name__)
    app.add_api_route('/api/projects/{project_id}/live/edit/sections/media-inventory',inventory_page,methods=['GET'],name='perf03g_media_inventory')
    for suffix,handler in [('/feature-step',feature_step),('/feature-stop',feature_stop),('/feature-status',feature_status),('/review-clip',review_clip),('/review-clips',clips),('/copy-review-clip',copy_clip),('/create-backup',backup),('/restore-copy',restore_copy),('/optimize-recording',optimize),('/optimize-edits',optimize_edits),('/optimize-scenes',optimize_scenes)]:
        app.add_api_route('/api/projects/{project_id}/live/edit/sections'+suffix,handler,methods=['POST'],name='perf03g_protected_'+handler.__name__)
    for prefix,tag in [('edit','ordinary'),('live/edit','protected')]:
        for method,suffix,handler in [('GET','',directory),('POST','/page',page),('POST','/preview',preview),('POST','/save',publish),('POST','/activation-preview',preview_activation),('POST','/activate',activate),('POST','/paged-activation-preview',preview_paged),('POST','/paged-activate',activate_paged),('POST','/active-page',active_page),('POST','/picture',picture),('POST','/sound',sound),('POST','/delivery-review',delivery_review),('GET','/storage-review',storage_review)]:
            app.add_api_route('/api/projects/{project_id}/'+prefix+'/sections'+suffix,handler,methods=[method],name=f'perf03g_{tag}_{handler.__name__}')

    app.add_api_route('/api/projects/{project_id}/live/edit/sections/recover',recover,methods=['POST'],name='perf03g_protected_editorial_recovery')
