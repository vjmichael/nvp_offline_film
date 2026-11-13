"""W1-G release-safe runtime subprocess graph has no undeclared production bypass."""
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_w1g_launch_surface_audit import audit_release_launch_surface,FORMAT


class RuntimeLaunchAuditTests(unittest.TestCase):
    def test_all_original_backend_worker_paths_are_audited(self):
        repo=Path(__file__).resolve().parents[1]
        receipt=audit_release_launch_surface(repo)
        self.assertEqual(receipt["format"],FORMAT)
        self.assertGreaterEqual(receipt["source_modules_audited"],100)
        self.assertFalse(receipt["kernel_execution_verified"])
        self.assertIn("backend/nvp_filming_cgroup_launch.py",
                      receipt["reviewed_legacy_launch_modules"])

    def test_new_uncontained_subprocess_fails_closed(self):
        repo=Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as td:
            root=Path(td)
            shutil.copytree(repo/"backend",root/"backend")
            rogue=root/"backend"/"nvp_studio.py"
            rogue.write_text(rogue.read_text("utf8")+
                "\nimport subprocess\ndef unauthorized_release_worker():\n"
                "    return subprocess.Popen(['fake-unreviewed'])\n","utf8")
            with self.assertRaisesRegex(PermissionError,"Unregistered"):
                audit_release_launch_surface(root)


if __name__=="__main__":
    unittest.main()
