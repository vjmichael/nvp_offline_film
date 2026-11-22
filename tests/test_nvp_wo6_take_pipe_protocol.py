"""Actual private worker CLI refusal cases; not native sandbox acceptance."""
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from tempfile import TemporaryDirectory

from backend.nvp_openusd_take import canonical
from tools.nvp_wo6_take_worker import MAGIC_IN


class NativePipeDenials(unittest.TestCase):
    def test_code_only_root_pin_and_isolated_package_import(self):
        from backend.nvp_wo6_native_take_action import _source_code_scope
        repo=Path(__file__).resolve().parents[1]
        with _source_code_scope(repo) as (root,verify):
            files=verify()
            self.assertIn("backend/__init__.py",files)
            self.assertEqual(set(p for p in files if p.startswith("tools/")),{
                "tools/__init__.py","tools/nvp_wo6_take_worker.py",
                "tools/nvp_g03_protected_scene_worker.py"})
            self.assertTrue(all(p.endswith(".py") for p in files))
            result=subprocess.run([sys.executable,"-I","-B",
                str(root/"tools"/"nvp_wo6_take_worker.py"),"x"],
                input=b"",capture_output=True,timeout=30,cwd=root.parent)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(3,b"",b""))
            (root/"tools"/"nvp_wo6_take_worker.py").write_bytes(b"tampered")
            with self.assertRaises(PermissionError):verify()
        self.assertFalse(root.exists())

    def test_pipe_write_retries_short_writes(self):
        from backend.nvp_wo6_native_take_action import _write_all
        class ShortPipe:
            def __init__(self):self.data=bytearray();self.closed=False
            def write(self,data):self.data.extend(data[:3]);return min(3,len(data))
            def flush(self):pass
            def close(self):self.closed=True
        pipe=ShortPipe();errors=[]
        _write_all(pipe,b"exact-original-frame",errors)
        self.assertEqual(bytes(pipe.data),b"exact-original-frame")
        self.assertEqual(errors,[])
        self.assertTrue(pipe.closed)

    def test_malformed_scope_trailing_and_asset_input_fail_silently(self):
        worker=Path(__file__).resolve().parents[1]/"tools"/"nvp_wo6_take_worker.py"
        source={"format":"nvp.wo6.take_worker_input.v1","scope_sha256":"a"*64,
                "scene":{"contains_external_references":False,
                         "asset_bindings":[{"foreign":"blocked"}]},
                "layers":{},"events":[],"ticks":[]}
        raw=canonical(source)
        frame=MAGIC_IN+struct.pack("!Q",len(raw))+raw
        for scope,payload in (("x",frame),("b"*64,frame),
                              ("a"*64,frame+b"x"),("a"*64,frame),("a"*64,b"wrong")):
            with self.subTest(scope=scope,payload_length=len(payload)):
                result=subprocess.run([sys.executable,"-B",str(worker),scope],
                    input=payload,capture_output=True,timeout=15)
                self.assertEqual((result.returncode,result.stdout,result.stderr),(3,b"",b""))


if __name__=="__main__":
    unittest.main()
