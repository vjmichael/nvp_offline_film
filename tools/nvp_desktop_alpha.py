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
    editor=dist/"postproduction.html"
    if not entry.is_file() or not editor.is_file() or not (dist/"assets").is_dir():
        raise RuntimeError("NVP director/editor frontend assets not installed: "+str(dist))
    app.add_middleware(TrustedHostMiddleware,
                       allowed_hosts=["127.0.0.1","localhost"])
    app.mount("/assets",StaticFiles(directory=str(dist/"assets")),name="nvp_assets")
    @app.get("/",include_in_schema=False)
    def desktop_home():
        return FileResponse(entry)
    @app.get("/postproduction.html",include_in_schema=False)
    def desktop_postproduction():
        return FileResponse(editor)
    return app


def serve(app):
    import uvicorn
    listening=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    listening.bind(("127.0.0.1",0))
    listening.listen(128)
    listening.set_inheritable(False)
    port=listening.getsockname()[1]
    # Frozen PyInstaller --windowed deliberately has sys.stdout and
    # sys.stderr set to None. Uvicorn's default formatter calls isatty(),
    # crashing before the actual loopback server starts. No console logger
    # belongs in the installed filmmaker app: use host-owned diagnostics.
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
    """Real installed NVP: two projects, screenplay/revision, protected restart.

    Test passphrases and source text are synthetic. Diagnostic files contain
    stage IDs only. This is Windows runner verification, not owner-operated UI.
    """
    _smoke_checkpoint("persistent_"+mode+"_entered")
    import json
    from hashlib import sha256
    from http.cookiejar import CookieJar
    from urllib.error import HTTPError
    home=os.environ.get("NVP_HOME")
    if not home:
        raise RuntimeError("Installed acceptance requires explicit NVP_HOME")
    root=Path(home)
    root.mkdir(parents=True,exist_ok=True)
    marker=root/"installed-smoke-project.json"
    password="NVP-G03-SYNTHETIC-RUNNER-ONLY-PASSPHRASE-2026"
    app=create_app()
    _smoke_checkpoint("persistent_"+mode+"_app_ready")
    server,worker,port,sock=serve(app)
    _smoke_checkpoint("persistent_"+mode+"_server_started")
    base="http://127.0.0.1:"+str(port)

    def call(path,method="GET",payload=None,*,client=None):
        data=None if payload is None else json.dumps(payload).encode("utf8")
        headers={} if data is None else {"Content-Type":"application/json",
                                         "x-nvp-director":"1"}
        request=urllib.request.Request(base+path,headers=headers,
                                       data=data,method=method)
        with (client or urllib.request.build_opener()).open(request,timeout=12) as reply:
            return json.load(reply)

    def denied(path,expected=423,*,client=None):
        try:
            call(path,client=client)
        except HTTPError as error:
            if error.code != expected:
                raise RuntimeError(
                    "Expected protected movie denial "+str(expected)+
                    ", got "+str(error.code)) from error
            return
        raise RuntimeError("Protected movie data exposed without unlocked session")

    try:
        with urllib.request.urlopen(base+"/api/status",timeout=10) as reply:
            if json.load(reply).get("status")!="ready":
                raise RuntimeError("Installed offline API is not ready")
        with urllib.request.urlopen(base+"/",timeout=10) as reply:
            if "assets/" not in reply.read().decode("utf8"):
                raise RuntimeError("Bundled React director UI unavailable")
        with urllib.request.urlopen(base+"/postproduction.html",timeout=10) as reply:
            if "assets/" not in reply.read().decode("utf8"):
                raise RuntimeError("Bundled separate editor unavailable")
        _smoke_checkpoint("persistent_"+mode+"_both_html_ok")
        if mode=="create":
            if marker.exists():
                raise RuntimeError("Installed test already has a project marker")
            first=call("/api/projects","POST",{
                "title":"NVP Installed Restart Acceptance",
                "idea":"Persistent native project save and reopen"})
            screenplay="INT. EDIT SUITE - DAY\n\nA camera rolls."
            changed=call("/api/projects/"+first["id"]+"/screenplay","PUT",{
                "screenplay":screenplay,"expected_revision":0})
            if changed["revision"]!=1:
                raise RuntimeError("Installed original screenplay failed to commit")
            second=call("/api/projects","POST",{
                "title":"NVP Protected Second Movie",
                "idea":"Confidential test description",
                "screenplay":"EXT. HARBOR - SUNSET\n\nAn empty boat returns."})
            if not second.get("scenes") or second["revision"]!=0:
                raise RuntimeError("Atomic original screenplay was not saved")
            call("/api/projects/"+second["id"]+"/protect","POST",{
                "passphrase":password})
            denied("/api/projects/"+second["id"])
            listing=call("/api/projects")
            hidden=next(row for row in listing if row["id"]==second["id"])
            if not hidden.get("locked") or "idea" in hidden:
                raise RuntimeError("Locked installed project disclosed synopsis")
            _smoke_checkpoint("persistent_create_two_projects_and_lock_verified")
            marker.write_text(json.dumps({
                "first_id":first["id"],"first_title":first["title"],
                "first_screenplay_sha256":sha256(screenplay.encode()).hexdigest(),
                "first_revision":1,"protected_id":second["id"],
                "protected_title":second["title"],
                "protected_screenplay_sha256":sha256(
                    second["screenplay"].encode()).hexdigest()
            },sort_keys=True),encoding="utf8")
        elif mode=="reopen":
            expected=json.loads(marker.read_text("utf8"))
            first=call("/api/projects/"+expected["first_id"])
            if (first["title"]!=expected["first_title"] or
                first["revision"]!=expected["first_revision"] or
                sha256(first["screenplay"].encode()).hexdigest()!=
                    expected["first_screenplay_sha256"]):
                raise RuntimeError("First movie did not survive installed restart")
            protected="/api/projects/"+expected["protected_id"]
            denied(protected)
            denied(protected+"/story-bible")
            listing=call("/api/projects")
            redacted=next(x for x in listing if x["id"]==expected["protected_id"])
            if redacted.get("unlocked") or "idea" in redacted:
                raise RuntimeError("Installed restart unexpectedly unlocked movie")
            cookies=CookieJar()
            opener=urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(cookies))
            unlocked=call(protected+"/unlock","POST",{
                "passphrase":password},client=opener)
            if unlocked.get("access")!="unlocked":
                raise RuntimeError("Installed protected movie could not unlock")
            second=call(protected,client=opener)
            if (second["title"]!=expected["protected_title"] or
                sha256(second["screenplay"].encode()).hexdigest()!=
                    expected["protected_screenplay_sha256"]):
                raise RuntimeError("Protected movie lost original screenplay")
            switched=call("/api/projects/"+expected["first_id"],client=opener)
            if switched["id"]!=expected["first_id"]:
                raise RuntimeError("Movie switching selected foreign project")
            call(protected+"/lock","POST",{},client=opener)
            denied(protected,client=opener)
            from backend.nvp_studio import Studio
            durable=Studio(root/"nvp_studio.sqlite3").get_project(
                expected["first_id"])
            if durable["revision"]!=expected["first_revision"]:
                raise RuntimeError("Durable film revision changed during reopen")
            _smoke_checkpoint("persistent_reopen_two_movies_lock_switch_verified")
        else:
            raise ValueError("Unknown installed restart mode")
        _smoke_checkpoint("persistent_"+mode+"_completed")
        return 0
    finally:
        server.should_exit=True
        worker.join(timeout=12)
        sock.close()
        _smoke_checkpoint("persistent_"+mode+"_server_shutdown")
        if worker.is_alive():
            raise RuntimeError("Installed NVP failed clean server shutdown")

