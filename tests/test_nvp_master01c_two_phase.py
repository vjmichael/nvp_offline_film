"""MASTER-01C: native prepared media never self-publishes; idempotent host commit."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_film_index import FilmIndex
from backend.nvp_longform_review import index_technical_reel, reopen_review
from backend.nvp_master01c_two_phase import (
    prepare_unpublished, verify_prepared, commit_prepared,
)
from backend.nvp_studio import Studio
from tests.test_nvp_longform_review import make_prores_with_pcm24


class TwoPhaseFilmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ff, cls.probe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if cls.ff is None or cls.probe is None:
            raise unittest.SkipTest("Genuine FFmpeg+FFprobe required")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nvp-master01c-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.studio = Studio(self.root / "studio.sqlite3")
        self.index = FilmIndex(self.studio)
        self.pid = self.studio.create_project("Two-phase", "Source-indexed technical review")["id"]
        self.refs = []
        for number, color in enumerate(("red", "green", "blue")):
            file = self.root / f"source{number}.mov"
            make_prores_with_pcm24(self.ff, file, seconds=10,
                                   color=color, tone=430 + number * 50)
            media = self.index.put_media_file(self.pid, file, "video/quicktime")
            producer = "p" + str(number)
            self.index.register_revision(self.pid, producer, "presentation", {
                "format": "nvp.master01c.original_test_source.v1",
                "movie_sha256": media["sha256"], "frames": 240,
                "creator_approved_final_master": False,
                "dcp_delivered": False}, expected_revision=0)
            name = "r" + str(number)
            index_technical_reel(self.index, self.pid, name, producer, 1)
            self.refs.append({"object_id": name, "revision": 1})

    def prepare(self, identity="prepared_review", folder="stage"):
        return prepare_unpublished(self.index, self.pid, identity, self.refs,
                                   self.root / folder, ffmpeg=self.ff, ffprobe=self.probe)

    def test_real_thirty_second_media_remains_unpublished_until_host_commit(self):
        staged = self.prepare()
        self.assertEqual(staged["status"], "PREPARED_UNPUBLISHED")
        self.assertEqual(staged["frames"], 720)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "prepared_review")
        proof = verify_prepared(self.index, self.root / "stage",
                                ffmpeg=self.ff, ffprobe=self.probe)
        self.assertEqual(proof["movie_sha256"], staged["movie_sha256"])
        done = commit_prepared(self.index, self.root / "stage",
                               ffmpeg=self.ff, ffprobe=self.probe)
        self.assertEqual(done["state"], "COMMITTED_UNAPPROVED")
        self.assertFalse(done["creator_approved_final_master"])
        self.assertEqual(done["frames"], 720)
        self.assertEqual(len(self.index.history(self.pid, "prepared_review")), 1)
        again = commit_prepared(FilmIndex(Studio(self.studio.db_path)),
                                self.root / "stage", ffmpeg=self.ff, ffprobe=self.probe)
        self.assertEqual(again["document_sha256"], done["document_sha256"])
        self.assertEqual(len(self.index.history(self.pid, "prepared_review")), 1)

    def test_tampered_prepared_video_rejected_before_any_index_publication(self):
        self.prepare()
        movie = self.root / "stage" / "prepared.mov"
        with movie.open("r+b") as file:
            file.seek(1024)
            original = file.read(1)
            file.seek(1024)
            file.write(bytes([original[0] ^ 1]))
        with self.assertRaisesRegex(RuntimeError, "changed"):
            commit_prepared(self.index, self.root / "stage", ffmpeg=self.ff, ffprobe=self.probe)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "prepared_review")

    def test_worker_crash_after_blob_storage_can_resume_without_encoding_again(self):
        self.prepare()
        original = self.index.register_revision
        def stop_before_commit(*args, **kwargs):
            raise RuntimeError("injected host failure after blob was stored")
        with patch.object(self.index, "register_revision", side_effect=stop_before_commit):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                commit_prepared(self.index, self.root / "stage",
                                ffmpeg=self.ff, ffprobe=self.probe)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "prepared_review")
        resumed = commit_prepared(FilmIndex(Studio(self.studio.db_path)),
                                  self.root / "stage", ffmpeg=self.ff, ffprobe=self.probe)
        self.assertEqual(resumed["revision"], 1)
        self.assertEqual(resumed["frames"], 720)

    def test_host_failure_after_index_commit_does_not_duplicate_immutable_film(self):
        self.prepare()
        original = self.index.register_revision
        def after_commit(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("injected crash immediately after FilmIndex commit")
        with patch.object(self.index, "register_revision", side_effect=after_commit):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                commit_prepared(self.index, self.root / "stage", ffmpeg=self.ff, ffprobe=self.probe)
        reopened = FilmIndex(Studio(self.studio.db_path))
        result = commit_prepared(reopened, self.root / "stage", ffmpeg=self.ff, ffprobe=self.probe)
        self.assertEqual(result["revision"], 1)
        self.assertEqual(len(reopened.history(self.pid, "prepared_review")), 1)
        self.assertEqual(reopen_review(reopened, self.pid, "prepared_review")["frames"], 720)

    def test_original_reel_tamper_blocks_postcrash_publication(self):
        self.prepare()
        reel = self.index.read_revision(self.pid, "r1", 1)
        path = Path(self.index.verify_media_file(self.pid, reel["data"]["movie_sha256"])["path"])
        with path.open("r+b") as file:
            file.seek(900)
            original = file.read(1)
            file.seek(900)
            file.write(bytes([original[0] ^ 1]))
        with self.assertRaisesRegex(RuntimeError, "integrity"):
            commit_prepared(self.index, self.root / "stage", ffmpeg=self.ff, ffprobe=self.probe)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid, "prepared_review")


if __name__ == "__main__":
    unittest.main()