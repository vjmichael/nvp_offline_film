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

    def test_direct_capture_enforces_aggregate_pcm_budget_before_publication(self):
        from unittest.mock import patch
        import backend.nvp_data_first_filming as filming
        req=self.payload()
        first=req["recordings"][0]
        first["pcm_chunks"]=[self.original]
        second=dict(first)
        second.update(event_id="Speech002",source_id="SecondOriginalSpeech")
        req["recordings"].append(second)
        # Each stream fits the artificial one-chunk budget, but the batch
        # exceeds it. No source, timeline, or Take may be published.
        with patch.object(filming,"MAX_CHUNK_BYTES",len(self.original)), patch.object(
                filming,"MAX_CHUNKS",1):
            with self.assertRaisesRegex(ValueError,"batch exceeds spool budget"):
                self.capture.capture(**req)
        for identity in ("NewRecordedSpeech","SecondOriginalSpeech",
                         "FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)
        self.assertEqual(self.capture.publications.unresolved(self.pid),[])

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

    def test_completed_publication_rejects_timeline_digest_mismatch(self):
        from unittest.mock import patch
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        journal = FilmingPublicationJournal(self.index)
        original_read = self.index.read_revision
        def substitute_timeline_digest(project_id, identity, revision):
            record = original_read(project_id, identity, revision)
            if identity == "FilmedTake":
                record = dict(record)
                record["data"] = dict(record["data"])
                record["data"]["timeline_document_sha256"] = "0" * 64
            return record
        with patch.object(self.index, "read_revision", side_effect=substitute_timeline_digest):
            result = journal.visibility(self.pid, "FilmedTake")
        self.assertFalse(result["visible"])
        self.assertEqual(result["reason"], "PUBLICATION_BINDING_MISMATCH")
        self.assertTrue(journal.visibility(self.pid, "FilmedTake")["visible"])
        self.assertEqual(original_read(self.pid, "FilmedTake", 1)["data"]["timeline_document_sha256"],
                         original_read(self.pid, "FilmingSoundTimeline", 1)["document_sha256"])

    def test_completion_holds_writer_lock_during_dependency_verification(self):
        import sqlite3
        from unittest.mock import patch
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        journal=FilmingPublicationJournal(self.index)
        # Model a recovered PREPARING receipt with already published immutable
        # dependencies, then independently test the completion transition.
        with self.index.studio._connection() as db:
            db.execute("""UPDATE nvp_filming_publications SET state='PREPARING'
                WHERE project_id=? AND take_id=?""",(self.pid,"FilmedTake"))
        original_read=self.index.read_revision
        checked=[]
        def check_writer_reservation(project_id,identity,revision):
            if identity=="FilmedTake":
                with self.index.studio._connection() as contender:
                    contender.execute("PRAGMA busy_timeout=0")
                    with self.assertRaises(sqlite3.OperationalError):
                        contender.execute("BEGIN IMMEDIATE")
                checked.append(True)
            return original_read(project_id,identity,revision)
        with patch.object(self.index,"read_revision",side_effect=check_writer_reservation):
            journal.finish(self.pid,"FilmedTake",completed=True)
        self.assertEqual(checked,[True])
        self.assertEqual(journal.unresolved(self.pid),[])

    def test_journal_rejects_cross_batch_identity_reuse(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        journal = FilmingPublicationJournal(self.index)
        journal.begin(self.pid, "ReservedTake", "ReservedTimeline", ["ReservedSource"])
        for take_id, timeline_id, source_id in (
            ("OtherTake", "OtherTimeline", "ReservedSource"),
            ("OtherTake", "ReservedTimeline", "OtherSource"),
            ("ReservedSource", "OtherTimeline", "OtherSource"),
        ):
            with self.subTest(take_id=take_id, timeline_id=timeline_id, source_id=source_id):
                with self.assertRaisesRegex(ValueError, "reserved"):
                    journal.begin(self.pid, take_id, timeline_id, [source_id])
        self.assertEqual([entry["take_id"] for entry in journal.unresolved(self.pid)],
                         ["ReservedTake"])

    def test_journal_rejects_preexisting_nonjournal_filmindex_identity(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        journal = FilmingPublicationJournal(self.index)
        # Legacy and independently published immutable objects do not have
        # filming-journal reservations, but still own their FilmIndex IDs.
        self.capture.sources.publish(
            self.pid, "LegacyOriginalPCM", [self.original], expected_revision=0)
        for take_id, timeline_id, sources in (
            ("LegacyOriginalPCM", "FreshTimelineA", ["FreshSourceA"]),
            ("FreshTakeB", "LegacyOriginalPCM", ["FreshSourceB"]),
            ("FreshTakeC", "FreshTimelineC", ["LegacyOriginalPCM"]),
        ):
            with self.subTest(take_id=take_id, timeline_id=timeline_id):
                with self.assertRaisesRegex(ValueError, "already exists in FilmIndex"):
                    journal.begin(self.pid, take_id, timeline_id, sources)
        self.assertEqual(journal.unresolved(self.pid), [])
        self.assertIsNotNone(self.index.read_revision(
            self.pid, "LegacyOriginalPCM", 1))

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

    def test_denied_publication_is_visible_after_journal_reopen(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        denied=NativeSceneSoundCapture(self.index,approve_take=lambda event,scope:False)
        request=self.payload()
        request["take_id"]="InterruptedFilmingTake"
        request["sound_timeline_id"]="InterruptedFilmingTimeline"
        request["recordings"][0]["source_id"]="InterruptedFilmingSource"
        with self.assertRaises(PermissionError):
            denied.capture(**request)
        inventory=FilmingPublicationJournal(self.index).unresolved(self.pid)
        row=next(r for r in inventory if r["take_id"]=="InterruptedFilmingTake")
        self.assertEqual(row["state"],"INTERRUPTED")
        self.assertEqual(row["source_ids"],["InterruptedFilmingSource"])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"InterruptedFilmingTake",1)
        self.assertIsNotNone(self.index.read_revision(
            self.pid,"InterruptedFilmingSource",1))

    def test_restart_reconciliation_reports_actual_immutable_revisions(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        denied=NativeSceneSoundCapture(self.index,approve_take=lambda event,scope:False)
        request=self.payload()
        request["take_id"]="ReconcileTake"
        request["sound_timeline_id"]="ReconcileTimeline"
        request["recordings"][0]["source_id"]="ReconcileSource"
        with self.assertRaises(PermissionError):
            denied.capture(**request)
        journal=FilmingPublicationJournal(self.index)
        before=journal.reconcile(self.pid)
        row=next(r for r in before if r["take_id"]=="ReconcileTake")
        self.assertEqual(row["state"],"INTERRUPTED")
        self.assertEqual(row["source_revisions_present"],{"ReconcileSource":True})
        self.assertTrue(row["sound_timeline_present"])
        self.assertFalse(row["take_present"])
        self.assertEqual(row["resolution"],"INTERRUPTED_TIMELINE_WITHOUT_TAKE")
        self.assertEqual(journal.reconcile(self.pid),before)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"ReconcileTake",1)

    def test_restart_reconciliation_distinguishes_partial_source_publication(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        # Reserve the identities before publishing any immutable source.
        # Simulate a crash after the first source is committed, while the
        # second source and timeline are still absent. A preexisting source
        # is correctly rejected by begin() and cannot model this crash.
        journal=FilmingPublicationJournal(self.index)
        journal.begin(self.pid,"CrashedTake","CrashedTimeline",
                      ["NewRecordedSpeech","MissingSecondSource"])
        self.capture.sources.publish(
            self.pid,"NewRecordedSpeech",[self.original],expected_revision=0)
        before=journal.reconcile(self.pid)
        row=next(r for r in before if r["take_id"]=="CrashedTake")
        self.assertEqual(row["state"],"PREPARING")
        self.assertEqual(row["source_revision_count"],1)
        self.assertEqual(row["expected_source_revision_count"],2)
        self.assertEqual(row["source_revisions_present"],
                         {"NewRecordedSpeech":True,"MissingSecondSource":False})
        self.assertFalse(row["sound_timeline_present"])
        self.assertFalse(row["take_present"])
        self.assertEqual(row["resolution"],"INTERRUPTED_PARTIAL_SOURCE_PUBLICATION")
        self.assertEqual(journal.reconcile(self.pid),before)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"MissingSecondSource",1)

    def test_journal_rejects_colliding_output_identities_without_receipt(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        journal=FilmingPublicationJournal(self.index)
        for take_id,timeline_id,source_ids in (
            ("CollisionTake","CollisionTake",["CollisionSource"]),
            ("CollisionTake","CollisionTimeline",["CollisionTake"]),
            ("CollisionTake","CollisionTimeline",["CollisionTimeline"]),
        ):
            with self.subTest(take_id=take_id,timeline_id=timeline_id,source_ids=source_ids):
                with self.assertRaisesRegex(ValueError,"identities must be distinct"):
                    journal.begin(self.pid,take_id,timeline_id,source_ids)
        self.assertFalse(any(r["take_id"]=="CollisionTake"
                             for r in journal.unresolved(self.pid)))

    def test_journal_cannot_complete_missing_immutable_dependencies(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        journal=FilmingPublicationJournal(self.index)
        journal.begin(self.pid,"IncompleteReceiptTake","IncompleteReceiptTimeline",
                      ["IncompleteReceiptSource"])
        with self.assertRaisesRegex(RuntimeError,"missing immutable dependencies"):
            journal.finish(self.pid,"IncompleteReceiptTake",completed=True)
        row=next(r for r in journal.reconcile(self.pid)
                 if r["take_id"]=="IncompleteReceiptTake")
        self.assertEqual(row["state"],"PREPARING")
        self.assertEqual(row["resolution"],"INTERRUPTED_BEFORE_SOURCE_PUBLICATION")
        self.assertFalse(row["take_present"])

    def test_successful_publication_is_not_unresolved(self):
        self.capture.capture(**self.payload())
        self.assertFalse(any(
            r["take_id"]=="FilmedTake"
            for r in self.capture.publications.unresolved(self.pid)))

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
        with self.assertRaisesRegex(ValueError,"sample count does not match"):
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
        with self.assertRaisesRegex(ValueError,"sample count does not match"):
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
            def flush(self):return self.inner.flush()
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

    def test_short_spool_write_rejects_batch_and_closes_temporary_files(self):
        from unittest.mock import patch
        import backend.nvp_data_first_filming as filming
        req=self.payload()
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      pcm_chunks=iter([self.original]))
        req["recordings"].append(second)
        real_factory=filming.tempfile.SpooledTemporaryFile
        created=[]
        class ShortWriteSpool:
            def __init__(self,inner,fail):
                self.inner=inner
                self.fail=fail
                self.closed=False
            def write(self,data):
                if self.fail:
                    self.fail=False
                    return len(data)-1
                return self.inner.write(data)
            def seek(self,*args):return self.inner.seek(*args)
            def read(self,*args):return self.inner.read(*args)
            def flush(self):return self.inner.flush()
            def close(self):
                self.closed=True
                return self.inner.close()
        def factory(**kwargs):
            wrapped=ShortWriteSpool(real_factory(**kwargs),len(created)==1)
            created.append(wrapped)
            return wrapped
        with patch.object(filming.tempfile,"SpooledTemporaryFile",factory):
            with self.assertRaisesRegex(OSError,"Incomplete captured PCM spool write"):
                self.capture.capture(**req)
        self.assertEqual(len(created),2)
        self.assertTrue(all(spool.closed for spool in created))
        for identity in ("NewRecordedSpeech","SecondSpeech","FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_delayed_spool_flush_failure_rejects_entire_batch(self):
        from unittest.mock import patch
        import backend.nvp_data_first_filming as filming
        req=self.payload()
        second=dict(req["recordings"][0])
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      pcm_chunks=iter([self.original]))
        req["recordings"].append(second)
        real_factory=filming.tempfile.SpooledTemporaryFile
        created=[]
        class FlushFailSpool:
            def __init__(self,inner,fail):
                self.inner=inner
                self.fail=fail
                self.closed=False
            def write(self,data):return self.inner.write(data)
            def seek(self,*args):return self.inner.seek(*args)
            def read(self,*args):return self.inner.read(*args)
            def flush(self):
                if self.fail:
                    self.fail=False
                    raise OSError("Delayed PCM spool flush failure")
                return self.inner.flush()
            def close(self):
                self.closed=True
                return self.inner.close()
        def factory(**kwargs):
            wrapped=FlushFailSpool(real_factory(**kwargs),len(created)==1)
            created.append(wrapped)
            return wrapped
        with patch.object(filming.tempfile,"SpooledTemporaryFile",factory):
            with self.assertRaisesRegex(OSError,"Delayed PCM spool flush failure"):
                self.capture.capture(**req)
        self.assertEqual(len(created),2)
        self.assertTrue(all(spool.closed for spool in created))
        for identity in ("NewRecordedSpeech","SecondSpeech","FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_checkpoint_overflow_rejects_before_any_immutable_publication(self):
        from unittest.mock import patch
        import backend.nvp_data_first_filming as filming
        req=self.payload()
        # The real capacity is much larger; force the same production guard
        # with a smaller bound instead of allocating thousands of sources.
        with patch.object(filming,"MAX_CHECKPOINTS",1):
            with self.assertRaisesRegex(ValueError,"checkpoint capacity"):
                self.capture.capture(**req)
        self.assertEqual(self.approvals,[])
        for identity in ("NewRecordedSpeech","FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_checkpoint_overflow_does_not_consume_recording_iterator(self):
        from unittest.mock import patch
        import backend.nvp_data_first_filming as filming
        req=self.payload()
        consumed=[]
        def guarded_pcm():
            consumed.append(True)
            raise AssertionError("Overflow must not read recording PCM")
            yield bytes(2)
        req["recordings"][0]["pcm_chunks"]=guarded_pcm()
        with patch.object(filming,"MAX_CHECKPOINTS",1):
            with self.assertRaisesRegex(ValueError,"checkpoint capacity"):
                self.capture.capture(**req)
        self.assertEqual(consumed,[])
        self.assertEqual(self.approvals,[])
        for identity in ("NewRecordedSpeech","FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_streaming_pcm_cannot_rewrite_frozen_sound_metadata(self):
        req=self.payload()
        event=req["recordings"][0]
        def mutating_pcm():
            event["gain"]=0.0
            event["subject_id"]="TamperedActor"
            yield self.original
        event["pcm_chunks"]=mutating_pcm()
        self.capture.capture(**req)
        events=TemporalLedger(self.index).events_in(
            self.pid,"FilmingSoundTimeline",1,
            start_tick=0,end_tick=3*T,limit=20)["events"]
        recorded=next(e for e in events if e["event_id"]=="Speech001")
        self.assertEqual(recorded["subject_id"],"Actor")
        self.assertEqual(recorded["payload"]["gain"],1.0)
        self.assertEqual(event["gain"],0.0)

    def test_earlier_pcm_generator_cannot_mutate_later_recording_metadata(self):
        req=self.payload()
        first=req["recordings"][0]
        second=dict(first)
        second.update(event_id="Speech002",source_id="SecondSpeech",
                      pcm_chunks=iter([self.original]))
        req["recordings"].append(second)
        def mutating_first_pcm():
            second["event_id"]="TamperedSpeech"
            second["subject_id"]="TamperedActor"
            second["usd_prim_path"]="/World/NotThere"
            second["gain"]=99.0
            yield self.original
        first["pcm_chunks"]=mutating_first_pcm()
        self.capture.capture(**req)
        events=TemporalLedger(self.index).events_in(
            self.pid,"FilmingSoundTimeline",1,
            start_tick=0,end_tick=3*T,limit=20)["events"]
        later=next(e for e in events if e["event_id"]=="Speech002")
        self.assertEqual(later["subject_id"],"Actor")
        self.assertEqual(later["payload"]["gain"],1.0)
        self.assertEqual(later["payload"]["usd_prim_path"],"/World/Actor")
        self.assertEqual(second["event_id"],"TamperedSpeech")

    def test_invalid_later_recording_rejected_before_first_pcm_iterator(self):
        req=self.payload()
        consumed=[]
        def guarded_pcm():
            consumed.append(True)
            raise AssertionError("No PCM may be consumed before batch preflight")
            yield b"\\x00\\x00"
        req["recordings"][0]["pcm_chunks"]=guarded_pcm()
        later=dict(req["recordings"][0])
        later.update(event_id="Speech002",source_id="SecondSpeech",
                     usd_prim_path="/World/NotThere",pcm_chunks=iter([self.original]))
        req["recordings"].append(later)
        with self.assertRaisesRegex(RuntimeError,"emitter"):
            self.capture.capture(**req)
        self.assertEqual(consumed,[])
        self.assertEqual(self.approvals,[])
        for identity in ("NewRecordedSpeech","SecondSpeech","FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)

    def test_recovery_does_not_trust_take_with_missing_recorded_dependencies(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        journal=FilmingPublicationJournal(self.index)
        # Model a crash/corrupt publication receipt whose Take revision exists
        # but whose claimed source and timeline revisions are unavailable.
        with self.index.studio._connection() as db:
            db.execute("""UPDATE nvp_filming_publications
                SET state='PREPARING', source_ids_json=?,
                    sound_timeline_id=?
                WHERE project_id=? AND take_id=?""",
                ('["MissingRecordedSource"]', "MissingRecordedTimeline",
                 self.pid, "FilmedTake"))
        row=next(r for r in journal.reconcile(self.pid)
                 if r["take_id"]=="FilmedTake")
        self.assertTrue(row["take_present"])
        self.assertFalse(row["sound_timeline_present"])
        self.assertEqual(row["source_revisions_present"],
                         {"MissingRecordedSource":False})
        self.assertEqual(row["resolution"],
                         "INCOMPLETE_FROZEN_TAKE_DEPENDENCIES")
        self.assertEqual(journal.reconcile(self.pid)[0],row)
        # Recovery never rewrites the real immutable Take or original PCM.
        self.assertIsNotNone(self.index.read_revision(self.pid,"FilmedTake",1))
        self.assertIsNotNone(self.index.read_revision(self.pid,"NewRecordedSpeech",1))

    def test_failed_interruption_journal_does_not_mask_capture_error(self):
        from unittest.mock import patch
        # A failure after the durable PREPARING reservation must retain the
        # original diagnostic even if the INTERRUPTED update also fails.
        with patch.object(OpenUSDTakeCapture, "freeze",
                          side_effect=RuntimeError("original capture failure")):
            with patch.object(self.capture.publications, "finish",
                              side_effect=OSError("journal storage unavailable")):
                with self.assertRaisesRegex(RuntimeError, "original capture failure") as caught:
                    self.capture.capture(**self.payload())
        self.assertTrue(any("journal storage unavailable" in note
                            for note in getattr(caught.exception, "__notes__", [])))
        # PREPARING remains recoverable; no false completed Take was created.
        unresolved=self.capture.publications.unresolved(self.pid)
        self.assertEqual(len(unresolved),1)
        self.assertEqual(unresolved[0]["state"],"PREPARING")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"FilmedTake",1)

    def test_recovery_interrupt_is_cas_and_preserves_frozen_sources(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        journal = FilmingPublicationJournal(self.index)
        journal.begin(self.pid, "RecoveryTake", "RecoveryTimeline", ["RecoveryPCM"])
        observed = journal.unresolved(self.pid)[0]
        with self.assertRaisesRegex(RuntimeError, "recovery state conflict"):
            journal.interrupt_preparing(
                self.pid, "RecoveryTake", expected_updated_at="stale-observation")
        self.assertEqual(journal.unresolved(self.pid)[0]["state"], "PREPARING")
        receipt = journal.interrupt_preparing(
            self.pid, "RecoveryTake", expected_updated_at=observed["updated_at"])
        self.assertEqual(receipt["state"], "INTERRUPTED")
        self.assertFalse(receipt["worker_termination_verified_by_journal"])
        self.assertFalse(receipt["immutable_revisions_modified"])
        with self.assertRaisesRegex(RuntimeError, "recovery state conflict"):
            journal.interrupt_preparing(
                self.pid, "RecoveryTake", expected_updated_at=observed["updated_at"])
        self.assertEqual(journal.visibility(self.pid, "RecoveryTake")["reason"],
                         "PUBLICATION_INTERRUPTED")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "RecoveryTake", 1)

    def test_recovery_cannot_demote_completed_publication(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        journal = FilmingPublicationJournal(self.index)
        with self.index.studio._connection() as db:
            row = db.execute("""SELECT updated_at FROM nvp_filming_publications
                WHERE project_id=? AND take_id=?""",
                (self.pid, "FilmedTake")).fetchone()
        original = self.index.read_revision(self.pid, "FilmedTake", 1)
        with self.assertRaisesRegex(RuntimeError, "recovery state conflict"):
            journal.interrupt_preparing(
                self.pid, "FilmedTake", expected_updated_at=row["updated_at"])
        self.assertTrue(journal.visibility(self.pid, "FilmedTake")["visible"])
        self.assertEqual(self.index.read_revision(self.pid, "FilmedTake", 1), original)

    def test_journaled_take_visibility_is_fail_closed(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        journal=FilmingPublicationJournal(self.index)
        self.assertEqual(journal.visibility(self.pid,"UnknownTake")["reason"],
                         "NO_JOURNAL_RECEIPT")
        self.assertFalse(journal.visibility(self.pid,"UnknownTake")["visible"])
        journal.begin(self.pid,"ReservedTake","ReservedTimeline",["ReservedSource"])
        pending=journal.visibility(self.pid,"ReservedTake")
        self.assertFalse(pending["visible"])
        self.assertEqual(pending["reason"],"PUBLICATION_PREPARING")
        journal.finish(self.pid,"ReservedTake",completed=False)
        self.assertEqual(journal.visibility(self.pid,"ReservedTake")["reason"],
                         "PUBLICATION_INTERRUPTED")
        self.capture.capture(**self.payload())
        completed=journal.visibility(self.pid,"FilmedTake")
        self.assertTrue(completed["journaled"])
        self.assertTrue(completed["visible"])
        self.assertEqual(completed["reason"],"COMPLETED_DEPENDENCIES_PRESENT")
        # Corrupt a journal reference, not the immutable historical source.
        with self.index.studio._connection() as db:
            db.execute("""UPDATE nvp_filming_publications
                SET source_ids_json=? WHERE project_id=? AND take_id=?""",
                ('["MissingOriginal"]',self.pid,"FilmedTake"))
        missing=journal.visibility(self.pid,"FilmedTake")
        self.assertFalse(missing["visible"])
        self.assertEqual(missing["reason"],"MISSING_IMMUTABLE_DEPENDENCY")
        self.assertIsNotNone(self.index.read_revision(self.pid,"NewRecordedSpeech",1))

    def test_completed_receipt_cannot_rebind_frozen_take_to_other_timeline(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        journal=FilmingPublicationJournal(self.index)
        original=self.index.read_revision(self.pid,"FilmedTake",1)
        # Existing camera timeline revision 1 is real, but it is not the
        # immutable sound timeline bound into the frozen Take manifest.
        with self.index.studio._connection() as db:
            db.execute("""UPDATE nvp_filming_publications
                SET sound_timeline_id=? WHERE project_id=? AND take_id=?""",
                ("FilmingCameraTimeline",self.pid,"FilmedTake"))
        decision=journal.visibility(self.pid,"FilmedTake")
        self.assertFalse(decision["visible"])
        self.assertEqual(decision["reason"],"PUBLICATION_BINDING_MISMATCH")
        reader=OpenUSDTakeCapture(self.index,verify_creator_action=lambda *_: False)
        with self.assertRaisesRegex(PermissionError,"PUBLICATION_BINDING_MISMATCH"):
            reader.verify_take(self.pid,"FilmedTake")
        self.assertEqual(self.index.read_revision(self.pid,"FilmedTake",1),original)
        self.assertIsNotNone(self.index.read_revision(self.pid,"NewRecordedSpeech",1))

    def test_completed_receipt_rejects_unbound_existing_original_source(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        # This source really exists, but the frozen sound timeline never
        # referenced it. Revision existence is not proof of a binding.
        self.capture.sources.publish(
            self.pid,"UnboundOriginalPCM",[self.original],expected_revision=0)
        with self.index.studio._connection() as db:
            db.execute("""UPDATE nvp_filming_publications
                SET source_ids_json=? WHERE project_id=? AND take_id=?""",
                ('["UnboundOriginalPCM"]',self.pid,"FilmedTake"))
        journal=FilmingPublicationJournal(self.index)
        decision=journal.visibility(self.pid,"FilmedTake")
        self.assertFalse(decision["visible"])
        self.assertEqual(decision["reason"],"PUBLICATION_SOURCE_BINDING_MISMATCH")
        reader=OpenUSDTakeCapture(self.index,verify_creator_action=lambda *_: False)
        with self.assertRaisesRegex(PermissionError,"PUBLICATION_SOURCE_BINDING_MISMATCH"):
            reader.verify_take(self.pid,"FilmedTake")
        self.assertIsNotNone(self.index.read_revision(self.pid,"NewRecordedSpeech",1))
        self.assertIsNotNone(self.index.read_revision(self.pid,"UnboundOriginalPCM",1))

    def test_visibility_rejects_invalid_original_recording_contract(self):
        from unittest.mock import patch
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        journal = FilmingPublicationJournal(self.index)
        original = TemporalLedger.events_in
        for field, invalid in (("source_sample_rate", 44100),
                               ("format", "unrelated.format"),
                               ("acoustic_mix_frozen", True)):
            def altered(ledger, *args, **kwargs):
                page = original(ledger, *args, **kwargs)
                events = []
                for event in page["events"]:
                    event = dict(event)
                    if event["event_kind"] in ("sound", "dialogue"):
                        event["payload"] = dict(event["payload"], **{field: invalid})
                    events.append(event)
                return dict(page, events=events)
            with self.subTest(field=field):
                with patch.object(TemporalLedger, "events_in", altered):
                    decision = journal.visibility(self.pid, "FilmedTake")
                self.assertFalse(decision["visible"])
                self.assertEqual(decision["reason"],
                                 "PUBLICATION_SOURCE_BINDING_MISMATCH")
        # Mocked reads must not rewrite immutable originals.
        self.assertTrue(journal.visibility(self.pid, "FilmedTake")["visible"])
        self.assertIsNotNone(self.index.read_revision(self.pid, "NewRecordedSpeech", 1))

    def test_visibility_rejects_non_native_or_flattened_source_manifest(self):
        from unittest.mock import patch
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        journal = FilmingPublicationJournal(self.index)
        original_read = self.index.read_revision
        for field, invalid in (("channels", 2),
                               ("sample_encoding", "float32"),
                               ("flattened_soundtrack", True)):
            def altered(project_id, identity, revision):
                record = original_read(project_id, identity, revision)
                if identity == "NewRecordedSpeech":
                    record = dict(record)
                    record["data"] = dict(record["data"], **{field: invalid})
                return record
            with self.subTest(field=field):
                with patch.object(self.index, "read_revision", side_effect=altered):
                    decision = journal.visibility(self.pid, "FilmedTake")
                self.assertFalse(decision["visible"])
                self.assertEqual(decision["reason"],
                                 "PUBLICATION_SOURCE_BINDING_MISMATCH")
        self.assertTrue(journal.visibility(self.pid, "FilmedTake")["visible"])
        self.assertIsNotNone(original_read(self.pid, "NewRecordedSpeech", 1))

    def test_visibility_rejects_sound_event_source_hash_substitution(self):
        from unittest.mock import patch
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        journal = FilmingPublicationJournal(self.index)
        original_events = TemporalLedger.events_in
        original_source = self.index.read_revision(
            self.pid, "NewRecordedSpeech", 1)
        original_take = self.index.read_revision(self.pid, "FilmedTake", 1)

        def substituted(ledger, *args, **kwargs):
            page = original_events(ledger, *args, **kwargs)
            events = []
            for event in page["events"]:
                event = dict(event)
                if event["event_kind"] in ("sound", "dialogue"):
                    event["source_document_sha256"] = "0" * 64
                events.append(event)
            return dict(page, events=events)

        with patch.object(TemporalLedger, "events_in", substituted):
            decision = journal.visibility(self.pid, "FilmedTake")
        self.assertFalse(decision["visible"])
        self.assertEqual(decision["reason"],
                         "PUBLICATION_SOURCE_BINDING_MISMATCH")
        self.assertTrue(journal.visibility(self.pid, "FilmedTake")["visible"])
        self.assertEqual(self.index.read_revision(
            self.pid, "NewRecordedSpeech", 1), original_source)
        self.assertEqual(self.index.read_revision(
            self.pid, "FilmedTake", 1), original_take)

    def test_take_reader_refuses_incomplete_journaled_publication(self):
        from backend.nvp_filming_publication_journal import FilmingPublicationJournal
        self.capture.capture(**self.payload())
        reader=OpenUSDTakeCapture(self.index,verify_creator_action=lambda *_: False)
        # A complete filming publication remains independently verifiable.
        self.assertIsNotNone(reader.verify_take(self.pid,"FilmedTake"))
        # Model restart after a partial journal transition. Immutable Take and
        # original PCM still exist, but must not be exposed by the reader.
        with self.index.studio._connection() as db:
            db.execute("""UPDATE nvp_filming_publications SET state='PREPARING'
                WHERE project_id=? AND take_id=?""",(self.pid,"FilmedTake"))
        with self.assertRaisesRegex(PermissionError,"PUBLICATION_PREPARING"):
            reader.verify_take(self.pid,"FilmedTake")
        with self.index.studio._connection() as db:
            db.execute("""UPDATE nvp_filming_publications SET state='COMPLETED',
                source_ids_json=? WHERE project_id=? AND take_id=?""",
                ('["MissingOriginal"]',self.pid,"FilmedTake"))
        with self.assertRaisesRegex(PermissionError,"MISSING_IMMUTABLE_DEPENDENCY"):
            reader.verify_take(self.pid,"FilmedTake")
        self.assertIsNotNone(self.index.read_revision(self.pid,"FilmedTake",1))
        self.assertIsNotNone(self.index.read_revision(self.pid,"NewRecordedSpeech",1))

    def test_pcm_callback_cannot_rewrite_preflighted_recording_gain(self):
        req=self.payload()
        event=req["recordings"][0]
        original_chunks=event["pcm_chunks"]
        def mutating_chunks():
            event["gain"]=2.0
            yield from original_chunks
        event["pcm_chunks"]=mutating_chunks()
        self.capture.capture(**req)
        page=TemporalLedger(self.index).events_in(
            self.pid,"FilmingSoundTimeline",1,start_tick=0,
            end_tick=int(req["recordings"][0]["end_tick"]),limit=100)
        sound=[e for e in page["events"] if e["event_kind"] in ("sound","dialogue")]
        self.assertEqual(len(sound),1)
        self.assertEqual(sound[0]["payload"]["gain"],1.0)

    def test_capture_refuses_extra_pcm_outside_exact_event_extent(self):
        req=self.payload()
        # The source is longer than its one-second Film Time event.
        # Previously the surplus sample was silently admitted to the
        # immutable original, leaving event extent and source length at odds.
        req["recordings"][0]["pcm_chunks"]=[self.original, bytes(2)]
        with self.assertRaisesRegex(ValueError,"sample count does not match"):
            self.capture.capture(**req)
        for identity in ("NewRecordedSpeech","FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)
        self.assertEqual(self.capture.publications.unresolved(self.pid),[])

    def test_surplus_pcm_stops_stream_before_later_chunks_are_consumed(self):
        req=self.payload()
        consumed=[]
        def recorder():
            yield self.original
            yield bytes(2)
            consumed.append("unexpected later chunk")
            yield bytes(2)
        req["recordings"][0]["pcm_chunks"]=recorder()
        with self.assertRaisesRegex(ValueError,"sample count does not match"):
            self.capture.capture(**req)
        self.assertEqual(consumed,[])
        for identity in ("NewRecordedSpeech","FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)
        self.assertEqual(self.capture.publications.unresolved(self.pid),[])

    def test_capture_preflights_pcm_stream_without_publication(self):
        req=self.payload()
        req["recordings"][0]["pcm_chunks"]=None
        with self.assertRaisesRegex(ValueError,"PCM chunks must be iterable"):
            self.capture.capture(**req)
        for identity in ("NewRecordedSpeech","FilmingSoundTimeline","FilmedTake"):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,identity,1)
        self.assertEqual(self.capture.publications.unresolved(self.pid),[])

    def test_capture_rejects_unknown_world_emitter(self):
        req=self.payload()
        req["recordings"][0]["usd_prim_path"]="/World/NotThere"
        with self.assertRaises(RuntimeError):
            self.capture.capture(**req)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"NewRecordedSpeech",1)


if __name__=="__main__":
    unittest.main()