def create_trusted_camera_bridge(port):
    """Desktop-only pywebview IPC; never registered as an HTTP route."""
    from backend.nvp_api import studio, film_access
    from backend.nvp_film_index import FilmIndex
    from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
    return TrustedDesktopCameraBridge(
        FilmIndex(studio),origin="http://127.0.0.1:"+str(port),
        project_lock_check=film_access().any_protected)


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
        app=create_app()
        from backend.nvp_api import studio
        from backend.nvp_film_index import FilmIndex
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        project=studio.create_project("SLATE-08B Window Acceptance",
            "One native source camera scene",
            "EXT. NATIVE CAMERA SOUND SOURCE - DAY\n\nA field and an owl.")
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
        server,worker,port,sock=serve(app)
    except BaseException:
        if old_home is None: os.environ.pop("NVP_HOME",None)
        else: os.environ["NVP_HOME"]=old_home
        shutil.rmtree(test_home,ignore_errors=True)
        raise
    loaded=Event()
    result={"passed":False,"phase":"started"}
    bridge=None
    try:
        bridge=create_trusted_camera_bridge(port)
        window=webview.create_window("NVP Director-first Native Sound Acceptance",
            "http://127.0.0.1:"+str(port),width=1100,height=760,js_api=bridge)
        bridge._attach_window(window)
        window.events.loaded += lambda:loaded.set()
        def wait_js(expression,seconds,description):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                if window.evaluate_js(expression) is True:
                    return
                time.sleep(.2)
            raise RuntimeError(description)
        def inspect_and_close():
            try:
                if not loaded.wait(timeout=30):
                    raise RuntimeError("Installed WebView2 page-loaded event missing")
                # Director-first navigation has replaced old engineering tabs.
                # Native A/V remains accessible to host/bridge, not in a
                # visible technical panel.
                wait_js(
                    "Boolean(document.querySelector('div[role=\"dialog\"]') "
                    "&& document.querySelector('aside.film-sidebar') "
                    "&& document.body.textContent.includes('New Movie') "
                    "&& document.body.textContent.includes('Resume Working'))",
                    25,"Real director New/Resume UI not mounted")
                technical=window.evaluate_js(
                    "Boolean(document.querySelector('nav.tabs') || "
                    "document.querySelector('section[aria-label=\"Data-first native A/V preview\"]'))")
                if technical:
                    raise RuntimeError("Hidden engineering panels visible to filmmaker")
                # Real native JS -> Python camera interface, not name existence.
                window.evaluate_js(
                    "window.__nvpBridgeCheck='PENDING';"
                    "Promise.resolve(window.pywebview?.api?.camera_render_capabilities?.())"
                    ".then(x=>{window.__nvpBridgeCheck="
                    "x?.format==='nvp.camera.desktop_capability.v1' && "
                    "x?.native_window===true ? 'PASSED':'FAILED'})"
                    ".catch(()=>{window.__nvpBridgeCheck='FAILED'})")
                wait_js("window.__nvpBridgeCheck==='PASSED'",15,
                        "Native camera host bridge did not answer in WebView2")
                # Real UI opens a project, but no technical tabs are restored.
                selected=window.evaluate_js(
                    "(()=>{let d=document.querySelector('div[role=\"dialog\"]');"
                    "let b=[...d.querySelectorAll('button')].find(x=>"
                    "x.textContent.includes('Resume Working'));"
                    "if(!b)return false;b.click();return true})()")
                if not selected:
                    raise RuntimeError("Director Resume Working button not clickable")
                wait_js(
                    "Boolean([...document.querySelectorAll('button.film-movie-card')]"
                    ".find(x=>x.textContent.includes('SLATE-08B Window Acceptance')))",
                    25,"Original film missing from director project list")
                chosen=window.evaluate_js(
                    "(()=>{let b=[...document.querySelectorAll('button.film-movie-card')]"
                    ".find(x=>x.textContent.includes('SLATE-08B Window Acceptance'));"
                    "if(!b)return false;b.click();return true})()")
                if not chosen:
                    raise RuntimeError("Director cannot open saved frozen source")
                wait_js(
                    "Boolean(document.querySelector('nav.film-steps') && "
                    "document.body.textContent.includes('EXT. NATIVE CAMERA SOUND SOURCE'))",
                    25,"Native original's film source not visible in director screen")
                # Direct native sound catalog via the same installed WebView2
                # bridge. --smoke-data-av separately proves sample-accurate
                # PCM output; this checks the actual native JS/host boundary.
                window.evaluate_js(
                    "window.__nvpNativeSoundCheck='PENDING';"
                    "window.pywebview.api.data_av_catalog('"+project["id"]+"')"
                    ".then(x=>{window.__nvpNativeSoundCheck="
                    "x.format==='nvp.data_av.native_session.v1' && "
                    "x.ffmpeg_runtime_required===false && "
                    "x.takes.some(t=>t.take_id==='smoke_frozen_take')"
                    "?'PASSED':'FAILED'})"
                    ".catch(()=>{window.__nvpNativeSoundCheck='FAILED'})")
                wait_js("window.__nvpNativeSoundCheck==='PASSED'",
                        20,"Installed native sound bridge cannot read original Digital Take")
                result["passed"]=True
                _smoke_checkpoint("native_data_av_bridge_director_screen_pass")
            except Exception as error:
                result["failure"]=str(error)
            finally:
                window.destroy()
        webview.start(func=inspect_and_close,gui="edgechromium",debug=False)
        if not result["passed"]:
            raise RuntimeError(
                "Native director screen or data-first IPC failed: "+
                result.get("failure","unknown"))
        return 0
    finally:
        try:
            if bridge is not None:
                bridge._close()
        finally:
            server.should_exit=True
            worker.join(timeout=12)
            sock.close()
            if old_home is None: os.environ.pop("NVP_HOME",None)
            else: os.environ["NVP_HOME"]=old_home
            shutil.rmtree(test_home,ignore_errors=True)


