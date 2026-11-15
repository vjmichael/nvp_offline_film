"""CONV-04/10 original camera lifecycle: source truth vs optional framing.

Real OpenUSD scene authoring and original performance tests. Camera-free
scene/Takes are permitted; a visual editing package must have an explicitly
chosen source perspective. Do not synthesize a renderer camera.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import unittest

from pxr import Sdf, Usd, UsdGeom

from backend.nvp_g05_scene_authoring import (
    FORMAT, _validate, _build_usd, _reopen_usd)
from backend.nvp_g06_filming import _author_performance
from backend.nvp_g07_edit import _presentation_camera
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T


class OriginalCameraLifecycle(unittest.TestCase):
    def setUp(self):
        self.handoff={
            "project_id":"OriginalCameraProject",
            "scene_id":"OriginalCameraScene",
            "scene_source_sha256":"a"*64,
            "script_revision":1,
            "director_notes_revision":1,
            "cast":[],
        }
        self.source={
            "project_id":self.handoff["project_id"],
            "scene_id":self.handoff["scene_id"],
            "scene_sha256":self.handoff["scene_source_sha256"],
            "script_revision":1,
            "notes_revision":1,
        }
        self.prop={
            "id":"O_0123456789ab","name":"Original stage prop",
            "role":"prop","shape":"box",
            "position":[1.,2.,.5],"rotation":[0.,0.,0.],
            "scale":[1.,1.,1.],"color":"#aabbcc","actor_id":None,
            "preset":"box","director_note":"","wardrobe_note":"",
        }
        self.camera={
            "id":"O_abcdef012345","name":"Director-authored perspective",
            "role":"camera","shape":"camera",
            "position":[3.,-4.,5.],"rotation":[0.,0.,0.],
            "scale":[.65,.65,.65],"color":"#68b8d3","actor_id":None,
            "preset":"camera","director_note":"","wardrobe_note":"",
        }

    def _scene(self,objects):
        return {
            "format":FORMAT,
            "source":deepcopy(self.source),
            "setting":{"weather":"clear","daylight":"day"},
            "objects":deepcopy(objects),
            "contains_external_asset_paths":False,
            "worker_authorized":False,
            "take_created":False,
        }

    @staticmethod
    def _reopened_stage(data):
        layer=Sdf.Layer.CreateAnonymous("camera_lifecycle_reopen.usda")
        if not layer.ImportFromString(data.decode("utf8")):
            raise AssertionError("Original USD layer failed to independently reopen")
        return Usd.Stage.Open(layer,Usd.Stage.LoadNone)

    def test_camera_free_scene_is_genuine_original_usd(self):
        original=self._scene([self.prop])
        _validate(original,self.handoff)
        frozen,manifest=_build_usd(original)
        self.assertEqual(_reopen_usd(frozen,original),manifest)
        self.assertEqual(len(manifest),1)
        stage=self._reopened_stage(frozen)
        self.assertTrue(stage.GetPrimAtPath("/World").IsDefined())
        self.assertFalse(stage.GetPrimAtPath(
            "/World/Objects/"+self.camera["id"]).IsDefined())
        self.assertFalse(any(p.IsA(UsdGeom.Camera)
            for p in Usd.PrimRange(stage.GetPseudoRoot())))
        original_sha=sha256(frozen).hexdigest()
        performance=_author_performance(
            frozen,original,{"duration_tick":30*T,"events":[]})
        recorded=self._reopened_stage(performance)
        self.assertEqual(recorded.GetPrimAtPath("/World").GetAttribute(
            "nvp:frozenSourceSceneSha256").Get(),original_sha)
        self.assertEqual(sha256(frozen).hexdigest(),original_sha)

    def test_camera_can_be_added_then_removed_without_touching_past_source(self):
        original=self._scene([self.prop])
        base,_=_build_usd(original)
        base_sha=sha256(base).hexdigest()
        framed=self._scene([self.prop,self.camera])
        _validate(framed,self.handoff)
        with_camera,manifest=_build_usd(framed)
        stage=self._reopened_stage(with_camera)
        camera_path="/World/Objects/"+self.camera["id"]+"/Geometry"
        self.assertTrue(stage.GetPrimAtPath(camera_path).IsA(UsdGeom.Camera))
        self.assertEqual(len(manifest),2)
        _validate(original,self.handoff)
        after,_=_build_usd(original)
        self.assertFalse(self._reopened_stage(after).GetPrimAtPath(
            camera_path).IsDefined())
        self.assertEqual(sha256(base).hexdigest(),base_sha)
        self.assertNotEqual(sha256(with_camera).hexdigest(),base_sha)

    def test_removing_last_object_still_preserves_world_source(self):
        empty=self._scene([])
        _validate(empty,self.handoff)
        data,manifest=_build_usd(empty)
        self.assertEqual(manifest,[])
        self.assertTrue(self._reopened_stage(data).GetPrimAtPath(
            "/World").IsDefined())

    def test_camera_limits_and_source_identity_remain_fail_closed(self):
        many=self._scene([{**self.camera,"id":"O_"+format(i,"012x")}
            for i in range(9)])
        with self.assertRaises(ValueError):
            _validate(many,self.handoff)
        forged=self._scene([self.prop])
        forged["source"]["scene_sha256"]="b"*64
        with self.assertRaises(RuntimeError):
            _validate(forged,self.handoff)
        disguised=self._scene([{**self.prop,"role":"camera"}])
        with self.assertRaises(ValueError):
            _validate(disguised,self.handoff)

    def test_visual_package_requires_camera_after_camera_free_take(self):
        class CameraStore:
            def __init__(self,revision,views):
                self.doc={"revision":revision,"views":views}
            def _camera(self,db,pid,take_id):
                return self.doc
        suggested={
            "name":"Wide","position":[5.,-8.,4.],
            "look_at":[0.,0.,1.],"focal_mm":24.,
        }
        source={"stage_objects":[self.prop]}
        with self.assertRaisesRegex(PermissionError,"explicitly saved camera"):
            _presentation_camera(
                CameraStore(0,[suggested]),None,"project","take",source)
        chosen=_presentation_camera(
            CameraStore(1,[suggested]),None,"project","take",source)
        self.assertEqual(chosen["name"],"Wide")
        with self.assertRaisesRegex(PermissionError,"No director camera"):
            _presentation_camera(
                CameraStore(1,[]),None,"project","take",source)
        legacy=_presentation_camera(
            CameraStore(0,[suggested]),None,"project","take",
            {"stage_objects":[self.camera]})
        self.assertEqual(legacy["focal_mm"],24.)


if __name__=="__main__":
    unittest.main()
