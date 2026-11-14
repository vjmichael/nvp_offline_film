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

if __name__=="__main__":
    unittest.main()
