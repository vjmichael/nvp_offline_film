"""MASTER-01C real OS-contained *prepare-only* worker and host-owned commit."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_film_index import FilmIndex
from backend.nvp_longform_review import index_technical_reel
from backend.nvp_master01b_native_host import NativeMasterReviewHost
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from tests.test_nvp_longform_review import make_prores_with_pcm24


def sample():
    return ResourceSnapshot(1, 32768, 28000, 0, ())


class HostOwnedPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ff, cls.probe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if cls.ff is None or cls.probe is None:
            raise unittest.SkipTest("Genuine ProRes/PCM24 FFmpeg required")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nvp-master01c-host-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.studio = Studio(self.root / "studio.sqlite3")
        self.index = FilmIndex(self.studio)
        self.pid = self.studio.create_project("Host-owned film", "Two-phase acceptance")["id"]
        self.ledger = TaskLedger(self.root / "activity", sampler=sample)
        self.host = NativeMasterReviewHost(
            self.index, self.ledger, self.root / "native",
            publication_mode="host_staged", verify_creator_action=lambda event,scope:
                event.startswith("creator-stage-") and scope.get("project_id") == self.pid
                and scope.get("publication_mode") == "host_staged")
        self.refs = []
        for i, color in enumerate(("green", "red", "blue")):
            movie = self.root / f"source{i}.mov"
            make_prores_with_pcm24(self.ff,movie,seconds=10,color=color,tone=540 + i*90)
            media = self.index.put_media_file(self.pid,movie,"video/quicktime")
            source_id=f"source{i}"
            self.index.register_revision(self.pid,source_id,"presentation",{
                "format":"nvp.master01c.original_av.v1", "frames":240,
                "movie_sha256":media["sha256"],"creator_approved_final_master":False,
                "dcp_delivered":False},expected_revision=0)
            reel_id=f"reel{i}"
            index_technical_reel(self.index,self.pid,reel_id,source_id,1)
            self.refs.append({"object_id":reel_id,"revision":1})

    def test_sixty_second_contained_host_publishes_original_clock(self):
        longer=[]
        for i,color in enumerate(("yellow","purple","cyan")):
            movie=self.root/f"long{i}.mov"
            make_prores_with_pcm24(self.ff,movie,seconds=20,color=color,tone=510+i*70)
            media=self.index.put_media_file(self.pid,movie,"video/quicktime")
            producer=f"longproducer{i}"
            self.index.register_revision(self.pid,producer,"presentation",{
                "format":"nvp.master01c.long_original.v1", "frames":480,
                "movie_sha256":media["sha256"],"creator_approved_final_master":False,
                "dcp_delivered":False},expected_revision=0)
            reel=f"longreel{i}"
            index_technical_reel(self.index,self.pid,reel,producer,1)
            longer.append({"object_id":reel,"revision":1})
        queued=self.host.stage_and_approve(self.pid,"sixty_second_review",longer,
            "creator-stage-sixty",ffmpeg=self.ff,ffprobe=self.probe)
        out=self.host.run_next(timeout_seconds=300)
        self.assertEqual(out["state"],"SUCCEEDED")
        self.assertEqual(out["frames"],1440)
        self.assertEqual(out["duration_seconds"],60)
        self.assertEqual(self.ledger.get_task(queued["job_id"])["state"],"SUCCEEDED")
        self.assertEqual(len(self.index.history(self.pid,"sixty_second_review")),1)

    def test_genuine_contained_worker_never_publishes_before_host(self):
        job=self.host.stage_and_approve(self.pid,"native_approved_review",self.refs,
            "creator-stage-001",ffmpeg=self.ff,ffprobe=self.probe)["job_id"]
        real=self.host._complete_staged_after_stop
        inspected=[]
        def check_before_host_commit(identity,plan):
            with self.assertRaises(KeyError):
                self.index.read_revision(self.pid,"native_approved_review")
            inspected.append(True)
            return real(identity,plan)
        with patch.object(self.host,"_complete_staged_after_stop",side_effect=check_before_host_commit):
            done=self.host.run_next(timeout_seconds=300)
        self.assertEqual(inspected,[True])
        self.assertEqual(done["state"],"SUCCEEDED")
        self.assertEqual(done["frames"],720)
        self.assertFalse(done["creator_approved_final_master"])
        self.assertEqual(self.ledger.get_task(job)["state"],"SUCCEEDED")
        self.assertEqual(len(self.index.history(self.pid,"native_approved_review")),1)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        fresh=NativeMasterReviewHost(FilmIndex(Studio(self.studio.db_path)),
            TaskLedger(self.root/"activity",sampler=sample),self.root/"native",
            verify_creator_action=lambda *_:False,publication_mode="host_staged")
        self.assertEqual(fresh.reconcile_after_restart(job)["state"],"SUCCEEDED")

    def test_cancel_during_postworker_staging_prevents_host_publication(self):
        job=self.host.stage_and_approve(self.pid,"cancel_before_commit",self.refs,
            "creator-stage-cancel",ffmpeg=self.ff,ffprobe=self.probe)["job_id"]
        original=self.host._complete_staged_after_stop
        def cancel_at_publication(identity,plan):
            self.host.request_cancel(job)
            return original(identity,plan)
        from backend.nvp_resource_supervisor import NativeCancelRequested
        with patch.object(self.host,"_complete_staged_after_stop",side_effect=cancel_at_publication):
            with self.assertRaises(NativeCancelRequested):
                self.host.run_next(timeout_seconds=300)
        self.assertEqual(self.ledger.get_task(job)["state"],"CANCELLED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"cancel_before_commit")

    def test_staged_film_tampered_between_worker_stop_and_publication_rejected(self):
        job=self.host.stage_and_approve(self.pid,"tampered_prepublication",self.refs,
            "creator-stage-003",ffmpeg=self.ff,ffprobe=self.probe)["job_id"]
        real=self.host._complete_staged_after_stop
        def corrupt_after_worker_stop(identity,plan):
            movie=self.root/"native"/identity/"stage"/"prepared.mov"
            with movie.open("r+b") as stream:
                stream.seek(800)
                old=stream.read(1)
                stream.seek(800)
                stream.write(bytes([old[0]^1]))
            return real(identity,plan)
        with patch.object(self.host,"_complete_staged_after_stop",side_effect=corrupt_after_worker_stop):
            with self.assertRaisesRegex(RuntimeError,"changed"):
                self.host.run_next(timeout_seconds=300)
        self.assertEqual(self.ledger.get_task(job)["state"],"FAILED")
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"tampered_prepublication")

    def test_true_host_crash_after_stop_before_film_publication_recovers_prepared_media(self):
        child='''
import os,sys
from pathlib import Path
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_master01b_native_host import NativeMasterReviewHost
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
root=Path(sys.argv[1]); pid=sys.argv[2]
def sample():return ResourceSnapshot(1,32768,28000,0.0,())
host=NativeMasterReviewHost(FilmIndex(Studio(root/'studio.sqlite3')),
    TaskLedger(root/'activity',sampler=sample),root/'native',
    publication_mode='host_staged',verify_creator_action=lambda event,scope:
        event=='creator-stage-before-commit' and scope.get('publication_mode')=='host_staged')
refs=[{'object_id':f'reel{i}','revision':1} for i in range(3)]
host.stage_and_approve(pid,'pending_publication',refs,'creator-stage-before-commit',ram_mb=1024)
host._complete_after_stop=lambda job: os._exit(81)
host.run_next(timeout_seconds=300)
'''
        result=subprocess.run([sys.executable,"-c",child,str(self.root),self.pid],
             cwd=Path(__file__).resolve().parents[1],stdin=subprocess.DEVNULL,
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=False)
        self.assertEqual(result.returncode,81,
                         result.stderr.decode("utf8","replace")[-1400:])
        with self.ledger._db() as db:
            job=db.execute("SELECT job_id FROM native_master01b_grants WHERE review_id=?",
                           ("pending_publication",)).fetchone()[0]
        self.assertEqual(self.host._grant(job)["stop_witness"],1)
        self.assertEqual(self.ledger.get_task(job)["state"],"ACTIVE")
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"pending_publication")
        fresh=NativeMasterReviewHost(FilmIndex(Studio(self.studio.db_path)),
            TaskLedger(self.root/"activity",sampler=sample),self.root/"native",
            verify_creator_action=lambda *_:False,publication_mode="host_staged")
        resumed=fresh.reconcile_after_restart(job)
        self.assertEqual(resumed["state"],"SUCCEEDED")
        self.assertEqual(resumed["frames"],720)
        self.assertEqual(len(self.index.history(self.pid,"pending_publication")),1)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_real_host_hard_crash_after_commit_then_reconcile_without_new_revision(self):
        child='''
import os,sys
from pathlib import Path
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_master01b_native_host import NativeMasterReviewHost
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
root=Path(sys.argv[1]); pid=sys.argv[2]
def sample():return ResourceSnapshot(1,32768,28000,0.0,())
host=NativeMasterReviewHost(FilmIndex(Studio(root/'studio.sqlite3')),
    TaskLedger(root/'activity',sampler=sample),root/'native',
    publication_mode='host_staged',verify_creator_action=lambda event,scope:
        event=='creator-stage-crash' and scope.get('publication_mode')=='host_staged')
refs=[{'object_id':f'reel{i}','revision':1} for i in range(3)]
host.stage_and_approve(pid,'crash_published',refs,'creator-stage-crash',ram_mb=1024)
real=host._complete_staged_after_stop
def crash_after_commit(job,plan):
    real(job,plan)
    os._exit(83)
host._complete_staged_after_stop=crash_after_commit
host.run_next(timeout_seconds=300)
'''
        result=subprocess.run([sys.executable,"-c",child,str(self.root),self.pid],
             cwd=Path(__file__).resolve().parents[1],stdin=subprocess.DEVNULL,
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=False)
        self.assertEqual(result.returncode,83,
                         result.stderr.decode("utf8","replace")[-1600:])
        with self.ledger._db() as db:
            job=db.execute("SELECT job_id FROM native_master01b_grants WHERE review_id=?",
                           ("crash_published",)).fetchone()[0]
        self.assertEqual(self.ledger.get_task(job)["state"],"ACTIVE")
        self.assertEqual(self.host._grant(job)["stop_witness"],1)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],1024)
        head=self.index.read_revision(self.pid,"crash_published")
        self.assertEqual(head["revision"],1)
        recovered=NativeMasterReviewHost(FilmIndex(Studio(self.studio.db_path)),
            TaskLedger(self.root/"activity",sampler=sample),self.root/"native",
            verify_creator_action=lambda *_:False,publication_mode="host_staged")
        done=recovered.reconcile_after_restart(job)
        self.assertEqual(done["state"],"SUCCEEDED")
        self.assertEqual(done["frames"],720)
        self.assertEqual(self.ledger.snapshot()["reservations"]["ram_mb"],0)
        self.assertEqual(len(self.index.history(self.pid,"crash_published")),1)
        self.assertEqual(recovered.reconcile_after_restart(job)["state"],"SUCCEEDED")


if __name__ == "__main__":
    unittest.main()