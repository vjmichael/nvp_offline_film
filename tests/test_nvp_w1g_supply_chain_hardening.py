"""W1-G refuses archive traversal and ambiguous reviewed worker identities."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from tools.nvp_w1g_native_dependencies import FORMAT as WHEEL_FORMAT,validate_lock
from tools.nvp_w1g_worker_package import FORMAT as WORKERS,_check_roster


class NativeSupplyChainHardening(unittest.TestCase):
    def _wheel(self,root,extra):
        name="sample_pkg-1.0-py3-none-any.whl"
        with zipfile.ZipFile(root/name,"w") as z:
            z.writestr("sample_pkg-1.0.dist-info/METADATA",
                       "Metadata-Version: 2.1\nName: sample-pkg\nVersion: 1.0\n")
            for filename,data in extra:
                z.writestr(filename,data)
        lock={"format":WHEEL_FORMAT,"platform":"windows-amd64",
              "wheels":[{"name":"sample-pkg","version":"1.0",
                         "filename":name,
                         "sha256":sha256((root/name).read_bytes()).hexdigest(),
                         "license_review":"Owner-reviewed redistribution reference"}]}
        return lock

    def test_wheel_rejects_parent_traversal_before_pip(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            lock=self._wheel(root,[("../outside","untrusted")])
            with self.assertRaisesRegex(RuntimeError,"Unsafe"):
                validate_lock(lock,root,platform="windows-amd64")

    def test_wheel_rejects_case_collisions_and_windows_drives(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            lock=self._wheel(root,[("dir/a.txt","one"),("dir/A.TXT","two")])
            with self.assertRaisesRegex(RuntimeError,"Unsafe"):
                validate_lock(lock,root,platform="windows-amd64")
            lock=self._wheel(root,[("C:dangerous","bad")])
            with self.assertRaisesRegex(RuntimeError,"Unsafe"):
                validate_lock(lock,root,platform="windows-amd64")

    def test_worker_roster_rejects_duplicate_files_and_special_names(self):
        base={"format":WORKERS,"platform":"windows-amd64"}
        sha="a"*64
        for names in (["Render.exe","render.exe"],["good.exe","CON.exe"],
                      ["good.exe","C:bad.exe"]):
            roster={**base,"workers":[
                {"role":role,"filename":name,"sha256":sha}
                for role,name in zip(["scene_render","editorial"],names)]}
            with self.assertRaisesRegex(RuntimeError,"Untrusted"):
                _check_roster(roster)


if __name__=="__main__":
    unittest.main()
