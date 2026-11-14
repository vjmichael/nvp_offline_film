"""CONV-06 source admission regression: original CAM-FX05 render/reopen is private.

The native executable, delegated cgroup and Windows SCM/AppContainer remain
independent OS-level acceptance requirements. These static checks do not
claim to witness kernel containment or approved picture publication.
"""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HOSTS=(
    "nvp_usd_film01f_blender_host.py",
    "nvp_usd_film02m_h_render_handoff.py",
    "nvp_cam_fx05_protected_cycles_host.py",
)

class PrivateFilmSourceAdmission(unittest.TestCase):
    def test_all_original_world_and_camera_render_operations_require_os_custody(self):
        for name in HOSTS:
            with self.subTest(host=name):
                source=(ROOT/"backend"/name).read_text("utf8")
                parsed=ast.parse(source,name)
                calls=[x for x in ast.walk(parsed) if isinstance(x,ast.Call)
                       and isinstance(x.func,ast.Name)
                       and x.func.id=="BlenderOperation"]
                self.assertEqual(len(calls),2,"Review newly added native worker contracts")
                for op in calls:
                    spec={k.arg:k.value for k in op.keywords}
                    for requirement in ("require_linux_cgroup_v2",
                                        "require_private_isolation"):
                        self.assertIn(requirement,spec)
                        self.assertIsInstance(spec[requirement],ast.Constant)
                        self.assertIs(spec[requirement].value,True)
                self.assertNotIn("subprocess.Popen(",source)
                self.assertNotIn("shell=True",source)

if __name__=="__main__":
    unittest.main()
