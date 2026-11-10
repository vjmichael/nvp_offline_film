"""DA-03 host-created private leaf contract tests (not real delegated-cgroup acceptance)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import nvp_filming_cgroup_launch as launch


class ProvisionTests(unittest.TestCase):
    def test_rejects_nonabsolute_root(self):
        with self.assertRaises(ValueError):
            launch.create_private_group_and_launch(Path("relative"), "/bin/true", ["/bin/true"])

    def test_provisions_before_launch_and_returns_owned_leaf(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "cgroup.controllers").write_text("", encoding="ascii")
            (root / "cgroup.procs").write_text("", encoding="ascii")
            with patch.object(launch, "launch_attached_worker", return_value=object()) as spawn:
                group, process = launch.create_private_group_and_launch(root, "/bin/true", ["/bin/true"])
                self.assertTrue(group.is_dir())
                self.assertEqual(group.parent, root)
                self.assertTrue(group.name.startswith("nvp-film-"))
                self.assertIsNotNone(process)
                spawn.assert_called_once_with(group, "/bin/true", ["/bin/true"])

    def test_failed_spawn_removes_empty_leaf(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "cgroup.controllers").write_text("", encoding="ascii")
            (root / "cgroup.procs").write_text("", encoding="ascii")
            with patch.object(launch, "launch_attached_worker", side_effect=RuntimeError("denied")):
                with self.assertRaisesRegex(RuntimeError, "denied"):
                    launch.create_private_group_and_launch(root, "/bin/true", ["/bin/true"])
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["cgroup.controllers", "cgroup.procs"])

    def test_missing_kernel_controls_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(OSError):
                launch.create_private_group_and_launch(Path(temp), "/bin/true", ["/bin/true"])


if __name__ == "__main__":
    unittest.main()
