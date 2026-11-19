"""W1-G: narrow per-window pywebview JavaScript IPC surface.

pywebview recursively walks public attributes when constructing the JS
bridge. Do NOT expose TrustedDesktopCameraBridge directly: its public
window and FilmIndex references reach cyclic GUI/SQLite object graphs and
deadlock the Windows WebView2 'before_load' event.

The proxy holds the original trusted bridge in one PRIVATE slot. Every
public attribute is an explicitly reviewed, bound method with the original
argument signature. All authorization, origin verification, transaction
scope, lifecycle and cancellation remain in the original native bridge.
No object, path, subprocess, callback or opaque handle is exposed.
"""
from __future__ import annotations

from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


class NativeWebviewIPCSurface:
    __slots__ = ("_delegate",)

    def __init__(self, delegate: TrustedDesktopCameraBridge):
        if type(delegate) is not TrustedDesktopCameraBridge:
            raise TypeError("Native per-window camera bridge required")
        self._delegate = delegate

    def wo6_retake_execute(self, request):
        return self._delegate.wo6_retake_execute(request)

    def wo6_retake_cancel(self, project_id, request_id):
        return self._delegate.wo6_retake_cancel(project_id, request_id)

    def wo6_retake_recover(self, project_id):
        return self._delegate.wo6_retake_recover(project_id)

    def wo6_plan_catalog(self, project_id):
        return self._delegate.wo6_plan_catalog(project_id)

    def wo6_plan_preview(self, request):
        return self._delegate.wo6_plan_preview(request)

    def wo6_plan_save(self, request):
        return self._delegate.wo6_plan_save(request)

    def wo6_plan_read(self, project_id, plan_id):
        return self._delegate.wo6_plan_read(project_id, plan_id)

    def wo5_review_catalog(self, project_id):
        return self._delegate.wo5_review_catalog(project_id)

    def wo5_review_read_intent(self, project_id, intent_id):
        return self._delegate.wo5_review_read_intent(project_id, intent_id)

    def wo5_review_save_intent(self, payload):
        return self._delegate.wo5_review_save_intent(payload)

    def wo5_review_feature_page(self, project_id, feature_id, first=0, kind="source"):
        return self._delegate.wo5_review_feature_page(project_id,feature_id,first,kind)

    def wo5_review_inspect_feature(self, project_id, feature_id):
        return self._delegate.wo5_review_inspect_feature(project_id, feature_id)

    def wo5_review_save_observations(self, payload):
        return self._delegate.wo5_review_save_observations(payload)

    def wo5_film_capabilities(self):
        return self._delegate.wo5_film_capabilities()

    def wo5_film_begin(self, project_id, feature_id, single_reel=False):
        return self._delegate.wo5_film_begin(project_id, feature_id, single_reel)

    def wo5_film_frame(self, session_id, frame_index):
        return self._delegate.wo5_film_frame(session_id, frame_index)

    def wo5_film_window(self, session_id, first_frame, count=4):
        return self._delegate.wo5_film_window(session_id, first_frame, count)

    def wo5_film_stop(self, session_id):
        return self._delegate.wo5_film_stop(session_id)

    # Source camera stills are deliberately RETIRED and fail closed in host.
    def camera_render_capabilities(self):
        return self._delegate.camera_render_capabilities()

    def request_camera_still(self, payload):
        return self._delegate.request_camera_still(payload)

    def poll_camera_still(self, ticket_id):
        return self._delegate.poll_camera_still(ticket_id)

    def cancel_camera_still(self, ticket_id):
        return self._delegate.cancel_camera_still(ticket_id)

    # CONV-12: the recovered original camera/ActorID director panel mounts
    # inside the ACTUAL installed WebView2. Do not expose the full trusted
    # bridge (its public window/FilmIndex graph deadlocks pywebview). Forward
    # ONLY these 15 reviewed methods consumed by the original director UI.
    # Project/origin checks, native dialogs, one-use creator authorization,
    # durable rail journals and source custody stay on the delegate.
    # This never grants a Take, film master, PNG path or browser authority.
    def camfx03_camera_sources(self, project_id):
        return self._delegate.camfx03_camera_sources(project_id)

    def camfx03_draft_catalog(self, project_id):
        return self._delegate.camfx03_draft_catalog(project_id)

    def film03_actor_catalog(self, project_id):
        return self._delegate.film03_actor_catalog(project_id)

    def film02md_architecture_catalog(self, project_id):
        return self._delegate.film02md_architecture_catalog(project_id)

    def film01c_texture_catalog(self, project_id):
        return self._delegate.film01c_texture_catalog(project_id)

    def film03_actor_profile(self, project_id, actor_id):
        return self._delegate.film03_actor_profile(project_id, actor_id)

    def camfx03_draft_create(self, request):
        return self._delegate.camfx03_draft_create(request)

    def camfx03_draft_reopen(self, request):
        return self._delegate.camfx03_draft_reopen(request)

    def camfx03_draft_save(self, request):
        return self._delegate.camfx03_draft_save(request)

    def camfx03_draft_undo(self, request):
        return self._delegate.camfx03_draft_undo(request)

    def camfx03_draft_publish(self, request):
        return self._delegate.camfx03_draft_publish(request)

    def camfx03_draft_discard(self, request):
        return self._delegate.camfx03_draft_discard(request)

    def camfx03_draft_recover_publish(self, request):
        return self._delegate.camfx03_draft_recover_publish(request)

    def film03_actor_profile_publish(self, request):
        return self._delegate.film03_actor_profile_publish(request)

    def data_av_import_original_mesh_texture(self, request):
        return self._delegate.data_av_import_original_mesh_texture(request)

    # Source PCM and digital takes. The JS caller never provides native paths.
    def data_av_import_original_audio(self, project_id, source_id):
        return self._delegate.data_av_import_original_audio(project_id, source_id)

    def data_av_freeze_timed_take(self, request):
        return self._delegate.data_av_freeze_timed_take(request)

    def data_av_catalog(self, project_id):
        return self._delegate.data_av_catalog(project_id)

    def data_av_begin(self, request):
        return self._delegate.data_av_begin(request)

    def data_av_audio_window(self, session_id, first_sample, count):
        return self._delegate.data_av_audio_window(session_id, first_sample, count)

    def data_av_scene_at(self, session_id, tick):
        return self._delegate.data_av_scene_at(session_id, tick)

    def data_av_stop(self, session_id):
        return self._delegate.data_av_stop(session_id)

    # Immutable source -> edited-film derivative, NOT film master approval.
    def data_av_edited_30s_catalog(self, project_id):
        return self._delegate.data_av_edited_30s_catalog(project_id)

    def data_av_edited_30s_preflight(self, project_id, edit_id, edit_revision):
        return self._delegate.data_av_edited_30s_preflight(
            project_id, edit_id, edit_revision)

    def data_av_edited_30s_begin(self, request):
        return self._delegate.data_av_edited_30s_begin(request)

    def data_av_edited_30s_poll(self, ticket):
        return self._delegate.data_av_edited_30s_poll(ticket)

    def data_av_edited_30s_cancel(self, ticket):
        return self._delegate.data_av_edited_30s_cancel(ticket)

    # P1-D original slate source edit: no browser edit mutation without OS grant.
    def data_av_film_stage_graph_catalog(self, project_id):
        return self._delegate.data_av_film_stage_graph_catalog(project_id)

    def data_av_film_stage_edit_draft(self, request):
        return self._delegate.data_av_film_stage_edit_draft(request)

    def data_av_film_stage_edit_commit(self, request):
        return self._delegate.data_av_film_stage_edit_commit(request)

    # P1-D/E/F/P2: tightly bounded source-only editorial and sound stages.
    # All writes use the host's original native OS approval, not JS.
    def data_av_film_stage_catalog(self, project_id):
        return self._delegate.data_av_film_stage_catalog(project_id)

    def data_av_film_stage_director_commit(self, request):
        return self._delegate.data_av_film_stage_director_commit(request)

    def data_av_film_stage_actor_bus_commit(self, request):
        return self._delegate.data_av_film_stage_actor_bus_commit(request)

    def data_av_film_stage_longform_publish(self, request):
        return self._delegate.data_av_film_stage_longform_publish(request)

    def data_av_film_stage_longform_page(self, request):
        return self._delegate.data_av_film_stage_longform_page(request)

    def data_av_film_stage_longform_audit_page(self, request):
        return self._delegate.data_av_film_stage_longform_audit_page(request)

    def data_av_film_stage_chunk_preflight(self, request):
        return self._delegate.data_av_film_stage_chunk_preflight(request)

    def data_av_film_stage_chunk_begin(self, request):
        return self._delegate.data_av_film_stage_chunk_begin(request)

    def data_av_film_stage_chunk_poll(self, ticket):
        return self._delegate.data_av_film_stage_chunk_poll(ticket)

    def data_av_film_stage_chunk_cancel(self, ticket):
        return self._delegate.data_av_film_stage_chunk_cancel(ticket)

    # P1-B: registered source GLB mesh inventory and new 3D cast source.
    def data_av_actor_asset_catalog(self, project_id):
        return self._delegate.data_av_actor_asset_catalog(project_id)

    def data_av_actor_scene_cast(self, request):
        return self._delegate.data_av_actor_scene_cast(request)

    # P1-B/C: reviewed, narrow ActorID + original dialogue IPC.
    def data_av_actor_cast(self, project_id):
        return self._delegate.data_av_actor_cast(project_id)

    def data_av_actor_register(self, request):
        return self._delegate.data_av_actor_register(request)

    def data_av_actor_dialogue_bind(self, request):
        return self._delegate.data_av_actor_dialogue_bind(request)

    def data_av_actor_dialogue_at(self, request):
        return self._delegate.data_av_actor_dialogue_at(request)

    # Explicit original audio/scene capture and sealed Take lifecycle.
    def data_av_capture_catalog(self, project_id):
        return self._delegate.data_av_capture_catalog(project_id)

    def data_av_capture_devices(self):
        return self._delegate.data_av_capture_devices()

    def data_av_capture_begin(self, request):
        return self._delegate.data_av_capture_begin(request)

    def data_av_capture_status(self):
        return self._delegate.data_av_capture_status()

    def data_av_capture_finish(self):
        return self._delegate.data_av_capture_finish()

    def data_av_capture_cancel(self):
        return self._delegate.data_av_capture_cancel()

    def data_av_capture_interrupted(self, project_id):
        return self._delegate.data_av_capture_interrupted(project_id)

    # Local model suggestions are proposals only; human confirms publication.
    def plan02c_catalog(self, project_id):
        return self._delegate.plan02c_catalog(project_id)

    def plan02c_preview(self, request):
        return self._delegate.plan02c_preview(request)

    def plan02c_publish(self, request):
        return self._delegate.plan02c_publish(request)

    def plan02c_models(self):
        return self._delegate.plan02c_models()

    def plan02c_model_candidate(self, request):
        return self._delegate.plan02c_model_candidate(request)
