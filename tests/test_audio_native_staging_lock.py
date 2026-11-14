"""Cross-process filesystem lock acceptance, including real child death."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from backend.nvp_audio_native_staging_lock import AudioStagingLock


class NativeAudioLockTests(unittest.TestCase):
    def test_single_owner_and_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "staging"
            with AudioStagingLock(path):
                with self.assertRaisesRegex(RuntimeError, "owned by another"):
                    with AudioStagingLock(path):
                        pass
            with AudioStagingLock(path):
                pass

    def test_real_child_killed_releases_os_lock(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "staging"
            marker = Path(d) / "locked.ready"
            script = (
                "import sys,time;from pathlib import Path;"
                "from backend.nvp_audio_native_staging_lock import AudioStagingLock;"
                "lock=AudioStagingLock(Path(sys.argv[1])).acquire();"
                "Path(sys.argv[2]).write_text('locked');"
                "time.sleep(60)"
            )
            root = Path(__file__).resolve().parents[1]
            proc = subprocess.Popen([sys.executable, "-c", script,
                                     str(path),str(marker)],
                                    cwd=root, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 15
                while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(marker.exists(), proc.stderr.read().decode()
                                if proc.poll() is not None else "Child never acquired OS lock")
                with self.assertRaisesRegex(RuntimeError, "owned by another"):
                    AudioStagingLock(path).acquire()
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=10)
                proc.stderr.close()
            # The OS releases the FD lock on process death, without deleting
            # the persistent lock-file identity or guessing an owner PID.
            with AudioStagingLock(path):
                pass


if __name__ == "__main__":
    unittest.main()
