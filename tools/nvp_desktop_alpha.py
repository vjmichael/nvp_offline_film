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
    # PyInstaller --windowed has sys.stdout/sys.stderr=None. Uvicorn's
    # default logging formatter calls stderr.isatty(), and exits before
    # binding the native loopback API. The installed application owns its
    # bounded diagnostic receipts; do not configure console logging from
    # a nonexistent Windows GUI stream.
    config=uvicorn.Config(app,host="127.0.0.1",port=port,
                          access_log=False,log_level="warning",
                          log_config=None,proxy_headers=False)
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


def run_basic_edge_window_smoke():
    """Real installed EdgeChromium + React DOM WITHOUT the native JS bridge.

    This is an independent diagnostic comparison, NOT W1-G IPC acceptance.
    It also must fail if a hosted runner never creates a working browser.
    """
    import webview
    from threading import Event
    with tempfile.TemporaryDirectory(prefix="nvp-w1g-basic-window-") as root:
        old_home=os.environ.get("NVP_HOME")
        os.environ["NVP_HOME"]=str(Path(root)/"Projects")
        server=worker=sock=None
        try:
            _smoke_checkpoint("basic_before_app")
            app=create_app()
            server,worker,port,sock=serve(app)
            _smoke_checkpoint("basic_after_serve")
            url="http://127.0.0.1:"+str(port)
            with urllib.request.urlopen(url+"/",timeout=8) as reply:
                if "assets/" not in reply.read().decode("utf8"):
                    raise RuntimeError("Basic browser target lacks native bundled React")
            _smoke_checkpoint("basic_loopback_verified")
            loaded=Event()
            result={"passed":False}
            window=webview.create_window(
                "NVP Basic Edge Chromium Test",url,width=980,height=680)
            window.events.loaded += lambda:(
                _smoke_checkpoint("basic_loaded_event"),loaded.set())
            window.events.before_show += lambda:_smoke_checkpoint("basic_before_show")
            window.events.shown += lambda:_smoke_checkpoint("basic_shown")
            window.events.before_load += lambda:_smoke_checkpoint("basic_before_load")
            def inspector():
                _smoke_checkpoint("basic_inspector_enter")
                try:
                    if not loaded.wait(25):
                        raise RuntimeError("Basic EdgeChromium failed loaded event")
                    _smoke_checkpoint("basic_loaded_ready")
                    if window.evaluate_js(
                            "Boolean(document.querySelector('#root') && "
                            "document.querySelector('#root').children.length > 0)") is not True:
                        raise RuntimeError("Basic installed React DOM never mounted")
                    result["passed"]=True
                    _smoke_checkpoint("basic_react_dom_verified")
                except Exception as exc:
                    result["error"]=str(exc)
                    _smoke_checkpoint("basic_inspector_failed")
                finally:
                    # Do not let smoke-only teardown hang forever on a
                    # Windows GUI host which cannot dispatch COM messages.
                    closed=Event()
                    def close_window():
                        try:window.destroy()
                        finally:closed.set()
                    threading.Thread(target=close_window,daemon=True).start()
                    if not closed.wait(6):
                        _smoke_checkpoint("basic_destroy_stalled_fail_closed")
                        os._exit(77)
            _smoke_checkpoint("basic_before_webview_start")
            webview.start(func=inspector,gui="edgechromium",debug=False)
            if not result["passed"]:
                raise RuntimeError(result.get("error","No genuine Basic WebView2 result"))
            _smoke_checkpoint("basic_success")
            return 0
        finally:
            if server is not None:
                server.should_exit=True
                worker.join(timeout=12)
                sock.close()
            if old_home is None:os.environ.pop("NVP_HOME",None)
            else:os.environ["NVP_HOME"]=old_home


