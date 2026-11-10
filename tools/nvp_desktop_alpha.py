"""NVP-E2E-01E: standalone offline Windows alpha desktop entry.

Embedded React/Vite bundle + local FastAPI, displayed in a native WebView2
window. Does not depend on Lu, Docker, a development Vite server, or
an external browser. Bind to loopback and an OS-assigned port; never listen
on a network interface. The CLI --smoke mode is headless installed-app
acceptance; a separate real WebView GUI smoke must also pass.
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import urllib.request

# Source-mode invocation (`python tools/nvp_desktop_alpha.py`) otherwise puts
# tools/ rather than the repository root on sys.path. A frozen PyInstaller
# bundle already has its own audited import search paths; leave those intact.
if not getattr(sys, "frozen", False):
    repo_root = str(Path(__file__).resolve().parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def bundle_root():
    return Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[1]))


def static_root():
    return bundle_root()/"frontend"/"dist"


def configure_home():
    if os.name=="nt":
        root=Path(os.environ.get("LOCALAPPDATA",str(Path.home()))) / "NVP" / "Projects"
    else:
        root=Path.home()/"NVP_Projects"
    os.environ.setdefault("NVP_HOME",str(root))
    return root


def _webview_profile_dir(root):
    """An explicit writable WinForms/WebView2 user-data folder.

    Never try to initialize WebView2 beside the NSIS executable or in the
    creator's SQLite books. Python pywebview maps storage_path to the real
    WebView2 CreationProperties.UserDataFolder on EdgeChromium.
    """
    path=Path(root)/"WebView2Profile"
    if path.is_symlink():
        raise PermissionError("Refusing symlinked WebView2 profile directory")
    path.mkdir(parents=True,exist_ok=True)
    if not path.is_dir():
        raise RuntimeError("WebView2 profile path is not a directory")
    probe=path/(".nvp-write-probe-"+str(os.getpid()))
    with probe.open("xb") as stream:
        stream.write(b"NVP-webview2-write-probe")
        stream.flush()
        os.fsync(stream.fileno())
    probe.unlink()
    return str(path)


def _windows_session_id():
    """Report the real native process session, not a claimed interactive GUI."""
    if os.name!="nt":
        return None
    import ctypes
    session=ctypes.c_ulong()
    fn=ctypes.windll.kernel32.ProcessIdToSessionId
    if not fn(os.getpid(),ctypes.byref(session)):
        raise OSError(ctypes.get_last_error(),"Cannot inspect Windows logon session")
    return session.value


def create_app():
    from backend.nvp_api import app
    from fastapi.staticfiles import StaticFiles
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import FileResponse
    dist=static_root()
    entry=dist/"index.html"
    if not entry.is_file() or not (dist/"assets").is_dir():
        raise RuntimeError("NVP frontend assets not installed: "+str(dist))
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=["127.0.0.1","localhost"])
    app.mount("/assets",StaticFiles(directory=str(dist/"assets")),name="nvp_assets")
    @app.get("/",include_in_schema=False)
    def desktop_home():
        return FileResponse(entry)
    return app


def serve(app):
    import uvicorn
    listening=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    listening.bind(("127.0.0.1",0))
    listening.listen(128)
    listening.set_inheritable(False)
    port=listening.getsockname()[1]
    # A PyInstaller --windowed Windows binary has sys.stdout/sys.stderr=None.
    # Uvicorn's default dictConfig constructs DefaultFormatter and calls
    # sys.stderr.isatty(), crashing the installed GUI before React opens.
    # Keep NVP's existing native diagnostic receipts; do not invoke the
    # console-only formatter or open a new listener/permission surface.
    config=uvicorn.Config(app,host="127.0.0.1",port=port,
                          access_log=False,log_level="warning",
                          proxy_headers=False,log_config=None)
    server=uvicorn.Server(config)
    server.install_signal_handlers=lambda:None
    worker=threading.Thread(target=server.run,kwargs={"sockets":[listening]},
                            name="NVP Local API",daemon=True)
    worker.start()
    until=time.monotonic()+20
    while not server.started:
        if not worker.is_alive():
            raise RuntimeError("NVP local API worker terminated")
        if time.monotonic()>=until:
            server.should_exit=True
            raise RuntimeError("NVP local API startup timed out")
        time.sleep(.05)
    return server,worker,port,listening


def run_smoke():
    with tempfile.TemporaryDirectory(prefix="nvp-installed-smoke-") as tmp:
        os.environ["NVP_HOME"]=str(Path(tmp)/"Projects")
        app=create_app()
        server,worker,port,sock=serve(app)
        base="http://127.0.0.1:"+str(port)
        try:
            with urllib.request.urlopen(base+"/api/status",timeout=10) as response:
                import json
                status=json.load(response)
            if status.get("status")!="ready":
                raise RuntimeError("Installed NVP API did not report ready")
            with urllib.request.urlopen(base+"/",timeout=10) as response:
                html=response.read().decode("utf8")
            if "assets/" not in html:
                raise RuntimeError("Bundled NVP React frontend unavailable")
            import json
            payload=json.dumps({"title":"Installed NVP Alpha Acceptance",
                                "idea":"Offline persistence smoke"}).encode("utf8")
            request=urllib.request.Request(base+"/api/projects",data=payload,
                headers={"Content-Type":"application/json"},method="POST")
            with urllib.request.urlopen(request,timeout=10) as response:
                project=json.load(response)
            from backend.nvp_studio import Studio
            from backend.nvp_api import studio
            if Studio(studio.db_path).get_project(project["id"])["title"]!=project["title"]:
                raise RuntimeError("Installed NVP project failed SQLite reopen")
            return 0
        finally:
            server.should_exit=True
            worker.join(timeout=12)
            sock.close()
            if worker.is_alive():
                raise RuntimeError("NVP API server refused clean shutdown")


def run_persistent_installed_smoke(mode):
    """Installed-app launch, exit, reopen must retain SQLite project data."""
    import json
    home=os.environ.get("NVP_HOME")
    if not home:
        raise RuntimeError("Installed acceptance requires explicit NVP_HOME")
    root=Path(home)
    root.mkdir(parents=True,exist_ok=True)
    marker=root/"installed-smoke-project.json"
    app=create_app()
    server,worker,port,sock=serve(app)
    base="http://127.0.0.1:"+str(port)
    try:
        with urllib.request.urlopen(base+"/api/status",timeout=10) as reply:
            if json.load(reply).get("status")!="ready":
                raise RuntimeError("Offline installed API isn't ready")
        with urllib.request.urlopen(base+"/",timeout=10) as reply:
            if "assets/" not in reply.read().decode("utf8"):
                raise RuntimeError("React desktop bundle unavailable after install")
        if mode=="create":
            if marker.exists():
                raise RuntimeError("Persistent test project marker already exists")
            payload=json.dumps({"title":"NVP Installed Restart Acceptance",
                                "idea":"Persistent native project save and reopen"}).encode()
            request=urllib.request.Request(
                base+"/api/projects",data=payload,
                headers={"Content-Type":"application/json"},method="POST")
            with urllib.request.urlopen(request,timeout=10) as reply:
                record=json.load(reply)
            screenplay="INT. EDIT SUITE - DAY\n\nA camera rolls."
            edit_request=urllib.request.Request(
                base+"/api/projects/"+record["id"]+"/screenplay",
                data=json.dumps({"screenplay":screenplay,
                                 "expected_revision":0}).encode("utf8"),
                headers={"Content-Type":"application/json"},method="PUT")
            with urllib.request.urlopen(edit_request,timeout=10) as reply:
                saved=json.load(reply)
            if saved.get("revision")!=1:
                raise RuntimeError("NVP installed screenplay save did not commit")
            marker.write_text(json.dumps({"id":record["id"],
                        "title":record["title"],"screenplay":screenplay,
                        "revision":1}),encoding="utf8")
        else:
            expected=json.loads(marker.read_text("utf8"))
            with urllib.request.urlopen(
                    base+"/api/projects/"+expected["id"],timeout=10) as reply:
                reopened=json.load(reply)
            if (reopened["title"]!=expected["title"]
                or reopened["screenplay"]!=expected["screenplay"]
                or reopened["revision"]!=expected["revision"]):
                raise RuntimeError("Installed NVP lost project/edit history across restart")
            from backend.nvp_studio import Studio
            durable=Studio(root/"nvp_studio.sqlite3").get_project(expected["id"])
            if (durable["title"]!=expected["title"]
                or durable["screenplay"]!=expected["screenplay"]
                or durable["revision"]!=expected["revision"]):
                raise RuntimeError("SQLite screenplay revision changed after reopening app")
        return 0
    finally:
        server.should_exit=True
        worker.join(timeout=12)
        sock.close()
        if worker.is_alive():
            raise RuntimeError("Installed NVP failed to exit cleanly")


def create_trusted_camera_bridge(port):
    """Desktop-only pywebview IPC; never registered as an HTTP route."""
    from backend.nvp_api import studio
    from backend.nvp_film_index import FilmIndex
    from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
    return TrustedDesktopCameraBridge(
        FilmIndex(studio),origin="http://127.0.0.1:"+str(port))


def run_visible_window_smoke():
    """Installed real WebView2 + native OpenUSD source panel smoke.

    Use a throwaway film workspace: tests must never publish a demo source
    or mutate the creator's durable Projects directory.
    """
    _smoke_checkpoint("window_enter")
    import webview
    from threading import Event
    test_home=Path(tempfile.mkdtemp(prefix="nvp-slate08b-installed-"))
    old_home=os.environ.get("NVP_HOME")
    os.environ["NVP_HOME"]=str(test_home)
    try:
        _smoke_checkpoint("window_before_app")
        app=create_app()
        from backend.nvp_api import studio
        from backend.nvp_film_index import FilmIndex
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        project=studio.create_project("SLATE-08B Window Acceptance",
            "One native source camera scene")
        # Genuine saved scenes, not a synthetic DOM fixture: the installed
        # Scene Library must fetch source-derived headings/cues/empty props.
        project=studio.save_screenplay(project["id"],
            "INT. KITCHEN - DAY\n\nA dog eats from a bowl.\n\n"
            "ALEX\nThe dog is eating.\n\n"
            "EXT. GARDEN - NIGHT\n\nThe dog goes outside.",
            project["revision"])
        _smoke_checkpoint("window_plan03_two_source_scenes_persisted")
        OpenUSDSceneBridge(FilmIndex(studio)).publish(
            project["id"],"smoke_scene",
            prims=[
                {"path":"/World/Actor","role":"actor",
                 "position":[0,0,0]},
                {"path":"/World/Camera","role":"camera",
                 "position":[0,0,8]},
            ],curves=[],native_schemas=True)
        # Separate native A/V smoke from FFmpeg-backed imported video.
        # This is one real frozen OpenUSD Digital Take with a SHA-addressed
        # captured mono signal, for the actual installed WebView2 catalog.
        from backend.nvp_data_av_source import RecordedSoundSources
        from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        import struct
        source_index=FilmIndex(studio)
        RecordedSoundSources(source_index).publish(
            project["id"],"smoke_signal",
            [struct.pack("<"+"h"*4800,*([6000]*4800))])
        TemporalLedger(source_index).publish(
            project["id"],"smoke_events",[{
                "event_id":"smoke_actor_sound","event_kind":"sound",
                "subject_id":"Actor","start_tick":0,
                "end_tick":TICKS_PER_SECOND//2,
                "source_id":"smoke_signal","source_revision":1,
                "payload":{"usd_prim_path":"/World/Actor","gain":0.8},
            }],duration_tick=TICKS_PER_SECOND)
        OpenUSDTakeCapture(
            source_index,verify_creator_action=lambda event,scope:
            event=="smoke_only" and scope["operation"]==
            "nvp.freeze.usd_temporal_take.v1").freeze(
                project["id"],"smoke_frozen_take",scene_id="smoke_scene",
                scene_revision=1,timeline_id="smoke_events",
                timeline_revision=1,sample_ticks=[0],
                creator_event="smoke_only")
        # The 30-second source film must also appear as a genuine saved
        # Digital Take in the installed GUI, not as a browser-generated demo
        # slideshow or a pre-rendered movie file. This is only a deterministic
        # test signal; not physical microphone or human approval evidence.
        from tools.nvp_plan02e_installed_acceptance import create as create_film
        create_film(source_index,project["id"])
        _smoke_checkpoint("window_plan02e_original_take_created")
        _smoke_checkpoint("window_before_serve")
        server,worker,port,sock=serve(app)
        _smoke_checkpoint("window_after_serve")
        # Browser-page failures must not be misreported as backend failures.
        with urllib.request.urlopen(
                "http://127.0.0.1:"+str(port)+"/",timeout=5) as resp:
            html=resp.read()
            if resp.status!=200 or b"assets/" not in html:
                raise RuntimeError("Installed React entry not served over loopback")
        _smoke_checkpoint("window_http_source_ready")
        session_id=_windows_session_id()
        if session_id is not None:
            _smoke_checkpoint("window_native_session_"+str(session_id))
        browser_profile=_webview_profile_dir(test_home)
        _smoke_checkpoint("window_explicit_webview2_profile_writable")
    except BaseException:
        if old_home is None: os.environ.pop("NVP_HOME",None)
        else: os.environ["NVP_HOME"]=old_home
        shutil.rmtree(test_home,ignore_errors=True)
        raise
    loaded=Event()
    result={"passed":False}
    bridge=None
    try:
        _smoke_checkpoint("window_before_native_bridge")
        bridge=create_trusted_camera_bridge(port)
        _smoke_checkpoint("window_before_webview_create")
        from backend.nvp_webview2_ipc_facade import NativeWebView2API
        window=webview.create_window("NVP Alpha Window Acceptance",
            "http://127.0.0.1:"+str(port),width=1000,height=700,
            js_api=NativeWebView2API(bridge))
        bridge._attach_window(window)
        _smoke_checkpoint("window_after_webview_create")
        def when_loaded():
            _smoke_checkpoint("window_native_loaded_event")
            loaded.set()
        window.events.loaded += when_loaded
        # Diagnostics must not replace the real loaded/React/IPC assertion.
        # In hosted Windows pywebview startup can hang before page-loaded;
        # distinguish OS window presentation from webview navigation.
        def window_event(stage):
            def witness():
                _smoke_checkpoint(stage)
            return witness
        for name in ("before_show","shown"):
            event=getattr(window.events,name,None)
            if event is not None:
                event += window_event("window_native_"+name+"_event")
        def inspect_and_close():
            _smoke_checkpoint("window_probe_enter")
            try:
                _smoke_checkpoint("window_wait_loaded_begin")
                native_loaded=loaded.wait(timeout=25)
                _smoke_checkpoint(
                    "window_wait_loaded_done_"+("yes" if native_loaded else "no"))
                if not native_loaded:
                    raise RuntimeError("Native WebView2 did not fire page-loaded event")
                _smoke_checkpoint("window_probe_loaded")
                # HTML loaded is insufficient: require actual React DOM mount.
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    mounted=window.evaluate_js(
                        "Boolean(document.querySelector('#root') && "
                        "document.querySelector('#root').children.length > 0)")
                    if mounted is True:
                        _smoke_checkpoint("window_react_mounted")
                        ipc=window.evaluate_js(
                            "Boolean(window.pywebview && window.pywebview.api && "
                            "typeof window.pywebview.api.request_camera_still === 'function' && "
                            "typeof window.pywebview.api.poll_camera_still === 'function' && "
                            "typeof window.pywebview.api.cancel_camera_still === 'function')")
                        if ipc is True:
                            _smoke_checkpoint("window_ipc_exposed")
                            # Type signatures alone don't prove that the
                            # installed WebView2 can invoke native host code.
                            # Execute a REAL non-mutating JS -> Python IPC,
                            # without approving any Blender worker.
                            window.evaluate_js(
                                "window.__nvpCameraProbe = 'PENDING';"
                                "window.pywebview.api.camera_render_capabilities()"
                                ".then(x => { window.__nvpCameraProbe = "
                                "x.format === 'nvp.camera.desktop_capability.v1' "
                                "&& x.native_window === true ? 'PASSED' : 'FAILED'; })"
                                ".catch(() => { window.__nvpCameraProbe = 'FAILED'; });")
                            until=time.monotonic()+10
                            while time.monotonic()<until:
                                outcome=window.evaluate_js(
                                    "window.__nvpCameraProbe")
                                if outcome=="PASSED":
                                    result["passed"]=True
                                    break
                                if outcome=="FAILED":
                                    raise RuntimeError(
                                        "Desktop native camera JS IPC failed origin/capability validation")
                                time.sleep(.1)
                            if result["passed"]:
                                _smoke_checkpoint("window_native_capability_pass")
                                # The browser must ALSO open a real project,
                                # visit its camera tab, resolve the authored
                                # source from SQLite and load native USD.
                                result["passed"]=False
                                opened=window.evaluate_js(
                                    "(() => {const b=[...document.querySelectorAll('aside button')]"
                                    ".find(x=>x.textContent.includes('SLATE-08B Window Acceptance'));"
                                    "if(b){b.click();return true;}return false;})()")
                                if opened is not True:
                                    raise RuntimeError("Installed test movie not present in sidebar")
                                # Opening a saved movie is asynchronous. Wait
                                # for the *real* fetched project workspace,
                                # and fail if React shows an error instead of
                                # proceeding to scene assertions.
                                workspace_ready=False
                                end=time.monotonic()+25
                                while time.monotonic()<end:
                                    workspace_ready=window.evaluate_js(
                                        "Boolean(document.querySelector("
                                        "'nav.filmmaker-navigation button')"
                                        "&&document.body.textContent.includes("
                                        "'SLATE-08B Window Acceptance'))")
                                    if workspace_ready:break
                                    time.sleep(.2)
                                if not workspace_ready:
                                    error=window.evaluate_js(
                                        "document.querySelector('[role=alert]')?.textContent || ''")
                                    raise RuntimeError(
                                        "Installed saved movie workspace did not load: "+
                                        str(error)[:180])
                                _smoke_checkpoint("window_plan03_saved_movie_workspace_ready")
                                # Prove the *installed* simplified path,
                                # not just unit-tested React. Read two real
                                # screenplay scenes via SQLite/FastAPI and
                                # change selection in the live WebView.
                                to_library=window.evaluate_js(
                                    "(() => {const b=[...document.querySelectorAll("
                                    "'nav.filmmaker-navigation button')]"
                                    ".find(x=>x.textContent.includes('Scene Library'));"
                                    "if(b){b.click();return true;}return false;})()")
                                if to_library is not True:
                                    raise RuntimeError("Installed filmmaker Scene Library navigation absent")
                                library_ready=False
                                end=time.monotonic()+25
                                while time.monotonic()<end:
                                    library_ready=window.evaluate_js(
                                        "Boolean(document.querySelector("
                                        "'section[aria-label=\\\"Scene Library\\\"]')"
                                        "&&document.body.textContent.includes('INT. KITCHEN - DAY')"
                                        "&&document.body.textContent.includes('EXT. GARDEN - NIGHT')"
                                        "&&document.body.textContent.includes('Not yet assigned'))")
                                    if library_ready:break
                                    time.sleep(.2)
                                if not library_ready:
                                    raise RuntimeError("Installed Scene Library failed to read saved screenplay")
                                scene_chosen=window.evaluate_js(
                                    "(() => {const b=[...document.querySelectorAll("
                                    "'nav.scene-library-list button')]"
                                    ".find(x=>x.textContent.includes('EXT. GARDEN - NIGHT'));"
                                    "if(!b)return false;b.click();"
                                    "return b.getAttribute('aria-current')==='true';})()")
                                if scene_chosen is not True:
                                    end=time.monotonic()+5
                                    while time.monotonic()<end:
                                        scene_chosen=window.evaluate_js(
                                            "Boolean([...document.querySelectorAll("
                                            "'nav.scene-library-list button')]"
                                            ".some(x=>x.textContent.includes('EXT. GARDEN - NIGHT')"
                                            "&&x.getAttribute('aria-current')==='true'))")
                                        if scene_chosen:break
                                        time.sleep(.1)
                                if scene_chosen is not True:
                                    raise RuntimeError("Installed Scene Library cannot select second scene")
                                _smoke_checkpoint("window_plan03_real_scene_library_and_selection_pass")
                                # PLAN-03 moves specialist tools behind an
                                # explicit Advanced Studio disclosure. The
                                # installed test must navigate as a filmmaker
                                # does, not assume a permanently visible
                                # 18-tab developer console. Assert disclosure.
                                expanded=window.evaluate_js(
                                    "(() => {const b=[...document.querySelectorAll("
                                    "'nav.filmmaker-navigation button')]"
                                    ".find(x=>x.textContent.includes('Advanced Studio'));"
                                    "if(!b)return false;"
                                    "if(b.getAttribute('aria-expanded')==='false')b.click();"
                                    "return b.getAttribute('aria-expanded')==='true';})()")
                                if expanded is not True:
                                    raise RuntimeError(
                                        "Installed Advanced Studio disclosure did not open")
                                _smoke_checkpoint("window_plan03_advanced_disclosure_pass")
                                end=time.monotonic()+20
                                while time.monotonic()<end:
                                    clicked=window.evaluate_js(
                                        "(() => {const b=[...document.querySelectorAll('nav.advanced-navigation button')]"
                                        ".find(x=>x.textContent.includes('Virtual camera'));"
                                        "if(b){b.click();return true;}return false;})()")
                                    if clicked is True:
                                        break
                                    time.sleep(.2)
                                if clicked is not True:
                                    raise RuntimeError(
                                        "Installed camera tab did not appear in actual project")
                                end=time.monotonic()+20
                                while time.monotonic()<end:
                                    panel=window.evaluate_js(
                                        "Boolean(document.querySelector("
                                        "'section[aria-label=\\\"Film source camera\\\"]') && "
                                        "document.querySelector("
                                        "'section[aria-label=\\\"Virtual Camera Workbench\\\"]') && "
                                        "document.body.textContent.includes('smoke_scene'))")
                                    if panel is True:
                                        result["passed"]=True
                                        break
                                    time.sleep(.2)
                                if not result["passed"]:
                                    raise RuntimeError(
                                        "Installed OpenUSD camera source did not reach real React workbench")
                                _smoke_checkpoint("window_camera_panel_pass")
                                # The same installed WebView2 must expose
                                # actual data-first 3D audio from a frozen
                                # Digital Take, without any FFmpeg discovery.
                                result["passed"]=False
                                have_bridge=window.evaluate_js(
                                    "Boolean(window.pywebview.api.data_av_catalog "
                                    "&& window.pywebview.api.data_av_begin "
                                    "&& window.pywebview.api.data_av_audio_window "
                                    "&& (window.AudioContext || window.webkitAudioContext))")
                                if not have_bridge:
                                    raise RuntimeError(
                                        "Native WebView2 sound bridge or Web Audio unavailable")
                                window.evaluate_js(
                                    "window.__nvpDataAVProbe='PENDING';"
                                    "window.pywebview.api.data_av_catalog('"+
                                    project["id"]+"').then(x=>{"
                                    "window.__nvpDataAVProbe="
                                    "x.format==='nvp.data_av.native_session.v1' &&"
                                    "x.ffmpeg_runtime_required===false &&"
                                    "x.takes.some(t=>t.take_id==='smoke_frozen_take')"
                                    "?'PASSED':'FAILED';}).catch(()=>{"
                                    "window.__nvpDataAVProbe='FAILED';});")
                                until=time.monotonic()+15
                                while time.monotonic()<until:
                                    state=window.evaluate_js("window.__nvpDataAVProbe")
                                    if state=="PASSED":break
                                    if state=="FAILED":
                                        raise RuntimeError("Native sound catalog IPC failed")
                                    time.sleep(.2)
                                if state!="PASSED":
                                    raise RuntimeError("Native sound IPC timed out")
                                _smoke_checkpoint("window_data_av_catalog_pass")
                                window.evaluate_js(
                                    "(()=>{const b=[...document.querySelectorAll('nav.tabs button')]"
                                    ".find(x=>x.textContent.includes('Native 3D sound'));"
                                    "if(b){b.click();return true;}return false;})()")
                                until=time.monotonic()+20
                                while time.monotonic()<until:
                                    ready=window.evaluate_js(
                                        "Boolean(document.querySelector("
                                        "'section[aria-label=\\\"Data-first native A/V preview\\\"]')"
                                        " && document.body.textContent.includes('smoke_frozen_take'))")
                                    if ready:
                                        result["passed"]=True
                                        break
                                    time.sleep(.2)
                                if not result["passed"]:
                                    raise RuntimeError(
                                        "Data-first source audition UI not mounted in installed WebView2")
                                _smoke_checkpoint("window_data_av_panel_pass")
                                # A REAL installed WebView2 must see the
                                # 30-second frozen Take via the same browser
                                # -> trusted Python catalog and React menu.
                                until=time.monotonic()+20
                                film_in_ui=False
                                while time.monotonic()<until:
                                    film_in_ui=window.evaluate_js(
                                        "Boolean([...document.querySelectorAll('select')].some("
                                        "x=>x.getAttribute('aria-label')==='Native frozen Digital Take'"
                                        "&&[...x.options].some(o=>o.value==='OriginalThirtySecondFilm')))")
                                    if film_in_ui is True:break
                                    time.sleep(.2)
                                if film_in_ui is not True:
                                    raise RuntimeError(
                                        "30-second native source film is absent from installed UI")
                                _smoke_checkpoint("window_plan02e_30s_film_catalog_pass")
                                break
                    time.sleep(.2)
                if not result["passed"]:
                    raise RuntimeError("Bundled NVP React interface did not render")
            except Exception as exc:
                result["failure"]=str(exc)
                _smoke_checkpoint("window_probe_failure_"+type(exc).__name__)
            finally:
                _smoke_checkpoint("window_before_destroy")
                window.destroy()
                _smoke_checkpoint("window_after_destroy")
        _smoke_checkpoint("window_before_webview_start")
        # A watchdog traceback is evidence, NOT a substitute for actual
        # Windows WebView2 loaded/React/IPC success. It can expose a blocked
        # WinForms/UI thread even if Python's callback never returns.
        diag=os.environ.get("NVP_SMOKE_DIAGNOSTIC_PATH")
        if diag:
            import faulthandler
            trace=Path(diag)
            if trace.is_symlink():
                raise RuntimeError("Refusing symlinked GUI diagnostic path")
            with trace.open("a",encoding="utf-8") as stream:
                faulthandler.dump_traceback_later(
                    40,repeat=True,file=stream,exit=False)
                try:
                    webview.start(
                        func=inspect_and_close,gui="edgechromium",debug=False,
                        storage_path=browser_profile,private_mode=True)
                finally:
                    faulthandler.cancel_dump_traceback_later()
        else:
            webview.start(
                func=inspect_and_close,gui="edgechromium",debug=False,
                storage_path=browser_profile,private_mode=True)
        _smoke_checkpoint("window_after_webview_start")
        if not result["passed"]:
            raise RuntimeError(
                "Real NVP WebView2 React UI failed: "+result.get("failure","unknown error"))
        return 0
    finally:
        try:
            if bridge is not None:
                bridge._close()
        finally:
            try:
                server.should_exit=True
                worker.join(timeout=12)
                sock.close()
            finally:
                if old_home is None: os.environ.pop("NVP_HOME",None)
                else: os.environ["NVP_HOME"]=old_home
                shutil.rmtree(test_home,ignore_errors=True)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan03-original-render-worker",action="store_true",
                        help="Trusted contained child: independently evaluate one frozen original source moment")
    parser.add_argument("--manifest",default=None,
                        help="Exact local source render manifest; only for trusted PLAN-03 child")
    parser.add_argument("--smoke",action="store_true",
                        help="Temporary bundled UI/backend/SQLite acceptance")
    parser.add_argument("--smoke-plan03-render",action="store_true",
                        help="Real installed Windows Job Object original OpenUSD render worker and source audit")
    parser.add_argument("--smoke-consoleless",action="store_true",
                        help="Actually start packaged Uvicorn/React/SQLite without stdout or stderr")
    parser.add_argument("--smoke-create",action="store_true",
                        help="Create persistent project for cross-process installed acceptance")
    parser.add_argument("--smoke-reopen",action="store_true",
                        help="Reopen same project after fully exiting previous installed app")
    parser.add_argument("--smoke-window",action="store_true",
                        help="Launch a real native Windows WebView2 and verify page loaded")
    parser.add_argument("--smoke-data-av",action="store_true",
                        help="Verify native frozen USD and spatial PCM in this packaged executable")
    parser.add_argument("--smoke-plan02d",action="store_true",
                        help="Verify installed exact source camera PNG, OS review stand-in and SQLite restart")
    parser.add_argument("--smoke-plan02d-restart-create",action="store_true",
                        help="First installed process builds durable source and image")
    parser.add_argument("--smoke-plan02d-restart-reopen",action="store_true",
                        help="Second installed process verifies original, image and no replay")
    parser.add_argument("--smoke-plan02e",action="store_true",
                        help="Read complete 30s moving native USD + source PCM without proxy")
    parser.add_argument("--smoke-plan02e-restart-create",action="store_true",
                        help="Installed process creates original 30s film and streamed PCM receipt")
    parser.add_argument("--smoke-plan02e-restart-reopen",action="store_true",
                        help="Independent installed process verifies unchanged 30s source and film")
    parser.add_argument("--plan02e-seed-physical-playtest",action="store_true",
                        help="Create TEST-ONLY 30s film in a new TEMP workspace for real GUI sound playback")
    parser.add_argument("--plan02e-verify-physical-playtest",action="store_true",
                        help="Independently verify original 30s USD and PCM after installed GUI playback")
    args=parser.parse_args(argv)
    if args.plan03_original_render_worker:
        if not args.manifest:
            parser.error("A trusted source render manifest is required")
        from tools.nvp_plan03_original_render_worker import main as render_main
        return render_main(["--manifest",args.manifest])
    if args.manifest:
        parser.error("Manifest is allowed only for the trusted native child")
    if sum((args.smoke,args.smoke_plan03_render,args.smoke_consoleless,args.smoke_create,args.smoke_reopen,
            args.smoke_window,args.smoke_data_av,args.smoke_plan02d,
            args.smoke_plan02d_restart_create,args.smoke_plan02d_restart_reopen,
            args.smoke_plan02e,args.smoke_plan02e_restart_create,
            args.smoke_plan02e_restart_reopen,
            args.plan02e_seed_physical_playtest,
            args.plan02e_verify_physical_playtest))>1:
        parser.error("Choose only one installed-app smoke mode")
    if args.smoke:
        return run_smoke()
    if args.smoke_plan03_render:
        from tools.nvp_plan03_original_render_witness import run as render_witness
        report=(Path(os.environ.get("RUNNER_TEMP",tempfile.gettempdir()))/
                "nvp-plan03-installed-real-source-render.json")
        render_witness(report)
        _smoke_checkpoint("plan03_installed_actual_original_render_and_kernel_custody_pass")
        return 0
    if args.smoke_consoleless:
        # Simulate the actual PyInstaller --windowed startup contract,
        # regardless of whether a GitHub-hosted runner provides inherited
        # console handles. Restore streams for healthy source/test harnesses.
        saved_stdout,saved_stderr=sys.stdout,sys.stderr
        try:
            sys.stdout=None
            sys.stderr=None
            _smoke_checkpoint("consoleless_streams_null")
            outcome=run_smoke()
            _smoke_checkpoint("consoleless_loopback_react_sqlite_pass")
            return outcome
        finally:
            sys.stdout,sys.stderr=saved_stdout,saved_stderr
    if args.smoke_window:
        return run_visible_window_smoke()
    if args.smoke_data_av:
        _smoke_checkpoint("before_native_acceptance_import")
        from tools.nvp_data_av_installed_acceptance import run_installed_data_av_smoke
        _smoke_checkpoint("after_native_acceptance_import")
        result = run_installed_data_av_smoke()
        _smoke_checkpoint("after_native_acceptance_run")
        return result
    if args.smoke_plan02d:
        _smoke_checkpoint("before_plan02d_installed_import")
        from tools.nvp_plan02d_installed_acceptance import run_installed_plan02d_smoke
        _smoke_checkpoint("before_plan02d_installed_run")
        result=run_installed_plan02d_smoke()
        _smoke_checkpoint("after_plan02d_installed_run")
        return result
    if args.smoke_plan02d_restart_create or args.smoke_plan02d_restart_reopen:
        _smoke_checkpoint("before_plan02d_cross_process_restart")
        from tools.nvp_plan02d_installed_acceptance import run_installed_plan02d_smoke
        result=run_installed_plan02d_smoke(
            "create" if args.smoke_plan02d_restart_create else "reopen")
        _smoke_checkpoint("after_plan02d_cross_process_restart")
        return result
    if args.smoke_create or args.smoke_reopen:
        return run_persistent_installed_smoke(
            "create" if args.smoke_create else "reopen")
    if (args.smoke_plan02e or args.smoke_plan02e_restart_create or
            args.smoke_plan02e_restart_reopen):
        _smoke_checkpoint("before_plan02e_installed_import")
        from tools.nvp_plan02e_installed_acceptance import run_installed_plan02e_smoke
        phase=("create" if args.smoke_plan02e_restart_create else
               "reopen" if args.smoke_plan02e_restart_reopen else "ephemeral")
        _smoke_checkpoint("before_plan02e_"+phase)
        result=run_installed_plan02e_smoke(phase)
        _smoke_checkpoint("after_plan02e_"+phase)
        return result
    if args.plan02e_seed_physical_playtest or args.plan02e_verify_physical_playtest:
        import json
        explicit=os.environ.get("NVP_HOME")
        if not explicit or not Path(explicit).is_absolute():
            raise PermissionError("Physical test seeding requires explicit absolute NVP_HOME")
        home=Path(explicit).resolve()
        scratch=Path(tempfile.gettempdir()).resolve()
        if (not home.is_relative_to(scratch) or
                not home.name.startswith("nvp-plan02e-physical-") or
                home.is_symlink()):
            raise PermissionError("Refusing to seed into creator-owned Projects")
        if args.plan02e_seed_physical_playtest and (home/"nvp_studio.sqlite3").exists():
            raise FileExistsError("Physical demo seed must target a new test workspace")
        from backend.nvp_studio import Studio
        from backend.nvp_film_index import FilmIndex
        from tools.nvp_plan02e_installed_acceptance import (
            create as create_film, _verify_original, _accept,
        )
        studio=Studio()
        if args.plan02e_verify_physical_playtest:
            marker=home/"plan02e-physical-seed-receipt.json"
            if not marker.is_file():
                raise RuntimeError("Original source receipt missing after GUI playback")
            receipt=json.loads(marker.read_text("utf8"))
            index=FilmIndex(studio)
            _verify_original(index,receipt)
            evidence=_accept(index,receipt,exhaustive=False)
            _verify_original(index,receipt)
            if evidence["original_source_modified"] is not False:
                raise RuntimeError("GUI playback modified original source")
            _smoke_checkpoint("plan02e_physical_original_unchanged_after_gui")
            return 0
        pid=studio.create_project(
            "PLAN02E Native 30-Second Film — TEST SOURCE",
            "Three original USD cameras, moving sphere and test-only 48k PCM",
        )["id"]
        receipt=create_film(FilmIndex(studio),pid)
        (home/"plan02e-physical-seed-receipt.json").write_text(
            json.dumps(receipt,sort_keys=True,indent=2),encoding="utf8")
        _smoke_checkpoint("plan02e_physical_test_only_source_created")
        return 0
    configure_home()
    app=create_app()
    server,worker,port,sock=serve(app)
    bridge=None
    try:
        import webview
        bridge=create_trusted_camera_bridge(port)
        from backend.nvp_webview2_ipc_facade import NativeWebView2API
        window=webview.create_window("NVP — Make Your Movie",
            "http://127.0.0.1:"+str(port),
            width=1280,height=800,min_size=(960,600),
            js_api=NativeWebView2API(bridge))
        bridge._attach_window(window)
        # Isolate browser UDF from the install directory and film source.
        # This keeps the native WebView2 profile writable after NSIS install.
        cache_root=(Path(os.environ.get("LOCALAPPDATA",str(Path.home())))/
                    "NVP")
        webview.start(gui="edgechromium",debug=False,private_mode=True,
                      storage_path=_webview_profile_dir(cache_root))
        return 0
    finally:
        try:
            if bridge is not None:
                bridge._close()
        finally:
            server.should_exit=True
            worker.join(timeout=12)
            sock.close()


def _smoke_checkpoint(stage):
    """Durable stage receipt for native crashes that bypass Python exceptions.

    Only enabled for explicitly requested CI diagnostics. Never records user
    paths, source audio, project data, or environment secrets.
    """
    diagnostic = os.environ.get("NVP_SMOKE_DIAGNOSTIC_PATH")
    if not diagnostic:
        return
    path = Path(diagnostic)
    if path.is_symlink():
        raise RuntimeError("Refusing symlink diagnostic target")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("NVP_SMOKE_STAGE " + stage + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def installed_smoke_entry():
    """Report packaged --windowed smoke exceptions through an opt-in CI file."""
    try:
        _smoke_checkpoint("entry")
        return main()
    except Exception:
        import traceback
        diagnostic = os.environ.get("NVP_SMOKE_DIAGNOSTIC_PATH")
        if diagnostic:
            path = Path(diagnostic)
            if path.is_symlink():
                raise RuntimeError("Refusing symlink diagnostic target")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(traceback.format_exc())
        raise


if __name__=="__main__":
    raise SystemExit(installed_smoke_entry())
