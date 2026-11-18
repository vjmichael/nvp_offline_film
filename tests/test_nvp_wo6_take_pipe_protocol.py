"""Actual private worker CLI refusal cases; not native sandbox acceptance."""
from pathlib import Path
import struct
import subprocess
import sys
import unittest

from backend.nvp_openusd_take import canonical
from tools.nvp_wo6_take_worker import MAGIC_IN


class NativePipeDenials(unittest.TestCase):
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
