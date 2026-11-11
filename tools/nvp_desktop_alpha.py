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
    config=uvicorn.Config(app,host="127.0.0.1",port=port,
                          access_log=False,log_level="warning",
                          proxy_headers=False)
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
        with (client or urllib.request).open(request,timeout=12) as reply:
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
            "One native source camera scene")
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
    result={"passed":False}
    bridge=None
    try:
        bridge=create_trusted_camera_bridge(port)
        window=webview.create_window("NVP Alpha Window Acceptance",
            "http://127.0.0.1:"+str(port),width=1000,height=700,
            js_api=bridge)
        bridge._attach_window(window)
        window.events.loaded += lambda:loaded.set()
        def inspect_and_close():
            try:
                if not loaded.wait(timeout=25):
                    raise RuntimeError("Native WebView2 did not fire page-loaded event")
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
            finally:
                window.destroy()
        webview.start(func=inspect_and_close,gui="edgechromium",debug=False)
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
    parser.add_argument("--smoke-data-av",action="store_true",
                        help="Verify native frozen USD and spatial PCM in this packaged executable")
    args=parser.parse_args(argv)
    if sum((args.smoke,args.smoke_create,args.smoke_reopen,
            args.smoke_window,args.smoke_g03_window,args.smoke_data_av))>1:
        parser.error("Choose only one installed-app smoke mode")
    if args.smoke:
        return run_smoke()
    if args.smoke_window:
        return run_visible_window_smoke()
    if args.smoke_g03_window:
        return run_g03_window_smoke()
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
        raise


if __name__=="__main__":
    raise SystemExit(installed_smoke_entry())
