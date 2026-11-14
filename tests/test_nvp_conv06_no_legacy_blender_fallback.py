"""CONV-06 fail-closed regression for W1-G retired uncontrolled Linux Blender fallback.

This is a source quarantine contract. Real Linux delegated cgroup and Windows
SCM/AppContainer kernel acceptance must be independently witnessed.
"""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class NoLegacyWorkerFallback(unittest.TestCase):
    def test_old_linux_subprocess_runner_is_not_installed(self):
        self.assertFalse(
            (ROOT/"backend"/"nvp_w1g_legacy_blender_launch.py").exists(),
            "Old Linux direct subprocess fallback must remain quarantined")
        self.assertFalse(
            (ROOT/"tests"/"test_nvp_w1g_legacy_blender_launch.py").exists(),
            "Historical unsafe-runner test cannot be mistaken for acceptance")

    def test_source_bound_native_camera_only_uses_owned_supervisor(self):
        for name in ("nvp_cam_fx05_protected_cycles_host.py",
                     "nvp_usd_film01f_blender_host.py",
                     "nvp_usd_film02m_h_render_handoff.py"):
            with self.subTest(host=name):
                code=(ROOT/"backend"/name).read_text("utf8")
                self.assertIn("BlenderWorkerSupervisor",code)
                self.assertIn("require_private_isolation=True",code)
                self.assertNotIn("legacy_blender_launch",code)
                self.assertNotIn("subprocess.Popen(",code)
                self.assertNotIn("shell=True",code)

    def test_original_blender_acceptance_imports_without_legacy_worker_or_staging(self):
        import sys
        from tempfile import TemporaryDirectory
        from backend.nvp_blender_acceptance import (
            blender_available,run_trusted_blender,run_acceptance,
            run_meshpack_acceptance)
        with self.assertRaisesRegex(PermissionError,"retired"):
            run_trusted_blender([sys.executable,"--version"],capture_output=True)
        found=blender_available(sys.executable)
        self.assertFalse(found["available"])
        self.assertIn("PermissionError",found["reason"])
        class SourceCannotStage:
            def export_manifest(self,*_):
                raise AssertionError("Unapproved source manifest was staged")
            def export_bundle(self,*_):
                raise AssertionError("Unapproved source mesh was staged")
        with TemporaryDirectory() as tmp:
            project=SourceCannotStage()
            first=run_acceptance(project,"f"*32,"Scene",tmp,executable=sys.executable)
            second=run_meshpack_acceptance(project,"f"*32,"Scene",tmp,executable=sys.executable)
            for response in (first,second):
                self.assertEqual(response["status"],"blocked_no_blender")
                self.assertFalse(response["source_staged"])
                self.assertFalse(response["worker_authorized"])
            self.assertEqual(list(Path(tmp).iterdir()),[],
                             "Unapproved Blender acceptance leaked original bytes")

if __name__=="__main__":
    unittest.main()
