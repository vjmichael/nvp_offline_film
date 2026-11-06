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


def trusted_source_bridge(port):
    from backend.nvp_api import studio
    from backend.nvp_index_time06_native_desktop import TrustedFootageDesktop
    return TrustedFootageDesktop(
        studio,origin="http://127.0.0.1:"+str(port))


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


def run_visible_window_smoke():
    """Exercise a real WebView2 desktop window; no headless substitute."""
    import webview
    from threading import Event
    test_home=tempfile.TemporaryDirectory(prefix="nvp-index06-webview-")
    old_home=os.environ.get("NVP_HOME")
    os.environ["NVP_HOME"]=str(Path(test_home.name)/"Projects")
    configure_home()
    app=create_app()
    from backend.nvp_api import studio
    project=studio.create_project("Indexed Footage Window Acceptance",
                                  "Real desktop source editing")
    server,worker,port,sock=serve(app)
    loaded=Event()
    result={"passed":False}
    native=None
    try:
        # Prepare a real indexed source edit without automating consent
        # through a spoofed WebView click: this CI-only disposable fixture
        # exercises the exact same native ingestion as the human OS picker.
        # The visible Windows WebView2 then tests the actual source editing
        # controls in addition to the native JS bridge itself.
        from backend.nvp_index_time06_native_desktop import discover_video_tools
        import subprocess
        tools=discover_video_tools()
        if not tools:
            raise RuntimeError("Installed WebView2 editor has no bundled video tools")
        footage=Path(test_home.name)/"window_index_source.mov"
        subprocess.run([
            str(tools[0]),"-hide_banner","-v","error","-nostdin",
            "-f","lavfi","-i","testsrc2=size=128x72:rate=24",
            "-frames:v","36","-c:v","mpeg4","-bf","2","-g","12",
            "-q:v","5","-y",str(footage),
        ],check=True,timeout=60)
        class FixtureFileDialog:
            def get_current_url(self):
                return "http://127.0.0.1:"+str(port)+"/"
            def create_file_dialog(self,**kwargs):
                return (str(footage),)
            def create_confirmation_dialog(self,title,question):
                return True
        fixture=trusted_source_bridge(port)
        fixture._attach_window(FixtureFileDialog())
        try:
            created=fixture.pick_and_import_footage(project["id"])
            if created.get("status")!="IMPORTED":
                raise RuntimeError("Installed editor fixture source could not be indexed")
        finally:
            fixture._close()
        native=trusted_source_bridge(port)
        window=webview.create_window("NVP Alpha Window Acceptance",
            "http://127.0.0.1:"+str(port),width=1000,height=700,
            js_api=native)
        native._attach_window(window)
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
                        # Actual JS->Python IPC, not merely a registered name.
                        window.evaluate_js(
                            "window.__nvpIndexProbe='PENDING';"
                            "window.pywebview.api.video_import_capabilities()"
                            ".then(x=>{window.__nvpIndexProbe="
                            "x.format==='nvp.index_time06.native_capability.v1'"
                            "&&x.native_window===true"
                            "&&x.video_tools_available===true?'PASSED':'FAILED';})"
                            ".catch(()=>{window.__nvpIndexProbe='FAILED';});")
                        until=time.monotonic()+10
                        while time.monotonic()<until:
                            probe=window.evaluate_js("window.__nvpIndexProbe")
                            if probe=="PASSED":
                                result["passed"]=True
                                break
                            if probe=="FAILED":
                                raise RuntimeError("Actual native footage JS IPC failed")
                            time.sleep(.2)
                        if result["passed"]:
                            result["passed"]=False
                            end=time.monotonic()+20
                            opened=False
                            while time.monotonic()<end:
                                opened=window.evaluate_js(
                                    "(()=>{const b=[...document.querySelectorAll('aside button')]"
                                    ".find(x=>x.textContent.includes('Indexed Footage Window Acceptance'));"
                                    "if(b){b.click();return true;}return false;})()")
                                if opened:break
                                time.sleep(.2)
                            if not opened:
                                raise RuntimeError("Real installed film project did not appear in sidebar")
                            end=time.monotonic()+20
                            tabbed=False
                            while time.monotonic()<end:
                                tabbed=window.evaluate_js(
                                    "(()=>{const b=[...document.querySelectorAll('nav.tabs button')]"
                                    ".find(x=>x.textContent.includes('Indexed footage'));"
                                    "if(b){b.click();return true;}return false;})()")
                                if tabbed:break
                                time.sleep(.2)
                            if not tabbed:
                                raise RuntimeError("Installed indexed footage tab never appeared")
                            end=time.monotonic()+20
                            while time.monotonic()<end:
                                ready=window.evaluate_js(
                                    "Boolean([...document.querySelectorAll('button')]"
                                    ".some(x=>x.textContent.includes('Import original footage')))")
                                if ready:
                                    result["passed"]=True
                                    break
                                time.sleep(.2)
                            if not result["passed"]:
                                raise RuntimeError("Native footage picker was not wired to real React UI")
                            # An imported original must expose the human
                            # non-destructive controls within the installed
                            # React DOM, not just backend unit tests.
                            result["passed"]=False
                            end=time.monotonic()+25
                            while time.monotonic()<end:
                                editing=window.evaluate_js(
                                    "Boolean([...document.querySelectorAll('section')]"
                                    ".some(x=>x.getAttribute('aria-label')==='Original footage assembly editor')"
                                    "&&[...document.querySelectorAll('button')]"
                                    ".some(x=>x.textContent.includes('Split clip at source frame')))")
                                if editing:
                                    result["passed"]=True
                                    break
                                time.sleep(.25)
                            if not result["passed"]:
                                raise RuntimeError("Real installed indexed source assembly UI never opened")
                            result["passed"]=False
                            if not window.evaluate_js(
                                "Boolean([...document.querySelectorAll('button')]"
                                ".some(x=>x.textContent.includes('Review & play original footage'))"
                                "&&[...document.querySelectorAll('section')]"
                                ".some(x=>x.getAttribute('aria-label')==='Non-destructive footage playback'))"):
                                raise RuntimeError("Native source player was not mounted in installed React")
                            result["passed"]=True
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
            if native is not None:native._close()
        finally:
            try:
                server.should_exit=True
                worker.join(timeout=12)
                sock.close()
            finally:
                if old_home is None:
                    os.environ.pop("NVP_HOME",None)
                else:
                    os.environ["NVP_HOME"]=old_home
                test_home.cleanup()


