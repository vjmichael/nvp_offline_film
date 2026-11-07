"""No-spoofing durability contracts for native 30-60s color package output."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from backend.nvp_native_color_export_journal import NativeColorOutputJournal


class NativeColorOutputRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="nvp-color-recovery-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.scope={
            "color_pipeline":"ocio_aces2_scene_linear_png16_unmastered",
            "project_id":"native.test.project",
            "take_document_sha256":"a"*64,
            "color_grade_sha256":"b"*64,
            "aces_config_sha256":"c"*64,
            "frame_count":1440,"fps_num":24,"fps_den":1,
            "original_data_immutable":True,
        }

    def journal(self,scope=None):
        return NativeColorOutputJournal(
            self.root,"RecoverColor001",scope or self.scope,
            picture_ext=".png")

    def test_crash_reopen_exact_source_and_safely_finish(self):
        first=self.journal()
        original=b"source-derived-picture-not-original-take"
        path=first.pictures/"0000001.png"
        path.write_bytes(original)
        row={"sample_index":0,"source_tick":"0",
             "camera_path":"/World/Camera",
             "original_scene_snapshot_sha256":"d"*64,
             "png_file":"0000001.png",
             "sha256":sha256(original).hexdigest(),
             "width":640,"height":360,"pixel_bit_depth":16}
        first.append(row)
        first.release()  # Simulated native host crash: OS unlocks.
        resumed=self.journal()
        try:
            self.assertEqual(resumed.records,[row])
            self.assertEqual(path.read_bytes(),original)
            # A staged/unreceipted second derivative is disposable only.
            unsealed=resumed.pictures/"0000002.png"
            unsealed.write_bytes(b"interrupted-original-derived-render")
        finally:resumed.release()
        third=self.journal()
        try:
            self.assertEqual(third.records,[row])
            self.assertFalse(unsealed.exists())
            with self.assertRaises(RuntimeError):
                self.journal({**self.scope,"color_grade_sha256":"f"*64})
            self.assertEqual(path.read_bytes(),original)
        finally:third.release()

    def test_no_concurrent_native_producer_and_no_changed_picture_sha(self):
        first=self.journal()
        try:
            with self.assertRaises(RuntimeError):
                self.journal()
            img=first.pictures/"0000001.png"
            img.write_bytes(b"verified-derived")
            first.append({"sample_index":0,"source_tick":"0",
                "camera_path":"/World/Camera",
                "png_file":"0000001.png",
                "sha256":sha256(img.read_bytes()).hexdigest()})
        finally:first.release()
        img.write_bytes(b"hostile-changed-image")
        with self.assertRaises(RuntimeError):
            self.journal()
        self.assertFalse(first.target.exists())

    def test_no_replace_publication_keeps_scope_receipt_until_rename(self):
        from backend.nvp_final_2d_native import _publish_no_replace
        first=self.journal()
        try:
            first.prepare_publish()
            self.assertTrue((first.staged/"scope.json").is_file())
            self.assertFalse(first.target.exists())
            _publish_no_replace(first.staged,first.target)
            first.finish_published()
            self.assertTrue(first.target.is_dir())
            self.assertFalse((first.target/"scope.json").exists())
            self.assertFalse((first.target/"owner.lock").exists())
            with self.assertRaises(FileExistsError):
                self.journal()
        finally:first.release()


if __name__=="__main__":
    unittest.main()
