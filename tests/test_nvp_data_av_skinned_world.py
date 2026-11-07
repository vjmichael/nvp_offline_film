"""DA-04B: real original UsdSkel actor, two exact Film Time GPU poses.

This is real pxr USD composition/evaluate_skin, not a fake character mesh
or screenshot comparison. Accepted native WebView2/GPU playback is separate.
"""
import unittest

from backend.nvp_data_av_visual import visual_state
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T

import test_nvp_slate07_skinned_camera as fixture


class RealNativeSkinnedWorld(unittest.TestCase):
    def setUp(self):
        fixture.RealCharacterAndLens.setUp(self)
        self.state=OpenUSDTimeState(self.index)

    def snapshot(self,tick):
        return self.state.evaluate(
            self.pid,"world",1,"acting",1,tick=tick)

    def test_real_skinned_actor_mesh_moves_at_exact_time(self):
        original=self.index.read_revision(self.pid,"world",1)
        at_zero=self.snapshot(0)
        at_one=self.snapshot(T)
        view0=visual_state(
            self.index,self.pid,at_zero,scene_id="world",scene_revision=1)
        view1=visual_state(
            self.index,self.pid,at_one,scene_id="world",scene_revision=1)
        actor0=next(o for o in view0["objects"]
                    if o["path"]=="/World/Actor")
        actor1=next(o for o in view1["objects"]
                    if o["path"]=="/World/Actor")
        self.assertEqual(actor0["shape"],"skinned_mesh")
        self.assertEqual(actor0["geometry_asset_sha256"],
                         original["data"]["skeleton_layer_sha256"])
        self.assertFalse(actor1["gizmo_only"])
        self.assertEqual(actor0["mesh_triangles"],actor1["mesh_triangles"])
        self.assertEqual(len(actor1["mesh_triangles"]),12)
        self.assertEqual(actor0["source_skinning_tick"],"0")
        self.assertEqual(actor1["source_skinning_tick"],str(T))
        for got,want in zip(actor1["source_color_rgb"],self.skin["display_color"]):
            self.assertAlmostEqual(got,want,places=6)
        self.assertAlmostEqual(actor0["mesh_points"][4][0],1.,places=4)
        self.assertAlmostEqual(actor1["mesh_points"][4][0],2.,places=4)
        self.assertEqual(
            self.index.read_revision(self.pid,"world",1)["document_sha256"],
            self.original_scene_sha)
        self.assertFalse(view1["image_samples_rendered"])

    def test_animated_usd_rig_without_bound_mesh_is_not_a_character_sphere(self):
        # A real authored skeleton without source skin geometry must not be
        # misrepresented as an actor body in the live Three.js viewport.
        bare={k:v for k,v in self.rigs[0].items() if k!="skin"}
        self.scene.publish(self.pid,"unbound_rig_scene",prims=[
            {"path":"/World/Actor","role":"actor","position":[0,0,0]},
            {"path":"/World/Camera","role":"camera","position":[0,0,8]},
            {"path":"/World/Key","role":"light","position":[0,5,5]},
        ],curves=[],skeletal_rigs=[bare])
        snapshot=self.state.evaluate(
            self.pid,"unbound_rig_scene",1,"acting",1,tick=T)
        view=visual_state(self.index,self.pid,snapshot,
                          scene_id="unbound_rig_scene",scene_revision=1)
        actor=next(o for o in view["objects"] if o["path"]=="/World/Actor")
        self.assertEqual(actor["shape"],"missing_rig_geometry")
        self.assertTrue(actor["source_rigged_actor"])
        self.assertFalse(actor["gizmo_only"])
        self.assertEqual(actor["native_geometry_status"],
                         "MISSING_BOUND_USD_MESH")
        self.assertIsNone(actor["mesh_points"])
        self.assertFalse(view["image_samples_rendered"])

    def test_live_skin_refuses_scene_rebind_and_missing_scope(self):
        snap=self.snapshot(T)
        with self.assertRaises(ValueError):
            visual_state(self.index,self.pid,snap,scene_id="world")
        with self.assertRaises(RuntimeError):
            visual_state(self.index,self.pid,
                         {**snap,"scene_document_sha256":"0"*64},
                         scene_id="world",scene_revision=1)
        before=visual_state(self.index,self.pid,snap)
        self.assertTrue(next(x for x in before["objects"] if
                             x["path"]=="/World/Actor")["gizmo_only"])
        self.assertEqual(self.index.read_revision(
            self.pid,"world",1)["document_sha256"],self.original_scene_sha)


if __name__=="__main__":
    unittest.main()
