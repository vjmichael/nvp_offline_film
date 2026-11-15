"""CONV-01/06: genuine source-authoritative skinned actor live DataAV audition.

Uses the REAL pxr USD skeleton/mesh, FilmIndex source revision and evaluator.
No fake renderer, model-generated actor or original film-master approval.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_data_av_visual import visual_state
from backend.nvp_temporal_ledger import TICKS_PER_SECOND


class OriginalNativeSkinnedActorPreview(unittest.TestCase):
    def setUp(self):
        work=tempfile.TemporaryDirectory(prefix="nvp-original-live-usdskin-")
        self.addCleanup(work.cleanup)
        studio=Studio(Path(work.name)/"studio.sqlite")
        self.pid=studio.create_project(
            "Original Actor USD Skin Audition",
            "No renderer, no inferred character geometry")["id"]
        self.index=FilmIndex(studio)
        self.scenes=OpenUSDSceneBridge(self.index)

    def _publish(self,*,with_skin=True,with_material=False):
        skin={
            "points":[[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]],
            "faces":[[0,1,2],[0,2,3]],
            "joint_indices":[[0],[0],[0],[0]],
            "joint_weights":[[1.],[1.],[1.],[1.]],
            "display_color":[.25,.50,.75]}
        if with_material:
            # Artist-authored original USD PBR input, not renderer fallback.
            skin["roughness"]=.42
        rig={
            "path":"/World/Actor",
            "joints":["Root"],
            "samples":[
                {"tick":0,"translations":[[0.,0.,0.]]},
                {"tick":TICKS_PER_SECOND,
                 "translations":[[1.,0.,0.]]}]}
        if with_skin:
            rig["skin"]=skin
        return self.scenes.publish(
            self.pid,"OriginalUsdActor" if with_skin else "UnmeshedActor",
            prims=[{"path":"/World/Actor","role":"actor",
                    "position":[0,0,0]},
                   {"path":"/World/Camera","role":"camera",
                    "position":[0,0,5]}],
            curves=[],native_schemas=True,skeletal_rigs=[rig])

    def _snapshot(self,original,tick):
        return {
            "time_tick":tick,
            "scene_document_sha256":original["document_sha256"],
            "timeline_document_sha256":"b"*64,
            "objects":[{
                "path":"/World/Actor","semantic_role":"actor",
                "world_matrix":[[1.,0.,0.,0.],[0.,1.,0.,0.],
                                [0.,0.,1.,0.],[0.,0.,0.,1.]],
                "world_translation":[0.,0.,0.],
                "asset":None}]}

    def test_actual_joint_time_motion_only_from_reopened_usd_layer(self):
        record=self._publish()
        self.assertEqual(record["revision"],1)
        first=self._snapshot(record,0)
        start=visual_state(self.index,self.pid,first,
            scene_id="OriginalUsdActor",scene_revision=1)
        actor=start["objects"][0]
        self.assertEqual(actor["shape"],"skinned_mesh")
        self.assertEqual(actor["mesh_triangles"],[[0,1,2],[0,2,3]])
        self.assertEqual(actor["source_color_rgb"],[.25,.50,.75])
        self.assertEqual(len(actor["mesh_points"]),4)
        self.assertTrue(actor["source_skinning_authorized"])
        self.assertEqual(actor["source_skinning_tick"],"0")
        self.assertEqual(actor["original_blend_shape_count"],0)
        self.assertEqual(
            len(actor["source_rig_binding"]["source_skeleton_layer_sha256"]),64)
        self.assertFalse(start["image_samples_rendered"])
        self.assertFalse(start["frame_grid_authority"])
        self.assertFalse(start["source_modified"])
        # Real joint animation from original USD, not an interpolated proxy.
        later=visual_state(self.index,self.pid,
            self._snapshot(record,TICKS_PER_SECOND),
            scene_id="OriginalUsdActor",scene_revision=1)
        shifted=later["objects"][0]["mesh_points"]
        original=actor["mesh_points"]
        self.assertNotEqual(shifted,original)
        self.assertEqual(len(shifted),len(original))
        for a,b in zip(shifted,original):
            self.assertAlmostEqual(a[0]-b[0],1.,places=4)

    def test_real_original_usd_joint_pose_baked_into_one_protected_cycles_source(self):
        # This proves the real exact-time USD DATA handed to the current
        # protected Blender supervisor, NOT a completed Cycles render.
        from pxr import Sdf,Usd,UsdGeom,UsdSkel
        from backend.nvp_openusd_take import OpenUSDTakeCapture
        from backend.nvp_temporal_ledger import TemporalLedger
        from backend.nvp_int02_cycles_renderer import static_composed_usd
        scene=self._publish(with_material=True)
        timeline=TemporalLedger(self.index).publish(
            self.pid,"OriginalSkinEvents",[
                {"event_id":"OriginalActorMoves","event_kind":"action",
                 "subject_id":"Actor","start_tick":0,
                 "end_tick":TICKS_PER_SECOND,
                 "source_id":"OriginalUsdActor","source_revision":1,
                 "payload":{"usd_prim_path":"/World/Actor"}}],
            duration_tick=2*TICKS_PER_SECOND)
        take=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
                event=="NATIVE_SOURCE_TEST" and
                scope.get("operation")=="nvp.freeze.usd_temporal_take.v1"
        ).freeze(self.pid,"OriginalSkinTake",
            scene_id="OriginalUsdActor",scene_revision=1,
            timeline_id="OriginalSkinEvents",timeline_revision=1,
            sample_ticks=[0,TICKS_PER_SECOND],
            creator_event="NATIVE_SOURCE_TEST")
        self.assertEqual(scene["revision"],1)
        self.assertEqual(timeline["revision"],1)
        points=[]
        for tick in (0,TICKS_PER_SECOND):
            layer_bytes,params,materials=static_composed_usd(
                self.index,self.pid,"OriginalSkinTake",
                take["document_sha256"],tick,
                camera_path="/World/Camera")
            self.assertGreater(len(layer_bytes),100)
            self.assertEqual(round(params["camera_focal_length_mm"]),50)
            self.assertEqual(materials,[{
                "prim_path":"/World/Actor/Rig/CharacterMesh",
                "material_path":"/World/Actor/Rig/OriginalArtistMaterial",
                "shader_path":"/World/Actor/Rig/OriginalArtistMaterial/PreviewSurface",
                "linear_diffuse_rgb":[.25,.50,.75],
                "roughness":.42,
            }])
            flat=Sdf.Layer.CreateAnonymous("real_original_skin_source.usda")
            self.assertTrue(flat.ImportFromString(layer_bytes.decode("utf8")))
            stage=Usd.Stage.Open(flat)
            prim=stage.GetPrimAtPath("/World/Actor/Rig/CharacterMesh")
            self.assertTrue(prim and prim.IsA(UsdGeom.Mesh))
            self.assertFalse(prim.HasAPI(UsdSkel.BindingAPI))
            self.assertFalse(prim.GetProperty("skel:skeleton"))
            self.assertFalse(UsdGeom.Mesh(prim).GetPointsAttr().GetTimeSamples())
            points.append([[float(x) for x in value]
                           for value in UsdGeom.Mesh(prim).GetPointsAttr().Get()])
        self.assertNotEqual(points[0],points[1])
        for at_start,at_end in zip(*points):
            self.assertAlmostEqual(at_end[0]-at_start[0],1.,places=4)
        with self.assertRaises(RuntimeError):
            static_composed_usd(
                self.index,self.pid,"OriginalSkinTake","f"*64,0,
                camera_path="/World/Camera")

    def test_unbound_original_artist_skin_still_refuses_invented_cycles_material(self):
        # A source display-color preview is NOT a native shaded material.
        self._publish()
        _,stage=self.scenes.open(self.pid,"OriginalUsdActor",1)
        from backend.nvp_int02_usd_materials import source_preview_materials
        with self.assertRaisesRegex(
                RuntimeError,"cannot invent an unbound source material"):
            source_preview_materials(stage,0)

    def test_invalid_artist_roughness_is_refused_before_usd_authoring(self):
        from backend.nvp_openusd_skinning import normalize_skin
        original={
            "points":[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],
            "faces":[[0,1,2]],
            "joint_indices":[[0],[0],[0]],
            "joint_weights":[[1.],[1.],[1.]],
            "display_color":[.25,.50,.75],
        }
        for invalid in (None,True,"0.42",float("nan"),-0.1,1.1):
            with self.subTest(roughness=invalid):
                with self.assertRaises(ValueError):
                    normalize_skin({**original,"roughness":invalid},1)
        # GLB provenance still requires an independently authored roughness.
        with self.assertRaises(ValueError):
            normalize_skin({**original,"source_glb_sha256":"a"*64},1)

    def test_forged_original_scene_or_implicit_skin_authority_is_refused(self):
        record=self._publish()
        snap=self._snapshot(record,0)
        with self.assertRaises(PermissionError):
            visual_state(self.index,self.pid,snap,
                scene_id="OriginalUsdActor")
        unsafe={**snap,"scene_document_sha256":"f"*64}
        with self.assertRaises(RuntimeError):
            visual_state(self.index,self.pid,unsafe,
                scene_id="OriginalUsdActor",scene_revision=1)
        replaced={**snap,"objects":[{
            **snap["objects"][0],"asset":{
                "asset_id":"FakeGeometry","asset_revision":1}}]}
        with self.assertRaises(RuntimeError):
            visual_state(self.index,self.pid,replaced,
                scene_id="OriginalUsdActor",scene_revision=1)
        # Data without a native-approved Take scene pair cannot become an
        # authentic dynamic face or skin evaluation by mere browser input.
        no_source=visual_state(self.index,self.pid,snap)
        self.assertEqual(no_source["objects"][0]["shape"],"gizmo")
        self.assertFalse(no_source["objects"][0]["source_skinning_authorized"])

    def test_unmeshed_original_actor_never_becomes_fake_character_geometry(self):
        record=self._publish(with_skin=False)
        state=visual_state(self.index,self.pid,
            self._snapshot(record,0),
            scene_id="UnmeshedActor",scene_revision=1)
        actor=state["objects"][0]
        self.assertEqual(actor["shape"],"missing_rig_geometry")
        self.assertEqual(actor["native_geometry_status"],"MISSING_BOUND_USD_MESH")
        self.assertIsNone(actor["mesh_points"])
        self.assertFalse(actor["source_skinning_authorized"])
        self.assertFalse(actor["facial_animation_evaluated"])


if __name__=="__main__":
    unittest.main()
