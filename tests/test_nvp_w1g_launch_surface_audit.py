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

    def test_g03_pinned_host_acl_exemption_rejects_arbitrary_new_subprocess(self):
        # The original SID-grant and low-integrity icacls host operations
        # cannot license another worker subprocess in this module.
        repo=Path(__file__).resolve().parents[1]
        receipt=audit_release_launch_surface(repo)
        self.assertNotIn("backend/nvp_g03_windows_appcontainer.py",
                         receipt["reviewed_legacy_launch_modules"])
        with TemporaryDirectory() as td:
            root=Path(td)
            shutil.copytree(repo/"backend",root/"backend")
            candidate=root/"backend"/"nvp_g03_windows_appcontainer.py"
            candidate.write_text(candidate.read_text("utf8")+
                "\nimport subprocess\ndef rogue_appcontainer():\n"
                "    subprocess.run(['uncontained-worker'])\n",encoding="utf8")
            with self.assertRaisesRegex(PermissionError,"AppContainer ACL host"):
                audit_release_launch_surface(root)

    def test_g03_pinned_host_acl_executable_refuses_tampering(self):
        repo=Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as td:
            root=Path(td)
            shutil.copytree(repo/"backend",root/"backend")
            candidate=root/"backend"/"nvp_g03_windows_appcontainer.py"
            original=candidate.read_text("utf8")
            self.assertIn('args=["icacls",str(path)]',original)
            candidate.write_text(original.replace(
                'args=["icacls",str(path)]',
                'args=["powershell",str(path)]'),encoding="utf8")
            with self.assertRaisesRegex(PermissionError,"AppContainer ACL host"):
                audit_release_launch_surface(root)

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

    def test_legacy_color_ffmpeg_windows_refusal_precedes_spawn(self):
        # A marker anywhere in source is not a process boundary: preserve
        # the original Windows denial in the actual _run control flow.
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/"backend"/"nvp_color_ocio.py").read_text("utf8"))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                and n.name=="_run")
        guard=next(n for n in fn.body if isinstance(n,ast.If))
        self.assertEqual(ast.unparse(guard.test),"os.name == 'nt'")
        self.assertTrue(any(isinstance(n,ast.Raise) for n in guard.body))
        calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call)
               and isinstance(n.func,ast.Attribute)
               and isinstance(n.func.value,ast.Name)
               and n.func.value.id=="subprocess" and n.func.attr=="run"]
        self.assertEqual(len(calls),1)
        self.assertLess(guard.lineno,calls[0].lineno)

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
