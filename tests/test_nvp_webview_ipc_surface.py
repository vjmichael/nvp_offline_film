"""W1-G regression: pywebview may introspect ONLY reviewed IPC methods.

The Windows prior native traceback pointed at webview.util.get_functions()
recursing through the trusted bridge's PUBLIC FilmIndex and GUI window.
Introspection must not traverse live authority, SQLite or COM objects.
"""
import ast
import inspect
import re
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
            "slate_publish_section",
            "wo6_plan_catalog","wo6_plan_preview","wo6_plan_save","wo6_plan_read","wo6_retake_execute",
            "wo6_retake_cancel","wo6_retake_recover",
            "wo5_review_catalog","wo5_review_read_intent","wo5_review_save_intent",
            "wo5_review_feature_page","wo5_review_inspect_feature","wo5_review_save_observations","wo5_film_capabilities",
            "wo5_film_begin","wo5_film_frame","wo5_film_window","wo5_film_stop",
            "camera_render_capabilities",
            "request_camera_still","poll_camera_still","cancel_camera_still",
            # CONV-12 installed movie mounts this original native director
            # panel. No browser/window/FilmIndex references may be exposed.
            "camfx03_camera_sources","camfx03_draft_catalog",
            "film03_actor_catalog","film02md_architecture_catalog",
            "film01c_texture_catalog","film03_actor_profile",
            "camfx03_draft_create","camfx03_draft_reopen",
            "camfx03_draft_save","camfx03_draft_undo",
            "camfx03_draft_publish","camfx03_draft_discard",
            "camfx03_draft_recover_publish",
            "film03_actor_profile_publish",
            "data_av_import_original_mesh_texture",
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
        self.assertEqual(len(names),81)
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

    def test_every_mounted_original_director_call_has_an_explicit_native_proxy(self):
        # The installed React panel mounts even when its Advanced <details>
        # is collapsed. A missing callable crashes the entire WebView2 React
        # root after a successful HTTP film open. Catch missing methods in
        # the original source acceptance rather than waiting for NSIS.
        path=Path(__file__).resolve().parents[1]/"frontend"/"src"/(
            "DirectorCameraActorContinuity.jsx")
        code=path.read_text(encoding="utf-8")
        called=set(re.findall(r"\bnative\.([a-z][a-z0-9_]*)\s*\(",code))
        required={
            "camfx03_camera_sources","camfx03_draft_catalog",
            "film03_actor_catalog","film02md_architecture_catalog",
            "film01c_texture_catalog","film03_actor_profile",
            "camfx03_draft_create","camfx03_draft_reopen",
            "camfx03_draft_save","camfx03_draft_undo",
            "camfx03_draft_publish","camfx03_draft_discard",
            "camfx03_draft_recover_publish",
            "film03_actor_profile_publish",
            "data_av_import_original_mesh_texture",
        }
        self.assertEqual(called,required)
        installed=(Path(__file__).resolve().parents[1]/"tools"/
                   "nvp_desktop_alpha.py").read_text(encoding="utf-8")
        self.assertIn("window_original_director_ipc_surface_verified",installed)
        self.assertIn("missing_native_director_methods",installed)
        for name in sorted(required):
            self.assertIn(name,installed,
                          "Installed WebView2 must check all original methods")
            self.assertTrue(callable(getattr(self.api,name,None)),name)
            self.assertEqual(
                inspect.signature(getattr(self.api,name)),
                inspect.signature(getattr(self.trusted,name)),name)
        # Do not expose a direct rail publication bypass, private handles,
        # OS prompts, model grants, or a conventional FFmpeg/still worker.
        for denied in ("camfx02_publish","window","index","origin",
                       "create_confirmation_dialog","_grant","_approve",
                       "film03_run_actor_voice_candidate"):
            if not denied.startswith("_"):
                self.assertFalse(hasattr(self.api,denied),denied)

    def test_original_director_ipc_remains_origin_and_custody_bound(self):
        self.native_window.url="http://outside.example/"
        for name,arg in (
            ("camfx03_camera_sources",("a"*32,)),
            ("camfx03_draft_catalog",("a"*32,)),
            ("film03_actor_catalog",("a"*32,)),
            ("film02md_architecture_catalog",("a"*32,)),
            ("film01c_texture_catalog",("a"*32,)),
            ("film03_actor_profile",("a"*32,"ActorAAA")),
            ("camfx03_draft_publish",({},)),
            ("film03_actor_profile_publish",({},)),
            ("data_av_import_original_mesh_texture",({},)),
        ):
            with self.subTest(name=name):
                with self.assertRaises(PermissionError):
                    getattr(self.api,name)(*arg)
        self.assertEqual(self.native_window.prompt_count,0)

    def test_finished_review_calls_are_explicit_and_origin_bound(self):
        frontend=Path(__file__).resolve().parents[1]/"frontend"/"src"
        calls=set()
        for name,receiver in (("DirectorFinishedReview.jsx","api"),("FinishedFilmPlaybackPanel.jsx","native")):
            code=(frontend/name).read_text(encoding="utf-8")
            calls.update(re.findall(r"\b"+receiver+r"\.(wo5_[a-z_]+)\s*\(",code))
        for name in calls:
            self.assertTrue(callable(getattr(self.api,name,None)),name)
        self.assertTrue({"wo5_review_catalog","wo5_film_begin","wo5_film_window",
                         "wo5_review_save_observations"} <= calls)
        self.native_window.url="http://outside.example/"
        for name,args in (("wo5_review_catalog",("a"*32,)),
                          ("wo5_review_save_intent",({},)),
                          ("wo5_film_capabilities",()),
                          ("wo5_film_begin",("a"*32,"Feature")),
                          ("wo5_film_stop",("not-a-ticket",))):
            with self.subTest(name=name),self.assertRaises(PermissionError):
                getattr(self.api,name)(*args)
        self.assertEqual(self.native_window.prompt_count,0)

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
        # Exposing the reviewed UI methods must never traverse
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

    def test_installed_navigation_failure_captures_bounded_real_browser_evidence(self):
        # A missing phase after an actual film click must remain a native
        # acceptance failure, with enough state to distinguish failed HTTP
        # loading from a broken React mount on the installed executable.
        path=Path(__file__).resolve().parents[1]/"tools"/"nvp_desktop_alpha.py"
        source=path.read_text(encoding="utf-8")
        smoke=source.split("def run_visible_window_smoke():",1)[1].split(
            "def run_g03_window_smoke():",1)[0]
        for marker in (
            "window_original_film_navigation_diagnostic",
            "movieReadRequests", "movieReadStatus", "rootChildren",
            "phaseNav", "savedHeadingMatches", "resumeCards",
            "firstAlert", "windowErrors",
            "window.__nvpMovieRuntimeErrors",
        ):
            self.assertIn(marker,smoke)
        # The smoke must observe, not replace the installed React/HTTP APIs.
        self.assertNotIn("window.fetch=",smoke)
        self.assertIn("window_original_film_director_phases_ready",smoke)
        self.assertIn("textarea.line-numbered-input",smoke)
        self.assertIn("window_native_source_sound_verified",smoke)
        self.assertIn("raise RuntimeError(",smoke)

    def test_reject_untrusted_bridge_object(self):
        with self.assertRaises(TypeError):
            NativeWebviewIPCSurface(self.native_window)


