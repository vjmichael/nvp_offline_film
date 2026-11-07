"""WO3 native process-kill acceptance at the atomic directory publication boundary.

Uses a fresh child process with os._exit (no Python finally/cleanup). Verifies
that prior user directories cannot be replaced and successfully promoted data
survives the parent process's inspection after an abrupt writer exit.
This is not a full filesystem power-failure or FilmIndex transaction test.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import subprocess
import sys
import unittest


class WO3ProcessKillPublish(unittest.TestCase):
    @unittest.skipUnless(sys.platform in ("linux","win32"),
                         "Native no-replace platform required")
    def test_child_exits_immediately_after_atomic_publish(self):
        with TemporaryDirectory() as t:
            root = Path(t).resolve()
            stage = root/".nvp-wo3-crash-boundary"
            stage.mkdir()
            (stage/"CPL.xml").write_bytes(b"original-export-payload")
            destination = root/"DCP_test"
            code = (
                "import os,sys;"
                "from backend.nvp_wo3_atomic_publish import atomic_publish_directory;"
                "atomic_publish_directory(sys.argv[1],sys.argv[2]);"
                "os._exit(91)"
            )
            env = dict(os.environ)
            # The dedicated test executes from checked-out project root.
            child = subprocess.run([sys.executable,"-c",code,
                                    str(stage),str(destination)],
                                   cwd=str(Path(__file__).resolve().parents[1]),
                                   env=env,timeout=20,check=False,
                                   stdin=subprocess.DEVNULL,capture_output=True)
            self.assertEqual(child.returncode,91,
                             child.stderr.decode("utf-8","replace")[:300])
            self.assertFalse(stage.exists())
            self.assertEqual((destination/"CPL.xml").read_bytes(),
                             b"original-export-payload")

    @unittest.skipUnless(sys.platform in ("linux","win32"),
                         "Native no-replace platform required")
    def test_foreign_preexisting_directory_survives_writer_collision(self):
        with TemporaryDirectory() as t:
            root = Path(t).resolve()
            stage = root/".nvp-wo3-collision"
            stage.mkdir()
            (stage/"CPL.xml").write_bytes(b"uncommitted")
            destination=root/"DCP_reserved"
            destination.mkdir()
            (destination/"owner").write_bytes(b"creator-original")
            code=(
                "import sys;"
                "from backend.nvp_wo3_atomic_publish import atomic_publish_directory;"
                "atomic_publish_directory(sys.argv[1],sys.argv[2])"
            )
            child=subprocess.run([sys.executable,"-c",code,
                                  str(stage),str(destination)],
                                 cwd=str(Path(__file__).resolve().parents[1]),
                                 timeout=20,check=False,
                                 stdin=subprocess.DEVNULL,capture_output=True)
            self.assertNotEqual(child.returncode,0)
            self.assertEqual((destination/"owner").read_bytes(),
                             b"creator-original")
            self.assertEqual((stage/"CPL.xml").read_bytes(),b"uncommitted")


if __name__ == "__main__":
    unittest.main()
