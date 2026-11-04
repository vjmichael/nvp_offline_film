"""B14 isolated mapping and output safety contracts; real Blender path is later CI."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from backend.nvp_b14_picture_conform import _source_rows, _safe_directory, _frame_name, _sha


def fixture():
    source = {"frame_count": 3, "media_frames": [
        {"frame": n, "shot_id": "shot_A" if n < 3 else "shot_B",
         "png16_sha256": hashlib.sha256(f"p{n}".encode()).hexdigest(),
         "rgb48_sha256": hashlib.sha256(f"r{n}".encode()).hexdigest(),
         "source_exr_sha256": hashlib.sha256(f"e{n}".encode()).hexdigest()}
        for n in range(1, 4)]}
    mapping = []
    for dest, srcno in enumerate((3, 1, 1, 2), 1):
        row = source["media_frames"][srcno - 1]
        mapping.append({
            "edit_frame": dest, "source_frame": srcno, "shot_id": row["shot_id"],
            "original_png16_sha256": row["png16_sha256"],
            "original_rgb48_sha256": row["rgb48_sha256"],
            "original_float32_sha256": row["source_exr_sha256"]})
    return {"editorial_map": {"fps": 24, "frame_count": 4,
                               "frame_map": mapping}}, source


class B14PictureConformContract(unittest.TestCase):
    def test_trim_reorder_repeat_exact_source_frame_mapping(self):
        edit, original = fixture()
        self.assertEqual([(n, s["frame"]) for n, s in _source_rows(edit, original)],
                         [(1, 3), (2, 1), (3, 1), (4, 2)])

    def test_changed_source_hash_is_rejected(self):
        edit, original = fixture()
        edit["editorial_map"]["frame_map"][0]["original_png16_sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "disagrees"):
            list(_source_rows(edit, original))

    def test_changed_source_shot_is_rejected(self):
        edit, original = fixture()
        edit["editorial_map"]["frame_map"][1]["shot_id"] = "invented"
        with self.assertRaisesRegex(RuntimeError, "disagrees"):
            list(_source_rows(edit, original))

    def test_noncontiguous_destination_frames_rejected(self):
        edit, original = fixture()
        edit["editorial_map"]["frame_map"][2]["edit_frame"] = 4
        with self.assertRaisesRegex(RuntimeError, "contiguous"):
            list(_source_rows(edit, original))

    def test_out_of_range_source_frames_rejected(self):
        edit, original = fixture()
        edit["editorial_map"]["frame_map"][0]["source_frame"] = 4
        with self.assertRaisesRegex(RuntimeError, "bounded"):
            list(_source_rows(edit, original))

    def test_wrong_frame_rate_rejected(self):
        edit, original = fixture()
        edit["editorial_map"]["fps"] = 25
        with self.assertRaisesRegex(RuntimeError, "Unbounded"):
            list(_source_rows(edit, original))

    def test_reject_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output"
            _safe_directory(path)
            path.mkdir()
            with self.assertRaisesRegex(RuntimeError, "absent"):
                _safe_directory(path)

    def test_reject_symlinked_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            link = Path(tmp) / "link"
            try:
                link.symlink_to(real, target_is_directory=True)
            except OSError:
                self.skipTest("Symlink creation unavailable")
            with self.assertRaisesRegex(RuntimeError, "unsafe"):
                _safe_directory(link / "frames")

    def test_distinct_output_frame_names(self):
        self.assertEqual([_frame_name(n) for n in (1, 2, 10, 480)],
                         ["edit_000001.png", "edit_000002.png",
                          "edit_000010.png", "edit_000480.png"])

    def test_sha_bytes(self):
        self.assertEqual(_sha(b"abc"), hashlib.sha256(b"abc").hexdigest())


if __name__ == "__main__":
    unittest.main()