class WebviewLoadObservationTests(unittest.TestCase):
    @staticmethod
    def _helper():
        path = Path(__file__).resolve().parents[1] / "tools" / "nvp_desktop_alpha.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "_await_native_window_load")
        scope = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), scope)
        return scope[node.name]

    @staticmethod
    def _window(*, loaded=False, before_load=False):
        from threading import Event
        from types import SimpleNamespace
        events = SimpleNamespace(**{name: Event() for name in
            ("initialized", "before_show", "shown", "before_load", "loaded")})
        events.initialized.set()
        events.before_show.set()
        events.shown.set()
        if before_load:
            events.before_load.set()
        if loaded:
            events.loaded.set()
        return SimpleNamespace(events=events)

    def test_native_event_is_sufficient_without_observer_callback(self):
        from types import SimpleNamespace
        self.assertIsNone(self._helper()(self._window(loaded=True, before_load=True),
            SimpleNamespace(started=True), SimpleNamespace(is_alive=lambda: True), timeout=0))

    def test_missing_native_event_still_fails_with_lifecycle_evidence(self):
        from types import SimpleNamespace
        with self.assertRaisesRegex(RuntimeError, "Installed WebView2 page-loaded event missing") as exc:
            self._helper()(self._window(before_load=True), SimpleNamespace(started=True),
                SimpleNamespace(is_alive=lambda: True), timeout=0)
        self.assertIn("'before_load': True", str(exc.exception))
        self.assertIn("'loaded': False", str(exc.exception))
        self.assertIn("'local_api_alive': True", str(exc.exception))

    def test_real_smoke_uses_native_event_and_keeps_original_ui_assertions(self):
        path = Path(__file__).resolve().parents[1] / "tools" / "nvp_desktop_alpha.py"
        source = path.read_text(encoding="utf-8")
        smoke = source.split("def run_visible_window_smoke():", 1)[1].split(
            "def run_g03_window_smoke():", 1)[0]
        self.assertIn("_await_native_window_load(window,server,worker)", smoke)
        self.assertNotIn("window.events.loaded +=", smoke)
        self.assertIn("window_real_page_loaded", smoke)
        self.assertIn("window_director_home_visible", smoke)
        self.assertIn("window_native_camera_ipc_verified", smoke)
        self.assertIn("window_native_source_sound_verified", smoke)


