"""WO4-LF02 deterministic unit acceptance, real FilmIndex/Take, mocked codecs.

Mock boundaries here are deliberately NOT real OpenJPEG/MXF acceptance.
They validate the durable supervisor journal, source SHA mapping, ordered
checkpoints, staged crash/restart safety and no automatic deletion.
"""
from hashlib import sha256
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from test_nvp_wo3_native_delivery import (
    WO3OriginalCinemaAuthoring,synthetic_header)
from backend.nvp_production_cinema import CinemaJournal
from backend.nvp_production_supervisor import ProductionSupervisor,SingletonSupervisor
from backend.nvp_wo4_pcm_master import master_pcm24_candidate
from backend.nvp_wo4_master_qc import evaluate_master_candidates
from backend.nvp_wo4_mastering_decision import register_mastering_decision
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_wo3_j2k_audit import PROFILES


class PictureReelJournalTest(unittest.TestCase):
    def setUp(self):
        fixture=WO3OriginalCinemaAuthoring(
            "test_real_smpte_package_metadata_is_written_and_reopened")
        fixture.setUp()
        self.addCleanup(fixture.tmp.cleanup)
        self.f=fixture
        self.root=Path(fixture.tmp.name).resolve()
        self.journal=CinemaJournal(self.root/"production")
        self.profile="2K_FLAT_24"
        self.profile_patch=patch.dict(PROFILES,{self.profile:(2,1,24)})
        self.profile_patch.start()
        self.addCleanup(self.profile_patch.stop)
        self.pictures=[]
        self.files=[]
        for n in (1,2,3):
            pix=(n.to_bytes(2,"big")*3)*2
            image={"format":"nvp.wo4.xyz12_master_candidate.v1",
                   "original_take_sha256":fixture.sha,
                   "xyz12":pix,"xyz12_sha256":sha256(pix).hexdigest(),
                   "profile":self.profile,"width":2,"height":1,
                   "source_modified":False,
                   "production_picture_accepted":False}
            self.pictures.append(image)
            source=self.root/f"original_source_{n}.xyz12"
            source.write_bytes(pix)
            self.files.append(str(source))
        samples=b"\x00\x00\x00\x03\x00\x00"*6000
        sound=master_pcm24_candidate(
            samples,source_sha256=sha256(samples).hexdigest(),
            original_take_sha256=fixture.sha,cinema_frames=3,
            channel_layout="stereo",creator_approved=True)
        qc=evaluate_master_candidates(self.pictures[0],sound)
        self.decision=register_mastering_decision(
            fixture.index,fixture.pid,take_id="FrozenFixture",
            take_revision=1,take_sha256=fixture.sha,
            picture=self.pictures[0],ordered_pictures=self.pictures,
            sound=sound,qc=qc,decision_id="ProductionPictureApproval",
            approve=lambda _:True)
        exe=Path(sys.executable).resolve(strict=True)
        digest=digest_file(exe)
        self.codec=ApprovedCodecBinary(
            exe,sha256=digest,product="OpenJPEG-opj_compress")
        self.wrap=ApprovedCodecBinary(
            exe,sha256=digest,product="ASDCP-asdcp_wrap")
        self.info=ApprovedCodecBinary(
            exe,sha256=digest,product="ASDCP-asdcp_info")

    def submit(self,frame_sources=None,approve=lambda _:True):
        return self.journal.submit_reel(
            self.f.index,self.f.pid,
            mastering_decision_id="ProductionPictureApproval",
            frame_sources=self.files if frame_sources is None else frame_sources,
            openjpeg=self.codec,wrapper=self.wrap,info=self.info,
            approve=approve)

    def test_exact_source_master_and_creator_scope_binding(self):
        self.assertEqual(self.submit(approve=lambda _:False)["status"],"DENIED")
        self.assertEqual(self.journal.list_jobs(),[])
        result=self.submit()
        status=self.journal.status(result["job_id"])
        self.assertEqual(status["task_kind"],
                         "ENCODE_APPROVED_XYZ12_PICTURE_REEL_V1")
        self.assertEqual(status["total_segments"],3)
        self.assertEqual(status["segments"][0]["start_tick"],0)
        self.assertEqual(status["segments"][1]["start_tick"],294000000)
        self.assertFalse(status["production_dcp_accepted"])
        self.assertEqual(self.journal.reel(result["job_id"])["take_sha256"],
                         self.f.sha)
        self.assertEqual(self.f.index.read_revision(
            self.f.pid,"FrozenFixture",1)["document_sha256"],self.f.sha)

    def test_reordered_or_changed_source_refused(self):
        with self.assertRaises(PermissionError):
            self.submit(frame_sources=self.files[::-1])
        self.files and Path(self.files[1]).write_bytes(bytes(12))
        with self.assertRaises(PermissionError):
            self.submit()
        self.assertEqual(self.journal.list_jobs(),[])

    def test_three_real_durable_checkpoints_with_mocked_codec_only(self):
        job_id=self.submit()["job_id"]
        raw=synthetic_header(width=2,height=1)
        hash_value=sha256(raw).hexdigest()
        def mock_encode(codec,*,private_work,source_sha256,**kwargs):
            (Path(private_work)/"frame.j2c").write_bytes(raw)
            return {"status":"ENCODED_J2K_STAGE_VERIFIED",
                    "source_sha256":source_sha256,
                    "native_codec_sha256":codec.sha256,
                    "codestream_sha256":hash_value,
                    "codestream_bytes":len(raw)}
        def mock_track(wrap,info,*,stage_dir,asset_uuid,**kwargs):
            data=b"TEST ONLY NOT REAL MXF"*16
            (Path(stage_dir)/"picture.mxf").write_bytes(data)
            return {"status":"NATIVE_PICTURE_MXF_STAGE_VERIFIED",
                    "file_sha256":sha256(data).hexdigest(),
                    "file_bytes":len(data),"asset_uuid":asset_uuid,
                    "wrapper_sha256":wrap.sha256,"info_sha256":info.sha256}
        with SingletonSupervisor(self.journal.root), patch(
             "backend.nvp_production_supervisor.encode_disk_xyz12",
             side_effect=mock_encode), patch(
             "backend.nvp_production_supervisor.wrap_disk_j2k_picture",
             side_effect=mock_track):
            runner=ProductionSupervisor(self.journal)
            for position in range(3):
                result=runner.run_one()
                self.assertEqual(result["status"],
                                 "PICTURE_FRAME_CHECKPOINTED",result)
                self.assertEqual(result["position"],position)
                self.assertEqual(self.journal.status(job_id)["verified_segments"],
                                 position+1)
                self.assertEqual(len(self.journal.events(job_id)),position*2+3)
            track=runner.run_one()
            self.assertEqual(track["status"],"FILE_BACKED_PICTURE_MXF_READY")
            self.assertEqual(self.journal.status(job_id)["state"],"OUTPUT_READY")
            self.assertFalse(track["production_dcp_accepted"])
            self.assertTrue(Path(track["path"]).is_file())
        self.assertEqual(self.journal.cinema_reconcile()["jobs"][0]["status"],
                         "RECONCILED")
        self.assertEqual(self.journal.status(job_id)["state"],"OUTPUT_READY")

    def test_killed_worker_with_uncommitted_stage_never_autopublishes(self):
        job=self.submit()["job_id"]
        segment=self.journal.claim_next("KilledEncoder",12345)
        self.assertEqual(segment["position"],0)
        work=self.journal.spool(job)/"frame-work"/"000000"
        work.mkdir(parents=True)
        (work/"frame.ppm").write_bytes(b"half-made disposable stage")
        report=self.journal.cinema_reconcile()
        self.assertEqual(report["jobs"][0]["status"],"REVIEW_REQUIRED")
        self.assertEqual(self.journal.status(job)["state"],"REVIEW_REQUIRED")
        self.assertEqual((work/"frame.ppm").read_bytes(),
                         b"half-made disposable stage")
        self.assertEqual(self.journal.cinema_reconcile()["jobs"][0]["status"],
                         "REVIEW_REQUIRED")

    def test_explicit_review_quarantines_stage_then_requeues_without_deleting(self):
        job=self.submit()["job_id"]
        self.journal.claim_next("InterruptedEncoder",876)
        stage=self.journal.spool(job)/"frame-work"/"000000"
        stage.mkdir(parents=True)
        (stage/"frame.ppm").write_bytes(b"KEEP_CREATOR_EVIDENCE")
        self.journal.cinema_reconcile()
        self.assertEqual(self.journal.approve_rebuild_uncommitted(
            job,lambda _:False)["status"],"DENIED")
        self.assertTrue(stage.exists())
        result=self.journal.approve_rebuild_uncommitted(
            job,lambda scope:scope["preserve_all_uncommitted_files"] is True)
        self.assertEqual(result["status"],"QUEUED")
        self.assertEqual(result["requeued_frames"],3)
        self.assertFalse(stage.exists())
        self.assertEqual(self.journal.status(job)["state"],"QUEUED")
        reviewed=list((self.journal.spool(job)/"frame-work").glob(
            ".nvp-reviewed-000000-*"))
        self.assertEqual(len(reviewed),1)
        self.assertEqual((reviewed[0]/"frame.ppm").read_bytes(),
                         b"KEEP_CREATOR_EVIDENCE")

    def test_output_without_receipt_is_preserved_in_review_quarantine(self):
        job=self.submit()["job_id"]
        self.journal.claim_next("PostLinkCrash",222)
        frame=self.journal.spool(job)/"frames"/"000000.j2c"
        frame.parent.mkdir(parents=True)
        original=synthetic_header(width=2,height=1)
        frame.write_bytes(original)
        self.journal.cinema_reconcile()
        result=self.journal.approve_rebuild_uncommitted(job,lambda _:True)
        self.assertEqual(result["status"],"QUEUED")
        self.assertFalse(frame.exists())
        reviewed=list(frame.parent.glob(".nvp-reviewed-000000.j2c-*"))
        self.assertEqual(len(reviewed),1)
        self.assertEqual(reviewed[0].read_bytes(),original)
        self.assertEqual(self.journal.status(job)["verified_segments"],0)

    def test_rebuild_refuses_changed_original_source_without_data_loss(self):
        job=self.submit()["job_id"]
        self.journal.claim_next("FailedEncoder",1357)
        stage=self.journal.spool(job)/"frame-work"/"000000"
        stage.mkdir(parents=True)
        (stage/"frame.ppm").write_bytes(b"evidence")
        self.journal.cinema_reconcile()
        Path(self.files[1]).write_bytes(b"changed source")
        with self.assertRaises(PermissionError):
            self.journal.approve_rebuild_uncommitted(job,lambda _:True)
        self.assertTrue((stage/"frame.ppm").exists())
        self.assertEqual(self.journal.status(job)["state"],"REVIEW_REQUIRED")

    def test_claim_after_crash_with_no_stage_may_safely_requeue(self):
        job=self.submit()["job_id"]
        self.journal.claim_next("KilledBeforeStart",12345)
        report=self.journal.cinema_reconcile()
        self.assertEqual(report["jobs"][0]["interrupted_requeued"],[0])
        self.assertEqual(self.journal.status(job)["state"],"QUEUED")
        self.assertEqual(self.journal.status(job)["verified_segments"],0)

    def test_real_os_exit_after_uncommitted_stage_preserves_review_evidence(self):
        job=self.submit()["job_id"]
        source=(
            "import os,sys;"
            "from pathlib import Path;"
            "from backend.nvp_production_cinema import CinemaJournal;"
            "j=CinemaJournal(sys.argv[1]);"
            "s=j.claim_next('DiedDuringFrame',os.getpid());"
            "assert s is not None;"
            "p=j.spool(s['job_id'])/'frame-work'/'000000';"
            "p.mkdir(parents=True);"
            "(p/'frame.ppm').write_bytes(b'ORPHAN_UNCOMMITTED');"
            "os._exit(79)"
        )
        proc=subprocess.run(
            [sys.executable,"-c",source,str(self.journal.root)],
            cwd=str(Path(__file__).resolve().parents[1]),
            stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,79,proc.stderr[-800:])
        reopened=CinemaJournal(self.journal.root)
        evidence=reopened.cinema_reconcile()
        self.assertEqual(evidence["jobs"][0]["status"],"REVIEW_REQUIRED")
        orphan=reopened.spool(job)/"frame-work"/"000000"/"frame.ppm"
        self.assertEqual(orphan.read_bytes(),b"ORPHAN_UNCOMMITTED")
        self.assertEqual(reopened.status(job)["verified_segments"],0)
        self.assertEqual(reopened.status(job)["state"],"REVIEW_REQUIRED")

    def test_explicit_cancel_during_frame_refuses_output_checkpoint(self):
        job=self.submit()["job_id"]
        def cancelled_encode(codec,*,private_work,check_cancel,**kwargs):
            self.assertEqual(self.journal.request_cancel(
                job,lambda scope:scope["job_id"]==job)["status"],
                "CANCEL_REQUESTED")
            self.assertTrue(check_cancel())
            raise InterruptedError("Native worker abort after explicit cancellation")
        with SingletonSupervisor(self.journal.root), patch(
                "backend.nvp_production_supervisor.encode_disk_xyz12",
                side_effect=cancelled_encode):
            result=ProductionSupervisor(self.journal).run_one()
        self.assertEqual(result["status"],"CANCELLED")
        self.assertEqual(self.journal.status(job)["state"],"CANCELLED")
        self.assertEqual(self.journal.status(job)["verified_segments"],0)
        self.assertFalse((self.journal.spool(job)/"frames"/"000000.j2c").exists())

    def test_published_frame_without_sqlite_commit_requires_review(self):
        job=self.submit()["job_id"]
        self.journal.claim_next("KilledAfterPublish",12345)
        frames=self.journal.spool(job)/"frames"
        frames.mkdir(parents=True)
        (frames/"000000.j2c").write_bytes(synthetic_header(width=2,height=1))
        result=self.journal.cinema_reconcile()
        self.assertEqual(result["jobs"][0]["status"],"REVIEW_REQUIRED")
        self.assertTrue((frames/"000000.j2c").is_file())
        self.assertEqual(self.journal.status(job)["verified_segments"],0)


if __name__=="__main__":
    unittest.main()