def run_visible_window_smoke():
    """Installed real WebView2 + native OpenUSD source panel smoke.

    Use a throwaway film workspace: tests must never publish a demo source
    or mutate the creator's durable Projects directory.
    """
    import webview
    from threading import Event
    test_home=Path(tempfile.mkdtemp(prefix="nvp-slate08b-installed-"))
    old_home=os.environ.get("NVP_HOME")
    os.environ["NVP_HOME"]=str(test_home)
    try:
        _smoke_checkpoint("visible_before_create_app")
        app=create_app()
        _smoke_checkpoint("visible_after_create_app")
        from backend.nvp_api import studio
        from backend.nvp_film_index import FilmIndex
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        _smoke_checkpoint("visible_before_project_create")
        project=studio.create_project("SLATE-08B Window Acceptance",
            "One native source camera scene")
        _smoke_checkpoint("visible_before_scene_publish")
        OpenUSDSceneBridge(FilmIndex(studio)).publish(
            project["id"],"smoke_scene",
            prims=[
                {"path":"/World/Actor","role":"actor",
                 "position":[0,0,0]},
                {"path":"/World/Camera","role":"camera",
                 "position":[0,0,8]},
            ],curves=[],native_schemas=True)
        _smoke_checkpoint("visible_after_scene_publish")
        # Separate native A/V smoke from FFmpeg-backed imported video.
        # This is one real frozen OpenUSD Digital Take with a SHA-addressed
        # captured mono signal, for the actual installed WebView2 catalog.
        from backend.nvp_data_av_source import RecordedSoundSources
        from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        import struct
        source_index=FilmIndex(studio)
        _smoke_checkpoint("visible_before_original_pcm_publish")
        RecordedSoundSources(source_index).publish(
            project["id"],"smoke_signal",
            [struct.pack("<"+"h"*4800,*([6000]*4800))])
        _smoke_checkpoint("visible_after_original_pcm_publish")
        TemporalLedger(source_index).publish(
            project["id"],"smoke_events",[{
                "event_id":"smoke_actor_sound","event_kind":"sound",
                "subject_id":"Actor","start_tick":0,
                "end_tick":TICKS_PER_SECOND//2,
                "source_id":"smoke_signal","source_revision":1,
                "payload":{"usd_prim_path":"/World/Actor","gain":0.8},
            }],duration_tick=TICKS_PER_SECOND)
        _smoke_checkpoint("visible_before_take_freeze")
        OpenUSDTakeCapture(
            source_index,verify_creator_action=lambda event,scope:
            event=="smoke_only" and scope["operation"]==
            "nvp.freeze.usd_temporal_take.v1").freeze(
                project["id"],"smoke_frozen_take",scene_id="smoke_scene",
                scene_revision=1,timeline_id="smoke_events",
                timeline_revision=1,sample_ticks=[0],
                creator_event="smoke_only")
        _smoke_checkpoint("visible_after_take_freeze")
        server,worker,port,sock=serve(app)
        _smoke_checkpoint("visible_after_serve")
        # Prove the actual installed loopback server, HTML and original
        # project catalog BEFORE attributing a browser failure to WebView2.
        import json
        with urllib.request.urlopen("http://127.0.0.1:"+str(port)+"/",timeout=8) as page:
            if "assets/" not in page.read().decode("utf8"):
                raise RuntimeError("Installed WebView2 target lacks bundled React HTML")
        _smoke_checkpoint("visible_loopback_html_verified")
        with urllib.request.urlopen("http://127.0.0.1:"+str(port)+"/api/status",timeout=8) as page:
            if json.load(page).get("status")!="ready":
                raise RuntimeError("Installed local NVP API unavailable to WebView2")
        _smoke_checkpoint("visible_loopback_api_verified")
    except BaseException:
        if old_home is None: os.environ.pop("NVP_HOME",None)
        else: os.environ["NVP_HOME"]=old_home
        shutil.rmtree(test_home,ignore_errors=True)
        raise
    loaded=Event()
    result={"passed":False}
    bridge=None
    try:
        _smoke_checkpoint("visible_before_bridge")
        bridge=create_trusted_camera_bridge(port)
        from backend.nvp_webview_ipc_surface import NativeWebviewIPCSurface
        exposed_api=NativeWebviewIPCSurface(bridge)
        _smoke_checkpoint("visible_before_create_window")
        window=webview.create_window("NVP Alpha Window Acceptance",
            "http://127.0.0.1:"+str(port),width=1000,height=700,
            js_api=exposed_api)
        bridge._attach_window(window)
        _smoke_checkpoint("visible_after_create_window")
        window.events.loaded += lambda:(_smoke_checkpoint("visible_page_loaded_event"), loaded.set())
        # WebView2 on a noninteractive Windows service runner may create
        # a Python window object but never receive a real shown/load event.
        # Distinguish that state from a server/React/IPC failure.
        window.events.before_show += lambda:_smoke_checkpoint("visible_before_show_event")
        window.events.initialized += lambda renderer:_smoke_checkpoint(
            "visible_renderer_initialized_"+str(renderer))
        window.events.shown += lambda:_smoke_checkpoint("visible_native_shown_event")
        window.events.before_load += lambda:_smoke_checkpoint("visible_before_load_event")
        window.events.closed += lambda:_smoke_checkpoint("visible_native_closed_event")
        def inspect_and_close():
            _smoke_checkpoint("visible_inspector_enter")
            try:
                if not loaded.wait(timeout=25):
                    _smoke_checkpoint("visible_loaded_event_timeout")
                    # Some WebView2 hosts omit loaded callback despite a
                    # working DOM. Probe a REAL React mount, never a fake
                    # success. Bound the COM call: a broken renderer must not
                    # hang the smoke process for minutes.
                    probe_done=Event()
                    probe={"mounted":False}
                    def inspect_loaded_dom():
                        try:
                            probe["mounted"]=window.evaluate_js(
                                "Boolean(document.querySelector('#root') && "
                                "document.querySelector('#root').children.length > 0)") is True
                        except BaseException as exc:
                            probe["error_type"]=type(exc).__name__
                        finally:
                            probe_done.set()
                    probe_thread=threading.Thread(
                        target=inspect_loaded_dom,daemon=True,
                        name="NVP WebView2 bounded DOM recovery probe")
                    probe_thread.start()
                    if not probe_done.wait(timeout=5):
                        raise RuntimeError(
                            "Native WebView2 never emitted loaded and COM DOM probe stalled")
                    if not probe["mounted"]:
                        raise RuntimeError(
                            "Native WebView2 neither emitted loaded nor mounted real React DOM")
                    _smoke_checkpoint("visible_dom_recovered_without_loaded_event")
                _smoke_checkpoint("visible_inspector_page_ready")
                # HTML loaded is insufficient: require actual React DOM mount.
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    mounted=window.evaluate_js(
                        "Boolean(document.querySelector('#root') && "
                        "document.querySelector('#root').children.length > 0)")
                    if mounted is True:
                        ipc=window.evaluate_js(
                            "Boolean(window.pywebview && window.pywebview.api && "
                            "typeof window.pywebview.api.request_camera_still === 'function' && "
                            "typeof window.pywebview.api.poll_camera_still === 'function' && "
                            "typeof window.pywebview.api.cancel_camera_still === 'function')")
                        if ipc is True:
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
                                # The browser must ALSO open a real project,
                                # visit its camera tab, resolve the authored
                                # source from SQLite and load native USD.
                                result["passed"]=False
                                window.evaluate_js(
                                    "(() => {const b=[...document.querySelectorAll('aside button')]"
                                    ".find(x=>x.textContent.includes('SLATE-08B Window Acceptance'));"
                                    "if(b){b.click();return true;}return false;})()")
                                end=time.monotonic()+20
                                while time.monotonic()<end:
                                    clicked=window.evaluate_js(
                                        "(() => {const b=[...document.querySelectorAll('nav.tabs button')]"
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
                                break
                    time.sleep(.2)
                if not result["passed"]:
                    raise RuntimeError("Bundled NVP React interface did not render")
            except Exception as exc:
                result["failure"]=str(exc)
                _smoke_checkpoint("visible_inspector_failed_"+type(exc).__name__)
            finally:
                _smoke_checkpoint("visible_before_window_destroy")
                # An uninitialized EdgeChromium COM host can deadlock when
                # destroy() is called synchronously from the pywebview
                # inspection callback. Bound it, fail closed, and leave the
                # surrounding OS Job/CI owner to reap the test process.
                close_done=Event()
                def close_native_window():
                    try:
                        window.destroy()
                    except BaseException as exc:
                        result["destroy_error"]=type(exc).__name__
                    finally:
                        close_done.set()
                closer=threading.Thread(
                    target=close_native_window,daemon=True,
                    name="NVP WebView2 bounded smoke shutdown")
                closer.start()
                if not close_done.wait(timeout=6):
                    _smoke_checkpoint("visible_destroy_stalled_fail_closed")
                    os._exit(75)  # Test-only isolated process, never user UI.
                if result.get("destroy_error"):
                    _smoke_checkpoint("visible_destroy_failed")
                    os._exit(76)
                _smoke_checkpoint("visible_after_window_destroy")
        _smoke_checkpoint("visible_before_webview_start")
        webview.start(func=inspect_and_close,gui="edgechromium",debug=False)
        _smoke_checkpoint("visible_after_webview_start")
        if not result["passed"]:
            raise RuntimeError(
                "Real NVP WebView2 React UI failed: "+result.get("failure","unknown error"))
        _smoke_checkpoint("visible_verified")
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


def run_release_review_smoke():
    """Real packaged Ed25519 verifier test using a DISPOSABLE in-memory key.

    This verifies runtime availability, reviewed full-file coverage and
    tamper refusal, not a signed creator release or legal approval.
    """
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from tools.nvp_w1g_reviewed_release import (
        FORMAT, _canonical, license_review_digest, verify_signed_release_review,
    )
    receipt={
        "platform":"windows-amd64",
        "app_sha256":"a"*64,
        "files":{
            "NVP.exe":{"bytes":123,"sha256":"a"*64},
            "_internal/approved-worker.exe":{"bytes":456,"sha256":"b"*64},
        },
    }
    review={
        "format":FORMAT,
        "payload_sha256":license_review_digest(receipt),
        "platform":"windows-amd64",
        "reviewer_reference":"ephemeral packaged-verifier smoke only",
        "reviewed_artifacts":[
            {"file":name,"sha256":row["sha256"],"spdx_license":"MIT",
             "redistribution_reference":"ephemeral test reference only"}
            for name,row in receipt["files"].items()
        ],
    }
    private=Ed25519PrivateKey.generate()
    public=private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    signed={"payload":review,"signature_base64":base64.b64encode(
        private.sign(_canonical(review))).decode("ascii")}
    accepted=verify_signed_release_review(
        receipt,signed,pinned_reviewer_public_key=public)
    if (accepted["reviewed_artifact_count"]!=2 or
        accepted["license_review_signature_verified"] is not True):
        raise RuntimeError("Packaged Ed25519 review did not accept exact bytes")
    _smoke_checkpoint("review_verifier_signed_full_inventory")
    receipt["files"]["_internal/approved-worker.exe"]["sha256"]="c"*64
    try:
        verify_signed_release_review(
            receipt,signed,pinned_reviewer_public_key=public)
    except PermissionError:
        _smoke_checkpoint("review_verifier_tampered_binary_refused")
    else:
        raise RuntimeError("Packaged Ed25519 verifier accepted tampered binary")
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true",
                        help="Temporary bundled UI/backend/SQLite acceptance")
    parser.add_argument("--smoke-create",action="store_true",
                        help="Create persistent project for cross-process installed acceptance")
    parser.add_argument("--smoke-reopen",action="store_true",
                        help="Reopen same project after fully exiting previous installed app")
    parser.add_argument("--smoke-window",action="store_true",
                        help="Launch a real native Windows WebView2 and verify page loaded")
    parser.add_argument("--smoke-window-basic",action="store_true",
                        help="Isolate actual installed EdgeChromium React load without native bridge")
    parser.add_argument("--smoke-data-av",action="store_true",
                        help="Verify native frozen USD and spatial PCM in this packaged executable")
    parser.add_argument("--smoke-release-review",action="store_true",
                        help="Verify packaged Ed25519 signature admission and tamper refusal")
    args=parser.parse_args(argv)
    if sum((args.smoke,args.smoke_create,args.smoke_reopen,
            args.smoke_window,args.smoke_window_basic,args.smoke_data_av,
            args.smoke_release_review))>1:
        parser.error("Choose only one installed-app smoke mode")
    if args.smoke_release_review:
        return run_release_review_smoke()
    if args.smoke:
        return run_smoke()
    if args.smoke_window_basic:
        return run_basic_edge_window_smoke()
    if args.smoke_window:
        return run_visible_window_smoke()
    if args.smoke_data_av:
        _smoke_checkpoint("before_native_acceptance_import")
        from tools.nvp_data_av_installed_acceptance import run_installed_data_av_smoke
        _smoke_checkpoint("after_native_acceptance_import")
        result = run_installed_data_av_smoke()
        _smoke_checkpoint("after_native_acceptance_run")
        return result
    if args.smoke_create or args.smoke_reopen:
        return run_persistent_installed_smoke(
            "create" if args.smoke_create else "reopen")
    # Normal installed GUI must remain an owned release participant for
    # its complete lifetime. An external upgrade coordinator cannot switch
    # binaries while the creator's WebView2 host is still open or launching
    # worker domains that do not yet have their own launch slot.
    from contextlib import ExitStack
    with ExitStack() as lifetime:
        if os.name=="nt":
            from backend.nvp_w1g_release_gate import WindowsWorkerLifetimeSlot
            slot=WindowsWorkerLifetimeSlot().acquire()
            lifetime.callback(slot.release)
        configure_home()
        app=create_app()
        server,worker,port,sock=serve(app)
        bridge=None
        try:
            import webview
            bridge=create_trusted_camera_bridge(port)
            from backend.nvp_webview_ipc_surface import NativeWebviewIPCSurface
            exposed_api=NativeWebviewIPCSurface(bridge)
            window=webview.create_window("NVP — Make Your Movie",
                "http://127.0.0.1:"+str(port),
                width=1280,height=800,min_size=(960,600),js_api=exposed_api)
            bridge._attach_window(window)
            webview.start(gui="edgechromium",debug=False)
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
    stacks=None
    try:
        if (os.environ.get("NVP_SMOKE_DIAGNOSTIC_PATH") and
            ("--smoke-window" in sys.argv or
             "--smoke-window-basic" in sys.argv)):
            import faulthandler
            target=Path(os.environ["NVP_SMOKE_DIAGNOSTIC_PATH"])
            stack_path=target.with_name(target.stem+"-stacks.txt")
            if stack_path.is_symlink() or stack_path.exists():
                raise RuntimeError("Refusing existing native WebView2 thread-stack evidence")
            stacks=stack_path.open("x",encoding="utf8")
            faulthandler.enable(file=stacks,all_threads=True)
            faulthandler.dump_traceback_later(30,repeat=True,file=stacks)
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
    finally:
        if stacks is not None:
            import faulthandler
            faulthandler.cancel_dump_traceback_later()
            faulthandler.disable()
            stacks.close()


if __name__=="__main__":
    raise SystemExit(installed_smoke_entry())