class PrivateProfileTests(unittest.TestCase):
    @staticmethod
    def _helper():
        import tempfile
        path = Path(__file__).resolve().parents[1] / "tools" / "nvp_desktop_alpha.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "_start_private_webview")
        scope = {"tempfile": tempfile, "Path": Path}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), scope)
        return scope[node.name]

    def test_profile_exists_unique_and_removed(self):
        from types import SimpleNamespace
        paths = []
        callback = lambda: None
        def run(**kwargs):
            profile = Path(kwargs["storage_path"])
            self.assertTrue(profile.is_dir())
            self.assertTrue(kwargs["private_mode"])
            self.assertFalse(kwargs["debug"])
            self.assertEqual(kwargs["gui"], "edgechromium")
            self.assertIs(kwargs["func"], callback)
            (profile / "synthetic").write_text("test")
            paths.append(profile)
        webview = SimpleNamespace(start=run, renderer="edgechromium")
        start = self._helper()
        start(webview, func=callback)
        start(webview, func=callback)
        self.assertNotEqual(paths[0], paths[1])
        self.assertTrue(all(not p.parent.exists() for p in paths))

    def test_failure_is_not_swallowed_or_raw_diagnostic_retained(self):
        import logging
        from types import SimpleNamespace
        observed = {}
        paths = []
        logger = logging.getLogger("pywebview")
        original_handlers = list(logger.handlers)
        def run(**kwargs):
            paths.append(Path(kwargs["storage_path"]))
            logger.error("WebView2 initialization failed with exception:\n SECRET_PATH")
            logger.error("Cache directory SECRET_PATH creation failed")
            raise RuntimeError("native startup failed")
        with self.assertRaisesRegex(RuntimeError, "native startup failed"):
            self._helper()(SimpleNamespace(start=run, renderer="edgechromium"), diagnostics=observed)
        self.assertEqual(observed, {"native_initialization_failed": True,
            "profile_creation_failed": True, "renderer_is_edgechromium": True})
        self.assertNotIn("SECRET_PATH", repr(observed))
        self.assertEqual(logger.handlers, original_handlers)
        self.assertFalse(paths[0].parent.exists())

    def test_fallback_renderer_is_not_misreported(self):
        from types import SimpleNamespace
        observed = {}
        self._helper()(SimpleNamespace(start=lambda **kwargs: None, renderer="mshtml"), diagnostics=observed)
        self.assertFalse(observed["renderer_is_edgechromium"])
        self.assertFalse(observed["native_initialization_failed"])


if __name__=="__main__":
    unittest.main()
