"""INDEX-TIME-02 real native source-index and FilmIndex editorial acceptance.

No fake FFmpeg, FFprobe, source inventory, FilmIndex, or SQLite manifest.
No image rendering is claimed here: saved placements are source-time metadata.
"""
import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_external_media_catalog import ExternalMediaCatalog
from backend.nvp_source_media_inventory import SourceMediaInventory
from backend.nvp_source_film_bridge import SourceFilmBridge
from backend.nvp_native_frame_index import NVPFrameIndex
from backend.nvp_film_time_editorial import FilmTimeEditorialPublisher
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

T=TICKS_PER_SECOND


class FilmTimeEditorialNativeTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg=shutil.which("ffmpeg")
        self.ffprobe=shutil.which("ffprobe")
        if not self.ffmpeg or not self.ffprobe:
            self.fail("Real native FFmpeg and FFprobe required")
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.db_path=self.root/"film.sqlite"
        self.volume=self.root/"camera_sd"
        self.volume.mkdir()
        self.movie=self.volume/"vfr_bframes.mov"
        subprocess.run([
            self.ffmpeg,"-hide_banner","-v","error","-nostdin",
            "-f","lavfi","-i","testsrc2=size=160x90:rate=24",
            "-frames:v","150",
            "-vf","setpts=(N+floor(N/10))/(24*TB)+3/TB",
            "-fps_mode","vfr","-c:v","mpeg4","-bf","2",
            "-g","24","-q:v","4","-y",str(self.movie),
        ],check=True,timeout=120)
        self.studio=Studio(self.db_path)
        self.pid=self.studio.create_project("Imported footage","Film time")["id"]
        self.catalog=ExternalMediaCatalog(self.studio)
        self.inventory=SourceMediaInventory(self.catalog)
        self.film=FilmIndex(self.studio)
        self.bridge=SourceFilmBridge(self.film,self.inventory)
        self.inventory.register_volume(self.pid,"sd",self.volume,label="Camera SD")
        self.catalog.register(self.pid,"camera_take",self.movie,
                              media_type="video/quicktime")
        self.inventory.enrich(self.pid,"camera_take","sd",
                              ffprobe=self.ffprobe)
        self.source=self.bridge.register_source_revision(self.pid,"camera_take")
        self.sha=self.catalog.list_assets(self.pid)[0]["sha256"]
        self.cache_root=self.root/"index_cache"
        self.cache=NVPFrameIndex(self.cache_root,ffprobe=Path(self.ffprobe))
        self.publisher=FilmTimeEditorialPublisher(self.film,self.bridge,self.cache)

    def new_publisher(self):
        studio=Studio(self.db_path)
        index=FilmIndex(studio)
        catalog=ExternalMediaCatalog(studio)
        inventory=SourceMediaInventory(catalog)
        bridge=SourceFilmBridge(index,inventory)
        frame=NVPFrameIndex(self.cache_root,ffprobe=Path(self.ffprobe))
        return FilmTimeEditorialPublisher(index,bridge,frame)

    def clip(self, *, start=5*T, first=10, out=25, rounding="exact"):
        return {
            "source_id":"camera_take","source_revision":1,
            "source_in_frame_zero":first,
            "source_out_frame_zero":out,
            "film_in_tick":start,
            "rounding":rounding,
        }

    def test_native_vfr_placements_persist_and_restart_without_cfr(self):
        saved=self.publisher.publish(self.pid,"film_time_edit",[
            self.clip(),self.clip(start=20*T,first=40,out=55)])
        self.assertEqual(saved["kind"],"edit")
        self.assertEqual(saved["revision"],1)
        before=self.publisher.verify_revision(self.pid,"film_time_edit",1)
        self.assertEqual(before["status"],"VERIFIED_FILMINDEX_IMPORTED_PLACEMENTS")
        self.assertEqual(before["clips"],2)
        self.assertFalse(before["source_bytes_verified"])
        record=self.film.read_revision(self.pid,"film_time_edit",1)
        self.assertEqual(record["data"]["format"],
                         "nvp.edit.imported_film_time.v1")
        self.assertNotIn("fps_num",record["data"])
        self.assertFalse(record["data"]["native_film_events_modified"])
        reopened=self.new_publisher()
        page=reopened.clips(self.pid,"film_time_edit",1)
        self.assertEqual(len(page["clips"]),2)
        self.assertEqual(page["clips"][0]["film_start_tick"],5*T)
        self.assertEqual(page["clips"][1]["film_start_tick"],20*T)
        self.assertEqual(page["clips"][0]["source_sha256"],self.sha)
        self.assertEqual(page["clips"][0]["source_document_sha256"],
                         self.source["document_sha256"])
        self.assertIsNone(reopened.at(self.pid,"film_time_edit",1,tick=4*T))
        self.assertEqual(reopened.at(
            self.pid,"film_time_edit",1,tick=5*T)["ordinal"],0)
        self.assertIsNone(reopened.at(self.pid,"film_time_edit",1,tick=10*T))
        self.assertEqual(reopened.at(
            self.pid,"film_time_edit",1,tick=20*T)["ordinal"],1)
        mapped=reopened.map_clip_window(
            self.pid,"film_time_edit",1,clip_ordinal=0,
            first_zero=12,count=5)
        self.assertEqual([f["source_frame_zero"] for f in mapped["frames"]],
                         [12,13,14,15,16])
        self.assertEqual(mapped["frames"][0]["time_tick"],
                         5*T+(mapped["frames"][0]["source_pts"]-
                              page["clips"][0]["source_in_pts"])*
                              page["clips"][0]["time_base_num"]*T//
                              page["clips"][0]["time_base_den"])
        self.assertFalse(mapped["source_sha_verified_this_operation"])
        self.assertFalse(mapped["verified_original_bytes"])
        self.assertEqual(mapped["edit_document_sha256"],
                         record["document_sha256"])

    def test_new_placement_revision_preserves_old_and_source_impact(self):
        original=self.publisher.publish(self.pid,"moving_edit",[
            self.clip(),self.clip(start=20*T,first=40,out=55)])
        moved=self.publisher.publish(
            self.pid,"moving_edit",[self.clip(start=40*T)],
            expected_revision=1)
        self.assertNotEqual(original["document_sha256"],moved["document_sha256"])
        self.assertEqual(self.publisher.clips(
            self.pid,"moving_edit",1)["clips"][0]["film_start_tick"],5*T)
        self.assertEqual(self.publisher.clips(
            self.pid,"moving_edit",2)["clips"][0]["film_start_tick"],40*T)
        self.assertEqual(self.publisher.verify_revision(
            self.pid,"moving_edit",1)["clips"],2)
        self.assertEqual(self.publisher.verify_revision(
            self.pid,"moving_edit",2)["clips"],1)
        impacted=self.film.direct_dependents(self.pid,"camera_take",1)
        self.assertIn({"object_id":"moving_edit","revision":1},impacted)
        self.assertIn({"object_id":"moving_edit","revision":2},impacted)
        self.assertEqual(self.film.impact(self.pid,"camera_take",1),impacted)

    def test_saved_placements_remain_accessible_when_volume_offline(self):
        self.publisher.publish(self.pid,"offline_edit",[self.clip()])
        self.movie.unlink()
        record=self.new_publisher().clips(self.pid,"offline_edit",1)
        self.assertEqual(len(record["clips"]),1)
        checked=self.publisher.verify_revision(self.pid,"offline_edit",1)
        self.assertEqual(checked["clips"],1)
        self.assertFalse(checked["source_bytes_verified"])
        with self.assertRaises(RuntimeError):
            self.publisher.map_clip_window(
                self.pid,"offline_edit",1,clip_ordinal=0,
                first_zero=10,count=2)

    def test_source_revision_and_edit_tampering_are_refused(self):
        self.publisher.publish(self.pid,"tamper_edit",[self.clip()])
        with self.studio._connection() as db:
            db.execute("""UPDATE nvp_time_editorial_clips
                SET source_in_pts=source_in_pts+1
                WHERE project_id=? AND edit_id=?""",
                (self.pid,"tamper_edit"))
        with self.assertRaises(RuntimeError):
            self.publisher.verify_revision(self.pid,"tamper_edit",1)
        with self.assertRaises(RuntimeError):
            self.publisher.clips(self.pid,"tamper_edit",1)

    def test_guard_rolls_back_rows_and_edit_revision(self):
        actual=self.film.register_revision
        def fail_after_rows(*args,**kwargs):
            guard=kwargs["precommit_guard"]
            def inject(db):
                guard(db)
                raise RuntimeError("INJECTED_SQLITE_ROLLBACK_AFTER_CLIP_ROWS")
            kwargs["precommit_guard"]=inject
            return actual(*args,**kwargs)
        with patch.object(self.film,"register_revision",side_effect=fail_after_rows):
            with self.assertRaisesRegex(
                    RuntimeError,"INJECTED_SQLITE_ROLLBACK_AFTER_CLIP_ROWS"):
                self.publisher.publish(
                    self.pid,"rollback_edit",[self.clip()])
        with self.studio._connection() as db:
            count=db.execute("""SELECT COUNT(*) FROM nvp_time_editorial_clips
                WHERE project_id=? AND edit_id=?""",
                (self.pid,"rollback_edit")).fetchone()[0]
        self.assertEqual(count,0)
        with self.assertRaises(KeyError):
            self.film.read_revision(self.pid,"rollback_edit")

    def test_duplicate_overlap_foreign_project_and_unmeasured_tail_fail(self):
        with self.assertRaises(ValueError):
            self.publisher.publish(self.pid,"overlap_edit",[
                self.clip(),self.clip(start=5*T,first=40,out=55)])
        with self.assertRaises(ValueError):
            self.publisher.publish(self.pid,"reversed_source",[
                self.clip(first=25,out=10)])
        with self.assertRaises(ValueError):
            self.publisher.publish(self.pid,"beyond_source",[
                self.clip(first=120,out=150)])
        other=self.studio.create_project("Separate project","")["id"]
        with self.assertRaises(KeyError):
            self.publisher.publish(other,"cross_project_edit",[self.clip()])
        self.publisher.publish(self.pid,"bounded_map",[self.clip()])
        with self.assertRaises(ValueError):
            self.publisher.map_clip_window(
                self.pid,"bounded_map",1,clip_ordinal=0,
                first_zero=24,count=2)

    def test_paged_placement_manifest_remains_bounded(self):
        items=[self.clip(start=(10+n*3)*T,first=10,out=25)
               for n in range(6)]
        self.publisher.publish(self.pid,"paged_edit",items)
        got=[]
        token=-1
        while True:
            page=self.publisher.clips(self.pid,"paged_edit",1,
                                      after_ordinal=token,limit=2)
            got+=page["clips"]
            token=page["next_after_ordinal"]
            if token is None:
                break
        self.assertEqual([x["ordinal"] for x in got],list(range(6)))
        self.assertEqual(self.publisher.verify_revision(
            self.pid,"paged_edit",1)["clips"],6)


if __name__=="__main__":
    unittest.main()
