"""WO3 genuine nonconstant 2K Scope cinematic codec quality evidence.

Exercises physical OpenJPEG encoder/decoder executables, not a mocked
synthetic JPEG2000 header. This does not certify cinema color mastering,
second-implementation decoder parity, or projector acceptance.
"""
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_wo3_native_codecs import ApprovedCodecBinary, encode_xyz12_frame
from backend.nvp_wo3_independent_essence import _ppm_header
from backend.nvp_wo3_j2k_audit import inspect_j2k_header, PROFILES


@unittest.skipUnless(
    os.environ.get("NVP_NATIVE_OPENJPEG") and
    os.environ.get("NVP_NATIVE_OPENJPEG_DECODE"),
    "Native OpenJPEG encode/decode executables not provided")
class NonconstantCinemaCodecQuality(unittest.TestCase):
    def codec(self, env, product):
        path = Path(os.environ[env]).resolve(strict=True)
        return ApprovedCodecBinary(
            path, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            product=product)

    def test_2k_scope_chromatic_gradient_roundtrip_quality(self):
        profile = "2K_SCOPE_24"
        width, height, _ = PROFILES[profile]
        # 16 distinguishable horizontal patches. Full raster uses genuine
        # 12-bit unsigned XYZ data rather than a constant image.
        scan = bytearray()
        for x in range(width):
            patch = x * 16 // width
            values = (256 + patch*160, 3200-patch*152, 1024+patch*96)
            for v in values:
                scan.extend(v.to_bytes(2, "big"))
        original = bytes(scan) * height
        encoder = self.codec("NVP_NATIVE_OPENJPEG", "OpenJPEG-opj_compress")
        decoder = self.codec("NVP_NATIVE_OPENJPEG_DECODE", "OpenJPEG-opj_decompress")
        result = encode_xyz12_frame(
            encoder, original, profile=profile,
            source_presentation_sha256="c"*64, creator_approved=True)
        self.assertEqual(inspect_j2k_header(result["codestream"], profile)["width"],
                         width)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/"image.j2k").write_bytes(result["codestream"])
            decoder.run(["-i","image.j2k","-o","decoded.ppm"],cwd=root)
            decoded = _ppm_header(root/"decoded.ppm",width=width,height=height)
        self.assertEqual(len(decoded),len(original))
        # Sampling avoids a giant NumPy dependency and reports both
        # numerical deviation and retained gradient contrast.
        errors = []
        sampled_original = []
        sampled_decoded = []
        for patch in range(16):
            x = (patch*width//16) + (width//32)
            offset = (height//2*width + x)*6
            for component in range(3):
                offset2 = offset + component*2
                before = int.from_bytes(original[offset2:offset2+2],"big")
                after = int.from_bytes(decoded[offset2:offset2+2],"big")
                sampled_original.append(before)
                sampled_decoded.append(after)
                errors.append(abs(before-after))
        # Result must retain the source-driven changes, not merely decode
        # as a uniform image or valid header.
        self.assertGreater(len(set(sampled_decoded)), 8)
        self.assertLess(max(errors), 256,
                        "Native codec destroyed too much of the XYZ12 patch contrast")
        self.assertLess(len(result["codestream"]), 16*1024*1024)
        self.assertFalse(result["dci_certified"])
        print("WO3_NONCONSTANT_NATIVE_SCOPE_QUALITY", {
            "source_sha256": hashlib.sha256(original).hexdigest(),
            "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
            "max_component_error_12bit": max(errors),
            "mean_sampled_component_abs_error": sum(errors)/len(errors),
            "codestream_bytes": len(result["codestream"]),
            "profile": profile, "production_dcp_accepted": False},flush=True)


if __name__ == "__main__":
    unittest.main()
