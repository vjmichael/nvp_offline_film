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
    from backend.nvp_wo6_desktop_bridge import TrustedDesktopWO6Bridge
    from backend.nvp_wo5_codec_binding import desktop_finished_decoder_provider
    # Original DataFirst A/V remains active; finished DCP decoding requires
    # separately SHA-pinned native OpenJPEG/CineCert binaries installed by
    # the trusted host. Ordinary browser/AI callers cannot supply paths.
    return TrustedDesktopWO6Bridge(
        FilmIndex(studio),origin="http://127.0.0.1:"+str(port),
        finished_codec_provider=desktop_finished_decoder_provider(bundle_root()))


def _native_window_stage(message):
    """Persist installed-source UI progress before timeouts or hard exit."""
    destination=os.environ.get("NVP_NATIVE_SMOKE_DIAGNOSTICS")
    if not destination or type(message) is not str or len(message)>96:
        return
    path=Path(destination)
    if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
        return
    with path.open("a",encoding="utf8") as stream:
        stream.write("NVP_INSTALLED_WINDOW_STAGE="+message+"\\n")
        stream.flush()
        os.fsync(stream.fileno())


def run_visible_window_smoke():
    """Installed real WebView2 + native OpenUSD source panel smoke.

    Use a throwaway film workspace: tests must never publish a demo source
    or mutate the creator's durable Projects directory.
    """
    import webview
    from threading import Event
    _native_window_stage("source_smoke_enter")
    test_home=Path(tempfile.mkdtemp(prefix="nvp-slate08b-installed-"))
    old_home=os.environ.get("NVP_HOME")
    os.environ["NVP_HOME"]=str(test_home)
    try:
        _native_window_stage("create_source_app")
        app=create_app()
        from backend.nvp_api import studio
        from backend.nvp_film_index import FilmIndex
        from backend.nvp_openusd_scene import OpenUSDSceneBridge
        project=studio.create_project("SLATE-08B Window Acceptance",
            "One native source camera scene")
        from io import BytesIO
        from PIL import Image
        from backend.nvp_openusd_assets import OpenUSDAssetRegistry
        smoke_index=FilmIndex(studio)
        tile=Image.new("RGB",(2,2))
        tile.putdata([(0,255,0),(255,255,255),
                      (255,0,0),(0,0,255)])
        image_buffer=BytesIO()
        tile.save(image_buffer,format="PNG")
        def encode_source_map(rgb):
            item=BytesIO()
            Image.new("RGB",(2,2),rgb).save(item,format="PNG")
            return item.getvalue()
        source_material_maps={
            "roughness":encode_source_map((80,80,80)),
            "metallic":encode_source_map((200,200,200)),
            "emission":encode_source_map((12,50,80)),
            "normal":encode_source_map((128,128,255)),
            "opacity":encode_source_map((255,255,255)),
        }
        OpenUSDAssetRegistry(smoke_index).publish(
            project["id"],"smoke_gpu_original_mesh",
            shape="mesh",size_m=2.,
            points=[[-1.,-1.,0.],[1.,-1.,0.],[1.,1.,0.],[-1.,1.,0.]],
            triangles=[[0,1,2],[0,2,3]],
            mesh_uvs=[[0,0],[1,0],[1,1],[0,1]],
            preview_material={"base_color_rgb":[1.,1.,1.],
                              "roughness":.5,"metallic":0.},
            texture_png=image_buffer.getvalue(),
            pbr_maps_png=source_material_maps)
        OpenUSDSceneBridge(smoke_index).publish(
            project["id"],"smoke_scene",
            prims=[
                {"path":"/World/Actor","role":"actor",
                 "position":[0,0,0]},
                {"path":"/World/Camera","role":"camera",
                 "position":[0,0,8]},
            ],curves=[],native_schemas=True,
            asset_bindings=[{
                "path":"/World/Actor",
                "asset_id":"smoke_gpu_original_mesh","asset_revision":1}])
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
        _native_window_stage("original_source_take_frozen")
        server,worker,port,sock=serve(app)
        _native_window_stage("original_source_service_ready")
    except BaseException:
        if old_home is None: os.environ.pop("NVP_HOME",None)
        else: os.environ["NVP_HOME"]=old_home
        shutil.rmtree(test_home,ignore_errors=True)
        raise
    loaded=Event()
    result={"passed":False}
    bridge=None
    try:
        from backend.nvp_wo6_desktop_bridge import (
            TrustedDesktopWO6Bridge)
        from backend.nvp_native_usd_texture import texture_transport
        class InstalledWO2ProbeBridge(TrustedDesktopWO6Bridge):
            """Test-only native IPC: uses one exact ephemeral smoke asset."""
            def wo2_gpu_texture_probe(self):
                self._native_window()
                record,_=OpenUSDAssetRegistry(self.index).open(
                    project["id"],"smoke_gpu_original_mesh",1)
                desc=record["data"]["preview_material"]["texture"]
                return {
                    "format":"nvp.wo2.installed_texture_probe.v1",
                    "status":"READY","source_modified":False,
                    "texture":texture_transport(
                        self.index,project["id"],desc),
                }
        bridge=InstalledWO2ProbeBridge(
            FilmIndex(studio),origin="http://127.0.0.1:"+str(port))
        window=webview.create_window("NVP Alpha Window Acceptance",
            "http://127.0.0.1:"+str(port),width=1000,height=700,
            js_api=bridge)
        bridge._attach_window(window)
        _native_window_stage("native_source_webview_window_created")
        window.events.loaded += lambda:loaded.set()
        def inspect_and_close():
            try:
                _native_window_stage("source_webview_inspection_started")
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
                                result["passed"]=False
                                gpu_button=window.evaluate_js(
                                    "(()=>{const b=[...document.querySelectorAll('button')]"
                                    ".find(x=>x.textContent.includes("
                                    "'Run installed original PNG GPU comparison'));"
                                    "if(b){b.click();return true;}return false;})()")
                                if gpu_button is not True:
                                    raise RuntimeError(
                                        "Installed source-GPU acceptance button missing")
                                until=time.monotonic()+25
                                while time.monotonic()<until:
                                    evidence=window.evaluate_js(
                                        "(()=>{const txt=document.body.textContent;"
                                        "if(txt.includes('WO2 installed source GPU texel comparison PASSED'))"
                                        "return 'PASSED';"
                                        "if(txt.includes('WO2 installed source GPU texel comparison FAILED'))"
                                        "return 'FAILED';return 'PENDING';})()")
                                    if evidence=="PASSED":
                                        result["passed"]=True
                                        break
                                    if evidence=="FAILED":
                                        raise RuntimeError(
                                            "Installed WebView2 source PNG CPU/GPU texel comparison failed")
                                    time.sleep(.2)
                                if not result["passed"]:
                                    raise RuntimeError(
                                        "Installed source PNG GPU readback timed out")
                                # WO5 actual installed desktop: reuse the
                                # same trusted window, project and real FilmIndex
                                # to open the native director-review workspace.
                                # No synthetic finished film/creator approval.
                                result["passed"]=False
                                clicked=window.evaluate_js(
                                    "(()=>{const b=[...document.querySelectorAll('nav.tabs button')]"
                                    ".find(x=>x.textContent.includes('Watch & review film'));"
                                    "if(b){b.click();return true;}return false;})()")
                                if clicked is not True:
                                    raise RuntimeError(
                                        "Installed WO5 film review tab unavailable")
                                until=time.monotonic()+20
                                while time.monotonic()<until:
                                    present=window.evaluate_js(
                                        "Boolean(document.querySelector("
                                        "'[aria-label=\\\"Director film review\\\"]')"
                                        " && document.body.textContent.includes("
                                        "'Direct, preview and review the film'))")
                                    if present:
                                        break
                                    time.sleep(.2)
                                if not present:
                                    raise RuntimeError(
                                        "Installed WO5 director review component not mounted")
                                window.evaluate_js(
                                    "window.__nvpWO5Probe='PENDING';"
                                    "window.pywebview.api.wo5_review_catalog('"+
                                    project["id"]+"').then(x=>{"
                                    "window.__nvpWO5Probe="
                                    "x.format==='nvp.wo5.trusted_desktop_director_review.v1' && "
                                    "x.status==='NATIVE_PROJECT_SCOPED_READ_ONLY' && "
                                    "x.project_id==='"+project["id"]+"' && "
                                    "x.host_native_only===true && "
                                    "x.full_finished_dcp_playback_verified===false "
                                    "?'PASSED':'FAILED';}).catch(()=>{"
                                    "window.__nvpWO5Probe='FAILED';});")
                                until=time.monotonic()+15
                                while time.monotonic()<until:
                                    result_state=window.evaluate_js(
                                        "window.__nvpWO5Probe")
                                    if result_state=="PASSED":
                                        result["passed"]=True
                                        break
                                    if result_state=="FAILED":
                                        raise RuntimeError(
                                            "Installed WO5 JS-to-native FilmIndex catalog denied")
                                    time.sleep(.2)
                                if not result["passed"]:
                                    raise RuntimeError(
                                        "Installed WO5 review IPC timed out")
                                if os.environ.get("NVP_WO5_EXPECT_CODEC_INSTALL")=="1":
                                    # REAL installed WebView2 -> native Python
                                    # capability boundary, not a browser fake.
                                    # Final feature playback still needs the
                                    # indexed FilmIndex movie and OS consent.
                                    window.evaluate_js(
                                        "window.__nvpWO5Codec='PENDING';"
                                        "window.pywebview.api.wo5_film_capabilities().then(x=>{"
                                        "window.__nvpWO5Codec="
                                        "x.format==='nvp.wo5.finished_dcp_pcm24_picture_review.v1'&&"
                                        "x.native_finished_mxf_decode_configured===true&&"
                                        "x.FFmpeg_used===false&&"
                                        "x.production_accepted===false"
                                        "?'PASSED':'FAILED';}).catch(()=>{"
                                        "window.__nvpWO5Codec='FAILED';});")
                                    until=time.monotonic()+15
                                    while time.monotonic()<until:
                                        seen=window.evaluate_js("window.__nvpWO5Codec")
                                        if seen=="PASSED":
                                            break
                                        if seen=="FAILED":
                                            raise RuntimeError(
                                                "Installed WebView2 cannot reach native cinema decoder")
                                        time.sleep(.2)
                                    if seen!="PASSED":
                                        raise RuntimeError(
                                            "Installed native codec capability IPC timed out")
                                # WO6-07: the actual installed React
                                # director-native tab and loopback OS host
                                # must present source-bound preview with NO
                                # automatic creative or native worker grant.
                                result["passed"]=False
                                selected=window.evaluate_js(
                                    "(()=>{const b=[...document.querySelectorAll('nav.tabs button')]"
                                    ".find(x=>x.textContent.includes('Native director approvals'));"
                                    "if(b){b.click();return true;}return false;})()")
                                if selected is not True:
                                    raise RuntimeError(
                                        "Installed WO6 director-native tab missing")
                                until=time.monotonic()+20
                                while time.monotonic()<until:
                                    found=window.evaluate_js(
                                        "Boolean(document.querySelector("
                                        "'section[aria-label=\\\"Director native source operations\\\"]'))")
                                    if found:
                                        break
                                    time.sleep(.2)
                                if not found:
                                    raise RuntimeError(
                                        "Installed WO6 native creator panel never mounted")
                                _native_window_stage("wo6_real_creator_panel_mounted")
                                window.evaluate_js(
                                    "window.__nvpWO6Catalog='PENDING';"
                                    "window.pywebview.api.wo6_source_catalog('"+
                                    project["id"]+"').then(x=>{"
                                    "window.__nvpWO6Catalog="
                                    "x.format==='nvp.wo6.director_desktop_native_consent.v1'&&"
                                    "x.model_execute_enabled===false&&"
                                    "x.approvals_preissued===false&&"
                                    "x.scenes.some(s=>s.id==='smoke_scene')&&"
                                    "x.takes.some(t=>t.id==='smoke_frozen_take')"
                                    "?'PASSED':'FAILED';}).catch(()=>{"
                                    "window.__nvpWO6Catalog='FAILED';});")
                                until=time.monotonic()+15
                                while time.monotonic()<until:
                                    proof=window.evaluate_js("window.__nvpWO6Catalog")
                                    if proof=="PASSED":break
                                    if proof=="FAILED":
                                        raise RuntimeError(
                                            "Installed WO6 native FilmIndex catalog IPC denied")
                                    time.sleep(.2)
                                if proof!="PASSED":
                                    raise RuntimeError(
                                        "Installed WO6 native creator catalog timed out")
                                _native_window_stage("wo6_real_film_index_read_only_catalog_passed")
                                result["passed"]=True
                                break
                    time.sleep(.2)
                if not result["passed"]:
                    raise RuntimeError("Bundled NVP React interface did not render")
            except Exception as exc:
                result["failure"]=str(exc)
                _native_window_stage("source_webview_inspection_failed")
            finally:
                _native_window_stage("source_webview_destroy_request")
                window.destroy()
        _native_window_stage("source_webview_message_loop_start")
        webview.start(func=inspect_and_close,gui="edgechromium",debug=False)
        _native_window_stage("source_webview_message_loop_returned")
        if not result["passed"]:
            raise RuntimeError(
                "Real NVP WebView2 React UI failed: "+result.get("failure","unknown error"))
        # Emit independently sampled native Windows display-adapter evidence
        # AFTER real installed WebView2 texture readback. Enumeration itself
        # is not proof of dedicated hardware acceleration or calibration.
        from backend.nvp_wo2_hardware_evidence import collect_windows_gpu_evidence
        import json
        result["native_windows_gpu_evidence"]=collect_windows_gpu_evidence()
        _native_window_stage("source_webview_full_acceptance_finished")
        print("NVP_WO2_HARDWARE_EVIDENCE="+json.dumps(
            result["native_windows_gpu_evidence"],sort_keys=True),flush=True)
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


