"""W1-G regression: pywebview may introspect ONLY reviewed IPC methods.

The Windows prior native traceback pointed at webview.util.get_functions()
recursing through the trusted bridge's PUBLIC FilmIndex and GUI window.
Introspection must not traverse live authority, SQLite or COM objects.
"""
import inspect
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_webview_ipc_surface import NativeWebviewIPCSurface


class FakeWindow:
    def __init__(self):
        self.url="http://127.0.0.1:7777/"
        self.prompt_count=0

    def get_current_url(self):
        return self.url

    def create_confirmation_dialog(self, *_):
        self.prompt_count+=1
        return False


class NativeWebviewSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        index=FilmIndex(Studio(Path(self.tmp.name)/"studio.sqlite3"))
        self.trusted=TrustedDesktopCameraBridge(
            index,origin="http://127.0.0.1:7777")
        self.native_window=FakeWindow()
        self.trusted._attach_window(self.native_window)
        self.addCleanup(self.trusted._close)
        self.api=NativeWebviewIPCSurface(self.trusted)

    def test_no_public_graph_references_or_dynamic_reflection(self):
        names={name for name in dir(self.api) if not name.startswith("_")}
        expected={
            "camera_render_capabilities",
            "request_camera_still","poll_camera_still","cancel_camera_still",
            "data_av_import_original_audio","data_av_freeze_timed_take",
            "data_av_catalog","data_av_begin","data_av_audio_window",
            "data_av_scene_at","data_av_stop",
            "data_av_edited_30s_catalog","data_av_edited_30s_preflight",
            "data_av_edited_30s_begin","data_av_edited_30s_poll",
            "data_av_edited_30s_cancel","data_av_capture_catalog",
            "data_av_capture_devices","data_av_capture_begin",
            "data_av_capture_status","data_av_capture_finish",
            "data_av_capture_cancel","data_av_capture_interrupted",
            "plan02c_catalog","plan02c_preview","plan02c_publish",
            "plan02c_models","plan02c_model_candidate",
        }
        self.assertEqual(names,expected)
        self.assertEqual(len(names),28)
        self.assertFalse(hasattr(self.api,"__dict__"))
        for name in names:
            method=getattr(self.api,name)
            self.assertTrue(inspect.ismethod(method),name)
            original=getattr(self.trusted,name)
            self.assertEqual(inspect.signature(method),
                             inspect.signature(original),name)
        for name in ("window","index","origin","studio","api",
                     "delegate","get_current_url","create_confirmation_dialog"):
            self.assertFalse(hasattr(self.api,name),name)

    def test_delegation_keeps_native_window_authorization(self):
        result=self.api.camera_render_capabilities()
        self.assertTrue(result["native_window"])
        self.assertTrue(result["native_data_first_scene"])
        self.assertTrue(result["legacy_render_retired"])
        self.native_window.url="http://outside.example/"
        with self.assertRaises(PermissionError):
            self.api.camera_render_capabilities()
        with self.assertRaises(PermissionError):
            self.api.request_camera_still({})
        self.assertEqual(self.native_window.prompt_count,0)

    def test_closed_bridge_stays_closed_through_js_proxy(self):
        self.trusted._close()
        with self.assertRaises(PermissionError):
            self.api.camera_render_capabilities()

    def test_reject_untrusted_bridge_object(self):
        with self.assertRaises(TypeError):
            NativeWebviewIPCSurface(self.native_window)


if __name__=="__main__":
    unittest.main()
