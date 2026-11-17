"""Scoped WO3 admission denials; no synthetic native success claims."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from backend.nvp_wo3_native_codecs import (
    ApprovedCodecBinary,_approved_arguments,_sha,ProtectedCodecAuthority)
from backend.nvp_wo3_mxf_native import _frame_receipts

class ProtectedWO3Contract(unittest.TestCase):
    def test_binary_hash_is_not_execution_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            tool=root/"codec.exe";tool.write_bytes(b"synthetic-test-only")
            codec=ApprovedCodecBinary(tool,sha256=hashlib.sha256(tool.read_bytes()).hexdigest(),
                                      product="OpenJPEG-opj_decompress")
            with self.assertRaises(PermissionError):
                codec.stage("a"*64)
            with self.assertRaises(PermissionError):
                codec.run(["-i","file.j2k","-o","out.ppm"],cwd=root)

    def test_finite_cli_rejects_paths_switches_and_reparse_aliases(self):
        self.assertEqual(_approved_arguments("OpenJPEG-opj_decompress",
            ["-i","p_000000.j2c","-o","xyz_000000.ppm"])[0],"-i")
        for args in (["-i","../file.j2k","-o","out.ppm"],
                     ["-i","CON.j2k","-o","out.ppm"],
                     ["-i","file.j2k","-o","out.ppm","-h"],
                     ["-i","a.j2k","-o","a.ppm:alt"]):
            with self.subTest(args=args),self.assertRaises(PermissionError):
                _approved_arguments("OpenJPEG-opj_decompress",args)

    def test_hash_length_alone_is_not_sha(self):
        with self.assertRaises(PermissionError):
            _sha("g"*64)

if __name__=="__main__":
    unittest.main()