def run_g03_window_smoke():
    """Real Windows WebView2 director-first UI, not the legacy engineering tabs.

    An ephemeral movie is created in a throwaway home. Source is inspected in
    the actual native React page, including the separate editor navigation.
    This is runner UI acceptance, not an owner-operated physical workstation.
    """
    import webview
    from threading import Event
    temp_home=Path(tempfile.mkdtemp(prefix="nvp-g03-native-"))
    previous=os.environ.get("NVP_HOME")
    os.environ["NVP_HOME"]=str(temp_home)
    server=worker=sock=None
    try:
        app=create_app()
        from backend.nvp_api import studio
        movie=studio.create_project(
            "G03 Visual Movie",
            "A valley in the early morning",
            "EXT. VALLEY - MORNING\n\nMist drifts across the hillside.")
        second_movie=studio.create_project(
            "G03 Second Film",
            "Waves at the coast",
            "EXT. COAST - DAY\n\nA cloud crosses the water.")
        server,worker,port,sock=serve(app)
        loaded=Event()
        result={"passed":False,"phase":"not_started"}
        window=webview.create_window(
            "NVP Director-first Acceptance",
            "http://127.0.0.1:"+str(port),width=1100,height=760)
        window.events.loaded += lambda:loaded.set()

        def assert_visible():
            try:
                if not loaded.wait(30):
                    raise RuntimeError("G03 native WebView did not load")
                deadline=time.monotonic()+25
                ready=False
                while time.monotonic()<deadline:
                    ready=window.evaluate_js(
                        "Boolean(document.querySelector('div[role=\\\"dialog\\\"]') "
                        "&& document.querySelector('aside.film-sidebar') "
                        "&& document.body.textContent.includes('New Movie') "
                        "&& document.body.textContent.includes('Resume Working'))")
                    if ready is True:break
                    time.sleep(.2)
                if not ready:
                    raise RuntimeError("New Movie / Resume Working director home missing")
                result["phase"]="welcome"
                _smoke_checkpoint("g03_native_welcome_observed")
                hold_welcome=int(os.environ.get("NVP_G03_UIA_WELCOME_HOLD_SECONDS","0"))
                if hold_welcome<0 or hold_welcome>30:
                    raise ValueError("Invalid native welcome UIA hold")
                if hold_welcome:
                    time.sleep(hold_welcome)
                # Verify that the old engineering navigation is not mounted.
                technical=window.evaluate_js(
                    "Boolean(document.querySelector('nav.tabs') "
                    "|| document.querySelector('aside .sidebar-bottom') "
                    "|| document.querySelector('[aria-label=\\\"Data-first native A/V preview\\\"]'))")
                if technical:
                    raise RuntimeError("Old engineering workspace remains visible")
                choose=window.evaluate_js(
                    "(()=>{const d=document.querySelector('div[role=\\\"dialog\\\"]');"
                    "const b=[...d.querySelectorAll('button')].find(x=>"
                    "x.textContent.trim()==='Resume Working');"
                    "if(!b)return false;b.click();return true;})()")
                if not choose:
                    raise RuntimeError("Resume Working cannot be selected")
                deadline=time.monotonic()+18
                opened=False
                while time.monotonic()<deadline:
                    opened=window.evaluate_js(
                        "(()=>{const b=[...document.querySelectorAll('button.film-movie-card')]"
                        ".find(x=>x.textContent.includes('G03 Visual Movie'));"
                        "if(!b)return false;b.click();return true;})()")
                    if opened:break
                    time.sleep(.2)
                if not opened:
                    raise RuntimeError("Saved film missing from Resume Working")
                deadline=time.monotonic()+20
                scene=False
                while time.monotonic()<deadline:
                    scene=window.evaluate_js(
                        "Boolean(document.querySelector('nav.film-steps')"
                        "&& document.body.textContent.includes('Actor-free scenes welcome')"
                        "&& document.body.textContent.includes('EXT. VALLEY - MORNING'))")
                    if scene:break
                    time.sleep(.2)
                if not scene:
                    raise RuntimeError("Real saved actor-free scene not visible")
                result["phase"]="scenes"
                # A real React click must switch to a second project and
                # back without borrowing the first movie's source scene.
                next_movie=window.evaluate_js(
                    "(()=>{const b=[...document.querySelectorAll('aside.film-sidebar .film-project')]"
                    ".find(x=>x.textContent.includes('G03 Second Film'));"
                    "if(!b)return false;b.click();return true;})()")
                if not next_movie:
                    raise RuntimeError("Cannot select second saved movie")
                deadline=time.monotonic()+18
                changed=False
                while time.monotonic()<deadline:
                    changed=window.evaluate_js(
                        "Boolean(document.querySelector('main.film-main h1')"
                        "&& document.querySelector('main.film-main h1').textContent==='G03 Second Film'"
                        "&& document.body.textContent.includes('EXT. COAST - DAY')"
                        "&& !document.body.textContent.includes('Mist drifts across the hillside'))")
                    if changed:break
                    time.sleep(.2)
                if not changed:
                    raise RuntimeError("Native UI failed project switch or leaked prior source")
                first_movie=window.evaluate_js(
                    "(()=>{const b=[...document.querySelectorAll('aside.film-sidebar .film-project')]"
                    ".find(x=>x.textContent.includes('G03 Visual Movie'));"
                    "if(!b)return false;b.click();return true;})()")
                if not first_movie:
                    raise RuntimeError("Cannot return to original saved movie")
                deadline=time.monotonic()+18
                returned=False
                while time.monotonic()<deadline:
                    returned=window.evaluate_js(
                        "Boolean(document.querySelector('main.film-main h1')"
                        "&& document.querySelector('main.film-main h1').textContent==='G03 Visual Movie'"
                        "&& document.body.textContent.includes('EXT. VALLEY - MORNING'))")
                    if returned:break
                    time.sleep(.2)
                if not returned:
                    raise RuntimeError("Native UI did not restore first movie")
                result["phase"]="two_movie_switch_verified"
                switched=window.evaluate_js(
                    "(()=>{const b=[...document.querySelectorAll('nav.film-steps button')]"
                    ".find(x=>x.textContent.includes('Edit Film'));"
                    "if(!b)return false;b.click();return true;})()")
                if not switched:
                    raise RuntimeError("Edit Film phase cannot be selected")
                deadline=time.monotonic()+15
                link=False
                while time.monotonic()<deadline:
                    link=window.evaluate_js(
                        "Boolean(document.querySelector("
                        "'a[href*=\\\"postproduction.html\\\"][target=\\\"_blank\\\"]'))")
                    if link:break
                    time.sleep(.2)
                if not link:
                    raise RuntimeError("Separate Post-Production window link missing")
                result["phase"]="postproduction_link"
                with urllib.request.urlopen(
                    "http://127.0.0.1:"+str(port)+"/postproduction.html",
                    timeout=5) as response:
                    if response.status!=200 or b"/assets/" not in response.read():
                        raise RuntimeError("Installed editor HTML not served")
                result["phase"]="postproduction_loaded"
                result["passed"]=True
                _smoke_checkpoint("g03_native_ui_observed")
                # CI-only: preserve the actual installed window for a separate
                # OS UIAutomation inspection, not only JavaScript DOM checks.
                hold=int(os.environ.get("NVP_G03_UIA_HOLD_SECONDS","0"))
                if hold < 0 or hold > 45:
                    raise ValueError("Invalid G03 UIAutomation hold duration")
                if hold:
                    time.sleep(hold)
            except Exception as exc:
                result["failure"]=str(exc)
            finally:
                window.destroy()

        webview.start(func=assert_visible,gui="edgechromium",debug=False)
        if not result["passed"]:
            raise RuntimeError("G03 native WebView acceptance failed ("+
                               result["phase"]+"): "+
                               result.get("failure","unknown"))
        print("G03_NATIVE_WEBVIEW_DIRECTOR_RESUME_EDITOR_PASS")
        return 0
    finally:
        if server is not None:server.should_exit=True
        if worker is not None:worker.join(timeout=12)
        if sock is not None:sock.close()
        if previous is None:os.environ.pop("NVP_HOME",None)
        else:os.environ["NVP_HOME"]=previous
        shutil.rmtree(temp_home,ignore_errors=True)

