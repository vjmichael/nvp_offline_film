"""SLATE-06 actual SQLite one-use approval transaction and cache durability."""
import tempfile
from pathlib import Path
import unittest

from backend.nvp_slate_preview_cache import SlatePreviewCache


class SQLiteOriginalPreviewReceipt(unittest.TestCase):
    def test_pending_and_denied_preview_states_persist_after_new_connection(self):
        with tempfile.TemporaryDirectory(prefix="nvp-slate06-durable-") as root:
            first=SlatePreviewCache(Path(root)/"cache")
            key="a"*64
            source="b"*64
            recipe="c"*64
            result=first.reserve(
                "project_durable",key,job_id="preview_first",
                source_sha256=source,recipe_sha256=recipe,
                width=320,height=180)
            self.assertEqual(result["status"],"PENDING")
            second=SlatePreviewCache(Path(root)/"cache")
            row=second._job("preview_first")
            self.assertEqual(row["state"],"PENDING")
            self.assertEqual(row["recipe_sha256"],recipe)
            duplicate=second.reserve(
                "project_durable",key,job_id="unapproved_duplicate",
                source_sha256=source,recipe_sha256=recipe,
                width=320,height=180)
            self.assertEqual(duplicate["status"],"ALREADY_PENDING")
            second.fail("preview_first",state="INTERRUPTED")
            self.assertEqual(first._job("preview_first")["state"],"INTERRUPTED")
            retry=first.reserve(
                "project_durable",key,job_id="new_authorization",
                source_sha256=source,recipe_sha256=recipe,
                width=320,height=180)
            self.assertEqual(retry["status"],"PENDING")
            with self.assertRaises(KeyError):
                second._job("preview_first")
            self.assertEqual(second._job("new_authorization")["state"],"PENDING")


if __name__=="__main__":
    unittest.main()