def _run_private_wo6_worker(argv):
    """Packaged native NVP.exe worker mode, no UI/loopback server/model dispatch.

    A frozen PyInstaller executable is not a Python interpreter; passing a
    .py path to it would instead launch the main desktop process and strand
    the approved task. The real internal workers perform their own durable
    ACTIVE/reserved/owner/spec-SHA checks before any FilmIndex writes.
    """
    if type(argv) is not list or len(argv)<3 or argv[0]!="--nvp-wo6-worker":
        raise ValueError("Malformed private native worker invocation")
    entrypoint=argv[1]
    if entrypoint=="take":
        from tools.nvp_wo6_take_worker import main as run_worker
    elif entrypoint=="shot":
        from tools.nvp_wo6_shot_worker import main as run_worker
    elif entrypoint=="data":
        from tools.nvp_wo6_data_worker import main as run_worker
    else:
        raise PermissionError("No arbitrary worker dispatch in installed NVP")
    return run_worker(argv[2:])


def main(argv=None):
    raw_args=sys.argv[1:] if argv is None else list(argv)
    if raw_args and raw_args[0]=="--nvp-wo6-worker":
        return _run_private_wo6_worker(raw_args)
    parser=argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true",
                        help="Temporary bundled UI/backend/SQLite acceptance")
    parser.add_argument("--smoke-create",action="store_true",
                        help="Create persistent project for cross-process installed acceptance")
    parser.add_argument("--smoke-reopen",action="store_true",
                        help="Reopen same project after fully exiting previous installed app")
    parser.add_argument("--smoke-window",action="store_true",
                        help="Launch a real native Windows WebView2 and verify page loaded")
    parser.add_argument("--smoke-data-av",action="store_true",
                        help="Verify native frozen USD and spatial PCM in this packaged executable")
    parser.add_argument("--smoke-finished-playback",action="store_true",
                        help="Probe real installed licensed native picture MXF/J2K and mastered PCM")
    parser.add_argument("--smoke-visible-finished-av",action="store_true",
                        help="Verify all actual published DCP frames and sound play in visible installed WebView2")
    parser.add_argument("--smoke-wo6-native-actions",action="store_true",
                        help="Installed first-party WO6 native child/FilmIndex source-only acceptance")
    parser.add_argument("--smoke-wo6-real-gguf",action="store_true",
                        help="Explicit disposable real GGUF, original OpenUSD Take and model response acceptance")
    parser.add_argument("--gguf-path",default=None)
    parser.add_argument("--llama-server-path",default=None)
    parser.add_argument("--gguf-report",default=None)
    parser.add_argument("--gguf-test-consent",default=None)
    args=parser.parse_args(argv)
    if sum((args.smoke,args.smoke_create,args.smoke_reopen,
            args.smoke_window,args.smoke_data_av,
            args.smoke_finished_playback,args.smoke_visible_finished_av,
            args.smoke_wo6_native_actions,args.smoke_wo6_real_gguf))>1:
        parser.error("Choose only one installed-app smoke mode")
    if args.smoke:
        return run_smoke()
    if args.smoke_window:
        return run_visible_window_smoke()
    if args.smoke_data_av:
        from tools.nvp_data_av_installed_acceptance import run_installed_data_av_smoke
        return run_installed_data_av_smoke()
    if args.smoke_finished_playback:
        from tools.nvp_wo5_installed_sustain import smoke_from_installed_bundle
        return smoke_from_installed_bundle(bundle_root())
    if args.smoke_visible_finished_av:
        from tools.nvp_wo5_installed_visible import run_installed_visible_finished_smoke
        return run_installed_visible_finished_smoke(bundle_root())
    if args.smoke_wo6_native_actions:
        from tools.nvp_wo6_installed_action_smoke import run_wo6_installed_native_smoke
        evidence=run_wo6_installed_native_smoke()
        if evidence.get("status")!="INSTALLED_NATIVE_WORKER_SOURCES_VERIFIED_NO_FILM":
            raise RuntimeError("Installed WO6 native source operations were not verified")
        return 0
    if args.smoke_wo6_real_gguf:
        if (not args.gguf_path or not args.llama_server_path or
                args.gguf_test_consent!="I_APPROVE_DISPOSABLE_LOCAL_GGUF_TEST"):
            raise PermissionError(
                "Explicit GGUF, llama-server and disposable model-test consent required")
        from tools.nvp_wo6_07b_real_gguf_smoke import run_real_gguf_acceptance
        measured=run_real_gguf_acceptance(
            model_path=args.gguf_path,server_path=args.llama_server_path,
            report_path=args.gguf_report,consent=args.gguf_test_consent)
        if (measured["status"]!="LOCAL_GGUF_COMPLETION_OBSERVED" or
                measured["human_director_reviewed"] is not False):
            raise RuntimeError("Native model test did not complete")
        return 0
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


