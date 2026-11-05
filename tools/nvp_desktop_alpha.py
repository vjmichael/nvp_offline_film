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


def run_visible_window_smoke():
    """Exercise a real WebView2 desktop window; no headless substitute."""
    import webview
    from threading import Event
    configure_home()
    app=create_app()
    server,worker,port,sock=serve(app)
    loaded=Event()
    result={"passed":False}
    try:
        window=webview.create_window("NVP Alpha Window Acceptance",
            "http://127.0.0.1:"+str(port),width=1000,height=700)
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
        server.should_exit=True
        worker.join(timeout=12)
        sock.close()


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
    args=parser.parse_args(argv)
    if sum((args.smoke,args.smoke_create,args.smoke_reopen,args.smoke_window))>1:
        parser.error("Choose only one installed-app smoke mode")
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
    try:
        import webview
        webview.create_window("NVP — Make Your Movie",
            "http://127.0.0.1:"+str(port),
            width=1280,height=800,min_size=(960,600))
        webview.start(gui="edgechromium",debug=False)
        return 0
    finally:
        server.should_exit=True
        worker.join(timeout=12)
        sock.close()


if __name__=="__main__":
    raise SystemExit(main())
