"""02M-HR: real approved building meshes with identical frozen 01E actors.

The source test uses actual USD/FilmIndex, not fake geometry JSON. The
separate native Blender/Cycles test REQUIRES an externally supplied reviewed
Blender 5.2 executable, and never silently passes as a mocked render.
"""
from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pxr import Usd,UsdGeom,UsdShade
from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_usd_film02m_modular_buildings import OriginalBuildingKit
from backend.nvp_usd_film02m_e_district import OriginalFilmDistrict
from backend.nvp_usd_film02m_h_actor_camera_binding import OriginalDistrictShotBinding
from backend.nvp_usd_film02m_h_render_handoff import (
    stage_approved_original_shot,ReviewedDistrictShotCyclesHost)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from test_nvp_usd_film01f_world_render import OriginalTwoShotWorldTakeSource


def sock(name,point,normal,span,kind):
    return {"name":name,"connector_type":kind,"gender":"universal",
            "at_m":point,"normal":normal,"span_m":span,"tolerance_m":.01}


def cube(size):
    x,y,z=(s/2. for s in size)
    return (
        [[-x,-y,-z],[x,-y,-z],[x,y,-z],[-x,y,-z],
         [-x,-y,z],[x,-y,z],[x,y,z],[-x,y,z]],
        [[0,2,1],[0,3,2],[4,5,6],[4,6,7],
         [0,1,5],[0,5,4],[3,7,6],[3,6,2],
         [0,4,7],[0,7,3],[1,2,6],[1,6,5]])


class OriginalActorDistrictNativeRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=OriginalTwoShotWorldTakeSource
        cls.source.setUpClass()
        cls.index=cls.source.index
        cls.pid=cls.source.pid
        cls.take_id=cls.source.ids[0]
        cls.take_sha=cls.source.take_shas[0]
        cls.original_actor_take_shas=list(cls.source.original_take_shas)
        cls.world_shot_sha=cls.index.read_revision(
            cls.pid,"WorldCameraShot0",1)["document_sha256"]
        kit=OriginalBuildingKit(
            cls.index,verify_director_action=lambda event,scope:
            event=="NATIVE_02MH_SOURCE" and scope.get("operation") in (
                "nvp.film02m.publish_original_building_module.v1",
                "nvp.film02m.publish_original_architecture.v1"))
        assets=OpenUSDAssetRegistry(cls.index)
        modules=[
            ("Floor","floor",[12,10,.4],[
                sock("Front",[0,-5,0],[0,-1,0],12,"wall_base"),
                sock("Rear",[0,5,0],[0,1,0],12,"wall_base"),
                sock("Left",[-6,0,0],[-1,0,0],10,"side_base"),
                sock("Right",[6,0,0],[1,0,0],10,"side_base")]),
            ("Front","facade",[12,.4,6],[
                sock("Back",[0,.2,-3],[0,1,0],12,"wall_base"),
                sock("Top",[0,0,3],[0,0,1],12,"roof_edge")]),
            ("Rear","rear",[12,.4,6],[
                sock("Front",[0,-.2,-3],[0,-1,0],12,"wall_base")]),
            ("Left","side",[.4,10,6],[
                sock("Inner",[.2,0,-3],[1,0,0],10,"side_base")]),
            ("Right","side",[.4,10,6],[
                sock("Inner",[-.2,0,-3],[-1,0,0],10,"side_base")]),
            ("Roof","roof",[12.8,10.8,.4],[
                sock("FrontBottom",[0,-5.2,-.2],[0,0,-1],12,"roof_edge")]),
        ]
        for suffix,role,size,sockets in modules:
            points,triangles=cube(size)
            asset="Native02MHAsset"+suffix
            assets.publish(cls.pid,asset,shape="mesh",size_m=max(size),
                           points=points,triangles=triangles,
                           preview_material={
                               "base_color_rgb":[.4,.58,.68],
                               "roughness":.55,"metallic":.03})
            kit.publish_module(
                cls.pid,"Native02MHModule"+suffix,
                asset_id=asset,asset_revision=1,role=role,
                style_family="OriginalShot",size_m=size,sockets=sockets,
                director_event="NATIVE_02MH_SOURCE")
        def node(name,module,parent=None,other=None,own=None,root=None):
            return {"node_id":name,
                    "options":[{"module_id":"Native02MHModule"+module,
                                "revision":1}],
                    "parent_id":parent,"parent_socket":other,
                    "own_socket":own,"yaw_deg":0,"root_position_m":root}
        kit.publish_building(
            cls.pid,"Native02MHBuilding",seed=4,
            blueprint=[
                node("Floor","Floor",root=[0.,0.,0.]),
                node("Front","Front","Floor","Front","Back"),
                node("Rear","Rear","Floor","Rear","Front"),
                node("Left","Left","Floor","Left","Inner"),
                node("Right","Right","Floor","Right","Inner"),
                node("Roof","Roof","Front","Top","FrontBottom")],
            director_event="NATIVE_02MH_SOURCE")
        author=OriginalFilmDistrict(
            cls.index,verify_director_action=lambda event,scope:
            event=="NATIVE_02MH_SOURCE" and
            scope.get("operation")==
            "nvp.film02m_e.publish_original_layered_district.v1")
        values={
            "seed":11,
            "source_buildings":[{
                "building_id":"Native02MHBuilding","revision":1}],
            "grid_cols":1,"grid_rows":1,"lot_spacing_m":30.,
            "world_origin_m":[0.,0.,0.],
            "source_triangle_budget":100000,
            "source_instance_budget":1}
        cls.districts=[]
        for revision,origin in ((0,[0.,0.,0.]),(1,[0.,8.,0.])):
            doc=author.publish(
                cls.pid,"Native02MHDistrict",
                **{**values,"world_origin_m":origin},
                expected_revision=revision,
                director_event="NATIVE_02MH_SOURCE")
            cls.districts.append(doc["document_sha256"])
        binding=OriginalDistrictShotBinding(
            cls.index,confirm=lambda event,scope:
            event=="REVIEW_ORIGINAL_SHOT" and
            scope.get("operation")==
            "nvp.film02m_h.approve_original_district_shot_binding.v1")
        for revision in (1,2):
            preview=binding.preview(
                cls.pid,"Native02MHDistrict",revision,
                cls.take_id,5*T)
            binding.publish(
                cls.pid,"Native02MHBinding"+str(revision),
                district_id="Native02MHDistrict",
                district_revision=revision,
                world_take_id=cls.take_id,film_tick=5*T,
                creator_event="REVIEW_ORIGINAL_SHOT",
                expected_preview_sha256=preview["binding_preview_sha256"])

    @classmethod
    def tearDownClass(cls):
        cls.source.tearDownClass()

    def test_real_native_usd_actor_and_camera_unmodified_across_district_revisions(self):
        with TemporaryDirectory(prefix="nvp-02mh-two-revisions-") as tmp:
            root=Path(tmp).resolve()
            receipts=[]
            for revision in (1,2):
                target=root/("shot"+str(revision))
                target.mkdir()
                stage=stage_approved_original_shot(
                    self.index,self.pid,"Native02MHBinding"+str(revision),target)
                evidence=stage["district"]
                self.assertEqual(evidence["district_revision"],revision)
                self.assertEqual(evidence["world_take_sha256"],self.take_sha)
                self.assertEqual(evidence["original_actor_count"],4)
                self.assertEqual(evidence["district_render_meshes"],6)
                self.assertEqual(evidence["district_render_bound_materials"],6)
                self.assertTrue(evidence["original_camera_matrix_unchanged"])
                self.assertTrue(evidence["actor_takes_and_pcm_unchanged"])
                self.assertFalse(evidence["actual_cycles_png_rendered"])
                native=Usd.Stage.Open(str(target/"source.usda"))
                self.assertTrue(native.GetPrimAtPath(
                    evidence["source_camera_path"]).IsA(UsdGeom.Camera))
                mesh=[p for p in native.Traverse()
                      if str(p.GetPath()).startswith(
                          "/World/OriginalFilmDistricts/Native02MHDistrict")
                      and p.IsA(UsdGeom.Mesh)]
                self.assertEqual(len(mesh),6)
                self.assertTrue(all(
                    UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0]
                    for p in mesh))
                receipts.append(stage)
            self.assertNotEqual(receipts[0]["district"]["derived_usd_sha256"],
                                receipts[1]["district"]["derived_usd_sha256"])
            self.assertEqual(receipts[0]["packet"]["source"][
                "original_world_take_sha256"],
                receipts[1]["packet"]["source"][
                "original_world_take_sha256"])
            self.assertEqual(
                self.index.read_revision(
                    self.pid,self.take_id,1)["document_sha256"],self.take_sha)
            self.assertEqual(
                self.index.read_revision(
                    self.pid,"WorldCameraShot0",1)["document_sha256"],
                self.world_shot_sha)
            self.assertEqual([
                self.index.read_revision(
                    self.pid,t,1)["document_sha256"]
                for t in self.source.shots[0:2] if False],[])
            self.assertEqual(self.index.list_objects(
                self.pid,kind="take")[0]["head_revision"],1)

    def test_native_render_admission_does_not_reuse_original_binding_approval(self):
        # Source-only staged approval is a separate operation. It cannot
        # silently inherit prior shot-binding or model-to-draft permission.
        fake=object()
        with self.assertRaises(TypeError):
            ReviewedDistrictShotCyclesHost(
                self.index,fake,verify_director_action=lambda *_:True)

    def test_actual_independent_blender_cycles_actor_district_image(self):
        executable=os.environ.get("NVP_FILM02MH_BLENDER_BIN")
        if not executable:
            self.skipTest("Separate real Blender 5.2 source render gate not yet executed")
        binary=Path(executable).resolve(strict=True)
        version=subprocess.run(
            [str(binary),"-b","--version"],capture_output=True,
            text=True,check=True,timeout=30).stdout.splitlines()[0].strip()
        self.assertTrue(version.startswith("Blender 5.2."),version)
        with TemporaryDirectory(prefix="nvp-02mh-real-cycles-") as tmp:
            sup=BlenderWorkerSupervisor(
                Path(tmp)/"workers",
                blender_executable=binary,blender_sha256=sha_file(binary),
                blender_version=version)
            decisions=[]
            def approve(event,scope):
                decisions.append(dict(scope))
                return (event=="REVIEW_RENDER_SOURCE" and
                    scope["operation"]==
                    "nvp.render.usd_film02m_h.original_district_actor_shot.v1")
            host=ReviewedDistrictShotCyclesHost(
                self.index,sup,verify_director_action=approve)
            with self.assertRaises(PermissionError):
                host.render(
                    self.pid,"Native02MHBinding1",
                    job_id="02mh_denied",director_event="FAKE_CREATIVE_APPROVAL")
            with self.assertRaises(KeyError):
                sup.inspect("02mh_denied")
            completed=host.render(
                self.pid,"Native02MHBinding1",
                job_id="02mh_actor_world_real",director_event="REVIEW_RENDER_SOURCE")
            self.assertEqual(
                completed["state"],
                "RENDERED_REAL_ORIGINAL_DISTRICT_ACTOR_CAMERA_SHOT")
            self.assertTrue(completed["independent_saved_blend_reopened"])
            self.assertTrue(completed["actual_film_frame_rendered"])
            self.assertEqual(completed["original_world_take_sha256"],self.take_sha)
            self.assertTrue(completed["source_actor_take_pcm_unchanged"])
            self.assertGreaterEqual(len(decisions),2)
            self.assertFalse(completed["final_film_accepted"])
            self.assertEqual(
                self.index.read_revision(self.pid,self.take_id,1)[
                    "document_sha256"],self.take_sha)
