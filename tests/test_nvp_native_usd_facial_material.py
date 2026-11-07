"""DA-04C: genuine USD BlendShape/UsdSkel Animation and PreviewSurface.

Checks the original typed native USD scene at two exact Film Time instants.
No fabricated actor avatars, 2D frame samples or Blender execution.
"""
from copy import deepcopy
import unittest

from pxr import Usd,UsdSkel,UsdShade

import test_nvp_slate07_skinned_camera as fixture
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_data_av_visual import visual_state
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T


class NativeOriginalFaceAndMaterial(unittest.TestCase):
    def setUp(self):
        fixture.RealCharacterAndLens.setUp(self)
        self.rig=deepcopy(self.rigs[0])
        offsets=[[0.,0.,0.] for _ in self.skin["points"]]
        offsets[4]=[0.,0.5,0.]
        self.rig["skin"]["blend_shapes"]=[
            {"name":"Smile","offsets":offsets}]
        self.rig["skin"]["preview_material"]={
            "roughness":0.37,"metallic":0.12}
        self.rig["samples"][0]["face_weights"]={"Smile":0.}
        self.rig["samples"][1]["face_weights"]={"Smile":1.}

    def _publish(self):
        self.scene.publish(
            self.pid,"face_world",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,8]},
                {"path":"/World/Key","role":"light","position":[0,5,5]},
            ],curves=[],skeletal_rigs=[self.rig])
        return self.index.read_revision(self.pid,"face_world",1)

    def test_real_original_blendshape_and_usd_pbr_material_move_skin(self):
        record=self._publish()
        source_sha=record["document_sha256"]
        _,stage=self.scene.open(self.pid,"face_world",1)
        shape=UsdSkel.BlendShape(stage.GetPrimAtPath(
            "/World/Actor/Rig/CharacterMesh/Blend_Smile"))
        self.assertTrue(shape)
        self.assertEqual(len(shape.GetOffsetsAttr().Get()),8)
        shader=UsdShade.Shader(stage.GetPrimAtPath(
            "/World/Actor/Rig/Material/PreviewSurface"))
        self.assertEqual(shader.GetIdAttr().Get(),"UsdPreviewSurface")
        self.assertAlmostEqual(shader.GetInput("roughness").Get(),.37,places=5)
        self.assertAlmostEqual(shader.GetInput("metallic").Get(),.12,places=5)
        animation=UsdSkel.Animation(stage.GetPrimAtPath(
            "/World/Actor/Rig/Skeleton/Animation"))
        weights=animation.GetBlendShapeWeightsAttr().Get(
            Usd.TimeCode(float(T)))
        self.assertAlmostEqual(float(weights[0]),.5,places=4)
        state=OpenUSDTimeState(self.index)
        snap=state.evaluate(self.pid,"face_world",1,"acting",1,tick=T)
        live=visual_state(self.index,self.pid,snap,
            scene_id="face_world",scene_revision=1)
        actor=next(x for x in live["objects"] if x["path"]=="/World/Actor")
        self.assertEqual(actor["shape"],"skinned_mesh")
        self.assertTrue(actor["facial_animation_evaluated"])
        self.assertEqual(actor["original_blend_shape_count"],1)
        self.assertEqual(actor["source_material"]["format"],
                         "nvp.original_usd_preview_surface.v1")
        self.assertAlmostEqual(actor["source_material"]["roughness"],.37,places=5)
        self.assertAlmostEqual(actor["mesh_points"][4][1],.05,places=4)
        self.assertEqual(self.index.read_revision(
            self.pid,"face_world",1)["document_sha256"],source_sha)
        self.assertFalse(live["image_samples_rendered"])

    def test_facial_samples_and_source_material_cannot_fabricate_shapes(self):
        corrupt=deepcopy(self.rig)
        corrupt["samples"][0]["face_weights"]["Smile"]=2.
        with self.assertRaises(ValueError):
            self.scene.publish(self.pid,"bad_face",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            ],curves=[],skeletal_rigs=[corrupt])
        corrupt=deepcopy(self.rig)
        corrupt["skin"]["preview_material"]["roughness"]=float("inf")
        with self.assertRaises(ValueError):
            self.scene.publish(self.pid,"bad_material",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            ],curves=[],skeletal_rigs=[corrupt])


    def test_real_rig_uvs_survive_source_skinning_and_live_view(self):
        uv=[[float(i%2),float((i//2)%2)]
            for i in range(len(self.skin["points"]))]
        self.rig["skin"]["mesh_uvs"]=uv
        self._publish()
        from pxr import UsdGeom
        _,stage=self.scene.open(self.pid,"face_world",1)
        mesh=UsdGeom.Mesh(
            stage.GetPrimAtPath("/World/Actor/Rig/CharacterMesh"))
        st=UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
        self.assertEqual(st.GetInterpolation(),"vertex")
        self.assertEqual([[float(x) for x in pair] for pair in st.Get()],uv)
        state=OpenUSDTimeState(self.index)
        snap=state.evaluate(self.pid,"face_world",1,"acting",1,tick=T)
        live=visual_state(self.index,self.pid,snap,
            scene_id="face_world",scene_revision=1)
        actor=next(x for x in live["objects"] if
                   x["path"]=="/World/Actor")
        self.assertEqual(actor["shape"],"skinned_mesh")
        self.assertEqual(actor["mesh_uvs"],uv)
        self.assertFalse(live["source_modified"])

    def test_real_usd_rig_texture_is_sha_verified_and_not_a_placeholder(self):
        from io import BytesIO
        from PIL import Image
        from backend.nvp_native_usd_texture import publish_texture
        png_stream=BytesIO()
        Image.new("RGB",(2,2),(35,150,230)).save(png_stream,format="PNG")
        texture=publish_texture(self.index,self.pid,png_stream.getvalue())
        uv=[[float(i%2),float((i//2)%2)]
            for i in range(len(self.skin["points"]))]
        self.rig["skin"]["mesh_uvs"]=uv
        self.rig["skin"]["texture"]=texture
        self._publish()
        _,stage=self.scene.open(self.pid,"face_world",1)
        shader=UsdShade.Shader(stage.GetPrimAtPath(
            "/World/Actor/Rig/Material/Texture"))
        self.assertEqual(shader.GetIdAttr().Get(),"UsdUVTexture")
        self.assertEqual(str(shader.GetInput("file").Get().path),
                         texture["usd_asset_path"])
        snapshot=OpenUSDTimeState(self.index).evaluate(
            self.pid,"face_world",1,"acting",1,tick=T)
        live=visual_state(self.index,self.pid,snapshot,
            scene_id="face_world",scene_revision=1)
        actor=next(x for x in live["objects"] if
                   x["path"]=="/World/Actor")
        self.assertEqual(actor["shape"],"skinned_mesh")
        self.assertEqual(actor["mesh_uvs"],uv)
        self.assertEqual(actor["source_material"]["texture"]["sha256"],
                         texture["sha256"])
        self.assertTrue(actor["source_material"][
            "texture_transport"]["png_base64"].startswith("iVBORw0KGgo"))
        self.assertFalse(live["source_modified"])

    def test_unregistered_rig_texture_blob_cannot_be_published(self):
        from io import BytesIO
        from PIL import Image
        from backend.nvp_native_usd_texture import publish_texture
        buf=BytesIO()
        Image.new("RGB",(1,1),(255,255,255)).save(buf,format="PNG")
        desc=publish_texture(self.index,self.pid,buf.getvalue())
        self.rig["skin"]["mesh_uvs"]=[[0.,0.]
            for _ in self.skin["points"]]
        self.rig["skin"]["texture"]={
            **desc,"sha256":"0"*64,
            "usd_asset_path":"nvp-blob://texture/"+"0"*64}
        with self.assertRaises(KeyError):
            self._publish()

    def test_skinned_quad_facevarying_seams_trianguled_without_replacement(self):
        from pxr import UsdGeom
        from backend.nvp_openusd_time_state import OpenUSDTimeState
        uv=[]
        for i,face in enumerate(self.skin["faces"]):
            uv.append([[float(i)/10.,float(j)/10.]
                       for j in range(len(face))])
        self.rig["skin"]["face_uvs"]=uv
        self._publish()
        _,stage=self.scene.open(self.pid,"face_world",1)
        mesh=UsdGeom.Mesh(
            stage.GetPrimAtPath("/World/Actor/Rig/CharacterMesh"))
        st=UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
        self.assertEqual(st.GetInterpolation(),"faceVarying")
        snap=OpenUSDTimeState(self.index).evaluate(
            self.pid,"face_world",1,"acting",1,tick=T)
        state=visual_state(self.index,self.pid,snap,
            scene_id="face_world",scene_revision=1)
        actor=next(x for x in state["objects"]
                   if x["path"]=="/World/Actor")
        self.assertEqual(actor["shape"],"skinned_mesh")
        self.assertIsNone(actor["mesh_uvs"])
        self.assertEqual(len(actor["mesh_face_uvs"]),
                         len(actor["mesh_triangles"]))
        self.assertEqual(actor["mesh_face_uvs"][0],
                         [uv[0][0],uv[0][1],uv[0][2]])
        self.assertEqual(actor["mesh_face_uvs"][1],
                         [uv[0][0],uv[0][2],uv[0][3]])
        self.assertFalse(state["source_modified"])

    def test_reject_rig_uvs_that_do_not_match_original_vertices(self):
        self.rig["skin"]["mesh_uvs"]=[[0.,0.]]
        with self.assertRaises(ValueError):
            self.scene.publish(self.pid,"bad_actor_uvs",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            ],curves=[],skeletal_rigs=[self.rig])



if __name__=="__main__":
    unittest.main()
