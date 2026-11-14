"""CONV-06 installed-bridge boundary tests; not OS/physical acceptance."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


def fake_bridge(*, locked=False, url="http://127.0.0.1:19991/"):
    bridge = object.__new__(TrustedDesktopCameraBridge)
    bridge.origin = "http://127.0.0.1:19991"
    bridge.window = SimpleNamespace(
        get_current_url=lambda: url,
        create_confirmation_dialog=lambda title, text: True)
    bridge._project_lock_check = lambda: locked
    bridge._closing = False
    bridge.index = SimpleNamespace(
        studio=SimpleNamespace(get_project=lambda pid: {"id": pid}))
    return bridge


class ConvergedDirectorDesktopTests(unittest.TestCase):
    def test_protected_project_denies_both_recovered_families(self):
        bridge = fake_bridge(locked=True)
        with self.assertRaisesRegex(PermissionError, "protected"):
            bridge.camfx03_draft_catalog("movie001")
        with self.assertRaisesRegex(PermissionError, "protected"):
            bridge.film03_actor_catalog("movie001")
        with self.assertRaisesRegex(PermissionError, "protected"):
            bridge.film03_actor_profile_publish({})

    def test_foreign_window_denies_actor_and_camera_methods(self):
        bridge = fake_bridge(url="http://127.0.0.1:19992/")
        with self.assertRaisesRegex(PermissionError, "origin"):
            bridge.camfx03_draft_catalog("movie001")
        with self.assertRaisesRegex(PermissionError, "origin"):
            bridge.film03_actor_catalog("movie001")

    def test_camera_publication_requires_fresh_native_event_and_scope(self):
        bridge = fake_bridge()
        observed = []
        class Rail:
            def __init__(self, index, *, verify_director_action):
                self.approve = verify_director_action
            def publish(self, pid, rid, spec, *, expected_revision,
                        preview_sha256, director_event):
                scope = {
                    "operation": "nvp.cam_fx02.publish_exact_director_camera_rail.v1",
                    "project_id": pid, "rail_id": rid,
                    "world_take_sha256": "a"*64,
                    "camera_bank_sha256": "b"*64,
                    "film_start_tick": 0, "film_end_tick": 1,
                    "proposed_rail_sha256": preview_sha256,
                    "stronger_usd_layer_sha256": "c"*64}
                assert not self.approve("web_claimed", scope)
                assert not self.approve(director_event, {
                    **scope, "operation": "web_publish_unapproved"})
                assert self.approve(director_event, scope)
                observed.append((pid,rid))
                return {"document_sha256": "d"*64, "revision": 1}
        request = {"project_id": "movie001", "rail_id": "Rail001",
                   "rail_spec": {}, "expected_revision": 0,
                   "preview_sha256": "e"*64}
        with patch("backend.nvp_cam_fx01_camera_rails.OriginalCameraRails", Rail):
            with self.assertRaisesRegex(PermissionError, "Direct browser"):
                bridge.camfx02_publish(request)
            with patch(
                "backend.nvp_cam_fx03_04_desktop_mixin.CameraRailDirectorMixin.camfx03_draft_publish",
                autospec=True,
                side_effect=lambda self, ignored: self.camfx02_publish(request)):
                result = bridge.camfx03_draft_publish({"project_id":"movie001"})
            with self.assertRaisesRegex(PermissionError, "Direct browser"):
                bridge.camfx02_publish(request)
        self.assertEqual(result["revision"], 1)
        self.assertEqual(observed, [("movie001","Rail001")])

    def test_failed_draft_publication_does_not_leave_browser_grant(self):
        bridge = fake_bridge()
        with patch(
            "backend.nvp_cam_fx03_04_desktop_mixin.CameraRailDirectorMixin.camfx03_draft_publish",
            autospec=True, side_effect=RuntimeError("cancelled")):
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                bridge.camfx03_draft_publish({"project_id":"movie001"})
        with self.assertRaisesRegex(PermissionError, "Direct browser"):
            bridge.camfx02_publish({"project_id":"movie001"})

    def test_actor_profile_approval_is_host_only_and_exact(self):
        bridge = fake_bridge()
        class Actor:
            def __init__(self,index,*,verify_creator_action):
                self.approve = verify_creator_action
            def publish(self,pid,actor_id,profile,*,expected_profile_revision,
                        expected_bible_revision,director_note,creator_event):
                scope={
                    "operation": "film03_publish_actor_identity_profile",
                    "project_id":pid,"actor_id":actor_id,
                    "expected_profile_revision":expected_profile_revision,
                    "expected_bible_revision":expected_bible_revision,
                    "profile_sha256":"f"*64, "voice_id":None,
                    "voice_cast_revision":None}
                assert self.approve("web_supplied",scope) is False
                assert self.approve(creator_event, {**scope,"operation":"publish_anything"}) is False
                assert self.approve(creator_event,scope) is True
                return {"project_id":pid,"actor_id":actor_id,"current":{"profile_revision":1}}
        with patch("backend.nvp_film03_actor_identity_core.ActorIdentityCore", Actor):
            result = bridge.film03_actor_profile_publish({
                "project_id":"movie001","actor_id":"a"*32,"profile":{},
                "expected_profile_revision":0,"expected_bible_revision":1,
                "director_note":"Director reviewed source"})
        self.assertTrue(result["native_director_identity_approved"])
        self.assertFalse(result["voice_or_animation_generated"])

    def test_original_actor_district_shot_binding_requires_exact_one_use_native_consent(self):
        # Real source composition and original actor/PCM identity are covered
        # by the unchanged 01E/02M-H native source test. This case protects
        # the newer exact-origin desktop handoff and its one-use OS authority.
        bridge=fake_bridge()
        digest="a"*64
        request={
            "project_id":"movie001","binding_id":"ApprovedDistrictShot001",
            "district_id":"OriginalDistrict001","district_revision":1,
            "world_take_id":"OriginalWorldTake001","film_tick":7056000000}
        observed=[]
        class Original:
            def __init__(self,index,*,confirm):
                self.confirm=confirm
            def preview(self,pid,district_id,district_revision,world_take_id,film_tick):
                observed.append(("preview",pid,district_id,world_take_id,film_tick))
                return {"binding_preview_sha256":digest}
            def publish(self,pid,binding_id,*,district_id,district_revision,
                        world_take_id,film_tick,creator_event,expected_preview_sha256):
                scope={
                    "operation":"nvp.film02m_h.approve_original_district_shot_binding.v1",
                    "project_id":pid,"binding_id":binding_id,
                    "district_id":district_id,"district_revision":district_revision,
                    "district_document_sha256":"b"*64,
                    "district_usd_root_sha256":"c"*64,
                    "world_take_id":world_take_id,"world_take_sha256":"d"*64,
                    "original_camera_shot_sha256":"e"*64,
                    "source_preview_sha256":digest,
                    "film_tick":film_tick,"actor_count":1}
                assert expected_preview_sha256==digest
                assert not self.confirm("browser_claim",scope)
                assert not self.confirm(creator_event,{**scope,"film_tick":-1})
                assert not self.confirm(creator_event,{
                    **scope,"operation":"unreviewed_renderer"})
                allowed=self.confirm(creator_event,scope)
                assert not self.confirm(creator_event,scope)
                if not allowed:
                    raise PermissionError("Director refused original source binding")
                observed.append(("publish",pid,binding_id))
                return {"revision":1,"document_sha256":"f"*64}
            def reopen(self,pid,binding_id):
                observed.append(("reopen",pid,binding_id))
                return {"binding_id":binding_id,"native_source_reopened":True}
        with patch("backend.nvp_usd_film02m_h_actor_camera_binding.OriginalDistrictShotBinding",Original):
            preview=bridge.film02mh_preview_shot(request)
            self.assertEqual(preview["binding_preview_sha256"],digest)
            with self.assertRaisesRegex(PermissionError,"Exact native-approved"):
                bridge.film02mh_commit_shot_binding({
                    **request,"source_preview_sha256":digest,
                    "creator_approved":True})
            with self.assertRaisesRegex(PermissionError,"preview SHA"):
                bridge.film02mh_commit_shot_binding({
                    **request,"source_preview_sha256":"not-a-digest"})
            bridge.window.create_confirmation_dialog=lambda *_:False
            with self.assertRaisesRegex(PermissionError,"refused"):
                bridge.film02mh_commit_shot_binding({
                    **request,"source_preview_sha256":digest})
            bridge.window.create_confirmation_dialog=lambda *_:True
            result=bridge.film02mh_commit_shot_binding({
                **request,"source_preview_sha256":digest})
            self.assertEqual(result["revision"],1)
            reopened=bridge.film02mh_reopen_shot_binding({
                "project_id":"movie001","binding_id":request["binding_id"]})
            self.assertTrue(reopened["native_source_reopened"])
            self.assertEqual(observed[-2:],[
                ("publish","movie001",request["binding_id"]),
                ("reopen","movie001",request["binding_id"])])
            bridge.window.get_current_url=lambda:"https://hostile.example/"
            with self.assertRaisesRegex(PermissionError,"origin"):
                bridge.film02mh_preview_shot(request)
            with self.assertRaisesRegex(PermissionError,"origin"):
                bridge.film02mh_commit_shot_binding({
                    **request,"source_preview_sha256":digest})

    def test_original_architecture_and_texture_catalog_require_native_origin(self):
        locked = fake_bridge(locked=True)
        foreign = fake_bridge(url="http://127.0.0.1:19992/")
        for bridge in (locked, foreign):
            with self.assertRaises(PermissionError):
                bridge.film02md_architecture_catalog("movie001")
            with self.assertRaises(PermissionError):
                bridge.film01c_texture_catalog("movie001")
            with self.assertRaises(PermissionError):
                bridge.film02md_publish_cells({
                    "project_id":"movie001","cell_world_id":"Cells001",
                    "cells":[],"expected_revision":0})

    def test_actual_source_catalog_is_metadata_only_and_reopened(self):
        from contextlib import contextmanager
        from backend.nvp_usd_film02m_modular_buildings import BUILD_FORMAT
        from backend.nvp_usd_film02m_d_cells import FORMAT as CELL_FORMAT
        bridge=fake_bridge()
        docs={
            ("Building001",1):{
                "kind":"world","document_sha256":"a"*64,
                "data":{"format":BUILD_FORMAT}},
            ("Cells001",1):{
                "kind":"presentation","document_sha256":"b"*64,
                "data":{"format":CELL_FORMAT}},
            ("Asset001",1):{
                "kind":"asset","document_sha256":"c"*64,
                "data":{"preview_material":{"texture":{"sha256":"d"*64}}}},
            ("Scene001",1):{
                "kind":"scene","document_sha256":"e"*64,"data":{}}}
        index=bridge.index
        def list_objects(pid,kind):
            assert pid=="movie001"
            keys={"world":["Building001"],
                  "presentation":["Cells001"],
                  "asset":["Asset001"],"scene":["Scene001"]}
            return [{"object_id":name,"head_revision":1}
                    for name in keys.get(kind,[])]
        index.list_objects=list_objects
        index.read_revision=lambda pid,id,rev: docs[id,rev]
        @contextmanager
        def original_building(pid,id,rev):
            self.assertEqual((pid,id,rev),("movie001","Building001",1))
            yield {"record":docs[id,rev],"mesh_count":11}
        @contextmanager
        def original_cells(pid,id,rev):
            self.assertEqual((pid,id,rev),("movie001","Cells001",1))
            yield SimpleNamespace(original={"CellWest":{},"CellEast":{}})
        class Kit:
            def __init__(self, index, *, verify_director_action):
                self.assert_denied=verify_director_action("web",{})
            open_building=staticmethod(original_building)
        class Cells:
            def __init__(self,index,*,verify_director_action):
                self.deny=verify_director_action("web",{})
            open=staticmethod(original_cells)
        with patch(
            "backend.nvp_usd_film02m_modular_buildings.OriginalBuildingKit",Kit),patch(
            "backend.nvp_usd_film02m_d_cells.OriginalBuildingCells",Cells),patch(
            "backend.nvp_usd_film01c_texture.source_texture_descriptors",
            side_effect=lambda index,pid,*,kind,record:
                {"d"*64:b"original_png"} if kind=="asset" else {}):
            world=bridge.film02md_architecture_catalog("movie001")
            textures=bridge.film01c_texture_catalog("movie001")
        self.assertEqual(world["project_id"],"movie001")
        self.assertEqual(len(world["buildings"]),1)
        self.assertEqual(world["buildings"][0]["original_mesh_count"],11)
        self.assertEqual(world["cell_worlds"][0]["cell_ids"],
                         ["CellEast","CellWest"])
        self.assertTrue(world["native_source_reopened"])
        self.assertFalse(world["actual_cycles_accepted"])
        self.assertFalse(world["original_take_or_pcm_modified"])
        self.assertEqual(textures["sources"][0]["png_sha256"],["d"*64])
        self.assertFalse(textures["original_png_bytes_exposed"])
        self.assertFalse(textures["external_texture_paths_allowed"])
        self.assertNotIn("original_png",str(textures))

    def test_original_cell_publication_uses_one_exact_native_scope(self):
        bridge=fake_bridge()
        class Cells:
            def __init__(self,index,*,verify_director_action):
                self.approve=verify_director_action
            def publish(self,pid,world,*,cells,expected_revision,director_event):
                scope={
                    "operation":"nvp.film02m.publish_original_building_cells.v1",
                    "project_id":pid,
                    "cell_world_id":world,
                    "expected_revision":expected_revision,
                    "source_cell_sha256":"a"*64,
                    "source_cell_manifest_sha256":"b"*64}
                assert not self.approve("web",scope)
                assert not self.approve(director_event,{
                    **scope,"cell_world_id":"OtherCellWorld"})
                assert not self.approve(director_event,{
                    **scope,"operation":"self_authorized_render"})
                assert self.approve(director_event,scope)
                assert not self.approve(director_event,scope), (
                    "Source publication consumed its one native consent")
                return {"revision":1,"document_sha256":"d"*64}
        request={
            "project_id":"movie001","cell_world_id":"CellWorld01",
            "cells":[{"cell_id":"CellWest","building_id":"Building001",
                      "building_revision":1}],
            "expected_revision":0}
        with self.assertRaisesRegex(PermissionError,"Exact source"):
            bridge.film02md_publish_cells({**request,"worker_executable":"blender"})
        with patch("backend.nvp_usd_film02m_d_cells.OriginalBuildingCells",Cells):
            accepted=bridge.film02md_publish_cells(request)
        self.assertTrue(accepted["native_director_approved"])
        self.assertFalse(accepted["original_take_or_pcm_modified"])
        self.assertFalse(accepted["film_master_approved"])
        bridge.window.create_confirmation_dialog=lambda *_:False
        with patch("backend.nvp_usd_film02m_d_cells.OriginalBuildingCells",Cells):
            with self.assertRaises(AssertionError):
                bridge.film02md_publish_cells(request)

    def test_browser_cannot_supply_extra_security_or_worker_fields(self):
        bridge = fake_bridge()
        with self.assertRaises(PermissionError):
            bridge.camfx02_publish({"project_id":"movie001","permission":"yes"})
        with self.assertRaises(PermissionError):
            bridge.film03_actor_profile_publish({
                "project_id":"movie001","worker_command":"blender.exe"})


if __name__ == "__main__":
    unittest.main()
