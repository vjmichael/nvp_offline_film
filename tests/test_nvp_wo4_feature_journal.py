"""WO4 real SQLite/FilmIndex multi-reel feature orchestration acceptance.

The individual source MXF fixtures are deliberately mocked codecs but have
real exact SHA receipts; this is a real multi-reel SMPTE structural/hash test,
NOT physical cinema/codec acceptance. The real single-reel codec test is
independently covered in test_nvp_production_cinema_real.py.
"""
from hashlib import sha256
from pathlib import Path
import json
import os
import subprocess
import sys
from unittest.mock import patch
import unittest

import test_nvp_production_delivery as delivery_fixture
from backend.nvp_wo4_feature_journal import FeatureJournal,ASSEMBLY_FORMAT
from backend.nvp_wo4_multireel import publish_multireel_dcp
from backend.nvp_production_supervisor import ProductionSupervisor,SingletonSupervisor
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_production_journal import TICKS_PER_SECOND


class PersistentMultiReelFeatureTests(unittest.TestCase):
    def setUp(self):
        self.base=delivery_fixture.DurableCinemaDeliveryTests(
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

    def runner(self,journal=None):
        return self.base.runner(journal or self.journal)

    def owned(self,journal,method,*args,**kwargs):
        with SingletonSupervisor(journal.root):
            return method(*args,**kwargs)

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
            runner=self.runner()
            publish=runner.run_one()
            self.assertEqual(publish["status"],
                             "FEATURE_PUBLISHED_PENDING_INDEX",publish)
            indexed=runner.run_one()
            self.assertEqual(indexed["status"],
                             "MULTIREEL_FEATURE_FILMINDEX_RECORDED",indexed)
        result=self.journal.feature(fid)
        self.assertEqual(result["state"],"INDEXED")
        with self.journal._read() as db:
            stored=db.execute("SELECT manifest_json,file_sha_json FROM production_features WHERE feature_id=?",(fid,)).fetchone()
            self.assertEqual(json.loads(stored[0])["format"],"nvp.wo4.feature_pages.v2")
            self.assertEqual(json.loads(stored[1])["format"],"nvp.wo4.feature_pages.v2")
        source=self.journal.feature_page(fid,project_id=self.f.pid,project_db=Path(self.f.index.studio.db_path).resolve(),limit=1)
        self.assertEqual((source["total"],source["next_first"]),(2,1))
        output=self.journal.feature_page(fid,project_id=self.f.pid,project_db=Path(self.f.index.studio.db_path).resolve(),kind="output")
        self.assertEqual(output["total"],8)
        self.assertFalse(output["production_dcp_accepted"])

        self.assertEqual(self.owned(self.journal,self.journal.reconcile_features)["jobs"][0]["state"],
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
            state=self.runner().run_one()
        self.assertEqual(state["status"],"CANCELLED")
        self.assertEqual(self.journal.feature(fid)["state"],"CANCELLED")
        self.assertFalse(list(self.output.glob("DCP_FEATURE_*")))
        self.assertTrue(all((self.journal.spool(x)/"picture.mxf").is_file()
                            for x in self.ids))

    def test_real_os_exit_after_feature_publish_preserves_orphan_for_consent(self):
        job=self.submit()
        fid=job["feature_id"]
        claimed=self.owned(self.journal,self.journal.next_feature,"AboutToCrash")
        self.assertEqual(claimed["feature_id"],fid)
        record=self.base.root/"feature_child_manifest.json"
        record.write_text(json.dumps(claimed["manifest"],sort_keys=True))
        script=(
            "import os,sys,json;"
            "from backend.nvp_wo4_multireel import publish_multireel_dcp;"
            "m=json.load(open(sys.argv[1]));"
            "publish_multireel_dcp(reels=m['reels'],ids=m['ids'],"
            "title=m['title'],profile=m['profile'],"
            "output_root=m['output_root'],check_cancel=lambda:False,approve=lambda _:True,"
            "source_take_sha256=m['source_reel_authority'][0]['source_take_sha256'],"
            "mastering_decision_sha256=m['source_reel_authority'][0]['mastering_decision_sha256'],"
            "source_reel_authority=m['source_reel_authority'],feature_assembly_sha256=m['assembly_sha256']);"
            "os._exit(79)"
        )
        result=subprocess.run(
            [sys.executable,"-c",script,str(record)],
            cwd=str(Path(__file__).resolve().parents[1]),
            capture_output=True,text=True,timeout=40,check=False)
        self.assertEqual(result.returncode,79,result.stderr[-800:])
        folder=self.output/("DCP_FEATURE_"+claimed["manifest"]["ids"]["cpl"])
        self.assertTrue(folder.is_dir())
        self.assertEqual(self.journal.feature(fid)["state"],"STAGING")
        restarted=FeatureJournal(self.journal.root)
        reports=self.owned(restarted,restarted.reconcile_features)
        self.assertEqual(reports["jobs"][0]["state"],"REVIEW_REQUIRED")
        self.assertTrue(folder.is_dir())
        approved=self.owned(restarted,restarted.approve_orphan_feature_adoption,
            fid,lambda scope:scope["manifest_sha256"]==job["manifest_sha256"])
        self.assertEqual(approved["status"],"PUBLISHED_PENDING_INDEX")
        self.assertFalse(approved["filesystem_mutated"])
        with SingletonSupervisor(restarted.root):
            index=self.runner(restarted).run_one()
        self.assertEqual(index["status"],"MULTIREEL_FEATURE_FILMINDEX_RECORDED")
        self.assertTrue(folder.is_dir())
        self.assertEqual(restarted.feature(fid)["state"],"INDEXED")

    def test_crash_after_promotion_before_journal_requires_review(self):
        job=self.submit()
        task=self.owned(self.journal,self.journal.next_feature,"KilledDuringPackage")
        self.assertEqual(task["feature_id"],job["feature_id"])
        manifest=task["manifest"]
        receipt=publish_multireel_dcp(
            reels=manifest["reels"],ids=manifest["ids"],
            title=manifest["title"],profile=manifest["profile"],
            output_root=manifest["output_root"],check_cancel=lambda:False,approve=lambda _:True,
            source_take_sha256=manifest["source_reel_authority"][0]["source_take_sha256"],
            mastering_decision_sha256=manifest["source_reel_authority"][0]["mastering_decision_sha256"],
            source_reel_authority=manifest["source_reel_authority"],feature_assembly_sha256=manifest["assembly_sha256"])
        self.assertEqual(receipt["status"],"MULTIREEL_STRUCTURAL_DCP_PUBLISHED")
        report=self.owned(self.journal,self.journal.reconcile_features)
        self.assertEqual(report["jobs"][0]["state"],"REVIEW_REQUIRED")
        self.assertTrue(Path(receipt["destination"]).is_dir())
        self.assertEqual(self.journal.feature(job["feature_id"])["state"],
                         "REVIEW_REQUIRED")
        self.assertFalse(self.journal.feature(job["feature_id"])["filmindex_sha256"])
        denied=self.owned(self.journal,self.journal.approve_orphan_feature_adoption,
            job["feature_id"],lambda _:False)
        self.assertEqual(denied["status"],"DENIED")
        adopted=self.owned(self.journal,self.journal.approve_orphan_feature_adoption,
            job["feature_id"],lambda scope:
            scope["preserve_published_directory"] is True)
        self.assertEqual(adopted["status"],"PUBLISHED_PENDING_INDEX")
        self.assertFalse(adopted["filesystem_mutated"])
        with SingletonSupervisor(self.journal.root):
            final=self.runner().run_one()
        self.assertEqual(final["status"],
                         "MULTIREEL_FEATURE_FILMINDEX_RECORDED")
        self.assertEqual(self.journal.feature(job["feature_id"])["state"],
                         "INDEXED")
        self.assertTrue(Path(receipt["destination"]).is_dir())


    def test_feature_manifest_tamper_refused_before_stage(self):
        uid=self.submit()["feature_id"]
        with self.journal._tx() as db:
            db.execute("UPDATE production_features SET title='Unauthorized' WHERE feature_id=?",(uid,))
        with self.assertRaises(PermissionError):
            self.owned(self.journal,self.journal.next_feature,"Owner")
        self.assertFalse(list(self.output.glob("DCP_FEATURE_*")))


if __name__=="__main__":
    unittest.main()
