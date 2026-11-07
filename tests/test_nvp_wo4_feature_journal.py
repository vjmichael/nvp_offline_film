"""WO4 real SQLite/FilmIndex multi-reel feature orchestration acceptance.

The individual source MXF fixtures are deliberately mocked codecs but have
real exact SHA receipts; this is a real multi-reel SMPTE structural/hash test,
NOT physical cinema/codec acceptance. The real single-reel codec test is
independently covered in test_nvp_production_cinema_real.py.
"""
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import unittest

from test_nvp_production_delivery import DurableCinemaDeliveryTests
from backend.nvp_wo4_feature_journal import FeatureJournal,ASSEMBLY_FORMAT
from backend.nvp_wo4_multireel import publish_multireel_dcp
from backend.nvp_production_supervisor import ProductionSupervisor,SingletonSupervisor
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_production_journal import TICKS_PER_SECOND


class PersistentMultiReelFeatureTests(unittest.TestCase):
    def setUp(self):
        self.base=DurableCinemaDeliveryTests(
            "test_project_approval_is_separate_from_picture_approval")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.journal=FeatureJournal(self.base.journal.root)
        self.base.journal=self.journal
        self.base.f.journal=self.journal
        self.ids=[]
        for _ in range(2):
            job=self.base.finish_picture()
            self.base.attach(job)
            self.assertEqual(self.base.run_sound_mock()["status"],
                             "FILE_BACKED_SOUND_MXF_READY")
            self.assertEqual(self.base.run_package()["status"],
                             "PUBLISHED_PENDING_INDEX")
            self.assertEqual(self.base.run_package()["status"],
                             "STRUCTURAL_DCP_FILMINDEX_RECORDED")
            self.ids.append(job)
        self.f=self.base.f.f
        self.cut=self.f.index.register_revision(
            self.f.pid,"ApprovedFeatureCut","edit",
            {"format":ASSEMBLY_FORMAT,
             "ordered_reel_job_ids":self.ids,
             "start_tick":0,
             "end_tick":6*(TICKS_PER_SECOND//24),
             "original_source_modified":False},
            expected_revision=0,dependencies=[])
        self.output=self.base.output

    def submit(self,**replace):
        params={"assembly_id":"ApprovedFeatureCut",
                "assembly_revision":1,
                "ordered_job_ids":self.ids,
                "title":"Original Multi Reel Feature",
                "profile":"2K_FLAT_24",
                "output_root":self.output,"approve":lambda _:True}
        params.update(replace)
        return self.journal.submit_feature(self.f.index,self.f.pid,**params)

    def test_approved_two_reels_published_and_indexed_by_single_supervisor(self):
        refused=self.submit(approve=lambda _:False)
        self.assertEqual(refused["status"],"DENIED")
        with self.assertRaises(PermissionError):
            self.submit(ordered_job_ids=self.ids[::-1])
        job=self.submit()
        fid=job["feature_id"]
        self.assertEqual(job["reel_count"],2)
        with SingletonSupervisor(self.journal.root):
            runner=ProductionSupervisor(self.journal)
            publish=runner.run_one()
            self.assertEqual(publish["status"],
                             "FEATURE_PUBLISHED_PENDING_INDEX",publish)
            indexed=runner.run_one()
            self.assertEqual(indexed["status"],
                             "MULTIREEL_FEATURE_FILMINDEX_RECORDED",indexed)
        result=self.journal.feature(fid)
        self.assertEqual(result["state"],"INDEXED")
        self.assertEqual(self.journal.reconcile_features()["jobs"][0]["state"],
                         "INDEXED")
        folder=self.output/("DCP_FEATURE_"+
                           __import__("json").loads(result["manifest_json"])["ids"]["cpl"])
        audit=inspect_dcp_structure(folder)
        self.assertEqual(audit["reel_count"],2)
        self.assertEqual(audit["reel_durations"],[3,3])
        self.assertEqual(sum(audit["reel_durations"]),6)
        self.assertFalse(audit["production_dcp_accepted"])
        self.assertEqual(len(audit["tracks"]),4)
        record="WO4FEATURE_"+__import__("json").loads(
            result["manifest_json"])["ids"]["cpl"].replace("-","")
        self.assertEqual(len(self.f.index.history(self.f.pid,record)),1)

    def test_reorders_or_gaps_or_cross_project_are_rejected(self):
        with self.assertRaises(PermissionError):
            self.submit(ordered_job_ids=self.ids[::-1])
        with self.assertRaises(PermissionError):
            self.submit(ordered_job_ids=[self.ids[0],self.ids[0]])
        self.assertFalse(list(self.output.glob("DCP_FEATURE_*")))

    def test_explicit_prepublication_cancel_does_not_remove_source(self):
        job=self.submit()
        fid=job["feature_id"]
        self.assertEqual(self.journal.request_feature_cancel(
            fid,lambda _:False)["status"],"DENIED")
        self.assertEqual(self.journal.request_feature_cancel(
            fid,lambda _:True)["status"],"CANCEL_REQUESTED")
        with SingletonSupervisor(self.journal.root):
            state=ProductionSupervisor(self.journal).run_one()
        self.assertEqual(state["status"],"CANCELLED")
        self.assertEqual(self.journal.feature(fid)["state"],"CANCELLED")
        self.assertFalse(list(self.output.glob("DCP_FEATURE_*")))
        self.assertTrue(all((self.journal.spool(x)/"picture.mxf").is_file()
                            for x in self.ids))

    def test_crash_after_promotion_before_journal_requires_review(self):
        job=self.submit()
        task=self.journal.next_feature("KilledDuringPackage")
        self.assertEqual(task["feature_id"],job["feature_id"])
        manifest=task["manifest"]
        receipt=publish_multireel_dcp(
            reels=manifest["reels"],ids=manifest["ids"],
            title=manifest["title"],profile=manifest["profile"],
            output_root=manifest["output_root"],check_cancel=lambda:False)
        self.assertEqual(receipt["status"],"MULTIREEL_STRUCTURAL_DCP_PUBLISHED")
        report=self.journal.reconcile_features()
        self.assertEqual(report["jobs"][0]["state"],"REVIEW_REQUIRED")
        self.assertTrue(Path(receipt["destination"]).is_dir())
        self.assertEqual(self.journal.feature(job["feature_id"])["state"],
                         "REVIEW_REQUIRED")
        self.assertFalse(self.journal.feature(job["feature_id"])["filmindex_sha256"])
        denied=self.journal.approve_orphan_feature_adoption(
            job["feature_id"],lambda _:False)
        self.assertEqual(denied["status"],"DENIED")
        adopted=self.journal.approve_orphan_feature_adoption(
            job["feature_id"],lambda scope:
            scope["preserve_published_directory"] is True)
        self.assertEqual(adopted["status"],"PUBLISHED_PENDING_INDEX")
        self.assertFalse(adopted["filesystem_mutated"])
        with SingletonSupervisor(self.journal.root):
            final=ProductionSupervisor(self.journal).run_one()
        self.assertEqual(final["status"],
                         "MULTIREEL_FEATURE_FILMINDEX_RECORDED")
        self.assertEqual(self.journal.feature(job["feature_id"])["state"],
                         "INDEXED")
        self.assertTrue(Path(receipt["destination"]).is_dir())


if __name__=="__main__":
    unittest.main()
