"""DA-05C: FFmpeg-free single-file AVI delivery regression gates.

These are synthetic native original-scene fixtures, not physical Windows
player acceptance or a claim of cinema-quality picture.
"""
import hashlib
from pathlib import Path
import struct
import unittest

from backend.nvp_native_avi_delivery import deliver_avi, FORMAT
from test_nvp_final_2d_native import NativeDataFirstOutputTests


class NativeAVIDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fx=NativeDataFirstOutputTests(
            "test_denied_export_never_creates_derived_or_mutates_take")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.sha=self.fx.create()
        receipt=self.fx.exporter.export(
            self.fx.pid,"OutputTake",self.sha,"AVIInput",self.fx.out,
            listener_path="/World/ListenerLeft")
        self.package=Path(receipt["directory"])
        self.output=self.fx.out/"Movie001.avi"

    def test_single_file_real_riff_avi_has_pcm_and_picture_index(self):
        approvals=[]
        result=deliver_avi(self.package,self.output,
            expected_take_sha256=self.sha,
            approve_delivery=lambda scope:
                approvals.append(scope) is None)
        raw=self.output.read_bytes()
        self.assertEqual(result["status"],"DERIVED_SINGLE_FILE_AVI")
        self.assertEqual(result["format"],FORMAT)
        self.assertTrue(raw.startswith(b"RIFF"))
        self.assertEqual(raw[8:12],b"AVI ")
        self.assertEqual(struct.unpack_from("<I",raw,4)[0]+8,len(raw))
        self.assertIn(b"movi",raw)
        self.assertIn(b"00db",raw)
        self.assertIn(b"01wb",raw)
        self.assertIn(b"idx1",raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         result["output_sha256"])
        self.assertEqual(approvals[0]["original_take_sha256"],self.sha)
        self.assertEqual(self.fx.index.read_revision(
            self.fx.pid,"OutputTake",1)["document_sha256"],self.sha)
        with self.assertRaises(FileExistsError):
            deliver_avi(self.package,self.output,
                expected_take_sha256=self.sha,approve_delivery=lambda s:True)

    def test_denial_and_stale_digest_refuse_publication(self):
        with self.assertRaises(PermissionError):
            deliver_avi(self.package,self.output,
                expected_take_sha256=self.sha,
                approve_delivery=lambda scope:False)
        self.assertFalse(self.output.exists())
        with self.assertRaises(RuntimeError):
            deliver_avi(self.package,self.output,
                expected_take_sha256="f"*64,
                approve_delivery=lambda scope:True)
        self.assertFalse(self.output.exists())

    def test_corrupt_approved_picture_refuses_delivery(self):
        path=self.package/"pictures"/"0000001.png"
        path.write_bytes(b"forged")
        with self.assertRaises(RuntimeError):
            deliver_avi(self.package,self.output,
                expected_take_sha256=self.sha,approve_delivery=lambda s:True)
        self.assertFalse(self.output.exists())


if __name__=="__main__":
    unittest.main()
