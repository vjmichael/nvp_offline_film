"""Portable real SQLite, exact-clock and bounded manifest tests (not native media)."""
import contextlib
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import nvp_p1de_hierarchy as hierarchy
from backend import nvp_p1de_edit_audio as editorial
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_p1f_p2_reel_plan import P1FReelPlan, reel_layout, FORMAT, FORMAT_COMPACT
from backend.nvp_production_journal import ProductionJournal, _canonical, _digest, TASK_KIND
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T


def ref(row):
    return {"edit_id":row["object_id"],"revision":row["revision"],"document_sha256":row["document_sha256"]}


class HierarchyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"film.sqlite3"
        self.studio=Studio(self.path)
        self.pid=self.studio.create_project("Portable hierarchy fixture", "")['id']
        self.index=FilmIndex(self.studio)
        # Only original Take/audio validation is simulated. Actual SQLite,
        # immutable revision hashes, typed edges and approval guards are real.
        def bound(index,pid,segments):
            ready=[{**s,"scene_sha256":"c"*64,"timeline_sha256":"d"*64} for s in segments]
            return ready,sum(s["out_tick"]-s["in_tick"] for s in segments),[]
        patcher=patch.object(editorial,"_bound_segments",side_effect=bound)
        patcher.start(); self.addCleanup(patcher.stop)
        self.scopes=[]
        def approve(event,scope):
            self.scopes.append(dict(scope)); return event=="yes"
        self.engine=editorial.P1DEConform(self.index,approve_edit=approve)
        self.leaf=self.engine.publish(self.pid,"leaf",[{"take_id":"Original","take_sha256":"a"*64,
            "in_tick":0,"out_tick":T,"listener_path":"/World/Camera","audio":[]}],creator_event="yes")

    def manifest(self,ident,children,event="yes"):
        return self.engine.publish_manifest(self.pid,ident,children,creator_event=event)

    def film(self):
        minute=self.manifest("minute",[ref(self.leaf)]*60)
        hour=self.manifest("hour",[ref(minute)]*60)
        return self.manifest("film",[ref(hour)]*8)

    def test_8h_compact_plan_reopen_and_original_clock(self):
        film=self.film(); self.assertEqual(film["duration_tick"],8*3600*T)
        row=self.engine.read(self.pid,"film",1)
        self.assertEqual(row["data"]["depth"],3)
        self.assertEqual(len(row["dependencies"]),1)
        self.assertEqual(len(row["data"]["children"]),8)
        self.assertEqual(self.scopes[-1]["operation"],"nvp.p1de.publish_source_edit_manifest.v2")
        page=self.engine.manifest_page(self.pid,"film",1,first_index=5,limit=2)
        self.assertEqual(page["next_index"],7)
        self.assertFalse(page["leaf"])
        plan=P1FReelPlan(self.index)
        receipt=plan.publish(self.pid,"plan",edit_id="film",edit_revision=1,
            expected_edit_document_sha256=film["document_sha256"])
        reopened=P1FReelPlan(FilmIndex(Studio(self.path)))
        record=reopened.read(self.pid,"plan")
        self.assertEqual(record["document_sha256"],receipt["document_sha256"])
        self.assertEqual(record["data"]["format"],FORMAT_COMPACT)
        self.assertNotIn("reels",record["data"])
        self.assertLess(len(json.dumps(record["data"])),2000)
        self.assertEqual(reopened.page(self.pid,"plan",first_index=2879)["reels"][0]["end_tick"],8*3600*T)
        frame=reopened.picture_instant(self.pid,"plan",2879,239)
        self.assertEqual((frame["output_frame"],frame["source_tick"]),(691199,23*T//24))
        self.assertFalse(frame["rendered"])
        with self.assertRaises(IndexError): reopened.picture_instant(self.pid,"plan",2880,0)

    def test_cross_child_windows_and_no_flattening(self):
        self.film()
        b=7*3600*48000
        res=self.engine.plan(self.pid,"film",1,first_sample=b-5,count=9)
        self.assertEqual([x["sample_count"] for x in res["slices"]],[5,4])
        self.assertEqual([x["source_first_sample"] for x in res["slices"]],[47995,0])
        self.assertEqual([x["output_first_sample"] for x in res["slices"]],[b-5,b])
        with self.assertRaises(ValueError): self.engine.plan(self.pid,"film",1,first_sample=b,count=4097)

    def test_refusal_wrong_sha_depth_and_exact_old_leaf(self):
        leaf=ref(self.leaf)
        with self.assertRaises(PermissionError): self.manifest("refused",[leaf],"no")
        with self.assertRaises(KeyError): self.index.read_revision(self.pid,"refused")
        with self.assertRaises(RuntimeError): self.manifest("wrong",[{**leaf,"document_sha256":"b"*64}])
        with self.assertRaises(ValueError): self.manifest("too_many",[leaf]*65)
        with self.assertRaises(ValueError): self.manifest("leaf",[leaf])
        film=self.film()
        with self.assertRaises(ValueError): self.manifest("deep",[ref(film)])
        scheduler=P1FReelPlan(self.index)
        receipt=scheduler.publish(self.pid,"old",edit_id="leaf",edit_revision=1,
                                  expected_edit_document_sha256=self.leaf["document_sha256"])
        old=scheduler.read(self.pid,"old")
        self.assertEqual(old["data"]["format"],FORMAT)
        self.assertEqual(old["data"]["reels"],list(reel_layout(T)))
        self.assertEqual(receipt["document_sha256"],old["document_sha256"])

    def test_host_guard_refuses_forged_child_table(self):
        doc,deps=hierarchy.compose([ref(self.leaf)],lambda ident,rev:self.index.read_revision(self.pid,ident,rev))
        doc["children"][0]["end_tick"]+=T
        self.index.register_revision(self.pid,"forged","edit",doc,dependencies=deps)
        with self.assertRaises(RuntimeError): self.engine.read(self.pid,"forged",1)

    def test_audio_iterator_bounded_cancel_and_cursor(self):
        film=self.film(); p=P1FReelPlan(self.index)
        p.publish(self.pid,"plan",edit_id="film",edit_revision=1,expected_edit_document_sha256=film["document_sha256"])
        # Derived PCM mocked: verify finite iteration/cancellation, not native mix.
        def audio(*args,first_sample,count):
            return {"first_sample":first_sample,"sample_count":count}
        with patch.object(p,"audio_window",side_effect=audio) as fn:
            rows=p.iter_audio_windows(self.pid,"plan",2879,window_samples=4096)
            first=next(rows); self.assertEqual(first["sample_count"],4096)
            self.assertEqual(first["first_sample"],2879*480000)
            self.assertEqual(fn.call_count,1)
            rows.close()
            with self.assertRaises(InterruptedError): next(p.iter_audio_windows(self.pid,"plan",2879,cancelled=lambda:True))


class ReelClockTests(unittest.TestCase):
    def test_duration_matrix_and_exact_last_partial_reel(self):
        for hours in (0.5,1,3,6,8,12,24):
            d=int(hours*3600)*T; x=reel_layout(d)
            self.assertEqual(len(x),int(hours*360))
            self.assertEqual(x[-1]["end_tick"],d)
            self.assertLessEqual(len(x.page(len(x)-1,64)),64)
        x=reel_layout(8*3600*T+T//24)
        self.assertEqual(x[-1]["frame_count"],1)
        self.assertEqual(x[-1]["sample_count"],2000)
        self.assertEqual(x[-1]["end_tick"],8*3600*T+T//24)
        with self.assertRaises(ValueError): reel_layout((2**53//T+1)*T)
        with self.assertRaises(ValueError): x.page(0,65)


class JournalPageTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:",isolation_level=None); self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript("""CREATE TABLE production_jobs(job_id,project_id,assembly_id,assembly_revision,
            assembly_sha256,manifest_sha256,manifest_json,task_kind,state,cancel_requested,owner_pid,updated_at);
            CREATE TABLE production_segments(job_id,position,start_tick,end_tick,source_path,expected_sha256,
            expected_bytes,state,verified_sha256,verified_bytes,verified_at);""")
        self.items=[{"position":i,"start_tick":i,"end_tick":i+1,"source_path":"fixture",
                     "source_sha256":"a"*64,"source_bytes":1} for i in range(150)]
        manifest={"project_id":"p","assembly_id":"a","assembly_revision":1,
                  "assembly_sha256":"b"*64,"task_kind":TASK_KIND,"segments":self.items}
        raw=_canonical(manifest)
        self.db.execute("INSERT INTO production_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("j","p","a",1,"b"*64,_digest(raw),raw.decode(),TASK_KIND,"QUEUED",0,None,"now"))
        self.db.executemany("INSERT INTO production_segments VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [("j",i,i,i+1,"fixture","a"*64,1,"VERIFIED" if i<10 else "PENDING",None,None,None) for i in range(150)])
        self.journal=object.__new__(ProductionJournal)
        @contextlib.contextmanager
        def read():
            try: yield self.db
            finally:
                if self.db.in_transaction:self.db.rollback()
        # No EFS claim: real SQLite cursor/query logic, OS storage guard omitted.
        self.journal._read=read

    def test_query_bounds_and_full_guard(self):
        p=self.journal.status_page("j",first_position=64,limit=64)
        self.assertEqual((len(p["segments"]),p["next_position"],p["total_segments"],p["verified_segments"]),(64,128,150,10))
        self.assertFalse(p["production_dcp_accepted"])
        last=self.journal.status_page("j",first_position=128)
        self.assertEqual(len(last["segments"]),22); self.assertIsNone(last["next_position"])
        self.db.execute("UPDATE production_segments SET expected_sha256='bad' WHERE position=149")
        with self.assertRaises(RuntimeError): self.journal.status_page("j",first_position=0,limit=1)

    def test_project_scope_checked_before_cursor_or_manifest(self):
        self.db.execute("UPDATE production_segments SET expected_sha256='bad' WHERE position=149")
        with self.assertRaises(PermissionError):
            self.journal.status_page("j",first_position=999,expected_project_id="foreign")
        with self.assertRaises(RuntimeError):
            self.journal.status_page("j",expected_project_id="p")

    def test_missing_and_extra_rows_refused(self):
        self.db.execute("DELETE FROM production_segments WHERE position=149")
        with self.assertRaises(RuntimeError): self.journal.status_page("j",limit=1)
        self.db.execute("INSERT INTO production_segments VALUES(?,?,?,?,?,?,?,?,?,?,?)",("j",149,149,150,"fixture","a"*64,1,"PENDING",None,None,None))
        self.db.execute("INSERT INTO production_segments VALUES(?,?,?,?,?,?,?,?,?,?,?)",("j",150,150,151,"fixture","a"*64,1,"PENDING",None,None,None))
        with self.assertRaises(RuntimeError): self.journal.status_page("j",limit=1)


if __name__=="__main__": unittest.main()
