"""W1-G release-safe runtime subprocess graph has no undeclared production bypass."""
import ast
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

    def test_retired_blender_launch_cannot_rejoin_reviewed_release_graph(self):
        root=Path(__file__).resolve().parents[1]
        retired="backend/nvp_w1g_legacy_blender_launch.py"
        self.assertFalse((root/retired).exists())
        receipt=audit_release_launch_surface(root)
        self.assertNotIn(retired,receipt["reviewed_legacy_launch_modules"])
        with TemporaryDirectory() as td:
            copied=Path(td)
            shutil.copytree(root/"backend",copied/"backend")
            (copied/retired).write_text(
                "import subprocess\\ndef retired_bypass():\\n"
                "    return subprocess.run(['unowned-blender'])\\n",
                encoding="utf8")
            with self.assertRaisesRegex(PermissionError,"Retired uncontrolled Blender"):
                audit_release_launch_surface(copied)

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

    def test_retired_webm_stt_windows_popen_remains_denied(self):
        # Do not import the legacy CUDA/Whisper engine just to test its guard.
        root=Path(__file__).resolve().parents[1]
        source=(root/"backend"/"nvp_stt_service.py").read_text("utf8")
        module=ast.parse(source)
        fn=next(n for n in module.body if isinstance(n,ast.FunctionDef)
                and n.name=="decode_webm_to_pcm")
        guard=next(n for n in fn.body if isinstance(n,ast.If))
        self.assertEqual(ast.unparse(guard.test),"os.name == 'nt'")
        self.assertTrue(any(isinstance(n,ast.Raise) for n in guard.body))
        popens=[n for n in ast.walk(fn) if isinstance(n,ast.Call)
                and isinstance(n.func,ast.Attribute) and n.func.attr=="Popen"]
        self.assertEqual(len(popens),1)
        self.assertLess(guard.lineno,popens[0].lineno)


if __name__=="__main__":
    unittest.main()
