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

    # Source camera stills are deliberately RETIRED and fail closed in host.
    def camera_render_capabilities(self):
        return self._delegate.camera_render_capabilities()

    def request_camera_still(self, payload):
        return self._delegate.request_camera_still(payload)

    def poll_camera_still(self, ticket_id):
        return self._delegate.poll_camera_still(ticket_id)

    def cancel_camera_still(self, ticket_id):
        return self._delegate.cancel_camera_still(ticket_id)

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
