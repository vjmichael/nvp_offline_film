"""WO3-02 optional genuine installed OpenJPEG executable acceptance.

Runs only in a native job that deliberately provides the OpenJPEG executable.
Creates actual XYZ12 component data at DCI 2K Flat dimensions, encodes one
real frame, and independently parses the returned JPEG2000 Part 1 codestream.
Not a DCI projection/display/color-management acceptance.
"""
import hashlib
import os
from pathlib import Path
import unittest

from backend.nvp_wo3_native_codecs import (
    ApprovedCodecBinary,encode_xyz12_frame)
from backend.nvp_wo3_j2k_audit import inspect_j2k_header


class WO3RealOpenJPEG2K(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("NVP_NATIVE_OPENJPEG"),
                         "No installed native OpenJPEG cinema encoder")
    def test_real_cinema_2k_xyz12_j2k_encodes_and_header_is_decodable(self):
        executable=Path(os.environ["NVP_NATIVE_OPENJPEG"]).resolve(strict=True)
        expected=hashlib.sha256(executable.read_bytes()).hexdigest()
        native=ApprovedCodecBinary(
            executable,sha256=expected,product="OpenJPEG-opj_compress")
        # DCI XYZ 12-bit input, big-endian PPM component values, no
        # implicit gamma, color transform or fabricated film sources.
        raw=b"\x08\x00\x08\x00\x08\x00"*(1998*1080)
        result=encode_xyz12_frame(
            native,raw,profile="2K_FLAT_24",
            source_presentation_sha256="a"*64,creator_approved=True)
        self.assertTrue(result["independent_header_constraints_verified"])
        self.assertEqual(result["profile"],"2K_FLAT_24")
        self.assertEqual(result["codec_result"]["exit_code"],0)
        assert_result=inspect_j2k_header(result["codestream"],"2K_FLAT_24")
        self.assertEqual(assert_result["width"],1998)
        self.assertEqual(assert_result["height"],1080)
        self.assertEqual(len(assert_result["components"]),3)
        self.assertFalse(result["independent_decoded_pixels_verified"])
        self.assertFalse(result["dci_certified"])
        self.assertFalse(result["original_source_modified"])
        print("WO3_REAL_NATIVE_OPENJPEG:",{
            "sha256":result["codestream_sha256"],
            "bytes":len(result["codestream"]),
            "profile":"2K_FLAT_24",
            "native_binary_sha256":native.sha256,
            "independent_full_decode":False,
            "dci_certified":False,
        },flush=True)


    @unittest.skipUnless(os.environ.get("NVP_NATIVE_OPENJPEG_4K"),
                         "Native 4K cinema encoding not requested")
    def test_real_4096x2160_xyz12_cinema4k_codestream(self):
        executable=Path(os.environ["NVP_NATIVE_OPENJPEG"]).resolve(strict=True)
        native=ApprovedCodecBinary(
            executable,sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
            product="OpenJPEG-opj_compress")
        raw=b"\x08\x00\x08\x00\x08\x00"*(4096*2160)
        result=encode_xyz12_frame(
            native,raw,profile="4K_FULL_24",
            source_presentation_sha256="b"*64,creator_approved=True)
        self.assertEqual(inspect_j2k_header(result["codestream"],
                                             "4K_FULL_24")["rsiz"],4)
        self.assertFalse(result["dci_certified"])
        print("WO3_REAL_NATIVE_OPENJPEG_4K:",{
            "bytes":len(result["codestream"]),
            "sha256":result["codestream_sha256"],
            "verified_full_decoder":False,
        },flush=True)


if __name__=="__main__":
    unittest.main()