def run_g03_live_installed_smoke(mode):
    """Actually installed Windows app: encrypted live SQLite/source + restart.

    No user's film is used. Smoke data are synthetic; original working
    screenplay, source PCM, encrypted revision and test key are never logged.
    """
    import base64
    import hashlib
    import http.cookiejar
    import json
    from urllib.error import HTTPError
    from backend.nvp_api import live_films, studio
    from backend.nvp_project_access import COOKIE
    _smoke_checkpoint("live_"+mode+"_entered")
    if sys.platform!="win32":
        raise RuntimeError("Real Windows user DPAPI is mandatory")
    home=Path(os.environ["NVP_HOME"])
    marker=home/"g03-live-windows-smoke.json"
    secret="G03-SYNTHETIC-ENCRYPTED-LIVE-ORIGINAL-DATA"
    scene="EXT. SECRET WINDOW - NIGHT\n\n"+secret
    payload=b"#usda 1.0\n\n# "+secret.encode("ascii")
    password="G03 synthetic live encrypted Windows passphrase 2026"
    app=create_app()
    server,thread,port,sock=serve(app)
    base="http://127.0.0.1:"+str(port)
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar))
    def call(path,method="GET",data=None):
        blob=None if data is None else json.dumps(data).encode("utf8")
        req=urllib.request.Request(base+path,data=blob,method=method,
            headers={"Content-Type":"application/json","x-nvp-director":"1"})
        with opener.open(req,timeout=15) as response:
            return json.load(response)
    def denied(path,status):
        try:
            call(path)
        except HTTPError as error:
            if error.code!=status:
                raise RuntimeError("Encrypted endpoint had unexpected denial")
            return
        raise RuntimeError("Encrypted movie leaked over a denied API path")
    try:
        if mode=="create":
            if marker.exists():
                raise RuntimeError("Encrypted installed smoke already exists")
            m=call("/api/projects/encrypted","POST",{
                "title":"G03 installed protected movie","idea":"SYNTHETIC SECRET IDEA",
                "screenplay":scene,"passphrase":password})
            pid=m["id"]
            if not m["encrypted"] or m["revision"]!=0:
                raise RuntimeError("Installed encrypted creation failed")
            denied("/api/projects/"+pid,403)
            recovered=call("/api/projects/"+pid+"/live")
            if recovered["screenplay"]!=scene:
                raise RuntimeError("Encrypted live movie did not read back")
            uploaded=call("/api/projects/"+pid+"/live/source","POST",{
                "name":"originals/test.usda","media_type":"model/vnd.usda",
                "base64_data":base64.b64encode(payload).decode("ascii")})
            if uploaded["sha256"]!=hashlib.sha256(payload).hexdigest():
                raise RuntimeError("Encrypted original source integrity failed")
            updated=call("/api/projects/"+pid+"/live/screenplay","PUT",{
                "screenplay":scene+"\n\nAn owl calls.","expected_revision":0})
            if updated["revision"]!=1:
                raise RuntimeError("Encrypted live revision not persisted")
            clear=b"".join(path.read_bytes() for path in
                (home/"nvp_g03_encrypted_live"/pid).rglob("*") if path.is_file())
            catalog=studio.db_path.read_bytes()
            if secret.encode("ascii") in clear+catalog or b"SYNTHETIC SECRET IDEA" in clear+catalog:
                raise RuntimeError("Encrypted source or idea leaked to plaintext disk")
            record={"id":pid,"screenplay_sha256":hashlib.sha256(
                updated["screenplay"].encode()).hexdigest(),
                "original_sha256":uploaded["sha256"]}
            marker.write_text(json.dumps(record),encoding="utf8")
            _smoke_checkpoint("live_created_and_disk_redaction_pass")
        elif mode=="reopen":
            record=json.loads(marker.read_text("utf8"))
            pid=record["id"]
            denied("/api/projects/"+pid+"/live",423)
            denied("/api/projects/"+pid,423)
            unlocked=call("/api/projects/"+pid+"/unlock","POST",{
                "passphrase":password})
            if not unlocked["encrypted"]:
                raise RuntimeError("Restarted encrypted movie could not unlock")
            current=call("/api/projects/"+pid+"/live")
            if hashlib.sha256(current["screenplay"].encode()).hexdigest()!=record["screenplay_sha256"]:
                raise RuntimeError("Encrypted screenplay lost on fresh installed process")
            token=next((x.value for x in jar if x.name==COOKIE),None)
            if not token or hashlib.sha256(live_films().get_original(
                    pid,token,"originals/test.usda")).hexdigest()!=record["original_sha256"]:
                raise RuntimeError("Original encrypted OpenUSD did not survive restart")
            if len(call("/api/projects/"+pid+"/live/recovery"))<2:
                raise RuntimeError("Encrypted recovery snapshots missing")
            call("/api/projects/"+pid+"/lock","POST",{})
            denied("/api/projects/"+pid+"/live",423)
            _smoke_checkpoint("live_reopen_source_recovery_relock_pass")
        else:
            raise ValueError("Invalid live encryption smoke mode")
        return 0
    finally:
        server.should_exit=True
        thread.join(timeout=12)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("Encrypted installed app did not close cleanly")


