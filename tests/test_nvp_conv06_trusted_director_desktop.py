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

    def test_browser_cannot_supply_extra_security_or_worker_fields(self):
        bridge = fake_bridge()
        with self.assertRaises(PermissionError):
            bridge.camfx02_publish({"project_id":"movie001","permission":"yes"})
        with self.assertRaises(PermissionError):
            bridge.film03_actor_profile_publish({
                "project_id":"movie001","worker_command":"blender.exe"})


if __name__ == "__main__":
    unittest.main()
