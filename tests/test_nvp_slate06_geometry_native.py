"""SLATE-06 native authored OpenUSD geometry, camera, light, shot and CI acceptance.

No mock stage: use real pxr-composed source asset references and freeze a
Digital Take. Only full Linux Blender smoke produces actual pixels. Tests
with a synthetic PNG and a patched worker receipt verify cache mechanics
but do NOT constitute proof of an actual native renderer.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import zlib

from pxr import Usd,UsdGeom

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_slate_lazy_preview import SlateLazyPreview
from backend.nvp_slate_proxy_recipe import preview_cache_key as blocking_key
from backend.nvp_slate06_geometry import (
    capture_geometry,preview_cache_key,recipe,BLENDER_SCRIPT,FORMAT,
    _mesh,MAX_SOURCE_BYTES,canonical)
from backend.nvp_slate_preview_host import NativeSlatePreviewHost
from backend.nvp_slate_preview_cache import SlatePreviewCache
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot,collect_resources

T=TICKS_PER_SECOND


def measured():
    return ResourceSnapshot(1,32768,25000,0,())


def fixture_png(width,height):
    def chunk(name,payload):
        return (struct.pack(">I",len(payload))+name+payload+
                struct.pack(">I",zlib.crc32(name+payload)&0xffffffff))
    scan=b"".join(b"\x00"+b"\x56\x85\xb5"*width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"+
        chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+
        chunk(b"IDAT",zlib.compress(scan,9))+
        chunk(b"IEND",b""))


class Slate06NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.studio=Studio(root/"film.sqlite")
        self.pid=self.studio.create_project("Actual Geometry Film","")["id"]
        self.index=FilmIndex(self.studio)
        self.assets=OpenUSDAssetRegistry(self.index)
        self.scene=OpenUSDSceneBridge(self.index)
        self.ledger=TemporalLedger(self.index)
        self.takes=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
            event=="freeze" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1")
        self.shots=OpenUSDShotOverrides(
            self.index,verify_director_action=lambda event,scope:
            event=="director_lens" and
            scope["operation"]=="nvp.usd.director_shot_override.v1")
        self.slate=DigitalSlateBranches(
            self.index,verify_editor_action=lambda *_:False)
        self.editor=SlateSequenceAssembly(
            self.slate,verify_editor_action=lambda event,scope:
            event=="commit_cut" and
            scope["operation"]=="nvp.slate.commit_assembled_edit.v1")
        self.assets.publish(self.pid,"body_mesh",shape="cube",size_m=1.6)
        self.assets.publish(self.pid,"prop_mesh",shape="sphere",size_m=1.2)
        prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Prop","role":"prop","position":[4,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,0,8]},
            {"path":"/World/Key","role":"light","position":[1,3,5]},
        ]
        controls=[
            {"path":"/World/Camera","property":"camera.focal_length_mm",
             "samples":[{"tick":0,"value":35.0},
                        {"tick":2*T,"value":85.0}]},
            {"path":"/World/Key","property":"light.intensity",
             "samples":[{"tick":0,"value":100.0},
                        {"tick":2*T,"value":300.0}]},
        ]
        self.scene.publish(
            self.pid,"world",prims=prims,
            curves=[{"path":"/World/Actor","samples":[
                {"tick":0,"position":[0,0,0]},
                {"tick":2*T,"position":[4,0,0]}]}],
            native_schemas=True,performance_channels=controls,
            asset_bindings=[
                {"path":"/World/Actor","asset_id":"body_mesh",
                 "asset_revision":1},
                {"path":"/World/Prop","asset_id":"prop_mesh",
                 "asset_revision":1},
            ])
        self.index.register_revision(
            self.pid,"performer","performance",
            {"format":"nvp.slate06.performer","actor":"one"})
        self.ledger.publish(self.pid,"acting",[
            {"event_id":"walk","event_kind":"action","subject_id":"Actor",
             "start_tick":0,"end_tick":2*T,
             "source_id":"performer","source_revision":1,
             "payload":{"usd_prim_path":"/World/Actor","action":"walk"}},
        ],duration_tick=3*T)
        self.takes.freeze(
            self.pid,"take",scene_id="world",scene_revision=1,
            timeline_id="acting",timeline_revision=1,
            sample_ticks=[0,T,2*T],creator_event="freeze")
        self.shots.publish(
            self.pid,"director_angle",take_id="take",start_tick=0,end_tick=2*T,
            changes=[
                {"path":"/World/Actor","property":"translation_offset",
                 "value":[1,0,0]},
                {"path":"/World/Camera","property":"camera_focal_length_mm",
                 "value":85.0},
                {"path":"/World/Key","property":"light_intensity",
                 "value":220.0},
            ],purpose="framing",continuity_policy="intentional_cheat",
            reason="Director moves actor to improve source-shot framing",
            creator_event="director_lens")
        def slate(kind,number):
            return {"scene":"01","setup":"A","shot":"01A",
                    "camera":"A","take_number":number,"wild":False,
                    "script_revision":"revision_1","notes":"Source test"}
        nodes=[
            {"branch_id":"original","kind":"performance",
             "parent_id":None,"fork_tick":None,
             "group_id":"all_scene","primary":True,"take_id":"take",
             "source_start_tick":0,"source_end_tick":3*T,
             "shot_id":None,"shot_revision":None,
             "slate":slate("performance",1)},
            {"branch_id":"camera_angle","kind":"coverage",
             "parent_id":"original","fork_tick":0,
             "group_id":"shot_angle","primary":True,"take_id":"take",
             "source_start_tick":0,"source_end_tick":2*T,
             "shot_id":"director_angle","shot_revision":1,
             "slate":slate("coverage",1)},
        ]
        self.slate.publish_graph(
            self.pid,"slate",scene_id="world",scene_label="01",nodes=nodes)
        self.editor.commit(
            self.pid,"cut",graph_id="slate",graph_revision=1,
            segments=[{"segment_id":"angle_part",
                       "branch_id":"camera_angle",
                       "source_in_tick":T,"source_out_tick":2*T}],
            editor_event="commit_cut")
        self.lazy=SlateLazyPreview(self.index)
        self.cache=SlatePreviewCache(root/"cached",max_ready=1)
        self.activity=TaskLedger(root/"activity",sampler=measured)
        exe=Path(sys.executable).resolve()
        self.supervisor=BlenderWorkerSupervisor(
            root/"worker",blender_executable=exe,
            blender_sha256=sha_file(exe),blender_version="Blender Test",
            activity_ledger=self.activity)
        self.trusted_event=object()
        def approved(event,context):
            return (event is self.trusted_event and
                    context["operation"] in (
                        "nvp.slate.authorize_openusd_geometry_preview.v1",
                        "nvp.slate.authorize_lowfi_preview.v1",
                        "nvp.slate.cancel_openusd_geometry_preview.v1"))
        self.host=NativeSlatePreviewHost(
            self.index,self.supervisor,self.activity,self.cache,
            verify_creator_action=approved)

    def ticket(self):
        return self.lazy.select(
            self.pid,"cut",1,film_tick=0,quality="thumbnail")

    def request(self,**kw):
        return self.host.request(
            self.pid,"cut",1,film_tick=0,quality="thumbnail",
            creator_event=self.trusted_event,presentation="geometry",**kw)

    def _publish_test_receipt(self,queued):
        row=self.cache._job(queued["job_id"])
        file=self.supervisor.root/queued["job_id"]/"preview.png"
        file.write_bytes(fixture_png(row["width"],row["height"]))
        digest=sha_file(file)
        with patch.object(self.supervisor,"verify_completed",return_value={
            "state":"SUCCEEDED","outputs":{
                "preview.png":{"kind":"png","sha256":digest,
                               "bytes":file.stat().st_size}}}):
            return self.cache.accept_verified(self.supervisor,queued["job_id"])

    def test_real_asset_geometry_and_shot_local_camera_light(self):
        ticket=self.ticket()
        source=capture_geometry(self.index,ticket,camera_path="/World/Camera")
        self.assertEqual(source["format"],FORMAT)
        kinds={x["geometry"]["kind"] for x in source["objects"]}
        self.assertEqual(kinds,{"cube","sphere"})
        self.assertEqual(source["camera"]["path"],"/World/Camera")
        self.assertAlmostEqual(source["camera"]["focal_length_mm"],85,places=3)
        self.assertAlmostEqual(source["camera"]["sensor_width_mm"],36.0,places=3)
        self.assertEqual(source["up_axis"],"Z")
        self.assertAlmostEqual(source["lights"][0]["intensity"],220,places=2)
        actor=next(x for x in source["objects"]
                   if x["path"]=="/World/Actor/Geometry")
        # row-vector Gf.Matrix4d -> column-vector Blender matrix, including
        # director's exact SHOT-01 offset atop original animated Take1.
        self.assertAlmostEqual(actor["world_matrix"][0][3],3,places=3)
        self.assertAlmostEqual(actor["geometry"]["size"],1.6,places=5)
        self.assertEqual(source["unmeshed_actors"],[])
        self.assertFalse(source["skinning_evaluated"])
        self.assertFalse(source["usd_light_photometry_exact"])
        self.assertFalse(source["final_presentation_approved"])
        self.assertLess(len(canonical(recipe(source,"thumbnail"))),MAX_SOURCE_BYTES)
        _,canonical_stage=self.scene.open(self.pid,"world",1)
        lens=UsdGeom.Camera(canonical_stage.GetPrimAtPath("/World/Camera"))
        self.assertEqual(str(UsdGeom.GetStageUpAxis(canonical_stage)),"Z")
        self.assertAlmostEqual(
            float(lens.GetFocalLengthAttr().Get(Usd.TimeCode(float(T))))*100,
            60,places=3)
        take=self.index.read_revision(self.pid,"take",1)
        self.assertTrue(take["data"]["frozen"])

    def test_native_usd_mesh_topology_is_not_replaced_with_a_cube(self):
        from pxr import Gf
        stage=Usd.Stage.CreateInMemory()
        shape=UsdGeom.Mesh.Define(stage,"/World/TriangleAndQuad")
        shape.GetPointsAttr().Set([
            Gf.Vec3f(0,0,0),Gf.Vec3f(1,0,0),
            Gf.Vec3f(1,1,0),Gf.Vec3f(0,1,0)])
        shape.GetFaceVertexCountsAttr().Set([4])
        shape.GetFaceVertexIndicesAttr().Set([0,1,2,3])
        geom=_mesh(shape.GetPrim(),UsdGeom,Usd.TimeCode.Default())
        self.assertEqual(geom["kind"],"mesh")
        self.assertEqual(geom["triangles"],[[0,1,2],[0,2,3]])
        shape.GetFaceVertexIndicesAttr().Set([0,1,2,9])
        with self.assertRaises(RuntimeError):
            _mesh(shape.GetPrim(),UsdGeom,Usd.TimeCode.Default())

    def test_metadata_only_camera_list_keeps_openusd_scene_unloaded(self):
        with patch.object(OpenUSDSceneBridge,"open",
                          side_effect=AssertionError("Camera list loaded USD")):
            result=self.host.source_camera_choices(
                self.pid,"cut",1,film_tick=0)
        self.assertEqual(result["status"],"SOURCE_CAMERA_CHOICES")
        self.assertEqual(result["cameras"],[
            {"path":"/World/Camera","label":"Camera"}])
        self.assertFalse(result["usd_loaded"])
        self.assertFalse(result["picture_generated"])

    def test_high_fidelity_cache_identity_differs_from_blocking_and_lens(self):
        ticket=self.ticket()
        native=preview_cache_key(ticket,"thumbnail",camera_path="/World/Camera")
        blocking=blocking_key(ticket,"thumbnail")
        self.assertNotEqual(native,blocking)
        self.assertEqual(native,preview_cache_key(
            ticket,"thumbnail",camera_path="/World/Camera"))
        self.assertNotEqual(native,preview_cache_key(
            ticket,"interactive",camera_path="/World/Camera"))
        self.assertNotEqual(native,preview_cache_key(ticket,"thumbnail"))
        self.assertIn('scene.render.engine="CYCLES"',BLENDER_SCRIPT)

    def test_native_host_approval_and_distinct_geometry_worker_script(self):
        saved=self.index.read_revision(self.pid,"take",1)["document_sha256"]
        with self.assertRaises(PermissionError):
            self.host.request(
                self.pid,"cut",1,film_tick=0,quality="thumbnail",
                presentation="geometry",camera_path="/World/Camera",
                creator_event={"clicked":True})
        req=self.request(camera_path="/World/Camera")
        self.assertEqual(req["presentation"],"geometry")
        self.assertEqual(req["status"],"QUEUED")
        self.assertFalse(req["native_worker_started"])
        with self.activity._db() as db:
            row=db.execute("""SELECT approval_id,spec_sha256,presentation,
                camera_path FROM nvp_slate_preview_consents WHERE task_id=?""",
                (req["task_id"],)).fetchone()
        self.assertEqual(row[2:4],("geometry","/World/Camera"))
        verified=self.host.dispatcher.bindings.verified_spec(
            req["task_id"],owner_key=self.host.dispatcher.owner_key,
            require_active=False)
        self.assertEqual(verified["operation"]["outputs"],{"preview.png":"png"})
        self.assertEqual(
            self.index.read_revision(self.pid,"take",1)["document_sha256"],saved)
        self.assertTrue(self.host._approval_check(
            row[0],row[1],verified))

    def test_verified_geometry_cache_reused_without_reopening_usd(self):
        req=self.request(camera_path="/World/Camera")
        cached=self._publish_test_receipt(req)
        self.assertEqual((cached["width"],cached["height"]),(320,180))
        with patch("backend.nvp_slate06_geometry.capture_geometry",
                   side_effect=AssertionError("Cache hit reopened USD")):
            reused=self.request(camera_path="/World/Camera")
        self.assertEqual(reused["status"],"CACHE_HIT")
        self.assertEqual(reused["cache_key"],req["cache_key"])
        delivered=self.host.read_preview_png(self.pid,req["cache_key"])
        self.assertEqual(delivered["presentation"],"geometry")
        self.assertTrue(delivered["authored_geometry_preview_only"])
        self.assertEqual(delivered["segment_id"],"angle_part")
        self.assertEqual(delivered["edit_document_sha256"],
                         self.index.read_revision(self.pid,"cut",1)[
                             "document_sha256"])
        self.assertEqual(delivered["source_tick"],T)
        self.assertEqual(delivered["unmeshed_actors"],[])
        self.assertEqual(delivered["skeletal_rig_count"],0)
        self.assertFalse(delivered["lowfi_proxy_only"])
        self.assertFalse(delivered["skinned_actor_performance_rendered"])
        self.assertFalse(delivered["full_film_frame_approved"])

    def test_only_trusted_authored_camera_can_be_selected(self):
        ticket=self.ticket()
        with self.assertRaises(ValueError):
            capture_geometry(self.index,ticket,camera_path="/World/NotACamera")
        with self.assertRaises(ValueError):
            self.request(camera_path="/World/NotACamera")
        with self.assertRaises(ValueError):
            self.host.request(
                self.pid,"cut",1,film_tick=0,quality="thumbnail",
                presentation="blocking",camera_path="/World/Camera",
                creator_event=self.trusted_event)

    def test_cancellation_does_not_change_source_or_accept_partial_png(self):
        req=self.request(camera_path="/World/Camera")
        cancelled=self.host.cancel(
            req["job_id"],creator_event=self.trusted_event)
        self.assertEqual(cancelled["state"],"CANCELLED_QUEUED")
        self.assertIsNone(self.cache.lookup(self.pid,req["cache_key"]))
        self.assertEqual(self.activity.get_task(req["task_id"])["state"],
                         "CANCELLED")

    def test_actual_contained_blender_geometry_png_if_native_binary_configured(self):
        executable=os.environ.get("NVP_NATIVE_BLENDER_EXECUTABLE")
        if not executable:
            self.skipTest("Real Blender binary not configured for this runner")
        blender=Path(executable).resolve()
        if not blender.is_file():
            self.skipTest("No installed native Blender binary")
        version=subprocess.run(
            [str(blender),"-b","--version"],capture_output=True,text=True,
            check=True,timeout=30).stdout.splitlines()[0]
        native_activity=TaskLedger(
            Path(self.tmp.name)/"actual_activity",sampler=collect_resources)
        native_supervisor=BlenderWorkerSupervisor(
            Path(self.tmp.name)/"actual_worker",
            blender_executable=blender,blender_sha256=sha_file(blender),
            blender_version=version,activity_ledger=native_activity)
        native_cache=SlatePreviewCache(Path(self.tmp.name)/"actual_cache")
        native_host=NativeSlatePreviewHost(
            self.index,native_supervisor,native_activity,native_cache,
            verify_creator_action=lambda event,ctx:
                event is self.trusted_event and
                ctx["operation"]=="nvp.slate.authorize_openusd_geometry_preview.v1")
        req=native_host.request(
            self.pid,"cut",1,film_tick=0,quality="thumbnail",
            creator_event=self.trusted_event,presentation="geometry",
            camera_path="/World/Camera",ram_mb=4096,timeout_seconds=240)
        result=native_host.run_next()
        self.assertEqual(result["state"],"SUCCEEDED",result)
        image=native_host.read_preview_png(self.pid,req["cache_key"])
        self.assertTrue(image["authored_geometry_preview_only"])
        self.assertEqual((image["width"],image["height"]),(320,180))
        self.assertGreater(len(image["png_bytes"]),100)
        self.assertFalse(image["full_film_frame_approved"])


if __name__=="__main__":
    unittest.main()
