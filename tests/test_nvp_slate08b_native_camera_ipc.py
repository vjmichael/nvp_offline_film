"""SLATE-08B desktop IPC trust and media-delivery unit gates.

The existing SLATE-07 actual USD/Blender native tests remain separate: this
suite verifies the real pywebview authorization boundary using fake window and
fake *host* (not fake source/camera metadata or a fake trusted grant).
"""
import hashlib
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import threading
import time
import unittest
import zlib

from backend.nvp_camera_workbench import lens_settings, workbench_preview_key
from backend.nvp_film_index import FilmIndex
from backend.nvp_slate_proxy_recipe import canonical
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_studio import Studio


def png(w=640,h=360):
    def chunk(name,data):
        return struct.pack(">I",len(data))+name+data+struct.pack(
            ">I",zlib.crc32(name+data)&0xffffffff)
    raw=b"".join(b"\\0"+b"\\xc0\\x80\\x40"*w for _ in range(h))
    return (b"\\x89PNG\\r\\n\\x1a\\n"+
        chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,2,0,0,0))+
        chunk(b"IDAT",zlib.compress(raw))+chunk(b"IEND",b""))


class Window:
    def __init__(self):
        self.url="http://127.0.0.1:7777/"
        self.yes=True
        self.questions=[]
    def get_current_url(self):
        return self.url
    def create_confirmation_dialog(self,title,message):
        self.questions.append((title,message))
        return self.yes


class Cache:
    def __init__(self,host):
        self.host=host
    def lookup(self,project_id,key):
        if not self.host.ready or self.host.cancelled:
            return None
        return {"status":"READY","job_id":"camtest_01","cache_key":key}
    def _job(self,job_id):
        return {"project_id":self.host.pid,
                "cache_key":self.host.key,
                "state":"PENDING" if not self.host.ready else "READY"}


class Host:
    def __init__(self,callback):
        self.approve=callback
        self.pid=None
        self.scene_id=None
        self.revision=None
        self.scene_sha=None
        self.tick=None
        self.path=None
        self.settings=None
        self.key=None
        self.ready=False
        self.cancelled=False
        self.runner_gate=threading.Event()
        self.runner_gate.set()
        self.cache=Cache(self)
        self.requests=0
        self.replays_rejected=False
    def request_camera_workbench(self,pid,scene_id,revision,*,
             source_tick,camera_path,settings,quality,creator_event,
             ram_mb,timeout_seconds):
        self.requests+=1
        self.pid=pid;self.scene_id=scene_id;self.revision=revision
        self.tick=source_tick;self.path=camera_path;self.settings=settings
        # The real production host independently verifies exact FilmIndex SHA,
        # fixed renderer script and resource approval fields.
        self.key=self.expected_key
        context={
            "operation":"nvp.camera.authorize_pre_take_still.v1",
            "project_id":pid,"scene_id":scene_id,"scene_revision":revision,
            "scene_document_sha256":self.scene_sha,
            "source_tick":source_tick,"camera_path":camera_path,
            "optical_settings_sha256":hashlib.sha256(canonical(settings)).hexdigest(),
            "preview_cache_key":self.key,
        }
        if not self.approve(creator_event,context):
            raise PermissionError("Native approval was not granted")
        self.replays_rejected=not self.approve(creator_event,context)
        return {"status":"QUEUED","job_id":"camtest_01","cache_key":self.key}
    def run_next(self):
        self.runner_gate.wait(timeout=3)
        if not self.cancelled:
            self.ready=True
        return {"id":"camtest_01",
                "state":"CANCELLED" if self.cancelled else "SUCCEEDED"}
    def read_camera_workbench_png(self,pid,key):
        data=png()
        return {
            "scene_id":self.scene_id,"scene_revision":self.revision,
            "scene_document_sha256":self.scene_sha,
            "source_tick":self.tick,"camera_path":self.path,
            "lens_settings":self.settings,
            "png_bytes":data,"image_sha256":hashlib.sha256(data).hexdigest(),
            "frozen_take_created":False,"film_master_approved":False}
    def cancel(self,job_id,*,creator_event):
        context={
            "operation":"nvp.camera.cancel_pre_take_still.v1",
            "project_id":self.pid,"scene_id":self.scene_id,
            "job_id":job_id,"preview_cache_key":self.key}
        if not self.approve(creator_event,context):
            raise PermissionError("Native cancel was not explicitly approved")
        self.cancelled=True
        return {"state":"CANCEL_REQUESTED"}


