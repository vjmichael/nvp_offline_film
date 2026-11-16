"""W1-G regression: pywebview may introspect ONLY reviewed IPC methods.

The Windows prior native traceback pointed at webview.util.get_functions()
recursing through the trusted bridge's PUBLIC FilmIndex and GUI window.
Introspection must not traverse live authority, SQLite or COM objects.
"""
import ast
import inspect
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_p1a_original_capture_worker_bridge import OriginalMicrophoneNativeWorkerAudit
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
            "data_av_actor_cast","data_av_actor_register",
            "data_av_actor_dialogue_bind","data_av_actor_dialogue_at",
            "data_av_actor_asset_catalog","data_av_actor_scene_cast",
            "data_av_film_stage_graph_catalog","data_av_film_stage_edit_draft",
            "data_av_film_stage_edit_commit",
            "data_av_film_stage_catalog","data_av_film_stage_director_commit",
            "data_av_film_stage_actor_bus_commit",
            "data_av_film_stage_longform_publish",
            "data_av_film_stage_longform_page",
            "data_av_film_stage_longform_audit_page",
            "data_av_film_stage_chunk_preflight","data_av_film_stage_chunk_begin",
            "data_av_film_stage_chunk_poll","data_av_film_stage_chunk_cancel",
        }
        self.assertEqual(names,expected)
        self.assertEqual(len(names),47)
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
        with self.assertRaises(PermissionError):
            self.api.data_av_film_stage_catalog("a"*32)
        with self.assertRaises(PermissionError):
            self.api.data_av_film_stage_chunk_begin({})
        with self.assertRaises(PermissionError):
            self.api.data_av_film_stage_chunk_cancel("untrusted_ticket")
        self.assertEqual(self.native_window.prompt_count,0)

    def test_closed_bridge_stays_closed_through_js_proxy(self):
        self.trusted._close()
        with self.assertRaises(PermissionError):
            self.api.camera_render_capabilities()

    def test_original_compiled_worker_auditor_is_host_only_not_js(self):
        auditor=object.__new__(OriginalMicrophoneNativeWorkerAudit)
        host=TrustedDesktopCameraBridge(
            self.trusted.index,origin="http://127.0.0.1:7777",
            native_capture_auditor=auditor)
        self.addCleanup(host._close)
        host._attach_window(FakeWindow())
        self.assertIs(host._original_capture().native_pcm_auditor,auditor)
        # Exposing 34 deliberately reviewed UI methods must never traverse
        # the protected worker, runtime directory or model/grant state.
        ui=NativeWebviewIPCSurface(host)
        self.assertFalse(hasattr(ui,"native_capture_auditor"))
        self.assertFalse(hasattr(ui,"_native_capture_auditor"))
        self.assertFalse(hasattr(ui,"worker"))
        with self.assertRaises(TypeError):
            TrustedDesktopCameraBridge(
                self.trusted.index,origin="http://127.0.0.1:7777",
                native_capture_auditor={"creator_approved":True})

    def test_installed_webview_entrypoints_use_the_reviewed_ipc_surface(self):
        # Source-wiring guard: the real packaged application and the actual
        # installed WebView2 smoke must NEVER hand pywebview the full trusted
        # bridge, whose public OS-window/SQLite graphs can deadlock before_load.
        path=Path(__file__).resolve().parents[1]/"tools"/"nvp_desktop_alpha.py"
        tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
        calls=[node for node in ast.walk(tree)
               if isinstance(node,ast.Call) and
               isinstance(node.func,ast.Attribute) and
               isinstance(node.func.value,ast.Name) and
               node.func.value.id=="webview" and
               node.func.attr=="create_window"]
        surfaces=[kw.value for call in calls for kw in call.keywords
                  if kw.arg=="js_api"]
        self.assertEqual(len(surfaces),2,
                         "Review every installed pywebview JS API binding")
        for surface in surfaces:
            self.assertIsInstance(surface,ast.Call)
            self.assertIsInstance(surface.func,ast.Name)
            self.assertEqual(surface.func.id,"NativeWebviewIPCSurface")
            self.assertEqual(len(surface.args),1)
            self.assertIsInstance(surface.args[0],ast.Name)
            self.assertEqual(surface.args[0].id,"bridge")

    def test_installed_visible_source_reads_script_editor_not_body_text(self):
        # A real resumed movie opens Scenes by default. The original
        # screenplay is a controlled textarea value only after Script is
        # selected; body.textContent can never prove it was displayed.
        path=Path(__file__).resolve().parents[1]/"tools"/"nvp_desktop_alpha.py"
        tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
        smoke=next(node for node in tree.body
                   if isinstance(node,ast.FunctionDef) and
                   node.name=="run_visible_window_smoke")
        source_strings=[node.value for node in ast.walk(smoke)
                        if isinstance(node,ast.Constant) and
                        isinstance(node.value,str)]
        self.assertTrue(any("Script phase not selectable" in s
                            for s in source_strings))
        self.assertTrue(any("textarea.line-numbered-input" in s
                            for s in source_strings))
        self.assertTrue(any(".startsWith('EXT. NATIVE CAMERA SOUND SOURCE" in s
                            for s in source_strings))
        self.assertFalse(any("document.body.textContent.includes('EXT. NATIVE" in s
                             for s in source_strings))

    def test_installed_resume_waits_for_real_saved_movie_phase_mount(self):
        # The original Windows installed failure was an async race: clicking
        # the movie card starts an HTTP request; the React working-phase nav
        # is not present synchronously. Never bypass the UI or fake source.
        path=Path(__file__).resolve().parents[1]/"tools"/"nvp_desktop_alpha.py"
        source=path.read_text(encoding="utf-8")
        smoke=source.split("def run_visible_window_smoke():",1)[1].split(
            "def run_g03_window_smoke():",1)[0]
        after_movie_click=smoke.split(
            'raise RuntimeError("Director cannot open saved frozen source")',
            1)[1]
        before_script_click=after_movie_click.split(
            "opened_script=window.evaluate_js(",1)[0]
        self.assertIn("wait_js(",before_script_click)
        self.assertIn(".film-film-head h1",before_script_click)
        self.assertIn("window_original_film_director_phases_ready",
                      before_script_click)
        self.assertIn("Saved original movie did not mount",before_script_click)
        self.assertIn("textarea.line-numbered-input",after_movie_click)
        self.assertIn("window_native_source_sound_verified",after_movie_click)

    def test_reject_untrusted_bridge_object(self):
        with self.assertRaises(TypeError):
            NativeWebviewIPCSurface(self.native_window)


if __name__=="__main__":
    unittest.main()
