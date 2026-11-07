"""WO2 real UsdGeom materialBind subsets and source raster fidelity."""
import unittest
from pxr import Usd,UsdGeom,UsdShade

import test_nvp_openusd_reusable_assets as fixture
from backend.nvp_data_av_visual import visual_state
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_native_scene_linear_raster import NativeSceneLinearRaster


POINTS=[[-1.,-1.,0.],[1.,-1.,0.],
        [1.,1.,0.],[-1.,1.,0.]]
FACES=[[0,1,2],[0,2,3]]
UV=[[[0,0],[1,0],[1,1]],[[0,0],[1,1],[0,1]]]
BASE={"base_color_rgb":[1.,1.,1.],"roughness":.6,"metallic":0.}
RED={"faces":[0],"base_color_rgb":[1.,0.,0.],
     "roughness":.2,"metallic":0.}
BLUE={"faces":[1],"base_color_rgb":[0.,0.,1.],
      "roughness":.8,"metallic":0.}


class WO2NativeMaterialSubsets(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)

    def publish(self,slots,expected_revision=0):
        return self.assets.publish(
            self.pid,"multi_material",shape="mesh",size_m=2.,
            points=POINTS,triangles=FACES,face_uvs=UV,
            preview_material=BASE,material_slots=slots,
            expected_revision=expected_revision)

    def test_original_usd_subsets_and_live_scene_are_not_fake_colors(self):
        first=self.publish([RED,BLUE])
        record,layer=self.assets.open(self.pid,"multi_material",1)
        stage=Usd.Stage.Open(layer)
        for i,color in enumerate(([1.,0.,0.],[0.,0.,1.])):
            subset=UsdGeom.Subset(stage.GetPrimAtPath(
                "/Asset/Geometry/MaterialSlot"+str(i)))
            self.assertEqual(subset.GetFamilyNameAttr().Get(),"materialBind")
            self.assertEqual(list(subset.GetIndicesAttr().Get()),[i])
            bound,_=UsdShade.MaterialBindingAPI(
                subset.GetPrim()).ComputeBoundMaterial()
            self.assertEqual(str(bound.GetPath()),
                             "/Asset/Materials/Slot"+str(i))
            shader=UsdShade.Shader(stage.GetPrimAtPath(
                "/Asset/Materials/Slot"+str(i)+"/PreviewSurface"))
            actual=shader.GetInput("diffuseColor").GetAttr().Get()
            self.assertEqual([float(x) for x in actual],color)
        self.scene.publish(
            self.pid,"multi_scene",
            prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/Light","role":"light","position":[1,2,3]},
            ],curves=[],native_schemas=True,asset_bindings=[{
                "path":"/World/Actor","asset_id":"multi_material",
                "asset_revision":1}])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"multi_shots",scene_id="multi_scene",
            scene_revision=1,duration_tick=str(fixture.T),shots=[{
                "shot_id":"ShotA","camera_path":"/World/Camera",
                "start_tick":"0","end_tick":str(fixture.T),
                "pattern":"continuous"}])
        take=self.takes.freeze(
            self.pid,"multi_take",scene_id="multi_scene",scene_revision=1,
            timeline_id="multi_shots",timeline_revision=1,
            sample_ticks=[0],creator_event="director_confirms")
        snapshot=self.state.evaluate(
            self.pid,"multi_scene",1,"multi_shots",1,tick=0)
        view=visual_state(self.index,self.pid,snapshot)
        actor=next(x for x in view["objects"] if x["path"]=="/World/Actor")
        self.assertEqual([slot["faces"] for slot in
                          actor["source_material_slots"]],[[0],[1]])
        pixels,receipt=NativeSceneLinearRaster(self.index).render(
            self.pid,"multi_take",take["document_sha256"],
            tick=0,camera_path="/World/Camera")
        self.assertGreater(receipt["rasterized_triangles"],0)
        self.assertGreater(float(pixels[:,:,0].max()),0.)
        self.assertGreater(float(pixels[:,:,2].max()),0.)
        self.assertEqual(self.index.read_revision(
            self.pid,"multi_material",1)["document_sha256"],
            first["document_sha256"])
        self.publish([BLUE,RED],expected_revision=1)
        old=self.assets.open(self.pid,"multi_material",1)[0]
        self.assertEqual(old["document_sha256"],first["document_sha256"])
        self.assertEqual(self.takes.verify_take(
            self.pid,"multi_take")["status"],"VERIFIED_FROZEN_DATA_TAKE")

    def test_reject_overlaps_and_bad_scalar_or_face_indices(self):
        for slots in (
            [RED,RED],[{**RED,"faces":[2]}],
            [{**RED,"metallic":2}],
            [{**RED,"base_color_rgb":[1,float("nan"),0]}],
            [{**RED,"unsafe_shader_path":"file:///tmp"}],
        ):
            with self.subTest(slots=slots):
                with self.assertRaises(ValueError):
                    self.publish(slots)
        with self.assertRaises(ValueError):
            self.assets.publish(
                self.pid,"bad_material_sphere",shape="sphere",size_m=1.,
                material_slots=[RED])


if __name__=="__main__":
    unittest.main()
