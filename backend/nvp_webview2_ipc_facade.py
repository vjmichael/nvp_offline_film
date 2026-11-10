"""Audited, flat and explicitly allowlisted WebView2 JavaScript-to-native IPC.

pywebview 6.2.1 recursively enumerates all *public* attributes of js_api in
webview.util.get_functions(). Passing a TrustedDesktopCameraBridge directly
exposes its .index (FilmIndex), .window (native WebView), and .origin internals
to uncontrolled recursive introspection. The resulting JS binding generator
can hang before window.events.loaded fires. Do not bypass native approval.
This limited interface delegates ONLY audited native-window methods.
No FilmIndex, OS window, authority, lock, thread or worker is reachable from
the JS bridge object by any public attribute.

An explicitly named method is preferable to dynamic __getattr__/__dir__ or
get_functions monkeypatching: pywebview can introspect each signature once,
and newer library versions cannot recursively traverse hidden state.
"""
from __future__ import annotations

from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


class NativeWebView2API:
    __slots__ = ("__backend",)

    def __init__(self, backend: TrustedDesktopCameraBridge):
        if not isinstance(backend, TrustedDesktopCameraBridge):
            raise TypeError("Only an actual trusted native desktop bridge is allowed")
        self.__backend = backend

    def camera_render_capabilities(self):
        return self.__backend.camera_render_capabilities()

    def request_camera_still(self, payload):
        return self.__backend.request_camera_still(payload)

    def poll_camera_still(self, ticket_id):
        return self.__backend.poll_camera_still(ticket_id)

    def cancel_camera_still(self, ticket_id):
        return self.__backend.cancel_camera_still(ticket_id)

    def data_av_import_original_audio(self, project_id, source_id):
        return self.__backend.data_av_import_original_audio(project_id, source_id)

    def data_av_freeze_timed_take(self, request):
        return self.__backend.data_av_freeze_timed_take(request)

    def data_av_catalog(self, project_id):
        return self.__backend.data_av_catalog(project_id)

    def data_av_begin(self, request):
        return self.__backend.data_av_begin(request)

    def data_av_audio_window(self, session_id, first_sample, count):
        return self.__backend.data_av_audio_window(session_id, first_sample, count)

    def data_av_scene_at(self, session_id, tick):
        return self.__backend.data_av_scene_at(session_id, tick)

    def data_av_stop(self, session_id):
        return self.__backend.data_av_stop(session_id)

    def data_av_capture_catalog(self, project_id):
        return self.__backend.data_av_capture_catalog(project_id)

    def data_av_capture_devices(self):
        return self.__backend.data_av_capture_devices()

    def data_av_capture_begin(self, request):
        return self.__backend.data_av_capture_begin(request)

    def data_av_capture_status(self):
        return self.__backend.data_av_capture_status()

    def data_av_capture_finish(self):
        return self.__backend.data_av_capture_finish()

    def data_av_capture_cancel(self):
        return self.__backend.data_av_capture_cancel()

    def data_av_capture_interrupted(self, project_id):
        return self.__backend.data_av_capture_interrupted(project_id)

    def plan02c_catalog(self, project_id):
        return self.__backend.plan02c_catalog(project_id)

    def plan02c_preview(self, request):
        return self.__backend.plan02c_preview(request)

    def plan02c_publish(self, request):
        return self.__backend.plan02c_publish(request)

    def plan02c_models(self):
        return self.__backend.plan02c_models()

    def plan02c_model_candidate(self, request):
        return self.__backend.plan02c_model_candidate(request)

    def plan02d_preview(self, request):
        return self.__backend.plan02d_preview(request)

    def plan02d_sample_at(self, request):
        return self.__backend.plan02d_sample_at(request)

    def plan02d_enqueue(self, request):
        return self.__backend.plan02d_enqueue(request)

    def plan02d_inspect(self, project_id, job_id):
        return self.__backend.plan02d_inspect(project_id, job_id)

    def plan02d_review(self, request):
        return self.__backend.plan02d_review(request)

    def plan02d_raster_preview(self, request):
        return self.__backend.plan02d_raster_preview(request)

    def plan02d_raster_publish(self, request):
        return self.__backend.plan02d_raster_publish(request)

    def plan03_render_original_once(self, request):
        return self.__backend.plan03_render_original_once(request)

    def plan04_render_cycles_once(self, request):
        return self.__backend.plan04_render_cycles_once(request)
