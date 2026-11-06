"""INDEX-TIME-07: real original VFR indexing and immutable editorial changes.

All tests use real native FFmpeg/FFprobe and a complete FilmIndex source;
source timestamp arithmetic is never simulated at a constant FPS.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_native_frame_index import NVPFrameIndex
from backend.nvp_film_time_editorial import FilmTimeEditorialPublisher
from backend.nvp_index_time07_assembly import IndexedFootageAssembler
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

T=TICKS_PER_SECOND


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        ffmpeg=shutil.which("ffmpeg")
        ffprobe=shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            self.fail("INDEX-TIME-07 needs actual native FFmpeg and FFprobe")
        tmp=tempfile.TemporaryDirectory(prefix="nvp-index07-native-")
        self.addCleanup(tmp.cleanup)
        home=Path(tmp.name)
        self.original=home/"camera_original.mov"
        subprocess.run([
            ffmpeg,"-hide_banner","-v","error","-nostdin",
            "-f","lavfi","-i","testsrc2=size=160x90:rate=24",
            "-frames:v","110",
            "-vf","setpts=(N+floor(N/10))/(24*TB)+3/TB",
            "-fps_mode","vfr","-c:v","mpeg4",
            "-bf","2","-g","24","-q:v","5","-y",str(self.original)
        ],check=True,timeout=90)
        self.source_sha=hashlib.sha256(self.original.read_bytes()).hexdigest()
        self.studio=Studio(home/"studio.sqlite3")
        self.pid=self.studio.create_project("Immutable assembly","")["id"]
        index=FilmIndex(self.studio)
        catalog=ExternalMediaCatalog(self.studio)
        inventory=SourceMediaInventory(catalog)
        inventory.register_volume(self.pid,"volume",home,label="Original volume")
        catalog.register(self.pid,"camera_original",self.original,
                         media_type="video/quicktime")
        inventory.enrich(self.pid,"camera_original","volume",ffprobe=ffprobe)
        bridge=SourceFilmBridge(index,inventory)
        bridge.register_source_revision(self.pid,"camera_original")
        frame=NVPFrameIndex(home/"indexes",ffprobe=Path(ffprobe))
        self.publisher=FilmTimeEditorialPublisher(index,bridge,frame)
        self.publisher.publish(self.pid,"assembly",[
            {"source_id":"camera_original","source_revision":1,
             "source_in_frame_zero":10,"source_out_frame_zero":40,
             "film_in_tick":5*T,"rounding":"nearest"},
            {"source_id":"camera_original","source_revision":1,
             "source_in_frame_zero":60,"source_out_frame_zero":85,
             "film_in_tick":20*T,"rounding":"nearest"},
        ])
        self.assembler=IndexedFootageAssembler(self.publisher)

    def _head(self):
        return self.publisher.index.read_revision(self.pid,"assembly")

    def _plan(self,change):
        head=self._head()
        return self.assembler.prepare(
            self.pid,"assembly",head["revision"],head["document_sha256"],change)

    def _save(self,change,approve=lambda _message:True):
        head=self._head()
        plan=self._plan(change)
        result=self.assembler.commit(
            self.pid,"assembly",head["revision"],head["document_sha256"],
            change,plan["plan_sha256"],confirm=approve)
        return plan,result

    def test_move_copy_and_immutable_versions_survive_restart(self):
        old=self._head()
        plan,result=self._save({"operation":"move","index":0,"target":2})
        self.assertEqual(plan["operation"],"move")
        self.assertEqual(result["status"],"SAVED_NEW_EDIT_REVISION")
        self.assertEqual(result["revision"],2)
        new=self.publisher.clips(self.pid,"assembly",2)
        self.assertEqual(new["clips"][0]["source_in_frame_zero"],60)
        self.assertEqual(new["clips"][1]["source_in_frame_zero"],10)
        self.assertNotEqual(old["document_sha256"],result["edit_document_sha256"])
        immutable=self.publisher.clips(self.pid,"assembly",1)
        self.assertEqual(immutable["clips"][0]["source_in_frame_zero"],10)
        newer_plan,newer=self._save({"operation":"copy","index":1,"target":2})
        self.assertEqual(newer_plan["clip_count"],3)
        self.assertEqual(newer["revision"],3)
        self.assertEqual(self.publisher.verify_revision(
            self.pid,"assembly",3)["clips"],3)
        self.assertEqual(self.publisher.verify_revision(
            self.pid,"assembly",1)["clips"],2)
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(),
                         self.source_sha)
        reopened=FilmIndex(Studio(self.studio.db_path))
        self.assertEqual(reopened.read_revision(
            self.pid,"assembly",1)["document_sha256"],old["document_sha256"])
        self.assertEqual(reopened.read_revision(
            self.pid,"assembly",3)["document_sha256"],
            newer["edit_document_sha256"])

    def test_trim_and_gap_are_exact_source_pts_not_guessed_fps(self):
        original=self.publisher.clips(self.pid,"assembly",1)["clips"][0]
        plan,saved=self._save({
            "operation":"trim","index":0,
            "source_in_frame_zero":"12","source_out_frame_zero":"39"})
        self.assertEqual(plan["placements"][0]["source_in_frame_zero"],"12")
        self.assertEqual(plan["placements"][0]["source_out_frame_zero"],"39")
        self.assertEqual(plan["placements"][0]["film_start_tick"],str(5*T))
        trimmed=self.publisher.clips(self.pid,"assembly",2)["clips"][0]
        self.assertNotEqual(trimmed["source_in_pts"],original["source_in_pts"])
        self.assertNotEqual(trimmed["film_end_tick"],original["film_end_tick"])
        self.assertEqual(trimmed["film_start_tick"],5*T)
        plan2,saved2=self._save({
            "operation":"set_gap","index":1,
            "gap_before_tick":str(3*T)})
        page=self.publisher.clips(self.pid,"assembly",3)["clips"]
        self.assertEqual(page[1]["film_start_tick"]-page[0]["film_end_tick"],3*T)
        self.assertEqual(plan2["duration_tick"],str(page[1]["film_end_tick"]))
        self.assertEqual(saved2["revision"],3)

    def test_insert_other_source_edit_and_restore_old_manifest(self):
        second=self.publisher.publish(self.pid,"other_source_edit",[{
            "source_id":"camera_original","source_revision":1,
            "source_in_frame_zero":86,"source_out_frame_zero":101,
            "film_in_tick":0,"rounding":"nearest",
        }])
        operation={
            "operation":"insert","target":1,
            "source_edit_id":"other_source_edit","source_edit_revision":1,
            "source_edit_sha256":second["document_sha256"],"source_ordinal":0,
        }
        _,saved=self._save(operation)
        self.assertEqual(saved["revision"],2)
        page=self.publisher.clips(self.pid,"assembly",2)["clips"]
        self.assertEqual(len(page),3)
        self.assertEqual(page[1]["source_in_frame_zero"],86)
        plan,restored=self._save({"operation":"restore","from_revision":1})
        self.assertEqual(plan["clip_count"],2)
        self.assertEqual(restored["revision"],3)
        self.assertEqual(self.publisher.clips(
            self.pid,"assembly",3)["clips"][0]["source_in_frame_zero"],10)
        self.assertEqual(self.publisher.clips(
            self.pid,"assembly",2)["clips"][1]["source_in_frame_zero"],86)

    def test_consent_denial_and_cas_conflict_leave_original_unchanged(self):
        head=self._head()
        operation={"operation":"remove","index":0}
        seen=[]
        plan,result=self._save(operation,approve=lambda message:(
            seen.append(message),False)[1])
        self.assertEqual(result["status"],"DENIED")
        self.assertEqual(self._head()["document_sha256"],head["document_sha256"])
        self.assertIn("Plan SHA256:",seen[0])
        with self.assertRaisesRegex(RuntimeError,"changed"):
            self.assembler.commit(
                self.pid,"assembly",1,head["document_sha256"],
                operation,"f"*64,confirm=lambda _:True)
        plan,saved=self._save(operation)
        with self.assertRaisesRegex(RuntimeError,"changed"):
            self.assembler.commit(
                self.pid,"assembly",1,head["document_sha256"],
                operation,plan["plan_sha256"],confirm=lambda _:True)
        self.assertEqual(saved["revision"],2)
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(),
                         self.source_sha)

    def test_untrusted_paths_out_of_range_and_noop_are_rejected(self):
        for change in (
            {"operation":"trim","index":0,"source_in_frame_zero":"0",
             "source_out_frame_zero":"50"},
            {"operation":"trim","index":0,"source_in_frame_zero":"10",
             "source_out_frame_zero":"40"},
            {"operation":"set_gap","index":1,"gap_before_tick":"-1"},
            {"operation":"move","index":0,"target":1},
            {"operation":"remove","index":3},
            {"operation":"delete_source","index":0},
            {"operation":"copy","index":0,"target":1,
             "source_path":str(self.original)},
        ):
            with self.subTest(change=change):
                with self.assertRaises((ValueError,RuntimeError)):
                    self._plan(change)
        self.assertEqual(self._head()["revision"],1)
        self.assertEqual(hashlib.sha256(self.original.read_bytes()).hexdigest(),
                         self.source_sha)

    def test_source_tamper_and_cross_project_edit_scope_fail_closed(self):
        original_head=self._head()
        other=self.studio.create_project("Foreign project","")["id"]
        with self.assertRaises((KeyError,RuntimeError)):
            self.assembler.prepare(
                other,"assembly",1,original_head["document_sha256"],
                {"operation":"remove","index":0})
        with self.original.open("ab") as fp:
            fp.write(b"changed external original")
        with self.assertRaises(RuntimeError):
            self._plan({"operation":"remove","index":0})
        self.assertEqual(self._head()["revision"],1)


if __name__=="__main__":
    unittest.main()