def run_g03_legacy_migration_installed_smoke():
    """Review-then-seal synthetic original film in installed Windows NVP.

    This does not switch the active original or silently claim full migration.
    Approval is a pinned synthetic CI ticket, not a human dialog receipt.
    """
    import hashlib
    from backend.nvp_studio import Studio
    from backend.nvp_film_index import FilmIndex
    from backend.nvp_g03_legacy_migration import LegacyFilmMigration
    from backend.nvp_g03_live_store import LiveFilmStore
    if sys.platform!="win32":
        raise RuntimeError("Native Windows DPAPI migration only")
    _smoke_checkpoint("g03_legacy_migration_entered")
    with tempfile.TemporaryDirectory(prefix="nvp-g03-installed-migration-") as temp:
        root=Path(temp)
        studio=Studio(root/"original-studio.sqlite3")
        original=studio.create_project("Original historical film",
            "Private idea that must survive migration",
            "EXT. ORIGINAL COAST - MORNING\n\nNo actor required.")
        pid=original["id"]
        index=FilmIndex(studio)
        audio=b"PCM_NATIVE_ORIGINAL_FROZEN_DATA"*1000
        sha=index.put_blob(pid,audio,"audio/pcm")
        approval={"used":False}
        def review(reviewed_pid,manifest):
            if reviewed_pid!=pid or approval["used"]:
                return False
            approval["used"]=True
            return True
        migrator=LegacyFilmMigration(studio,review_check=review)
        evidence=migrator.inspect(pid)
        if evidence["filmindex_blobs"][0]["sha256"]!=sha:
            raise RuntimeError("Original historical blob missing in inventory")
        sealed=migrator.stage_encrypted_candidate(
            pid,"G03-SYNTHETIC-LEGACY-MIGRATION-PASSPHRASE-2026",
            evidence["inventory_sha256"])
        if not sealed["legacy_film_untouched"] or sealed["active_project_switched"]:
            raise RuntimeError("Legacy original modified or migration prematurely activated")
        reopened=LiveFilmStore(root/"nvp_g03_migration_candidates")
        token="trusted-installed-test-"+("b"*32)
        reopened.authorize(pid,"G03-SYNTHETIC-LEGACY-MIGRATION-PASSPHRASE-2026",token)
        if reopened.get_original(pid,token,"migration/filmindex/"+sha)!=audio:
            raise RuntimeError("Independent encrypted FilmIndex PCM reopen failed")
        if reopened.read(pid,token)["screenplay"]!=original["screenplay"]:
            raise RuntimeError("Original screenplay not preserved in sealed candidate")
        if studio.get_project(pid)!=original or index.get_blob(pid,sha)!=audio:
            raise RuntimeError("Non-destructive migration changed creator originals")
        if (root/"nvp_g03_encrypted_live"/pid).exists():
            raise RuntimeError("Migration silently switched the active film")
        _smoke_checkpoint("g03_legacy_candidate_sealed_and_reopened_original_untouched")
    return 0


