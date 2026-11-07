"""WO4 durable supervised sound+file-backed DCP acceptance with mock MXF.

Actual FilmIndex/SQLite and SMPTE PKL hashes are real here. Native encoder
boundaries are deliberately mocked: this suite proves durable state, consent,
cancellation, source preservation and crash/ledger recovery only. The native
OpenJPEG/CineCert roundtrip runs separately in real-cinema workflow.
"""
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import unittest

from test_nvp_production_cinema import PictureReelJournalTest,synthetic_header
from backend.nvp_production_supervisor import ProductionSupervisor,SingletonSupervisor
from backend.nvp_wo4_delivery_journal import CinemaDeliveryJournal
from backend.nvp_wo4_pcm_stream import stream_master_pcm24_candidate
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo4_file_dcp import publish_file_backed_dcp
from backend.nvp_wo3_native_codecs import digest_file


class DurableCinemaDeliveryTests(unittest.TestCase):
    def setUp(self):
        f=PictureReelJournalTest(
            "test_exact_source_master_and_creator_scope_binding")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.f=f
        self.root=f.root
        self.journal=CinemaDeliveryJournal(f.journal.root)
        f.journal=self.journal
        self.output=self.root/"approved_export"
        self.output.mkdir()
        self.raw=b"\x00\x00\x00\x03\x00\x00"*6000
        self.pcm=self.root/"mastered_native_sound.pcm"
        self.pcm.write_bytes(self.raw)
        self.original_pcm_sha=sha256(self.raw).hexdigest()
        self.wav=stream_master_pcm24_candidate(
            self.pcm,source_sha256=self.original_pcm_sha,
            original_take_sha256=f.f.sha,cinema_frames=3,
            channel_layout="stereo",output_root=self.output,
            approve=lambda _:True)

    def finish_picture(self):
        job=self.f.submit()["job_id"]
        codestream=synthetic_header(width=2,height=1)
        digest=sha256(codestream).hexdigest()
        def mock_frame(codec,*,private_work,source_sha256,**kw):
            (Path(private_work)/"frame.j2c").write_bytes(codestream)
            return {"status":"ENCODED_J2K_STAGE_VERIFIED",
                    "source_sha256":source_sha256,
                    "native_codec_sha256":codec.sha256,
                    "codestream_sha256":digest,
                    "codestream_bytes":len(codestream)}
        def mock_picture(wrap,info,*,stage_dir,asset_uuid,**kw):
            data=b"MOCK PICTURE ESSENCE NOT REAL MXF"*16
            (Path(stage_dir)/"picture.mxf").write_bytes(data)
            return {"status":"NATIVE_PICTURE_MXF_STAGE_VERIFIED",
                    "file_sha256":sha256(data).hexdigest(),
                    "file_bytes":len(data),"asset_uuid":asset_uuid,
                    "wrapper_sha256":wrap.sha256,"info_sha256":info.sha256}
        with SingletonSupervisor(self.journal.root), patch(
             "backend.nvp_production_supervisor.encode_disk_xyz12",
             side_effect=mock_frame),patch(
             "backend.nvp_production_supervisor.wrap_disk_j2k_picture",
             side_effect=mock_picture):
            runner=ProductionSupervisor(self.journal)
            for _ in range(3):
                self.assertEqual(runner.run_one()["status"],
                                 "PICTURE_FRAME_CHECKPOINTED")
            self.assertEqual(runner.run_one()["status"],
                             "FILE_BACKED_PICTURE_MXF_READY")
        self.assertEqual(self.journal.status(job)["state"],"OUTPUT_READY")
        return job

    def attach(self,job,approve=lambda _:True):
        return self.journal.attach_delivery(
            self.f.f.index,job,sound_candidate=self.wav,
            output_root=self.output,title="Test Original Film",
            approve=approve)

    def run_sound_mock(self):
        def sound(wrap,info,*,stage_dir,source_take_sha,
                  candidate,frames,sound_uuid,**kw):
            data=b"MOCK SOUND ESSENCE NOT REAL MXF"*16
            (Path(stage_dir)/"sound.mxf").write_bytes(data)
            return {"status":"SOUND_MXF_STAGE_VERIFIED",
                    "asset_uuid":sound_uuid,
                    "original_take_sha256":source_take_sha,
                    "frame_count":frames,
                    "master_pcm_sha256":candidate["master_pcm_sha256"],
                    "source_master_wav_sha256":candidate["wav_file_sha256"],
                    "wrapper_sha256":wrap.sha256,
                    "info_sha256":info.sha256,
                    "file_sha256":sha256(data).hexdigest(),
                    "file_bytes":len(data)}
        with SingletonSupervisor(self.journal.root),patch(
            "backend.nvp_production_supervisor.wrap_supervised_sound",
            side_effect=sound):
            return ProductionSupervisor(self.journal).run_one()

    def run_package(self):
        with SingletonSupervisor(self.journal.root):
            return ProductionSupervisor(self.journal).run_one()

    def test_project_approval_is_separate_from_picture_approval(self):
        job=self.finish_picture()
        self.assertEqual(self.attach(job,approve=lambda _:False)["status"],"DENIED")
        with self.assertRaises(KeyError):
            self.journal.delivery(job)
        result=self.attach(job)
        self.assertEqual(result["status"],"SOUND_PENDING")
        with self.assertRaises(FileExistsError):
            self.attach(job)
        self.assertEqual(self.journal.status(job)["state"],"OUTPUT_READY")

    def test_sound_dcp_filmindex_and_reopened_journal_end_to_end(self):
        job=self.finish_picture()
        self.attach(job)
        self.assertEqual(self.run_sound_mock()["status"],
                         "FILE_BACKED_SOUND_MXF_READY")
        self.assertEqual(self.journal.delivery(job)["phase"],"SOUND_READY")
        package=self.run_package()
        self.assertEqual(package["status"],"PUBLISHED_PENDING_INDEX")
        folder=Path(package["destination"])
        self.assertEqual(inspect_dcp_structure(folder)["status"],
                         "STRUCTURE_AND_SHA_VERIFIED")
        self.assertEqual(self.journal.delivery(job)["phase"],
                         "PUBLISHED_PENDING_INDEX")
        reopened=CinemaDeliveryJournal(self.journal.root)
        reopened.reconcile_after_restart()
        reopened.cinema_reconcile()
        reopened.delivery_reconcile()
        self.assertEqual(reopened.delivery(job)["phase"],"PUBLISHED_PENDING_INDEX")
        with SingletonSupervisor(reopened.root):
            indexed=ProductionSupervisor(reopened).run_one()
        self.assertEqual(indexed["status"],"STRUCTURAL_DCP_FILMINDEX_RECORDED")
        self.assertEqual(reopened.delivery(job)["phase"],"INDEXED")
        self.assertEqual(reopened.status(job)["state"],"DCP_INDEXED")
        self.assertFalse(indexed["production_dcp_accepted"])
        d=reopened.delivery(job)
        record=self.f.f.index.read_revision(
            self.f.f.pid,"WO3DCP_"+d["cpl_uuid"].replace("-",""),1)
        self.assertEqual(record["data"]["file_sha256"],
                         __import__("json").loads(d["dcp_files_json"]))
        self.assertEqual(record["data"]["original_take_sha256"],self.f.f.sha)
        self.assertEqual(sha256(self.pcm.read_bytes()).hexdigest(),
                         self.original_pcm_sha)
        self.assertFalse(list(self.output.glob(".nvp-wo4-dcp-stage-*")))

    def test_cancel_during_native_sound_does_not_checkpoint(self):
        job=self.finish_picture()
        self.attach(job)
        def cancel(*args,**kwargs):
            self.assertEqual(self.journal.request_delivery_cancel(
                job,lambda _:False)["status"],"DENIED")
            self.assertEqual(self.journal.request_delivery_cancel(
                job,lambda _:True)["status"],"CANCEL_REQUESTED")
            raise InterruptedError("Native codec observed authenticated cancellation")
        with SingletonSupervisor(self.journal.root),patch(
            "backend.nvp_production_supervisor.wrap_supervised_sound",
            side_effect=cancel):
            result=ProductionSupervisor(self.journal).run_one()
        self.assertEqual(result["status"],"CANCELLED")
        self.assertEqual(self.journal.status(job)["state"],"CANCELLED")
        self.assertFalse((self.journal.spool(job)/"sound.mxf").exists())
        self.assertEqual(sha256(self.pcm.read_bytes()).hexdigest(),
                         self.original_pcm_sha)

    def test_crash_after_dcp_promotion_without_ledger_commit_needs_review(self):
        job=self.finish_picture()
        self.attach(job)
        self.run_sound_mock()
        claim=self.journal.next_delivery("CrashAtPromotion",28765)
        self.assertEqual(claim["stage"],"PACKAGE_RUNNING")
        reel=self.journal.reel(job)
        root=self.journal.spool(job)
        picture={"kind":"picture","asset_uuid":reel["picture_uuid"],
                 "source_take_sha256":reel["take_sha256"],
                 "file_path":str(root/"picture.mxf"),
                 "file_sha256":reel["track_sha256"],
                 "file_bytes":reel["track_bytes"],
                 "profile":reel["profile"],"frame_count":3,
                 "edit_rate":[24,1],"source_modified":False,
                 "production_dcp_accepted":False}
        sound={"kind":"sound","asset_uuid":claim["sound_uuid"],
               "source_take_sha256":reel["take_sha256"],
               "file_path":str(root/"sound.mxf"),
               "file_sha256":claim["sound_sha256"],
               "file_bytes":claim["sound_bytes"],
               "frame_count":3,"edit_rate":[24,1],
               "source_modified":False,"production_dcp_accepted":False}
        ids={"picture":reel["picture_uuid"],"sound":claim["sound_uuid"],
             "cpl":claim["cpl_uuid"],"pkl":claim["pkl_uuid"],
             "assetmap":claim["assetmap_uuid"],"reel":claim["reel_uuid"]}
        published=publish_file_backed_dcp(
            job_id=job,picture=picture,sound=sound,
            title=claim["title"],profile=reel["profile"],frames=3,
            output_root=self.output,ids=ids,check_cancel=lambda:False)
        self.assertTrue(Path(published["destination"]).is_dir())
        # No matching journal commit: cannot silently reuse as accepted.
        self.journal.cinema_reconcile()
        result=self.journal.delivery_reconcile()
        self.assertEqual(result["jobs"][0]["phase"],"REVIEW_REQUIRED")
        self.assertTrue(Path(published["destination"]).is_dir())
        self.assertEqual(self.journal.status(job)["state"],"REVIEW_REQUIRED")

    def test_published_package_does_not_hide_later_source_frame_tampering(self):
        job=self.finish_picture()
        self.attach(job)
        self.run_sound_mock()
        self.assertEqual(self.run_package()["status"],"PUBLISHED_PENDING_INDEX")
        original=Path(self.f.files[1])
        original.write_bytes(bytes(original.stat().st_size))
        with self.assertRaises(PermissionError):
            self.journal.commit_filmindex(job)
        self.assertEqual(self.journal.delivery(job)["phase"],
                         "PUBLISHED_PENDING_INDEX")
        folder=self.output/("DCP_"+self.journal.delivery(job)["cpl_uuid"])
        self.assertTrue(folder.is_dir())
        self.assertEqual(inspect_dcp_structure(folder)["status"],
                         "STRUCTURE_AND_SHA_VERIFIED")
        record_id="WO3DCP_"+self.journal.delivery(job)["cpl_uuid"].replace("-","")
        self.assertEqual(self.f.f.index.history(self.f.f.pid,record_id),[])

    def test_published_package_does_not_hide_approved_wav_tampering(self):
        job=self.finish_picture()
        self.attach(job)
        self.run_sound_mock()
        self.assertEqual(self.run_package()["status"],"PUBLISHED_PENDING_INDEX")
        wav=Path(self.wav["destination"])
        original=wav.read_bytes()
        wav.write_bytes(original[:-3]+b"\x00\x00\x00")
        with self.assertRaises(PermissionError):
            self.journal.commit_filmindex(job)
        self.assertEqual(self.journal.delivery(job)["phase"],
                         "PUBLISHED_PENDING_INDEX")
        self.assertTrue((self.output/(
            "DCP_"+self.journal.delivery(job)["cpl_uuid"])).exists())

    def test_post_filmindex_pre_journal_crash_retries_without_duplicate_revision(self):
        job=self.finish_picture()
        self.attach(job)
        self.run_sound_mock()
        self.assertEqual(self.run_package()["status"],"PUBLISHED_PENDING_INDEX")
        with patch.object(self.journal,"_tx",
                          side_effect=RuntimeError("simulated crash after FilmIndex")):
            with self.assertRaisesRegex(RuntimeError,"simulated crash"):
                self.journal.commit_filmindex(job)
        record="WO3DCP_"+self.journal.delivery(job)["cpl_uuid"].replace("-","")
        self.assertEqual(len(self.f.f.index.history(self.f.f.pid,record)),1)
        self.assertEqual(self.journal.delivery(job)["phase"],
                         "PUBLISHED_PENDING_INDEX")
        indexed=self.journal.commit_filmindex(job)
        self.assertEqual(indexed["status"],"STRUCTURAL_DCP_FILMINDEX_RECORDED")
        self.assertEqual(len(self.f.f.index.history(self.f.f.pid,record)),1)
        self.assertEqual(self.journal.delivery(job)["phase"],"INDEXED")


if __name__=="__main__":
    unittest.main()