class TrustedDesktopCameraContract(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        studio=Studio(Path(tmp.name)/"db.sqlite3")
        self.pid=studio.create_project("Native camera","")["id"]
        self.index=FilmIndex(studio)
        self.record=self.index.register_revision(
            self.pid,"scene_one","scene",
            {"format":"unit.native.source.v1",
             "prim_roles":{"/World/Camera":"camera","/World/Actor":"actor"},
             "native_schema_version":"unit_fixture"})
        self.window=Window()
        self.host=None
        def factory(callback):
            self.host=Host(callback)
            self.host.scene_sha=self.record["document_sha256"]
            self.host.expected_key=workbench_preview_key(
                self.record["document_sha256"],0,"/World/Camera",
                lens_settings(),"interactive")
            return self.host
        self.bridge=TrustedDesktopCameraBridge(self.index,
            origin="http://127.0.0.1:7777",host_factory=factory)
        self.bridge._attach_window(self.window)
        self.addCleanup(self.bridge._close)

    def payload(self):
        return {
            "project_id":self.pid,"source_scene_id":"scene_one",
            "source_scene_revision":1,
            "source_scene_document_sha256":self.record["document_sha256"],
            "source_tick":0,"camera_path":"/World/Camera",
            "lens_settings":lens_settings(),
            "source_modified":False,"frozen_take_created":False,
        }

    def test_os_denial_prevents_native_worker(self):
        self.window.yes=False
        result=self.bridge.request_camera_still(self.payload())
        self.assertEqual(result["status"],"DENIED")
        self.assertIsNone(self.host)
        self.assertEqual(len(self.window.questions),1)

    def test_origin_and_source_and_unapproved_optics_are_refused(self):
        self.window.url="https://outside.example/"
        with self.assertRaises(PermissionError):
            self.bridge.camera_render_capabilities()
        self.window.url="http://127.0.0.1:7777/"
        p=self.payload();p["source_scene_document_sha256"]="f"*64
        with self.assertRaises(RuntimeError):
            self.bridge.request_camera_still(p)
        p=self.payload();p["lens_settings"]={
            **p["lens_settings"],"squeeze_factor":2}
        with self.assertRaises(ValueError):
            self.bridge.request_camera_still(p)
        p=self.payload();p["source_tick"]=True
        with self.assertRaises(ValueError):
            self.bridge.request_camera_still(p)
        self.assertEqual(self.window.questions,[])

    def test_verified_native_png_is_bound_to_one_session_ticket(self):
        ticket=self.bridge.request_camera_still(self.payload())
        self.assertEqual(ticket["status"],"QUEUED")
        self.assertEqual(ticket["scene_document_sha256"],
                         self.record["document_sha256"])
        self.assertTrue(self.host.replays_rejected)
        with self.assertRaises(PermissionError):
            self.bridge.poll_camera_still("not_a_valid_ticket")
        result=None
        for _ in range(150):
            result=self.bridge.poll_camera_still(ticket["ticket_id"])
            if result["status"]=="READY":
                break
            time.sleep(.01)
        self.assertEqual(result["status"],"READY")
        self.assertEqual(result["format"],"nvp.camera.desktop_delivery.v1")
        self.assertTrue(result["image_data_url"].startswith(
            "data:image/png;base64,"))
        self.assertFalse(result["frozen_take_created"])
        self.assertEqual(self.index.read_revision(
            self.pid,"scene_one",1)["document_sha256"],
            self.record["document_sha256"])
        self.assertEqual(self.index.list_objects(self.pid,kind="take"),[])

    def test_second_native_confirmation_required_to_cancel(self):
        ticket=self.bridge.request_camera_still(self.payload())
        self.host.runner_gate.clear()
        self.window.yes=False
        refusal=self.bridge.cancel_camera_still(ticket["ticket_id"])
        self.assertEqual(refusal["status"],"DENIED")
        self.assertFalse(self.host.cancelled)
        self.window.yes=True
        approved=self.bridge.cancel_camera_still(ticket["ticket_id"])
        self.assertEqual(approved["status"],"CANCEL_REQUESTED")
        self.assertTrue(self.host.cancelled)
        self.host.runner_gate.set()
        result=self.bridge.poll_camera_still(ticket["ticket_id"])
        self.assertNotEqual(result["status"],"READY")

    def test_media_tamper_does_not_escape_native_audit(self):
        ticket=self.bridge.request_camera_still(self.payload())
        for _ in range(150):
            if self.host.ready:break
            time.sleep(.01)
        self.assertTrue(self.host.ready)
        orig=self.host.read_camera_workbench_png
        def tampered(*args):
            item=orig(*args)
            return {**item,"image_sha256":"0"*64}
        self.host.read_camera_workbench_png=tampered
        with self.assertRaises(RuntimeError):
            self.bridge.poll_camera_still(ticket["ticket_id"])


if __name__=="__main__":
    unittest.main()
