"""B12 native editorial interchange and optional technical codec contract tests.

The cut interchange uses actual OpenTimelineIO 0.18.1, not faux .otio JSON.
Real 120-frame Blender source/video package is exercised separately in CI.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import json
import hashlib

from backend.nvp_b12_editorial_delivery import (
    _otio,build_otio,verify_otio_document,_relative_filename,_review,
    verify_editorial_handoff)
from backend.nvp_b12_native_delivery import NativeB12DeliveryHost,PLAN_FILE
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from tools.nvp_stack02c3b8_real_frozen_take import prepare_capture


def plenty():
    return ResourceSnapshot(1,32768,28000,0,())


def too_low():
    return ResourceSnapshot(1,16384,900,0,())


CUTS=[
    {"shot_id":"shot_a","start_frame":1,"stop_frame_exclusive":49},
    {"shot_id":"shot_b","start_frame":49,"stop_frame_exclusive":121},
]


class OpenTimelineIOContracts(unittest.TestCase):
    def test_official_otio_0181_two_shots_120_frames_24fps(self):
        otio=_otio()
        timeline=build_otio(CUTS,project_id="a"*32,
                            source_take_id="take_1",review_id="review_1",frame_count=120)
        text=otio.adapters.write_to_string(timeline,adapter_name="otio_json")
        proof=verify_otio_document(text.encode("utf8"),CUTS,120)
        self.assertEqual(proof["frames"],120)
        self.assertEqual(proof["clips"],2)
        self.assertEqual(proof["duration_seconds"],5)
        again=otio.adapters.read_from_string(text,adapter_name="otio_json")
        self.assertEqual(len(list(again.tracks[0])),2)
        self.assertEqual(again.duration().value,120)
        self.assertEqual(again.tracks[0][1].media_reference.start_frame,49)

    def test_missing_overlapping_or_outside_shot_ranges_rejected(self):
        broken=(
            [{"shot_id":"x","start_frame":2,"stop_frame_exclusive":121}],
            [{"shot_id":"x","start_frame":1,"stop_frame_exclusive":50},
             {"shot_id":"y","start_frame":49,"stop_frame_exclusive":121}],
            [{"shot_id":"x","start_frame":1,"stop_frame_exclusive":120}],
            [{"shot_id":"x","start_frame":1,"stop_frame_exclusive":200}],
        )
        for cuts in broken:
            with self.subTest(cuts=cuts):
                with self.assertRaises(RuntimeError):
                    build_otio(cuts,project_id="a"*32,
                               source_take_id="take_1",review_id="review_1",
                               frame_count=120)

    def test_otio_forged_uri_or_duration_is_rejected_after_real_parser(self):
        otio=_otio()
        standard=build_otio(CUTS,project_id="a"*32,source_take_id="take_1",
                            review_id="review_1",frame_count=120)
        standard.tracks[0][0].media_reference.target_url_base="../../other_project/"
        data=otio.adapters.write_to_string(standard,adapter_name="otio_json")
        with self.assertRaisesRegex(RuntimeError,"OTIO"):
            verify_otio_document(data.encode(),CUTS,120)
        standard.tracks[0][0].media_reference.target_url_base="media/"
        standard.tracks[0][1].source_range=otio.opentime.TimeRange(
            otio.opentime.RationalTime(0,24),otio.opentime.RationalTime(71,24))
        data=otio.adapters.write_to_string(standard,adapter_name="otio_json")
        with self.assertRaisesRegex(RuntimeError,"OTIO"):
            verify_otio_document(data.encode(),CUTS,120)

    def test_portable_media_name_rejects_path_injection_or_outside_timeline(self):
        self.assertEqual(_relative_filename(49),"review_000049.png")
        for x in (0,121,True,"../../evil",1.5):
            with self.assertRaises(ValueError):
                _relative_filename(x)


class NativeB12ApprovalContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        root=Path(self.tmp.name)
        self.studio,self.capture,self.pid,self.scene,self.take_id,_=prepare_capture(root)
        self.take_sha=self.capture.reopen(self.pid,self.take_id)["record"]["document_sha256"]
        self.review_id="unit_b11_review"
        record=self.capture.index.register_revision(
            self.pid,self.review_id,"presentation",
            {"format":"unit_b12_mock_no_video_ever","source_take_id":self.take_id,
             "source_take_sha256":self.take_sha,
             "source_presentation_sha256":"0"*64,
             "source_presentation_id":"unit_float","frame_count":120,
             "width":160,"height":90,"color_policy":{"config_sha256":"a"*64},
             "cutlist":CUTS},
            dependencies=[{"object_id":self.take_id,"revision":1,"role":"source_take"}])
        self.mock_source={"record":record,
                          "data":self.capture.index.read_revision(
                              self.pid,self.review_id)["data"]}
        self.fixture=patch("backend.nvp_b12_native_delivery._review",
                           return_value=(self.capture.index.read_revision(
                               self.pid,self.review_id),self.mock_source["data"],{}))
        self.fixture.start()
        self.ledger=TaskLedger(root/"resources",sampler=plenty)
        self.signal=object()
        self.scopes=[]
        def creator(signal,scope):
            self.scopes.append(scope)
            return signal is self.signal
        self.host=NativeB12DeliveryHost(
            self.capture,self.ledger,root/"native",verify_creator_action=creator)

    def tearDown(self):
        self.fixture.stop()
        self.tmp.cleanup()

    def approve(self,**kw):
        return self.host.stage_and_approve(
            self.pid,self.review_id,self.signal,profiles=(),**kw)

    def test_native_creator_approval_binds_frozen_cut_timing_and_no_audio(self):
        with self.assertRaises(PermissionError):
            self.host.stage_and_approve(
                self.pid,self.review_id,{"clicked":True},profiles=())
        self.assertEqual(self.ledger.snapshot()["tasks"],[])
        approved=self.approve()
        self.assertEqual(approved["state"],"QUEUED")
        self.assertFalse(approved["native_worker_started"])
        scope=self.scopes[-1]
        self.assertEqual(scope["camera_cutlist"],CUTS)
        self.assertEqual(scope["frame_count"],120)
        self.assertEqual(scope["fps"],24)
        self.assertEqual(scope["otio_version"],"0.18.1")
        self.assertFalse(scope["audio_present"])
        self.assertFalse(scope["final_master_approved"])

    def test_measured_low_ram_never_launches_encode(self):
        ticket=self.approve()
        self.ledger.sampler=too_low
        with patch("backend.nvp_b12_native_delivery.launch_contained",
                   side_effect=AssertionError("FFmpeg cannot start without admission")) as launch:
            refused=self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(refused["state"],"QUEUED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_changed_staged_delivery_plan_refuses_before_worker_admission(self):
        ticket=self.approve()
        path=self.host.root/ticket["job_id"]/PLAN_FILE
        path.write_bytes(path.read_bytes()+b"modified")
        with patch("backend.nvp_b12_native_delivery.launch_contained") as launch:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            launch.assert_not_called()
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_native_creator_can_revoke_only_queued_export(self):
        ticket=self.approve()
        with self.assertRaises(PermissionError):
            self.host.revoke_from_trusted_native_action(ticket["job_id"],{"web":True})
        revoked=self.host.revoke_from_trusted_native_action(ticket["job_id"],self.signal)
        self.assertTrue(revoked["revoked"])
        self.assertTrue(revoked["queued_cancelled"])
        self.assertFalse(revoked["active_OS_process_terminated_claimed"])

    def test_expired_grant_and_unknown_native_launch_are_fail_closed(self):
        ticket=self.approve()
        with self.ledger._db() as db:
            db.execute("UPDATE native_b12_deliveries SET expires_at=0 WHERE job_id=?",
                       (ticket["job_id"],))
        with patch("backend.nvp_b12_native_delivery.launch_contained") as launch:
            with self.assertRaises(PermissionError):
                self.host.run_next()
            launch.assert_not_called()
        # Remove the revoked/expired head-of-line task before testing a
        # *different* admitted job and an unknown OS launcher outcome.
        self.ledger.cancel_queued(ticket["job_id"],owner_key=self.host.owner_key)
        second=self.approve()
        with patch("backend.nvp_b12_native_delivery.launch_contained",
                   side_effect=RuntimeError("kernel launch handle lost")):
            with self.assertRaisesRegex(RuntimeError,"handle lost"):
                self.host.run_next()
        self.assertEqual(self.ledger.get_task(second["job_id"])["state"],"ACTIVE")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],2048)

    def test_queued_state_never_claimed_as_delivery(self):
        ticket=self.approve()
        other=NativeB12DeliveryHost(
            self.capture,self.ledger,self.host.root,
            verify_creator_action=lambda *_:False)
        with self.assertRaises(RuntimeError):
            other.verify_completed(ticket["job_id"])


if __name__=="__main__":
    unittest.main()
