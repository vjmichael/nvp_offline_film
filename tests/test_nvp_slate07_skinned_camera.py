"""SLATE-07/CAM-01: real USD-bound skinned actor and pre-Take lens acceptance.

Real OpenUSD binding/animation APIs are REQUIRED for native test acceptance.
Fixture PNGs test only cache/consent, not Blender render fidelity.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import zlib

from pxr import Usd,UsdSkel,UsdGeom

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_slate_lazy_preview import SlateLazyPreview
from backend.nvp_openusd_skinning import normalize_skin,evaluate_skin
from backend.nvp_slate06_geometry import capture_geometry,BLENDER_SCRIPT
from backend.nvp_camera_workbench import (
    VirtualCameraWorkbench,lens_settings,workbench_preview_key,
    capture_workbench_still)
from backend.nvp_resource_guard import ResourceSnapshot,collect_resources
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_slate_preview_cache import SlatePreviewCache
from backend.nvp_slate_preview_host import NativeSlatePreviewHost

T=TICKS_PER_SECOND


def _sensor():
    return ResourceSnapshot(1,32768,25000,0,())


def _png(w,h):
    def part(key,content):
        return (struct.pack(">I",len(content))+key+content+
                struct.pack(">I",zlib.crc32(key+content)&0xffffffff))
    scan=b"".join(b"\0"+b"\x70\x9c\xb9"*w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n"+part(
        b"IHDR",struct.pack(">IIBBBBB",w,h,8,2,0,0,0)
        )+part(b"IDAT",zlib.compress(scan))+part(b"IEND",b"")


class RealCharacterAndLens(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.studio=Studio(root/"nvp.sqlite")
        self.pid=self.studio.create_project("Digital Actor Camera Lab","")["id"]
        self.index=FilmIndex(self.studio)
        self.scene=OpenUSDSceneBridge(self.index)
        self.timeline=TemporalLedger(self.index)
        self.takes=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda ev,context:
            ev=="freeze_take" and
            context["operation"]=="nvp.freeze.usd_temporal_take.v1")
        self.actions=lambda ev,ctx:(
            ev=="director" and ctx["operation"] in (
                "nvp.camera.save_optical_preset.v1",
                "nvp.usd.director_shot_override.v1"))
        self.workbench=VirtualCameraWorkbench(
            self.index,verify_director_action=self.actions)
        self.skin={
            "points":[
                [0,-0.2,-0.2],[0,0.2,-0.2],
                [0,0.2,0.2],[0,-0.2,0.2],
                [1,-0.2,-0.2],[1,0.2,-0.2],
                [1,0.2,0.2],[1,-0.2,0.2],
            ],
            "faces":[
                [0,1,2,3],[4,7,6,5],[0,4,5,1],
                [1,5,6,2],[2,6,7,3],[3,7,4,0],
            ],
            "joint_indices":[[0],[0],[0],[0],[1],[1],[1],[1]],
            "joint_weights":[[1.0] for _ in range(8)],
            "display_color":[0.35,0.55,0.82],
        }
        self.rigs=[{
            "path":"/World/Actor",
            "joints":["Root","Root/Arm"],
            "samples":[
                {"tick":0,"translations":[[0,0,0],[0,0,0]]},
                {"tick":2*T,"translations":[[0,0,0],[2,0,0]]},
            ],"skin":self.skin,
        }]
        self.scene.publish(
            self.pid,"world",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,8]},
                {"path":"/World/Key","role":"light","position":[0,5,5]},
            ],
            curves=[{"path":"/World/Actor","samples":[
                {"tick":0,"position":[0,0,0]},
                {"tick":2*T,"position":[4,0,0]}]}],
            native_schemas=True,skeletal_rigs=self.rigs)
        self.original_scene_sha=self.index.read_revision(
            self.pid,"world",1)["document_sha256"]
        self.index.register_revision(
            self.pid,"human_source","performance",
            {"format":"nvp.unit.real.skeletal.actor.v1"})
        self.timeline.publish(self.pid,"acting",[
            {"event_id":"raise_arm","event_kind":"gesture",
             "subject_id":"Actor","start_tick":0,"end_tick":2*T,
             "source_id":"human_source","source_revision":1,
             "payload":{"usd_prim_path":"/World/Actor","action":"raise_arm"}},
        ],duration_tick=3*T)
        root=Path(self.tmp.name)
        self.activity=TaskLedger(root/"tasks",sampler=_sensor)
        fake=Path(sys.executable).resolve()
        self.supervisor=BlenderWorkerSupervisor(
            root/"worker",blender_executable=fake,
            blender_sha256=sha_file(fake),
            blender_version="Blender fake unit host",
            activity_ledger=self.activity)
        self.cache=SlatePreviewCache(root/"cache")
        self.auth=object()
        self.host=NativeSlatePreviewHost(
            self.index,self.supervisor,self.activity,self.cache,
            verify_creator_action=lambda ev,ctx:
            ev is self.auth and ctx["operation"] in (
                "nvp.camera.authorize_pre_take_still.v1",
                "nvp.camera.cancel_pre_take_still.v1",
                "nvp.slate.authorize_openusd_geometry_preview.v1"))

    def freeze(self):
        self.takes.freeze(
            self.pid,"take",scene_id="world",scene_revision=1,
            timeline_id="acting",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="freeze_take")
        self.slate=DigitalSlateBranches(
            self.index,verify_editor_action=lambda *_:False)
        self.slate.publish_graph(
            self.pid,"slate",scene_id="world",scene_label="01",
            nodes=[{
                "branch_id":"original","kind":"performance",
                "parent_id":None,"fork_tick":None,
                "group_id":"performance","primary":True,
                "take_id":"take","source_start_tick":0,
                "source_end_tick":3*T,"shot_id":None,"shot_revision":None,
                "slate":{"scene":"01","setup":"A","shot":"01A",
                         "camera":"A","take_number":1,"wild":False,
                         "script_revision":"first","notes":"Animated actor"},
            }])
        edit=SlateSequenceAssembly(
            self.slate,verify_editor_action=lambda ev,ctx:ev=="make_active")
        edit.commit(
            self.pid,"edit",graph_id="slate",graph_revision=1,
            segments=[{"segment_id":"actor_time","branch_id":"original",
                       "source_in_tick":0,"source_out_tick":2*T}],
            editor_event="make_active")

    def _preview(self,optics=None,quality="thumbnail"):
        return self.host.request_camera_workbench(
            self.pid,"world",1,source_tick=T,camera_path="/World/Camera",
            settings=optics or lens_settings(),quality=quality,
            creator_event=self.auth)

    def _verified_cache(self,queued):
        row=self.cache._job(queued["job_id"])
        path=self.supervisor.root/queued["job_id"]/"preview.png"
        path.write_bytes(_png(row["width"],row["height"]))
        sha=sha_file(path)
        with patch.object(self.supervisor,"verify_completed",
             return_value={"state":"SUCCEEDED",
                            "outputs":{"preview.png":{
                               "kind":"png","sha256":sha,
                               "bytes":path.stat().st_size}}}):
            return self.cache.accept_verified(self.supervisor,queued["job_id"])

    def test_native_usd_skin_mesh_binding_and_true_performance_change(self):
        source,stage=self.scene.open(self.pid,"world",1)
        self.assertEqual(source["data"]["skeleton_rigs"][0]["skin_weighted"],True)
        mesh=stage.GetPrimAtPath("/World/Actor/Rig/CharacterMesh")
        self.assertTrue(mesh.IsA(UsdGeom.Mesh))
        self.assertTrue(mesh.HasAPI(UsdSkel.BindingAPI))
        idx=UsdSkel.BindingAPI(mesh).GetJointIndicesPrimvar().Get()
        self.assertEqual(len(idx),4*len(self.skin["points"]))
        pose0=evaluate_skin(stage,mesh,"/World/Actor",0)
        pose1=evaluate_skin(stage,mesh,"/World/Actor",T)
        self.assertAlmostEqual(pose0["deformed_points"][4][0],1,places=4)
        self.assertAlmostEqual(pose1["deformed_points"][4][0],2,places=4)
        self.assertTrue(pose1["skinning_evaluated"])
        self.assertFalse(pose1["facial_deformation_evaluated"])
        self.assertEqual(
            self.index.read_revision(self.pid,"world",1)["document_sha256"],
            self.original_scene_sha)

    def test_skinned_geometry_enters_frozen_take_render_at_exact_tick(self):
        self.freeze()
        self.assertTrue(self.index.read_revision(self.pid,"take",1)["data"]["frozen"])
        selected=SlateLazyPreview(self.index).select(
            self.pid,"edit",1,film_tick=T,quality="thumbnail")
        picture=capture_geometry(self.index,selected)
        self.assertTrue(picture["skinning_evaluated"])
        self.assertEqual(picture["skinned_mesh_paths"],
                         ["/World/Actor/Rig/CharacterMesh"])
        self.assertEqual(picture["unmeshed_actors"],[])
        posed=next(p for p in picture["objects"] if
                   p["path"]=="/World/Actor/Rig/CharacterMesh")
        self.assertEqual(posed["geometry"]["kind"],"mesh")
        self.assertEqual(
            posed["geometry"]["skinning_mode"],"native_UsdSkel_linear_blend")
        self.assertAlmostEqual(posed["geometry"]["points"][4][0],2,places=4)
        self.assertAlmostEqual(posed["world_matrix"][0][3],2,places=4)
        self.assertFalse(picture["facial_animation_evaluated"])

    def test_invalid_skin_influences_rejected_not_interpreted_as_geometry(self):
        bad=dict(self.skin)
        bad["joint_indices"]=[list(x) for x in self.skin["joint_indices"]]
        bad["joint_indices"][4]=[3]
        with self.assertRaises(ValueError):
            normalize_skin(bad,2)
        bad=dict(self.skin)
        bad["joint_weights"]=[list(x) for x in self.skin["joint_weights"]]
        bad["joint_weights"][4]=[0.5]
        with self.assertRaises(ValueError):
            normalize_skin(bad,2)

    def test_pre_take_lens_fov_and_scene_projection_no_frozen_take(self):
        snap=self.workbench.snapshot(
            self.pid,"world",1,tick=T,camera_path="/World/Camera")
        self.assertFalse(snap["frozen_take_created"])
        self.assertEqual(snap["scene_document_sha256"],self.original_scene_sha)
        self.assertGreater(len(snap["markers"]),0)
        wide=lens_settings(lens="wide_24",f_stop=1.4)
        portrait=lens_settings(lens="portrait_85",f_stop=8)
        self.assertGreater(wide["horizontal_fov_degrees"],
                           portrait["horizontal_fov_degrees"])
        self.assertFalse(wide["distortion_filter_applied"])
        self.assertEqual(
            self.index.read_revision(self.pid,"world",1)["document_sha256"],
            self.original_scene_sha)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"take",1)

    def test_temporary_camera_still_uses_real_geom_and_focus_not_source_edit(self):
        optics=lens_settings(lens="portrait_85",f_stop=1.4,
                             focus_distance_m=3)
        doc=capture_workbench_still(
            self.index,self.pid,"world",1,tick=T,
            camera_path="/World/Camera",
            settings=optics,quality="interactive")
        self.assertEqual(doc["source_take_sha256"],None)
        self.assertEqual(doc["source_kind"],"pre_take_scene_not_frozen_take")
        self.assertAlmostEqual(doc["camera"]["focal_length_mm"],85,places=4)
        self.assertAlmostEqual(doc["camera"]["f_stop"],1.4,places=4)
        self.assertAlmostEqual(doc["camera"]["focus_distance_m"],3,places=4)
        self.assertTrue(doc["skinning_evaluated"])
        self.assertEqual(doc["source_scene_document_sha256"],self.original_scene_sha)
        self.assertIn("data.dof.aperture_fstop=f_stop",BLENDER_SCRIPT)
        _,unchanged=self.scene.open(self.pid,"world",1)
        cam=UsdGeom.Camera(unchanged.GetPrimAtPath("/World/Camera"))
        self.assertAlmostEqual(
            float(cam.GetFocalLengthAttr().Get(Usd.TimeCode(float(T))))*100.,
            50.,places=4)
        self.assertEqual(
            self.index.read_revision(self.pid,"world",1)["document_sha256"],
            self.original_scene_sha)

    def test_director_saves_optics_then_applies_only_to_matching_frozen_shot(self):
        optics=lens_settings(lens="wide_24",sensor="super_35",
                             f_stop=4.0,focus_distance_m=9.)
        with self.assertRaises(PermissionError):
            self.workbench.save_preset(
                self.pid,"wide_setup",settings=optics,creator_event="AI")
        saved=self.workbench.save_preset(
            self.pid,"wide_setup",settings=optics,creator_event="director")
        self.assertEqual(saved["kind"],"presentation")
        self.assertEqual(
            self.workbench.open_preset(self.pid,"wide_setup",1)["data"]["optics"],
            optics)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"take",1)
        self.freeze()
        shot=self.workbench.apply_to_shot(
            self.pid,"lens_shot",take_id="take",scene_id="world",
            scene_revision=1,camera_path="/World/Camera",settings=optics,
            start_tick=0,end_tick=2*T,creator_event="director",
            reason="Director selects wide lens for emotional geography")
        # Shot publication returns a narrow receipt; reopen the immutable
        # FilmIndex revision to verify the actual director-approved source.
        self.assertEqual(shot["kind"],"shot")
        self.assertTrue(self.index.read_revision(
            self.pid,"lens_shot",1)["data"]["director_shot_change_approved"])
        evaluated=OpenUSDShotOverrides(
            self.index,verify_director_action=lambda *_:False).evaluate(
                self.pid,"lens_shot",1,tick=T)
        camera=evaluated["changes"][0]
        self.assertAlmostEqual(camera["shot_focal_length_mm"],24,places=3)
        self.assertAlmostEqual(camera["shot_f_stop"],4,places=4)
        self.assertAlmostEqual(camera["shot_focus_distance_m"],9,places=4)
        self.assertAlmostEqual(
            camera["shot_sensor_width_mm"],24.89,places=3)
        self.assertEqual(
            self.index.read_revision(self.pid,"world",1)["document_sha256"],
            self.original_scene_sha)

    def test_native_pre_take_worker_consent_and_cache_hit_without_usd(self):
        optics=lens_settings(lens="wide_24",f_stop=2.)
        with self.assertRaises(PermissionError):
            self.host.request_camera_workbench(
                self.pid,"world",1,source_tick=T,
                camera_path="/World/Camera",settings=optics,
                quality="thumbnail",creator_event="untrusted")
        queued=self._preview(optics)
        self.assertEqual(queued["status"],"QUEUED")
        self.assertFalse(queued["frozen_take_created"])
        with self.activity._db() as db:
            row=db.execute("""SELECT approval_id,spec_sha256
                FROM nvp_camera_preview_consents WHERE task_id=?""",
                (queued["task_id"],)).fetchone()
        with patch.object(self.host,"_camera_approval_check",
                         wraps=self.host._camera_approval_check) as auth:
            # Security proof is tied to the stored worker operation; this
            # stage contains no executable foreign asset or frozen Take.
            spec=self.host.dispatcher.bindings.verified_spec(
                queued["task_id"],owner_key=self.host.dispatcher.owner_key,
                require_active=False)
            self.assertTrue(self.host._approval_check(row[0],row[1],spec))
            self.assertTrue(auth.called)
        cached=self._verified_cache(queued)
        self.assertEqual(cached["status"],"READY")
        with patch("backend.nvp_camera_workbench.capture_workbench_still",
                   side_effect=AssertionError("Cache hit reopened original USD")):
            hit=self._preview(optics)
        self.assertEqual(hit["status"],"CACHE_HIT")
        photo=self.host.read_camera_workbench_png(
            self.pid,queued["cache_key"])
        self.assertFalse(photo["frozen_take_created"])
        self.assertEqual(photo["camera_path"],"/World/Camera")
        self.assertEqual(photo["scene_document_sha256"],self.original_scene_sha)
        self.assertEqual(photo["lens_settings"],optics)

    def test_native_pre_take_cancel_never_accepts_draft_output(self):
        queued=self._preview()
        cancelled=self.host.cancel(queued["job_id"],creator_event=self.auth)
        self.assertEqual(cancelled["state"],"CANCELLED_QUEUED")
        self.assertIsNone(self.cache.lookup(self.pid,queued["cache_key"]))
        with self.assertRaises(KeyError):
            self.host.read_camera_workbench_png(self.pid,queued["cache_key"])

    @unittest.skipUnless(os.environ.get("NVP_NATIVE_BLENDER_EXECUTABLE"),
                         "Installed Blender smoke not configured")
    def test_actual_contained_blender_skin_and_optical_still(self):
        binary=Path(os.environ["NVP_NATIVE_BLENDER_EXECUTABLE"]).resolve()
        if not binary.is_file():
            self.skipTest("No native Blender binary")
        version=subprocess.run(
            [str(binary),"-b","--version"],capture_output=True,
            text=True,timeout=30,check=True).stdout.splitlines()[0]
        tasks=TaskLedger(Path(self.tmp.name)/"native_tasks",sampler=collect_resources)
        worker=BlenderWorkerSupervisor(
            Path(self.tmp.name)/"native_worker",
            blender_executable=binary,
            blender_sha256=sha_file(binary),blender_version=version,
            activity_ledger=tasks)
        cache=SlatePreviewCache(Path(self.tmp.name)/"native_cache")
        host=NativeSlatePreviewHost(
            self.index,worker,tasks,cache,
            verify_creator_action=lambda event,scope:
            event is self.auth and
            scope["operation"]=="nvp.camera.authorize_pre_take_still.v1")
        approved=host.request_camera_workbench(
            self.pid,"world",1,source_tick=T,
            camera_path="/World/Camera",
            settings=lens_settings(lens="portrait_85",f_stop=1.4),
            quality="thumbnail",creator_event=self.auth,
            ram_mb=4096,timeout_seconds=240)
        receipt=host.run_next()
        self.assertEqual(receipt["state"],"SUCCEEDED")
        picture=host.read_camera_workbench_png(self.pid,approved["cache_key"])
        self.assertEqual((picture["width"],picture["height"]),(320,180))
        self.assertGreater(len(picture["png_bytes"]),100)
        self.assertFalse(picture["frozen_take_created"])


    @unittest.skipUnless(os.environ.get("NVP_NATIVE_BLENDER_EXECUTABLE"),
                         "Real Blender executable not configured")
    def test_native_desktop_camera_bridge_end_to_end_real_blender(self):
        """SLATE-08B true original USD skinned scene -> desktop consent
        -> native supervised Blender -> audited scene/lens PNG, no Take.
        """
        import time
        from backend.nvp_slate08b_native_camera_ipc import (
            TrustedDesktopCameraBridge)
        binary=Path(os.environ["NVP_NATIVE_BLENDER_EXECUTABLE"]).resolve()
        self.assertTrue(binary.is_file(),"An actual Blender executable is required")
        version=subprocess.run(
            [str(binary),"-b","--version"],capture_output=True,
            text=True,timeout=30,check=True).stdout.splitlines()[0]
        root=Path(self.tmp.name)
        created=[]
        def factory(approval_callback):
            ledger=TaskLedger(root/"desktop_tasks",sampler=collect_resources)
            worker=BlenderWorkerSupervisor(
                root/"desktop_workers",blender_executable=binary,
                blender_sha256=sha_file(binary),blender_version=version,
                activity_ledger=ledger)
            cache=SlatePreviewCache(root/"desktop_cache")
            host=NativeSlatePreviewHost(self.index,worker,ledger,cache,
                verify_creator_action=approval_callback)
            host.recover()
            created.append(host)
            return host

        class ConfirmingWindow:
            calls=0
            def get_current_url(self):
                return "http://127.0.0.1:7777/"
            def create_confirmation_dialog(self,title,message):
                self.calls+=1
                assert "Scene: world rev 1" in message
                assert "Camera: /World/Camera" in message
                return True
        window=ConfirmingWindow()
        bridge=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:7777",
            host_factory=factory)
        bridge._attach_window(window)
        optics=lens_settings(lens="portrait_85",f_stop=1.4)
        try:
            requested=bridge.request_camera_still({
                "project_id":self.pid,"source_scene_id":"world",
                "source_scene_revision":1,
                "source_scene_document_sha256":self.original_scene_sha,
                "source_tick":T,"camera_path":"/World/Camera",
                "lens_settings":optics,"source_modified":False,
                "frozen_take_created":False,
            })
            self.assertEqual(requested["status"],"QUEUED")
            deadline=time.monotonic()+240
            state=None
            while time.monotonic()<deadline:
                state=bridge.poll_camera_still(requested["ticket_id"])
                if state["status"]=="READY":
                    break
                if state["status"]!="QUEUED":
                    self.fail("Actual native desktop render failed closed: "+
                              str(state))
                time.sleep(.25)
            self.assertIsNotNone(state)
            self.assertEqual(state["status"],"READY")
            self.assertTrue(state["image_data_url"].startswith(
                "data:image/png;base64,"))
            self.assertEqual(state["scene_document_sha256"],
                             self.original_scene_sha)
            self.assertEqual(state["lens_settings"],optics)
            self.assertFalse(state["frozen_take_created"])
            self.assertFalse(state["film_master_approved"])
            self.assertEqual(window.calls,1)
            self.assertEqual(
                self.index.read_revision(self.pid,"world",1)["document_sha256"],
                self.original_scene_sha)
            self.assertEqual(self.index.list_objects(self.pid,kind="take"),[])
            self.assertTrue(created)
            jobs=created[0].supervisor
            with created[0].cache._db() as db:
                row=db.execute("SELECT job_id FROM slate_preview_cache "
                               "WHERE project_id=?",(self.pid,)).fetchone()
            proof=jobs.verify_completed(row[0])
            self.assertEqual(proof["state"],"SUCCEEDED")
        finally:
            bridge._close()


if __name__=="__main__":
    unittest.main()