def run_g03_protected_capture_denial_smoke():
    """Installed real Windows host: consent denial cannot open a microphone."""
    import secrets
    from backend.nvp_g03_live_store import LiveFilmStore
    from backend.nvp_g03_protected_capture_supervisor import (
        ProtectedCaptureSupervisor,ProtectedCaptureError)
    _smoke_checkpoint("g03_protected_capture_consent_denied_entered")
    if sys.platform!="win32":
        raise RuntimeError("Windows native audio capture consent smoke required")
    with tempfile.TemporaryDirectory(prefix="nvp-g03-capture-denied-") as tmp:
        root=Path(tmp)/"secured"
        pid=secrets.token_hex(16)
        store=LiveFilmStore(root)
        password="synthetic no-capture test phrase for DPAPI"
        token="native-host-"+secrets.token_hex(24)
        store.create(pid,"Microphone privacy acceptance","","",password)
        store.authorize(pid,password,token)
        review_ticket="reviewed-no-microphone-"+secrets.token_hex(20)
        consent_calls=[]
        supervisor=ProtectedCaptureSupervisor(
            store,review_authority=lambda *scope:scope[-1]==review_ticket,
            native_os_prompt=lambda *scope:consent_calls.append(scope) or False)
        try:
            supervisor.capture(pid,token,"capture/test.pcm16le",review_ticket,
                               device_id=-1,channels=1,frames=48000)
        except ProtectedCaptureError:
            pass
        else:
            raise RuntimeError("Native mic capture bypassed operator refusal")
        if len(consent_calls)!=1 or store.read(pid,token)["source_assets"]:
            raise RuntimeError("Operator refusal created original PCM or skipped prompt")
        if store.protected_worker_runs(pid,token):
            raise RuntimeError("Refused microphone permission spawned a worker")
        _smoke_checkpoint("g03_protected_capture_denied_no_pcm_no_job")
    return 0