if __name__=="__main__":
    # A windowed PyInstaller binary has no user-visible stderr. For
    # native smoke acceptance only, preserve a small opt-in execution
    # receipt before running the code. A missing START means bootloader/
    # native DLL initialization failed before Python; an error later
    # records the real Python traceback. Never take this path from JS.
    diagnostic=None
    smoke=any(flag in sys.argv for flag in (
        "--smoke","--smoke-create","--smoke-reopen",
        "--smoke-window","--smoke-data-av","--smoke-finished-playback",
        "--smoke-visible-finished-av","--smoke-wo6-real-gguf"))
    if smoke:
        report=os.environ.get("NVP_NATIVE_SMOKE_DIAGNOSTICS")
        if report:
            target=Path(report)
            if target.parent.is_dir() and not target.is_symlink() and (
                    not target.exists()):
                diagnostic=target
    def record_smoke_result(message,*,failure=False):
        if diagnostic is None:return
        import traceback
        mode="a" if diagnostic.exists() else "x"
        with diagnostic.open(mode,encoding="utf8") as sink:
            sink.write(message+"\n")
            if failure:
                traceback.print_exc(file=sink)
            sink.flush();os.fsync(sink.fileno())
    record_smoke_result("NVP_SMOKE_PYTHON_ENTRY")
    try:
        result=main()
    except BaseException:
        record_smoke_result("NVP_SMOKE_PYTHON_EXCEPTION",failure=True)
        raise
    else:
        record_smoke_result("NVP_SMOKE_PYTHON_EXIT="+str(result))
        raise SystemExit(result)
