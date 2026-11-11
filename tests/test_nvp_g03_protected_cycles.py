"""G03-F3 Blender/Cycles protocol and protected-host boundary tests.

Real Blender runs only with the separately SHA-verified official executable.
Until filesystem+network AppContainer custody is implemented and verified,
private movie rendering MUST be denied; synthetic CI is not security proof.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

from backend.nvp_g03_protected_cycles_supervisor import (
    ProtectedCyclesError,ProtectedCyclesSupervisor,_verify_png,
    _geometry_from_opensud)
from tools.nvp_g03_cycles_inmemory_worker import (
    _decode_spec,_png_rgba)

SAMPLE=b'#usda 1.0\n\ndef Cube "OriginalBox" { double size = 2 }\n'
PASS="G03 synthetic Blender source and renderer passphrase"


class CyclesProtocolTests(unittest.TestCase):
    def test_png_from_float_pixels_has_valid_crc_dimensions(self):
        data=_png_rgba(32,32,[0.25,0.5,0.75,1.0]*1024)
        self.assertEqual(_verify_png(data,width=32,height=32),None)
        broken=bytearray(data);broken[-6]^=1
        with self.assertRaises(ProtectedCyclesError):
            _verify_png(bytes(broken),width=32,height=32)

    def test_scene_schema_rejects_external_paths_and_code(self):
        identity=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
        allowed={"format":"nvp.g03.cycles.source.v1","width":64,
                 "height":64,"samples":2,"objects":[
                     {"kind":"Cube","name":"Box","matrix":identity,
                      "size":2,"vertices":[],"faces":[]}]}
        self.assertEqual(_decode_spec(json.dumps(allowed).encode())["width"],64)
        for key,value in [("script","bad"),("filepath","bad"),("texture","@x")]:
            with self.assertRaises(ValueError):
                _decode_spec(json.dumps({**allowed,key:value}).encode())
        malicious={**allowed,"objects":[{**allowed["objects"][0],
                     "kind":"PythonScript"}]}
        with self.assertRaises(ValueError):
            _decode_spec(json.dumps(malicious).encode())

    @unittest.skipUnless(sys.platform=="win32","Real USD native Windows gate")
    def test_real_usd_parser_accepts_primitive_and_refuses_external_assets(self):
        try:
            from pxr import Sdf
        except ImportError:
            self.skipTest("Real OpenUSD unavailable in this Python environment")
        parsed=json.loads(_geometry_from_opensud(SAMPLE))
        self.assertEqual(parsed["objects"][0]["kind"],"Cube")
        self.assertEqual(parsed["objects"][0]["name"],"OriginalBox")
        with self.assertRaises(ProtectedCyclesError):
            _geometry_from_opensud(
                b'#usda 1.0\n(\n subLayers = [@../../other.usda@]\n)\n')

    @unittest.skipUnless(sys.platform=="win32","Windows private film only")
    def test_real_windows_private_renderer_denied_without_sandbox(self):
        blender=os.environ.get("NVP_NATIVE_BLENDER_EXECUTABLE")
        if not blender:
            self.skipTest("No independently reviewed native Blender binary")
        from backend.nvp_blender_worker import sha_file
        from backend.nvp_g03_live_store import LiveFilmStore
        import secrets
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"encrypted"
            store=LiveFilmStore(root)
            pid=secrets.token_hex(16)
            token="host-reviewed-"+secrets.token_hex(24)
            store.create(pid,"Protected Blender scene","","",PASS)
            store.authorize(pid,PASS,token)
            store.put_original(pid,token,"scene/source.usda",SAMPLE)
            host=ProtectedCyclesSupervisor(
                store,blender_executable=blender,
                blender_sha256=sha_file(Path(blender)),
                review_authority=lambda *args:True)
            with self.assertRaisesRegex(ProtectedCyclesError,"AppContainer"):
                host.render(pid,token,"scene/source.usda",
                            "render/frame.png",
                            "native-approved-"+secrets.token_hex(20))
            self.assertEqual(len(store.read(pid,token)["source_assets"]),1)
            self.assertEqual(store.protected_worker_runs(pid,token),[])

    @unittest.skipUnless(sys.platform=="win32","Real Windows Job plus DPAPI only")
    def test_real_cycles_synthetic_ci_binary_and_encrypted_png(self):
        blender=os.environ.get("NVP_NATIVE_BLENDER_EXECUTABLE")
        if not blender or os.environ.get("GITHUB_ACTIONS")!="true":
            self.skipTest("Only actual SHA-verified Blender in isolated CI")
        from backend.nvp_blender_worker import sha_file
        from backend.nvp_g03_live_store import LiveFilmStore
        import secrets
        with tempfile.TemporaryDirectory(prefix="nvp-g03-real-blender-") as tmp:
            store=LiveFilmStore(Path(tmp)/"sealed")
            pid=secrets.token_hex(16)
            token="synthetic-one-use-"+secrets.token_hex(20)
            store.create(pid,"Synthetic Blender test","","",PASS)
            store.authorize(pid,PASS,token)
            store.put_original(pid,token,"original/box.usda",SAMPLE)
            ticket="reviewed-synthetic-"+secrets.token_hex(24)
            approvals={ticket}
            def review(*args):
                if args[-1] not in approvals:return False
                approvals.remove(args[-1]);return True
            worker=ProtectedCyclesSupervisor(
                store,blender_executable=blender,
                blender_sha256=sha_file(Path(blender)),
                review_authority=review)
            result=worker.render(pid,token,"original/box.usda",
                "derived/cycles.png",ticket,synthetic_ci_only=True)
            self.assertEqual(result["state"],"SUCCEEDED")
            png=store.get_original(pid,token,"derived/cycles.png")
            _verify_png(png)
            self.assertEqual(hashlib.sha256(png).hexdigest(),result["output_sha256"])
            self.assertEqual(store.get_original(pid,token,"original/box.usda"),SAMPLE)
            for file in (Path(tmp)/"sealed").rglob("*"):
                if file.is_file():
                    data=file.read_bytes()
                    self.assertNotIn(b"OriginalBox",data)
                    self.assertNotIn(b"\x89PNG",data)
            with self.assertRaises(ProtectedCyclesError):
                worker.render(pid,token,"original/box.usda",
                              "derived/cycles2.png",ticket,synthetic_ci_only=True)


if __name__=="__main__":
    unittest.main()