def run_g03_physical_capture_owner():
    """Explicit owner action only. Never run this mode in unattended CI."""
    import ctypes
    import hashlib
    import secrets
    from backend.nvp_g03_live_store import LiveFilmStore
    from backend.nvp_g03_protected_capture_supervisor import ProtectedCaptureSupervisor
    if sys.platform!="win32":
        raise RuntimeError("Physical Windows microphone approval required")
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("CI"):
        raise RuntimeError("Physical microphone recording is forbidden in CI")
    question=("NVP physical microphone acceptance. Record exactly 1 second "
              "of real default microphone PCM (48 kHz, 16-bit, mono) into "
              "a NEW synthetic encrypted test film? No actual movie will be used. "
              "Press Yes only if you are the machine owner.")
    answer=ctypes.windll.user32.MessageBoxW(
        None,question,"NVP — Approve protected microphone capture",0x4|0x20|0x1000)
    if answer!=6:
        return 2
    root=Path(tempfile.mkdtemp(prefix="nvp-g03-owner-audio-"))/"secured"
    pid=secrets.token_hex(16)
    store=LiveFilmStore(root)
    phrase="synthetic physical owner device acceptance "+secrets.token_hex(16)
    token="physical-owner-"+secrets.token_hex(24)
    store.create(pid,"Owner microphone consent test","","",phrase)
    store.authorize(pid,phrase,token)
    ticket="physical-owner-reviewed-"+secrets.token_hex(24)
    valid={ticket}
    def one_use(*scope):
        if scope[-1] not in valid:
            return False
        valid.remove(scope[-1])
        return True
    host=ProtectedCaptureSupervisor(
        store,review_authority=one_use,
        native_os_prompt=lambda *scope:ctypes.windll.user32.MessageBoxW(
            None,
            "Confirm you want to START exactly one second of live microphone "
            "recording, project-bound, then immediately encrypt the captured "
            "PCM with Windows DPAPI. Refuse = no recording.",
            "NVP — Final one-use microphone permission",0x4|0x30|0x1000)==6)
    result=host.capture(pid,token,"capture/physical-owner-test.pcm16le",
                        ticket,device_id=-1,channels=1,frames=48000,
                        synthetic_owner_only=True)
    if result["frames"]!=48000 or result["take_frozen"]:
        raise RuntimeError("Physical original capture contract failed")
    recovered=store.get_original(pid,token,"capture/physical-owner-test.pcm16le")
    if hashlib.sha256(recovered).hexdigest()!=result["pcm_sha256"]:
        raise RuntimeError("Physical native source SHA mismatch")
    _smoke_checkpoint("g03_physical_native_mic_pcm_encrypted_one_second_verified")
    store.revoke(pid)
    return 0


def run_g03_protected_native_worker_smoke():
    """Actually installed DPAPI movie and contained native USD worker.

    The acceptance ticket is SYNTHETIC and pinned to this test-only source;
    it does not simulate a human OS approval dialog.
    """
    import secrets
    from backend.nvp_g03_live_store import LiveFilmStore
    from backend.nvp_g03_protected_scene_supervisor import (
        ProtectedSceneSupervisor,SYNTHETIC_SCENE_CI_USDA)
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise RuntimeError("Installed synthetic scene smoke requires CI; private film sandbox unavailable")
    _smoke_checkpoint("g03_protected_scene_worker_entered")
    data=SYNTHETIC_SCENE_CI_USDA
    with tempfile.TemporaryDirectory(prefix="nvp-g03-protected-worker-") as tmp:
        root=Path(tmp)/"sealed"
        store=LiveFilmStore(root)
        pid=secrets.token_hex(16)
        password="G03 synthetic test-only protected native worker passphrase"
        token="host-test-approval-"+secrets.token_hex(20)
        store.create(pid,"Synthetic protected original","", "", password)
        store.authorize(pid,password,token)
        store.put_original(pid,token,"original/scene.usda",data,
                           "model/vnd.usda")
        approval_id="ci-reviewed-synthetic-ticket-"+secrets.token_hex(16)
        tickets={approval_id}
        def reviewed(review_pid,source_name,target_name,ticket):
            if (review_pid!=pid or source_name!="original/scene.usda" or
                    target_name!="review/camera-coverage.usda" or
                    ticket not in tickets):
                return False
            tickets.remove(ticket)
            return True
        result=ProtectedSceneSupervisor(
            store,review_authority=reviewed).run(
                pid,token,"original/scene.usda",
                "review/camera-coverage.usda",approval_id,
                synthetic_ci_only=True)
        if not(result["encrypted_output"] and result["native_job_tree_exited"]):
            raise RuntimeError("Protected native worker lacked custody")
        from pxr import Sdf,Usd
        source=store.get_original(pid,token,"original/scene.usda")
        derived=store.get_original(pid,token,"review/camera-coverage.usda")
        if source != data:
            raise RuntimeError("Protected original was modified")
        check=Sdf.Layer.CreateAnonymous("smoke-verified.usda")
        if not check.ImportFromString(derived.decode("utf8")):
            raise RuntimeError("Native staged USD did not reopen")
        stage=Usd.Stage.Open(check)
        if stage is None:
            raise RuntimeError("Native staged OpenUSD stage unavailable")
        for camera in ("Wide","Medium","CloseUp"):
            if not stage.GetPrimAtPath("/NVP_Coverage/"+camera):
                raise RuntimeError("Native OpenUSD camera missing from derived stage")
        records=store.protected_worker_runs(pid,token)
        if len(records)!=1 or records[0]["state"]!="SUCCEEDED":
            raise RuntimeError("Encrypted native worker acceptance receipt missing")
        store.revoke(pid)
        unlocked=LiveFilmStore(root)
        unlocked.authorize(pid,password,"fresh-authorized-"+secrets.token_hex(20))
        if unlocked.get_original(pid,list(unlocked._keys)[0],
                                 "review/camera-coverage.usda")!=derived:
            raise RuntimeError("Native protected worker output lost after reopen")
        for f in root.rglob("*"):
            if f.is_file():
                raw=f.read_bytes()
                if b'Original' in raw or b'NVP_Coverage' in raw:
                    raise RuntimeError("Native protected USD leaked to plaintext disk")
        _smoke_checkpoint("g03_protected_scene_worker_encrypted_verified")
        return 0


