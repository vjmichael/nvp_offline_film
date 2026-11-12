"""W1-G release build marker: new native-fenced installers only."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from tools.nvp_w1g_release_build_marker import (
    FILENAME,marker_from_sources,verify_build_marker,
)


class ReleasedFenceMarkerContracts(unittest.TestCase):
    def test_rejects_pre_fence_runtime_and_corrupt_declaration(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            with self.assertRaisesRegex(PermissionError,"predates"):
                verify_build_marker(root)
            launcher=root/"launcher.py";launcher.write_text("release-fenced-worker")
            desktop=root/"desktop.py";desktop.write_text("release-fenced-gui")
            marker=marker_from_sources(launcher,desktop)
            (root/FILENAME).write_text(json.dumps(marker))
            self.assertEqual(verify_build_marker(root)["actual_kernel_process_tree_custody_verified"],False)
            marker["host_lifetime_gated"]=False
            (root/FILENAME).write_text(json.dumps(marker))
            with self.assertRaisesRegex(PermissionError,"invalid"):
                verify_build_marker(root)


if __name__=="__main__":
    unittest.main()
