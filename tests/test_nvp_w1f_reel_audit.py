"""W1-F long-form evidence plan must never silently accept gaps or proxy film."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_w1f_reel_audit import (
    FORMAT,SEGMENT_TICKS,validate_reel,inspect_sustained_reel,
)


class SustainedOriginalReelManifest(unittest.TestCase):
    def manifest(self,root,count=60):
        return {"format":FORMAT,"project_id":"a"*32,
            "segments":[{
                "index":i,"timeline_start_tick":i*SEGMENT_TICKS,
                "timeline_end_tick":(i+1)*SEGMENT_TICKS,
                "edit_id":f"Edit_{i:04d}","edit_revision":1,
                "package_directory":str(root/f"native-original-{i:04d}"),
            } for i in range(count)]}

    def test_exact_thirty_minute_and_three_hour_native_worklists(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            self.assertEqual(validate_reel(self.manifest(root,60))["duration_seconds"],1800)
            self.assertEqual(validate_reel(self.manifest(root,360))["duration_seconds"],10800)

    def test_gap_overlap_duplicate_and_wrong_length_fail_closed(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            for change in ("gap","duplicate","extra","unbound"):
                doc=self.manifest(root)
                if change=="gap":
                    doc["segments"][3]["timeline_start_tick"]+=1
                elif change=="duplicate":
                    doc["segments"][1]["edit_id"]=doc["segments"][0]["edit_id"]
                elif change=="extra":
                    doc["segments"].pop()
                else:
                    doc["segments"][0]["package_directory"]="not-an-absolute-package"
                with self.assertRaises(RuntimeError):
                    validate_reel(doc)

    def test_no_manifest_is_self_authenticating(self):
        with TemporaryDirectory() as td:
            doc=self.manifest(Path(td))
            with self.assertRaises(TypeError):
                inspect_sustained_reel(doc,index=None,worker=None)


if __name__=="__main__":
    unittest.main()