def run_installed_source_smoke():
    """Real bundled EXE -> native FilmIndex import -> OS-contained child.

    Uses a deterministic fake FILE DIALOG only because CI cannot select a
    Windows OS file interactively. The separate actual WebView2 window smoke
    exercises the installed JS->Python IPC path. No user source is touched.
    """
    from backend.nvp_studio import Studio
    from backend.nvp_film_index import FilmIndex
    from backend.nvp_index_time06_native_desktop import (
        TrustedFootageDesktop,discover_video_tools,PNG_MAGIC)
    import hashlib
    import subprocess
    tools=discover_video_tools()
    if tools is None:
        raise RuntimeError("Installed source acceptance requires bundled FFmpeg/FFprobe")
    with tempfile.TemporaryDirectory(prefix="nvp-index06-installed-") as temp:
        root=Path(temp)
        movie=root/"source.mov"
        args=[str(tools[0]),"-hide_banner","-loglevel","error","-nostdin",
              "-f","lavfi","-i","testsrc2=size=160x90:rate=24",
              "-frames:v","60","-vf","setpts=(N+floor(N/10))/(24*TB)+3/TB",
              "-fps_mode","vfr","-c:v","mpeg4","-bf","2","-g","12",
              "-q:v","5","-y",str(movie)]
        subprocess.run(args,check=True,timeout=60)
        expected_sha=hashlib.sha256(movie.read_bytes()).hexdigest()
        studio=Studio(root/"nvp_studio.sqlite3")
        pid=studio.create_project("Installed source film","Native film clock")["id"]
        class NativeTestWindow:
            prompts=0
            def get_current_url(self):
                return "http://127.0.0.1:7777/"
            def create_file_dialog(self,**kwargs):
                assert kwargs.get("allow_multiple") is False
                return (str(movie),)
            def create_confirmation_dialog(self,title,message):
                self.prompts+=1
                assert "NVP" in title
                return True
        window=NativeTestWindow()
        native=TrustedFootageDesktop(
            studio,origin="http://127.0.0.1:7777",tools=tools)
        native._attach_window(window)
        try:
            imported=native.pick_and_import_footage(pid)
            if imported.get("status")!="IMPORTED":
                raise RuntimeError("Installed original source was not indexed")
            found=native.reader.seek(
                pid,imported["edit_id"],imported["edit_revision"],
                expected_edit_sha256=imported["edit_document_sha256"],
                tick=0)
            if found["status"]!="INDEXED_SOURCE_FRAME_SELECTED":
                raise RuntimeError("Installed original PTS cannot be sought")
            requested=native.request_source_frame_preview({
                "project_id":pid,"edit_id":imported["edit_id"],
                "edit_revision":imported["edit_revision"],
                "edit_document_sha256":imported["edit_document_sha256"],
                "source_tick":"0",
                "source_frame_zero":found["source_frame_zero"],
                "source_pts":found["source_pts"],
            })
            if requested.get("status")!="QUEUED":
                raise RuntimeError("Installed native preview did not receive exact consent")
            until=time.monotonic()+180
            result=None
            while time.monotonic()<until:
                result=native.poll_source_frame_preview(requested["ticket_id"])
                if result["status"]=="READY":break
                if result["status"]!="QUEUED":
                    raise RuntimeError("Native installed worker failed closed: "+
                                       result["status"])
                time.sleep(.25)
            if result is None or result["status"]!="READY":
                raise RuntimeError("Native source review did not produce verified PNG")
            if not result["image_data_url"].startswith("data:image/png;base64,"):
                raise RuntimeError("Missing audited original review picture")
            if (result["film_master_approved"] is not False or
                hashlib.sha256(movie.read_bytes()).hexdigest()!=expected_sha or
                studio.get_project(pid)["title"]!="Installed source film" or
                window.prompts!=2 or
                FilmIndex(studio).read_revision(pid,imported["source_id"],1)[
                    "document_sha256"]!=imported["source_document_sha256"]):
                raise RuntimeError("Installed native review violated source custody")
            # INDEX-TIME-07 acceptance in the SAME installed GUI EXE:
            # propose exact original-range trim, show the native consent,
            # publish revision 2 and prove revision 1/source SHA survive.
            change={
                "operation":"trim","index":0,
                "source_in_frame_zero":"0",
                "source_out_frame_zero":
                    str(int(imported["placed_frames"])-1),
            }
            request={
                "project_id":pid,"edit_id":imported["edit_id"],
                "edit_revision":imported["edit_revision"],
                "edit_document_sha256":imported["edit_document_sha256"],
                "change":change,
            }
            plan=native.preview_footage_assembly(request)
            if (plan.get("format")!="nvp.index_time07.assembly_plan.v1"
                or not plan.get("plan_sha256") or
                plan["source_document_sha256"]!=imported["edit_document_sha256"]):
                raise RuntimeError("Installed original footage assembly preview failed")
            updated=native.save_footage_assembly({
                **request,"plan_sha256":plan["plan_sha256"],
            })
            if (updated.get("status")!="SAVED_NEW_EDIT_REVISION" or
                updated["revision"]!=2 or
                updated["original_sources_modified"] is not False or
                window.prompts!=3):
                raise RuntimeError("Native edit approval or immutable revision failed")
            original=FilmIndex(studio).read_revision(
                pid,imported["edit_id"],1)
            successor=FilmIndex(studio).read_revision(
                pid,imported["edit_id"],2)
            if (original["document_sha256"]!=imported["edit_document_sha256"] or
                successor["document_sha256"]!=updated["edit_document_sha256"] or
                hashlib.sha256(movie.read_bytes()).hexdigest()!=expected_sha):
                raise RuntimeError("Installed assembly changed the original or earlier edit")
            # INDEX-TIME-08: the *installed* packaged EXE must also
            # decode multiple original frames as a bounded, creator-
            # approved source assembly review rather than a single still.
            preview=native.start_assembly_review({
                "project_id":pid,"edit_id":imported["edit_id"],
                "edit_revision":updated["revision"],
                "edit_document_sha256":updated["edit_document_sha256"],
                "start_tick":"0",
            })
            if preview.get("status")!="QUEUED":
                raise RuntimeError("Installed original assembly playback was not authorized")
            deadline=time.monotonic()+200
            playback=None
            while time.monotonic()<deadline:
                playback=native.poll_assembly_review(preview["ticket_id"])
                if playback["status"]=="COMPLETE":break
                if playback["status"]=="RECOVERY_REQUIRED":
                    raise RuntimeError("Installed original assembly playback worker failed")
                time.sleep(.3)
            if (playback is None or playback["status"]!="COMPLETE" or
                playback["ready_frames"]<2 or
                window.prompts!=4):
                raise RuntimeError("Packaged multi-frame video review did not complete")
            original_frame=native.get_assembly_review_frame(
                preview["ticket_id"],0)
            second_frame=native.get_assembly_review_frame(
                preview["ticket_id"],1)
            if (original_frame["status"]!="VERIFIED_FRAME" or
                second_frame["status"]!="VERIFIED_FRAME" or
                original_frame["source_pts"]==second_frame["source_pts"] or
                original_frame["master_approved"] is not False or
                hashlib.sha256(movie.read_bytes()).hexdigest()!=expected_sha):
                raise RuntimeError("Installed source PTS, PNG or original custody failed")
            if sys.stdout is not None:
                print("INDEX_TIME08_INSTALLED_ASSEMBLY_REVIEW_PASS",
                      updated["edit_document_sha256"],
                      original_frame["png_sha256"])
            return 0
        finally:
            native._close()


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0]=="--trusted-film-time-worker":
        # This path runs in a separate OS-contained EXE child. It has no
        # desktop window, file dialog, listener or arbitrary input launcher.
        # A bound parent supervisor must supply the pinned script SHA. The
        # verified source worker itself verifies all pinned media/tool/plan
        # hashes and exact editor revision again after process launch.
        if not getattr(sys,"frozen",False) or len(argv)<3:
            raise PermissionError("Trusted film-time worker requires installed NVP")
        import hashlib
        import runpy
        script=bundle_root()/"tools"/"nvp_source_window_worker.py"
        if script.is_symlink() or not script.is_file():
            raise RuntimeError("Packaged source review worker missing")
        expected=argv[1]
        if (len(expected)!=64 or
            any(c not in "0123456789abcdef" for c in expected) or
            hashlib.sha256(script.read_bytes()).hexdigest()!=expected):
            raise PermissionError("Native worker script changed since approval")
        sys.argv=[str(script),*argv[2:]]
        # Windowed PyInstaller builds can have no Python stdout/stderr.
        # Avoid failing an otherwise successful contained frame decode
        # when its worker writes a JSON diagnostic after fsync.
        if sys.stdout is None:sys.stdout=open(os.devnull,"w",encoding="utf8")
        if sys.stderr is None:sys.stderr=open(os.devnull,"w",encoding="utf8")
        runpy.run_path(str(script),run_name="__main__")
        return 0
    parser=argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true",
                        help="Temporary bundled UI/backend/SQLite acceptance")
    parser.add_argument("--smoke-create",action="store_true",
                        help="Create persistent project for cross-process installed acceptance")
    parser.add_argument("--smoke-reopen",action="store_true",
                        help="Reopen same project after fully exiting previous installed app")
    parser.add_argument("--smoke-window",action="store_true",
                        help="Launch a real native Windows WebView2 and verify page loaded")
    parser.add_argument("--smoke-source",action="store_true",
                        help="Exercise installed FFmpeg, original FilmIndex and native preview worker")
    args=parser.parse_args(argv)
    if sum((args.smoke,args.smoke_create,args.smoke_reopen,
            args.smoke_window,args.smoke_source))>1:
        parser.error("Choose only one installed-app smoke mode")
    if args.smoke_source:
        return run_installed_source_smoke()
    if args.smoke:
        return run_smoke()
    if args.smoke_window:
        return run_visible_window_smoke()
    if args.smoke_create or args.smoke_reopen:
        return run_persistent_installed_smoke(
            "create" if args.smoke_create else "reopen")
    configure_home()
    app=create_app()
    server,worker,port,sock=serve(app)
    native=None
    try:
        import webview
        native=trusted_source_bridge(port)
        window=webview.create_window("NVP — Make Your Movie",
            "http://127.0.0.1:"+str(port),
            width=1280,height=800,min_size=(960,600),js_api=native)
        native._attach_window(window)
        webview.start(gui="edgechromium",debug=False)
        return 0
    finally:
        try:
            if native is not None:native._close()
        finally:
            server.should_exit=True
            worker.join(timeout=12)
            sock.close()


if __name__=="__main__":
    raise SystemExit(main())