def run_g03_vault_smoke():
    """Independent Windows-account cryptography inside packaged NVP.exe.

    Uses ONLY synthetic data and never modifies the live movie project.
    This verifies DPAPI identity binding and AES-GCM archive authenticity;
    it does not imply active project data has been encrypted.
    """
    import tempfile
    from hashlib import sha256
    from backend.nvp_g03_windows_vault import (
        VaultError, create_archive, verify_archive, restore_archive
    )
    _smoke_checkpoint("windows_key_custody_entered")
    with tempfile.TemporaryDirectory(prefix="nvp-g03-vault-smoke-") as tmp:
        root=Path(tmp)/"plaintext-originals"
        root.mkdir()
        source_scene=root/"scene.usda"
        source_audio=root/"source.pcm"
        source_scene.write_bytes(b"#usda 1.0\n\n def Xform \"Nature\" {}")
        source_audio.write_bytes(bytes(range(256))*1000)
        original={p.name:sha256(p.read_bytes()).hexdigest()
                  for p in (source_scene,source_audio)}
        encrypted=Path(tmp)/"encrypted"
        reopened=Path(tmp)/"reopened"
        pid="a"*32
        passphrase="G03-SYNTHETIC-WINDOWS-LOCAL-PASS-2026"
        record=create_archive(pid,root,encrypted,passphrase)
        if record["status"]!="sealed_archive_verified":
            raise RuntimeError("Windows authenticated archive not sealed")
        _smoke_checkpoint("windows_key_custody_sealed")
        if verify_archive(pid,encrypted,passphrase)["source_files"]!=2:
            raise RuntimeError("Sealed film originals could not authenticate")
        try:
            verify_archive(pid,encrypted,"wrong test passphrase 2026")
        except VaultError:
            pass
        else:
            raise RuntimeError("Windows DPAPI accepted incorrect entropy")
        restore_archive(pid,encrypted,reopened,passphrase)
        if any(sha256((reopened/name).read_bytes()).hexdigest()!=digest
               for name,digest in original.items()):
            raise RuntimeError("Reopened originals do not match independent hash")
        if any(sha256((root/name).read_bytes()).hexdigest()!=digest
               for name,digest in original.items()):
            raise RuntimeError("Archive changed original working sources")
        _smoke_checkpoint("windows_key_custody_reopened_verified")
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
    parser.add_argument("--smoke-g03-window",action="store_true",
                        help="Test director-first New/Resume, actor-free scene and edit window in native WebView2")
    parser.add_argument("--smoke-vault",action="store_true",
                        help="Verify Windows-user DPAPI/AES-GCM encrypted source archive")
    parser.add_argument("--smoke-live-create",action="store_true",
                        help="Create real encrypted live film/source in packaged Windows host")
    parser.add_argument("--smoke-live-reopen",action="store_true",
                        help="Reopen encrypted live film in fresh installed host")
    parser.add_argument("--g03-protected-scene-worker",action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--g03-protected-capture-worker",action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--smoke-capture-denied",action="store_true",
                        help="Real installed native capture consent-denial smoke")
    parser.add_argument("--g03-physical-capture-owner",action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--smoke-live-worker",action="store_true",
                        help="Run synthetic real Windows Job Object protected OpenUSD staging")
    parser.add_argument("--smoke-legacy-migration",action="store_true",
                        help="Audit and non-destructively encrypt a synthetic legacy film")
    parser.add_argument("--smoke-data-av",action="store_true",
                        help="Verify native frozen USD and spatial PCM in this packaged executable")
    args=parser.parse_args(argv)
    if sum((args.smoke,args.smoke_create,args.smoke_reopen,
            args.smoke_window,args.smoke_g03_window,args.smoke_vault,
            args.smoke_live_create,args.smoke_live_reopen,
            args.g03_protected_scene_worker,args.g03_protected_capture_worker,
            args.smoke_live_worker,args.smoke_capture_denied,
            args.g03_physical_capture_owner,args.smoke_legacy_migration,
            args.smoke_data_av))>1:
        parser.error("Choose only one installed-app smoke mode")
    if args.g03_protected_scene_worker:
        from tools.nvp_g03_protected_scene_worker import worker_entry
        return worker_entry()
    if args.g03_protected_capture_worker:
        from tools.nvp_g03_protected_capture_worker import worker_entry
        return worker_entry()
    if args.smoke_capture_denied:
        return run_g03_protected_capture_denial_smoke()
    if args.g03_physical_capture_owner:
        return run_g03_physical_capture_owner()
    if args.smoke_live_worker:
        return run_g03_protected_native_worker_smoke()
    if args.smoke_legacy_migration:
        return run_g03_legacy_migration_installed_smoke()
    if args.smoke:
        return run_smoke()
    if args.smoke_window:
        return run_visible_window_smoke()
    if args.smoke_g03_window:
        return run_g03_window_smoke()
    if args.smoke_vault:
        return run_g03_vault_smoke()
    if args.smoke_live_create or args.smoke_live_reopen:
        return run_g03_live_installed_smoke(
            "create" if args.smoke_live_create else "reopen")
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
    configure_home()
    app=create_app()
    server,worker,port,sock=serve(app)
    bridge=None
    try:
        import webview
        bridge=create_trusted_camera_bridge(port)
        window=webview.create_window("NVP — Make Your Movie",
            "http://127.0.0.1:"+str(port),
            width=1280,height=800,min_size=(960,600),js_api=bridge)
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
                stream.flush()
                os.fsync(stream.fileno())
            # The windowed PyInstaller bootloader would otherwise display a
            # modal exception dialog, preventing the OS runner from observing
            # a deterministic failure. This is still a FAILED nonzero exit.
            return 1
        raise


if __name__=="__main__":
    raise SystemExit(installed_smoke_entry())
