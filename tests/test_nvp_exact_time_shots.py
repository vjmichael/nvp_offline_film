"""DA-01/DA-02: exact Film Time shots, source provenance and native Take approval.

Native OpenUSD layers, the real FilmIndex SQLite content store and the
actual temporal ledger are exercised. No FPS, FFmpeg, proxy movie or
flattened soundtrack is needed.
"""
import unittest

import test_nvp_data_av_native as _fixture
from test_nvp_data_av_native import Window,T
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_temporal_ledger import TemporalLedger
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture


class ExactTimeCameraSequenceTests(unittest.TestCase):
    def setUp(self):
        _fixture.NativeDigitalTakeAudioTests.setUp(self)
    def shots(self):
        return [
            {"shot_id":"Shot001","camera_path":"/World/ListenerLeft",
             "pattern":"single","start_tick":"0","end_tick":str(T)},
            {"shot_id":"Shot002","camera_path":"/World/ListenerLeft",
             "pattern":"tracking","start_tick":str(T+T//4),
             "end_tick":str(2*T)},
        ]

    def publish(self,*,expected_revision=0,shots=None):
        return ExactTimeShotSequence(self.index).publish(
            self.pid,"ExactCameraEdits",scene_id="spatial_world",
            scene_revision=1,duration_tick=str(3*T),
            shots=shots or self.shots(),
            expected_revision=expected_revision)

    def test_camera_shots_are_exact_event_data_and_gaps_survive_restart(self):
        first=self.publish()
        self.assertEqual(first["format"],"nvp.exact_time.usd_camera_shots.v1")
        self.assertEqual(first["ticks_per_second"],T)
        self.assertEqual(first["shots"][1]["gap_before_tick"],str(T//4))
        self.assertEqual(first["document_sha256"],
                         self.index.read_revision(
                             self.pid,"ExactCameraEdits",1)["document_sha256"])
        self.assertEqual(first["video_frames_created"],False)
        self.assertEqual(first["digital_take_frozen"],False)
        self.assertNotIn("fps",first)
        self.assertNotIn("frame_count",first)
        second=self.publish(expected_revision=1)
        self.assertEqual(second["revision"],2)
        self.assertEqual(ExactTimeShotSequence(self.index).read(
            self.pid,"ExactCameraEdits",1)["document_sha256"],
                         first["document_sha256"])
        with self.assertRaises(Exception):
            self.publish(expected_revision=1)
        self.assertEqual(ExactTimeShotSequence(self.index).read(
            self.pid,"ExactCameraEdits",2)["document_sha256"],
                         second["document_sha256"])

    def test_rejects_float_ticks_unknown_cameras_overlap_and_legacy_frames(self):
        editor=ExactTimeShotSequence(self.index)
        bad=self.shots()
        bad[0]["start_tick"]=0.0
        with self.assertRaises(ValueError):
            self.publish(shots=bad)
        bad=self.shots()
        bad[0]["camera_path"]="/World/Fake"
        with self.assertRaises(ValueError):
            self.publish(shots=bad)
        bad=self.shots()
        bad[1]["start_tick"]=str(T//2)
        with self.assertRaises(ValueError):
            self.publish(shots=bad)
        bad=self.shots()
        bad[0]["start_frame"]=0
        with self.assertRaises(ValueError):
            self.publish(shots=bad)
        with self.assertRaises(ValueError):
            editor.publish(self.pid,"FrameTimeline",
                scene_id="spatial_world",scene_revision=1,
                shots=self.shots(),duration_tick="1.23",
                expected_revision=0)

    def test_persisted_camera_events_fail_closed_on_bad_pattern_or_subject(self):
        # Bypass the authoring validator to exercise the persisted-data
        # reader, as a migration or damaged ledger may supply old events.
        editor=ExactTimeShotSequence(self.index)
        for name,pattern,subject in (
            ("BadPatternCamera","legacy_frame_proxy","Camera"),
            ("WrongSubjectCamera","single","Actor"),
        ):
            with self.subTest(name=name):
                TemporalLedger(self.index).publish(
                    self.pid,name,[{
                        "event_id":"Shot001","event_kind":"camera",
                        "subject_id":subject,"start_tick":0,"end_tick":T,
                        "source_id":"spatial_world","source_revision":1,
                        "payload":{
                            "format":"nvp.exact_time.usd_camera_shots.v1",
                            "usd_prim_path":"/World/ListenerLeft",
                            "observation_pattern":pattern,
                            "world_duplicated":False,
                            "picture_frames_recorded":False,
                        },
                    }],duration_tick=2*T,expected_revision=0)
                with self.assertRaises(RuntimeError):
                    editor.read(self.pid,name,1)

    def test_persisted_camera_revision_rejects_frame_metadata_and_duplicate_ids(self):
        editor=ExactTimeShotSequence(self.index)
        for name,extra,duplicate in (
            ("FrameCountCamera",{"frame_count":24},False),
            ("StartFrameCamera",{"start_frame":0},False),
            ("DuplicateShotCamera",{},True),
        ):
            with self.subTest(name=name):
                payload={
                    "format":"nvp.exact_time.usd_camera_shots.v1",
                    "usd_prim_path":"/World/ListenerLeft",
                    "observation_pattern":"single",
                    "world_duplicated":False,
                    "picture_frames_recorded":False,
                    **extra,
                }
                first={
                    "event_id":"Shot001","event_kind":"camera",
                    "subject_id":"Camera","start_tick":0,"end_tick":T,
                    "source_id":"spatial_world","source_revision":1,
                    "payload":payload,
                }
                events=[first]
                if duplicate:
                    events.append({**first,"start_tick":T,"end_tick":2*T})
                if duplicate:
                    # TemporalLedger itself rejects repeated event IDs at
                    # publication via its staged primary-key constraint.
                    with self.assertRaises(Exception):
                        TemporalLedger(self.index).publish(
                            self.pid,name,events,duration_tick=3*T,
                            expected_revision=0)
                else:
                    TemporalLedger(self.index).publish(
                        self.pid,name,events,duration_tick=3*T,
                        expected_revision=0)
                    with self.assertRaises(RuntimeError):
                        editor.read(self.pid,name,1)

    def test_camera_at_tick_preserves_half_open_boundaries_and_gaps(self):
        saved=self.publish()
        editor=ExactTimeShotSequence(self.index)
        def at(tick):
            return editor.camera_at_tick(self.pid,"ExactCameraEdits",1,str(tick))
        self.assertEqual(at(0)["shot_id"],"Shot001")
        self.assertEqual(at(T-1)["status"],"CAMERA")
        self.assertEqual(at(T)["status"],"GAP")
        self.assertIsNone(at(T)["camera_path"])
        self.assertEqual(at(T+T//4)["shot_id"],"Shot002")
        self.assertEqual(at(2*T)["status"],"GAP")
        self.assertEqual(at(3*T-1)["status"],"GAP")
        self.assertEqual(at(1)["tick"],"1")
        self.assertEqual(at(1)["document_sha256"],saved["document_sha256"])
        for bad in (3*T,-1):
            with self.assertRaises(ValueError):
                at(bad)
        with self.assertRaises(ValueError):
            editor.camera_at_tick(self.pid,"ExactCameraEdits",1,1.0)

    def test_camera_segments_partition_exact_window_without_frame_rounding(self):
        saved=self.publish()
        editor=ExactTimeShotSequence(self.index)
        def segments(a,b):
            return editor.camera_segments(self.pid,"ExactCameraEdits",1,str(a),str(b))
        window=segments(1,3*T)
        self.assertEqual(window["document_sha256"],saved["document_sha256"])
        self.assertFalse(window["video_frames_created"])
        self.assertEqual(
            [(s["status"],int(s["start_tick"]),int(s["end_tick"])) for s in window["segments"]],
            [("CAMERA",1,T),("GAP",T,T+T//4),
             ("CAMERA",T+T//4,2*T),("GAP",2*T,3*T)])
        self.assertEqual(segments(T,T+1)["segments"][0]["status"],"GAP")
        self.assertEqual(segments(T+T//4-1,T+T//4+1)["segments"][1]["shot_id"],"Shot002")
        for a,b in ((0,0),(T,T),(2*T,T),(0,3*T+1)):
            with self.assertRaises(ValueError):
                segments(a,b)
        with self.assertRaises(ValueError):
            editor.camera_segments(self.pid,"ExactCameraEdits",1,0.5,"1")

    def test_revise_one_shot_preserves_prior_revision_and_cas(self):
        first=self.publish()
        editor=ExactTimeShotSequence(self.index)
        replacement={**self.shots()[1],"start_tick":str(T+1)}
        second=editor.revise_shot(
            self.pid,"ExactCameraEdits",1,"Shot002",replacement)
        self.assertEqual(second["revision"],2)
        self.assertEqual(second["shots"][1]["start_tick"],str(T+1))
        self.assertEqual(editor.read(self.pid,"ExactCameraEdits",1)[
            "document_sha256"],first["document_sha256"])
        self.assertNotEqual(second["document_sha256"],first["document_sha256"])
        with self.assertRaises(Exception):
            editor.revise_shot(self.pid,"ExactCameraEdits",1,
                               "Shot002",replacement)
        with self.assertRaises(ValueError):
            editor.revise_shot(self.pid,"ExactCameraEdits",2,
                               "Shot002",{**replacement,"shot_id":"Changed"})
        with self.assertRaises(ValueError):
            editor.revise_shot(self.pid,"ExactCameraEdits",2,"Unknown",None)
        third=editor.revise_shot(self.pid,"ExactCameraEdits",2,"Shot002",None)
        self.assertEqual([s["shot_id"] for s in third["shots"]],["Shot001"])
        with self.assertRaises(ValueError):
            editor.revise_shot(self.pid,"ExactCameraEdits",3,"Shot001",None)
        self.assertEqual(editor.read(self.pid,"ExactCameraEdits",2)[
            "shots"][1]["shot_id"],"Shot002")

    def test_insert_shot_in_gap_preserves_source_history_and_cas(self):
        first=self.publish()
        editor=ExactTimeShotSequence(self.index)
        inserted={"shot_id":"Shot003","camera_path":"/World/ListenerLeft",
                  "pattern":"reaction","start_tick":str(T+1),
                  "end_tick":str(T+2)}
        second=editor.insert_shot(self.pid,"ExactCameraEdits",1,inserted)
        self.assertEqual(second["revision"],2)
        self.assertEqual([s["shot_id"] for s in second["shots"]],
                         ["Shot001","Shot003","Shot002"])
        self.assertEqual(editor.camera_at_tick(
            self.pid,"ExactCameraEdits",2,str(T+1))["shot_id"],"Shot003")
        self.assertEqual(editor.camera_at_tick(
            self.pid,"ExactCameraEdits",1,str(T+1))["status"],"GAP")
        self.assertEqual(editor.read(self.pid,"ExactCameraEdits",1)[
            "document_sha256"],first["document_sha256"])
        self.assertEqual(second["scene_document_sha256"],
                         first["scene_document_sha256"])
        with self.assertRaises(Exception):
            editor.insert_shot(self.pid,"ExactCameraEdits",1,inserted)
        with self.assertRaises(ValueError):
            editor.insert_shot(self.pid,"ExactCameraEdits",2,inserted)
        with self.assertRaises(ValueError):
            editor.insert_shot(self.pid,"ExactCameraEdits",2,{
                **inserted,"shot_id":"Shot004","start_frame":24})
        with self.assertRaises(ValueError):
            editor.insert_shot(self.pid,"ExactCameraEdits",2,{
                **inserted,"shot_id":"Shot004","start_tick":str(T-1)})
        self.assertEqual(editor.read(self.pid,"ExactCameraEdits",2)[
            "document_sha256"],second["document_sha256"])

    def test_os_authorization_controls_exact_scene_and_timeline_take_freeze(self):
        saved=self.publish()
        bridge=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:7777")
        self.addCleanup(bridge._close)
        window=Window()
        bridge._attach_window(window)
        request={
            "project_id":self.pid,"take_id":"NativeCameraTake",
            "scene_id":"spatial_world","scene_revision":1,
            "scene_document_sha256":saved["scene_document_sha256"],
            "timeline_id":"ExactCameraEdits","timeline_revision":1,
            "timeline_document_sha256":saved["document_sha256"],
        }
        window.allow=False
        with self.assertRaises(PermissionError):
            bridge.data_av_freeze_timed_take(request)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NativeCameraTake",1)
        window.allow=True
        committed=bridge.data_av_freeze_timed_take(request)
        self.assertEqual(committed["status"],"FROZEN_DATA_FIRST_TAKE")
        self.assertFalse(committed["frame_based_capture"])
        self.assertFalse(committed["master_approved"])
        self.assertEqual(len(window.questions),2)
        self.assertEqual(committed["scene_document_sha256"],
                         saved["scene_document_sha256"])
        verified=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:False
            ).verify_take(self.pid,"NativeCameraTake")
        self.assertEqual(verified["take_document_sha256"],
                         committed["take_document_sha256"])
        self.assertEqual(bridge.data_av_catalog(self.pid)["takes"][0][
            "take_id"],"NativeCameraTake")
        tampered={**request,"timeline_document_sha256":"0"*64}
        with self.assertRaises(RuntimeError):
            bridge.data_av_freeze_timed_take(tampered)


if __name__=="__main__":
    unittest.main()
