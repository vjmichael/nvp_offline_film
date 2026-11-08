"""DA-03 native OpenUSD filming capture with exact sound event provenance."""
import unittest

import test_nvp_data_av_native as fixture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_temporal_ledger import TemporalLedger
from backend.nvp_data_first_filming import NativeSceneSoundCapture
from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_openusd_take import OpenUSDTakeCapture

T=fixture.T

class NativeCapturedSpatialSoundTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        self.shots=ExactTimeShotSequence(self.index).publish(
            self.pid,"FilmingCameraTimeline",scene_id="spatial_world",
            scene_revision=1,duration_tick=str(3*T),shots=[{
                "shot_id":"Shot001",
                "camera_path":"/World/ListenerLeft",
                "pattern":"continuous",
                "start_tick":"0","end_tick":str(3*T)
            }])
        self.approvals=[]
        self.capture=NativeSceneSoundCapture(
            self.index,approve_take=lambda event,scope:
                self.approvals.append((event,scope)) is None
                and event.get("kind")=="trusted_native_filming_host")

    def payload(self):
        return dict(
            project_id=self.pid,take_id="FilmedTake",
            scene_id="spatial_world",scene_revision=1,
            camera_timeline_id="FilmingCameraTimeline",
            camera_timeline_revision=1,
            sound_timeline_id="FilmingSoundTimeline",
            recordings=[{
                "event_id":"Speech001",
                "event_kind":"dialogue",
                "subject_id":"Actor",
                "source_id":"NewRecordedSpeech",
                "usd_prim_path":"/World/Actor",
                "start_tick":0,"end_tick":T,
                "gain":1.0,
                "pcm_chunks":[self.original[:24000],self.original[24000:]],
            }]
        )

    def test_native_capture_freezes_original_sound_and_camera_in_same_take(self):
        receipt=self.capture.capture(**self.payload())
        self.assertEqual(receipt["status"],"FROZEN_ORIGINAL_SCENE_SOUND_TAKE")
        self.assertFalse(receipt["picture_frames_generated"])
        self.assertFalse(receipt["audio_mix_flattened"])
        self.assertFalse(receipt["master_approved"])
        self.assertEqual(len(self.approvals),1)
        verified=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:False
            ).verify_take(self.pid,"FilmedTake")
        self.assertEqual(verified["take_document_sha256"],
                         receipt["take_document_sha256"])
        left=FrozenSceneAV(self.index,self.pid,"FilmedTake",
            expected_take_sha256=receipt["take_document_sha256"],
            listener_path="/World/ListenerLeft")
        right=FrozenSceneAV(self.index,self.pid,"FilmedTake",
            expected_take_sha256=receipt["take_document_sha256"],
            listener_path="/World/ListenerRight")
        first=left.audio_window(64,1024)
        second=right.audio_window(64,1024)
        self.assertEqual(first["audible_event_ids"],["Speech001"])
        self.assertNotEqual(first["audio_sha256"],second["audio_sha256"])
        self.assertEqual(self.index.read_revision(
            self.pid,"spatial_world",1)["document_sha256"],
                         self.shots["scene_document_sha256"])
        self.assertEqual(self.index.read_revision(
            self.pid,"FilmingCameraTimeline",1)["document_sha256"],
                         self.shots["document_sha256"])
        self.assertEqual(self.index.read_revision(
            self.pid,"NewRecordedSpeech",1)["data"]["sample_count"],
                         48000)

    def test_denied_take_is_not_falsely_frozen(self):
        capture=NativeSceneSoundCapture(
            self.index,approve_take=lambda event,scope:False)
        request=self.payload()
        request["take_id"]="DeniedTake"
        request["sound_timeline_id"]="DeniedSoundTimeline"
        request["recordings"][0]["source_id"]="DeniedSoundSource"
        with self.assertRaises(PermissionError):
            capture.capture(**request)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"DeniedTake",1)
        self.assertIsNotNone(self.index.read_revision(
            self.pid,"DeniedSoundSource",1))

    def test_duplicate_source_identity_fails_before_any_pcm_publication(self):
        req=self.payload()
        duplicate=dict(req["recordings"][0])
        duplicate["event_id"]="Speech002"
        req["recordings"].append(duplicate)
        with self.assertRaisesRegex(ValueError,"Duplicate or reserved"):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewRecordedSpeech",1)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"FilmingSoundTimeline",1)

    def test_reserved_source_identity_fails_before_any_pcm_publication(self):
        req=self.payload()
        req["recordings"][0]["source_id"]="FilmingSoundTimeline"
        with self.assertRaisesRegex(ValueError,"Duplicate or reserved"):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"FilmingSoundTimeline",1)

    def test_second_invalid_recording_does_not_publish_first_pcm(self):
        req=self.payload()
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      end_tick=4*T)
        req["recordings"].append(second)
        with self.assertRaisesRegex(ValueError,"invalid timing/gain"):
            self.capture.capture(**req)
        for identity in ("NewRecordedSpeech","SecondSpeech","FilmingSoundTimeline"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_camera_event_collision_preflight_does_not_publish_pcm(self):
        req=self.payload()
        camera_event=TemporalLedger(self.index).events_in(
            self.pid,"FilmingCameraTimeline",1,start_tick=0,end_tick=3*T,
            limit=10)["events"][0]["event_id"]
        req["recordings"][0]["event_id"]=camera_event
        with self.assertRaisesRegex(ValueError,"Duplicate or reserved"):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewRecordedSpeech",1)

    def test_same_event_and_source_identity_rejected_before_pcm(self):
        req=self.payload()
        req["recordings"][0]["event_id"]="NewRecordedSpeech"
        with self.assertRaisesRegex(ValueError,"Duplicate or reserved"):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewRecordedSpeech",1)

    def test_existing_source_in_later_entry_rejected_before_first_pcm(self):
        existing=self.capture.sources.publish(
            self.pid,"PreviouslyRecorded", [self.original],
            expected_revision=0)
        self.assertEqual(existing["revision"],1)
        req=self.payload()
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="PreviouslyRecorded")
        req["recordings"].append(second)
        with self.assertRaisesRegex(ValueError,"already published"):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewRecordedSpeech",1)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"FilmingSoundTimeline",1)

    def test_existing_sound_timeline_preflight_does_not_publish_pcm(self):
        req=self.payload()
        self.capture.sources.publish(
            self.pid,"FilmingSoundTimeline",[self.original],
            expected_revision=0)
        with self.assertRaisesRegex(ValueError,"output identity already published"):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewRecordedSpeech",1)

    def test_existing_take_identity_preflight_does_not_publish_pcm(self):
        req=self.payload()
        # An occupied identity is enough to prevent a fresh Take at revision 1.
        self.capture.sources.publish(
            self.pid,"FilmedTake",[self.original],expected_revision=0)
        with self.assertRaisesRegex(ValueError,"output identity already published"):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewRecordedSpeech",1)

    def test_later_materialized_pcm_corruption_preflight_preserves_first_source(self):
        req=self.payload()
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      pcm_chunks=[b"\x00"])
        req["recordings"].append(second)
        with self.assertRaisesRegex(ValueError,"Invalid captured PCM16LE"):
            self.capture.capture(**req)
        for identity in ("NewRecordedSpeech","SecondSpeech","FilmingSoundTimeline"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_later_materialized_pcm_shortfall_preflight_preserves_first_source(self):
        req=self.payload()
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      pcm_chunks=[b"\x00\x00"])
        req["recordings"].append(second)
        with self.assertRaisesRegex(ValueError,"shorter than"):
            self.capture.capture(**req)
        for identity in ("NewRecordedSpeech","SecondSpeech","FilmingSoundTimeline"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_materialized_chunks_snapshot_survives_host_list_mutation(self):
        req=self.payload()
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      pcm_chunks=[self.original])
        req["recordings"].append(second)
        original_publish=self.capture.sources.publish
        def mutate_after_first(project_id,source_id,chunks,**kwargs):
            result=original_publish(project_id,source_id,chunks,**kwargs)
            if source_id=="NewRecordedSpeech":
                second["pcm_chunks"].clear()
            return result
        self.capture.sources.publish=mutate_after_first
        receipt=self.capture.capture(**req)
        self.assertEqual(receipt["original_sound_count"],2)
        self.assertEqual(self.index.read_revision(
            self.pid,"SecondSpeech",1)["data"]["sample_count"],48000)

    def test_validated_metadata_snapshot_survives_later_host_mutation(self):
        req=self.payload()
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      pcm_chunks=[self.original])
        req["recordings"].append(second)
        original_publish=self.capture.sources.publish
        def mutate_after_first(project_id,source_id,chunks,**kwargs):
            result=original_publish(project_id,source_id,chunks,**kwargs)
            if source_id=="NewRecordedSpeech":
                second["event_id"]="TamperedSpeech"
                second["usd_prim_path"]="/World/NotThere"
                second["start_tick"]=2*T
                second["gain"]=99.0
            return result
        self.capture.sources.publish=mutate_after_first
        self.capture.capture(**req)
        events=TemporalLedger(self.index).events_in(
            self.pid,"FilmingSoundTimeline",1,start_tick=0,end_tick=3*T,
            limit=10)["events"]
        recorded=[ev for ev in events if ev["event_kind"]=="dialogue"]
        self.assertEqual({ev["event_id"] for ev in recorded},
                         {"Speech001","Speech002"})
        later=next(ev for ev in recorded if ev["event_id"]=="Speech002")
        self.assertEqual(later["start_tick"],0)
        self.assertEqual(later["payload"]["usd_prim_path"],"/World/Actor")
        self.assertEqual(later["payload"]["gain"],1.0)


    def test_later_streaming_shortfall_does_not_publish_earlier_source(self):
        req=self.payload()
        req["recordings"][0]["pcm_chunks"]=iter([self.original])
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      pcm_chunks=iter([b"\x00\x00"]))
        req["recordings"].append(second)
        with self.assertRaisesRegex(ValueError,"shorter than"):
            self.capture.capture(**req)
        for identity in ("NewRecordedSpeech","SecondSpeech","FilmingSoundTimeline"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_streaming_chunks_are_replayed_from_validated_spool(self):
        req=self.payload()
        req["recordings"][0]["pcm_chunks"]=iter(
            [self.original[:24000],self.original[24000:]])
        receipt=self.capture.capture(**req)
        self.assertEqual(receipt["original_sound_count"],1)
        self.assertEqual(self.index.read_revision(
            self.pid,"NewRecordedSpeech",1)["data"]["sample_count"],48000)

    def test_spool_mutation_after_preflight_fails_closed_before_take(self):
        req=self.payload()
        original_publish=self.capture.sources.publish
        def tamper_spool(project_id,source_id,chunks,**kwargs):
            # The trusted worker's temporary spool is not authoritative:
            # replay must detect a changed byte before publishing its source.
            spool=chunks.gi_frame.f_locals["spool"]
            spool.seek(4)
            byte=spool.read(1)
            spool.seek(4)
            spool.write(bytes([byte[0]^1]))
            spool.flush()
            return original_publish(project_id,source_id,chunks,**kwargs)
        self.capture.sources.publish=tamper_spool
        with self.assertRaisesRegex(RuntimeError,"spool changed after validation"):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"FilmedTake",1)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewRecordedSpeech",1)

    def test_corrupted_later_spool_fails_before_first_source_publication(self):
        from unittest.mock import patch
        import backend.nvp_data_first_filming as filming
        req=self.payload()
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      pcm_chunks=iter([self.original]))
        req["recordings"].append(second)
        actual_spool=filming.tempfile.SpooledTemporaryFile
        created=[]
        class CorruptingSpool:
            def __init__(self,inner):
                self.inner=inner
                self.rewound=False
            def write(self,*args):return self.inner.write(*args)
            def read(self,*args):return self.inner.read(*args)
            def seek(self,offset,*args):
                result=self.inner.seek(offset,*args)
                if offset==0 and len(created)==2 and self is created[1] and not self.rewound:
                    self.rewound=True
                    self.inner.seek(4)
                    first=self.inner.read(1)
                    self.inner.seek(4)
                    self.inner.write(bytes([first[0]^1]))
                    self.inner.seek(0)
                return result
            def close(self):return self.inner.close()
        def spool_factory(**kwargs):
            wrapped=CorruptingSpool(actual_spool(**kwargs))
            created.append(wrapped)
            return wrapped
        with patch.object(filming.tempfile,"SpooledTemporaryFile",spool_factory):
            with self.assertRaisesRegex(RuntimeError,"spool changed after validation"):
                self.capture.capture(**req)
        for identity in ("NewRecordedSpeech","SecondSpeech","FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_capture_rejects_unknown_world_emitter(self):
        req=self.payload()
        req["recordings"][0]["usd_prim_path"]="/World/NotThere"
        with self.assertRaises(RuntimeError):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewRecordedSpeech",1)


if __name__=="__main__":
    unittest.main()
