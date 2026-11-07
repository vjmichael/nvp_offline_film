"""WO2: original USD mesh UV primvars are immutable, verified and viewable."""
import unittest
from pxr import UsdGeom
import test_nvp_openusd_reusable_assets as fixture

from backend.nvp_data_av_visual import visual_state


class NativeWO2MeshUVTests(fixture.NativeUSD02Integration):
    def test_real_st_primvar_and_revision_stable_live_view(self):
        pts=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]
        faces=[[0,1,2]]
        uv=[[0.,0.],[1.,0.],[0.,1.]]
        original=self.assets.publish(
            self.pid,"original_uv_mesh",shape="mesh",size_m=2.,
            points=pts,triangles=faces,mesh_uvs=uv)
        record,layer=self.assets.open(self.pid,"original_uv_mesh",1)
        from pxr import Sdf, Usd
        stage=Usd.Stage.Open(layer)
        mesh=UsdGeom.Mesh(stage.GetPrimAtPath("/Asset/Geometry"))
        st=UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
        self.assertEqual(st.GetInterpolation(),"vertex")
        self.assertEqual([[float(v) for v in p] for p in st.Get()],uv)
        self.assertEqual(record["data"]["mesh_uvs"],uv)
        self.scene.publish(
            self.pid,"scene_uv",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]}
            ],curves=[],asset_bindings=[
                {"path":"/World/Actor","asset_id":"original_uv_mesh",
                 "asset_revision":1}])
        state=self.state.evaluate(
            self.pid,"scene_uv",1,"event_timeline",1,tick=0)
        view=visual_state(self.index,self.pid,state)
        self.assertEqual(view["objects"][0]["mesh_uvs"],uv)
        self.assertFalse(view["source_modified"])
        self.assets.publish(
            self.pid,"original_uv_mesh",shape="mesh",size_m=2.,
            points=pts,triangles=faces,
            mesh_uvs=[[.25,.25],[.75,.25],[.25,.75]],
            expected_revision=1)
        prior,_=self.assets.open(self.pid,"original_uv_mesh",1)
        changed,_=self.assets.open(self.pid,"original_uv_mesh",2)
        self.assertEqual(prior["document_sha256"],original["document_sha256"])
        self.assertNotEqual(prior["document_sha256"],changed["document_sha256"])
        self.assertEqual(visual_state(self.index,self.pid,state)["objects"][0]["mesh_uvs"],uv)

    def test_reject_untrusted_or_non_mesh_uv(self):
        pts=[[0,0,0],[1,0,0],[0,1,0]]
        faces=[[0,1,2]]
        for invalid in (
            [[0,0]],[[0,0],[1,float("nan")],[0,1]],
            [[0,0],[1025,0],[0,1]],[[0,0],[1,0],["0",1]]
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.assets.publish(
                        self.pid,"reject_uv",shape="mesh",size_m=2,
                        points=pts,triangles=faces,mesh_uvs=invalid)
        with self.assertRaises(ValueError):
            self.assets.publish(
                self.pid,"reject_uv_sphere",shape="sphere",size_m=1,
                mesh_uvs=[[0,0]])


if __name__=="__main__":
    unittest.main()
