"""DA-03 host launch contract; no kernel custody acceptance implied."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.nvp_filming_cgroup_launch import launch_attached_worker


class HostLaunchContract(unittest.TestCase):
    def test_launch_requires_absolute_paths(self):
        if sys.platform != "linux":
            self.skipTest("Linux-only contract")
        with self.assertRaises(ValueError):
            launch_attached_worker(Path("relative"), "/bin/true", ["/bin/true"])
        with self.assertRaises(ValueError):
            launch_attached_worker(Path("/sys/fs/cgroup/private"), "true", ["true"])

    def test_launch_uses_child_gate_without_shell(self):
        if sys.platform != "linux":
            self.skipTest("Linux-only contract")
        with patch("subprocess.Popen") as popen:
            launch_attached_worker(Path("/sys/fs/cgroup/private"), "/bin/true", ["/bin/true"])
        args, kwargs = popen.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertEqual(args[0][1], "-c")
        self.assertIn("attach_then_exec", args[0][2])
        self.assertEqual(args[0][-2:], ["/sys/fs/cgroup/private", "/bin/true"])
        self.assertIs(kwargs["shell"], False)
        self.assertIs(kwargs["close_fds"], True)


if __name__ == "__main__":
    unittest.main()
