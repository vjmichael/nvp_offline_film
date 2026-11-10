"""The actual pywebview JS exposure surface is intentionally flat.

pywebview 6.2.1 webview.util.get_functions traverses public non-callable
objects recursively; NEVER expose a FilmIndex, window, RLock or native host
as a public js_api attribute. This checks the *exposure traversal contract*,
not just the existence of trusted backend methods.
"""
from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_webview2_ipc_facade import NativeWebView2API


# Intentional approved flat JS method names, reviewed separately from the
# implementation. Adding any public nested object requires a test change.
EXPECTED_JS_API = frozenset({
    "camera_render_capabilities", "request_camera_still",
    "poll_camera_still", "cancel_camera_still",
    "data_av_import_original_audio", "data_av_freeze_timed_take",
    "data_av_catalog", "data_av_begin", "data_av_audio_window",
    "data_av_scene_at", "data_av_stop", "data_av_capture_catalog",
    "data_av_capture_devices", "data_av_capture_begin",
    "data_av_capture_status", "data_av_capture_finish",
    "data_av_capture_cancel", "data_av_capture_interrupted",
    "plan02c_catalog", "plan02c_preview", "plan02c_publish",
    "plan02c_models", "plan02c_model_candidate", "plan02d_preview",
    "plan02d_sample_at", "plan02d_enqueue", "plan02d_inspect",
    "plan02d_review", "plan02d_raster_preview", "plan02d_raster_publish",
})


class Window:
    def __init__(self):
        self.url = "http://127.0.0.1:7777/"
        self.prompts = 0

    def get_current_url(self):
        return self.url

    def create_confirmation_dialog(self, *args):
        self.prompts += 1
        return False


class FlatWebView2APIContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        studio = Studio(Path(self.temp.name) / "studio.sqlite3")
        self.project_id = studio.create_project(
            "Source-only WebView2 proxy test", "No actual rendering")["id"]
        self.bridge = TrustedDesktopCameraBridge(
            FilmIndex(studio), origin="http://127.0.0.1:7777",
            host_factory=lambda callback: self.fail(
                "Unapproved native backend launched"),
        )
        self.window = Window()
        self.bridge._attach_window(self.window)
        self.addCleanup(self.bridge._close)
        self.api = NativeWebView2API(self.bridge)

    def test_real_pywebview_recursion_surface_contains_only_methods(self):
        # This follows get_functions' public attribute selection rule:
        # pywebview must NEVER see non-callable nested authoritative state.
        present = {}
        for name in dir(self.api):
            if name.startswith("_"):
                continue
            obj = getattr(self.api, name)
            self.assertTrue(inspect.ismethod(obj) or inspect.isfunction(obj),
                            "Recursive public JS API object: " + name)
            present[name] = tuple(inspect.signature(obj).parameters)
        self.assertEqual(frozenset(present), EXPECTED_JS_API)
        self.assertEqual(present["data_av_audio_window"],
                         ("session_id","first_sample","count"))
        self.assertEqual(present["plan02d_inspect"],
                         ("project_id","job_id"))
        for unsafe in ("index","window","origin","studio","_host",
                       "get_current_url","create_confirmation_dialog",
                       "native_window","_close"):
            self.assertFalse(hasattr(self.api, unsafe),
                             "Native authority escaped via browser API " + unsafe)
        self.assertFalse(hasattr(self.api, "__dict__"))

    def test_all_public_methods_bound_to_real_native_bridge(self):
        for name in EXPECTED_JS_API:
            self.assertTrue(callable(getattr(self.bridge, name)), name)
        result = self.api.camera_render_capabilities()
        self.assertTrue(result["legacy_render_retired"])
        self.assertTrue(result["native_data_first_scene"])
        self.assertEqual(self.window.prompts, 0)
        catalog = self.api.data_av_catalog(self.project_id)
        self.assertFalse(catalog["ffmpeg_runtime_required"])
        self.assertEqual(self.window.prompts, 0)

    def test_native_origin_and_retired_workers_still_refuse(self):
        self.window.url = "http://127.0.0.1:7788/"
        with self.assertRaises(PermissionError):
            self.api.camera_render_capabilities()
        with self.assertRaises(PermissionError):
            self.api.data_av_catalog(self.project_id)
        self.window.url = "http://127.0.0.1:7777/"
        with self.assertRaisesRegex(PermissionError, "retired"):
            self.api.request_camera_still({})
        self.assertEqual(self.window.prompts, 0)

    def test_bridge_closure_revokes_browser_ipc(self):
        self.bridge._close()
        with self.assertRaises(PermissionError):
            self.api.camera_render_capabilities()
        with self.assertRaises(PermissionError):
            self.api.data_av_catalog(self.project_id)


if __name__ == "__main__":
    unittest.main()
