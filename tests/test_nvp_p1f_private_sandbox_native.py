"""P1-F production boundary contracts: deny private unauthenticated OS launches.

These tests do not simulate passing real kernel custody. Actual Linux
delegated cgroup + bubblewrap and Windows AppContainer/WFP are independent
physical/release gates. They check the source cannot silently fall back to
bare Job/cgroup custody when source data is private.
"""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_worker_containment import launch_contained
from backend.nvp_worker_private_sandbox import sandbox_command,private_os_preflight


class PrivateFilmSandboxContract(unittest.TestCase):
    def test_no_unisolated_private_launch_or_shell_fallback(self):
        with self.assertRaisesRegex(RuntimeError,"whole-tree"):
            launch_contained(
                [str(Path(sys.executable).resolve()),"-V"],
                cwd=str(Path(tempfile.gettempdir()).resolve()),
                stdout=None,stderr=None,memory_mb=512,
                linux_cgroup_tree_required=False,
                private_isolation_required=True)
        with self.assertRaises(RuntimeError):
            private_os_preflight() if os.name=="nt" else (
                sandbox_command(["/bin/sh","-c","echo leak"],"relative"))

    @unittest.skipUnless(sys.platform=="linux","Linux namespace argv")
    def test_private_kernel_command_has_no_network_and_only_explicit_job_mount(self):
        with tempfile.TemporaryDirectory(prefix="nvp-sandbox-source-") as tmp:
            job=Path(tmp).resolve()
            binary=Path("/usr/bin/python3")
            if not binary.is_file():
                self.skipTest("System reviewed binary not installed")
            with patch("backend.nvp_worker_private_sandbox._pinned_linux_bwrap",
                       return_value="a"*64):
                argv=sandbox_command(
                    [str(binary),"-V"],str(job))
            words=argv["command"]
            self.assertEqual(words[0],"/usr/bin/bwrap")
            self.assertIn("--unshare-net",words)
            self.assertIn("--unshare-user",words)
            self.assertIn("--unshare-pid",words)
            self.assertIn("--die-with-parent",words)
            self.assertIn("--bind",words)
            self.assertEqual(words[words.index("--bind")+1],str(job))
            self.assertEqual(words[-3:],["--",str(binary),"-V"])
            self.assertNotIn("--share-net",words)
            self.assertNotIn("--bind-try",words)
            self.assertNotIn("--bind"," ".join(words[:words.index("--bind")]))


if __name__=="__main__":
    unittest.main()
