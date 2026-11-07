"""WO4 staged native-host acceptance away from checkout.

Runs real trusted host integration tests from a fresh isolated copied backend,
with source checkout excluded from PYTHONPATH and child cwd. This is an
INSTALLATION-LIKE SMOKE TEST, not an NSIS/DEB signed installer claim.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil
import subprocess
import sys
import unittest


class StagedNativeHostSmokeTest(unittest.TestCase):
    def test_staged_runtime_background_job_survives_uninstall_root(self):
        repo=Path(__file__).resolve().parents[1]
        with TemporaryDirectory(prefix="nvp-native-staged-") as tmp:
            root=Path(tmp).resolve()
            installed=root/"nvp-installed-runtime"
            installed.mkdir()
            shutil.copytree(
                repo/"backend",installed/"backend",
                ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
            tests=installed/"tests"
            tests.mkdir()
            shutil.copy2(repo/"tests"/"test_nvp_production_host.py",
                         tests/"test_nvp_production_host.py")
            env=os.environ.copy()
            env["PYTHONPATH"]=str(installed)
            env["PYTHONNOUSERSITE"]="1"
            result=subprocess.run(
                [sys.executable,"-m","unittest","discover",
                 "-s","tests","-p","test_nvp_production_host.py","-v"],
                cwd=installed,env=env,stdin=subprocess.DEVNULL,
                capture_output=True,text=True,timeout=130,check=False)
            self.assertEqual(result.returncode,0,
                             result.stderr[-2800:]+result.stdout[-1200:])
            self.assertIn("test_supervisor_survives_actual_short_lived_ui_parent_exit",
                          result.stderr)
            self.assertIn("OK",result.stderr)
            # The stage is user-replaceable; no created original media should
            # live under the released native code folder. Tests use temp media.
            self.assertFalse((installed/"studio.sqlite3").exists())
            self.assertTrue((installed/"backend"/"nvp_production_host.py").exists())


if __name__=="__main__":
    unittest.main()
