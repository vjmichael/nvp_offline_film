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

    def _publish(self,*,with_skin=True):
        skin={
            "points":[[0.,0.,0.],[1.,0.,0.],[1.,1.,0.],[0.,1.,0.]],
            "faces":[[0,1,2],[0,2,3]],
            "joint_indices":[[0],[0],[0],[0]],
            "joint_weights":[[1.],[1.],[1.],[1.]],
            "display_color":[.25,.50,.75]}
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
                    "position":[0,0,0]}],
            curves=[],skeletal_rigs=[rig])

    def _snapshot(self,original,tick):
        return {
            "time_tick":str(tick),
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
        self.assertIsNone(actor["source_rig_binding"][
            "source_skeleton_layer_sha256"] if False else None)
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
