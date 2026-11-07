"""Batch 3 native cinema toolchain security and no-false-master tests."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import os
import stat
import tempfile
import unittest

from backend.nvp_native_dcp_toolchain import (
    BINARY_NAMES,LICENSE,MANIFEST,admit_toolchain,
    require_native_dcdm_source)

SHA0="0"*64


class NativeCinemaToolchainAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="nvp-no-codec-proxy-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.expected={"format":MANIFEST,
                       "bundle_id":"NvpNativeCinemaV1",
                       "platform":"windows" if os.name=="nt" else "linux",
                       "dependency_audit_sha256":"1"*64,
                       "license_review_sha256":"2"*64,
                       "tools":{}}
        for role,name in BINARY_NAMES.items():
            file_name=name+(".exe" if os.name=="nt" else "")
            payload=("trusted-native-cinema-fixture-"+name).encode()
            path=self.root/file_name
            path.write_bytes(payload)
            if os.name!="nt":
                path.chmod(path.stat().st_mode|stat.S_IXUSR)
            self.expected["tools"][role]={
                "file_name":file_name,
                "sha256":sha256(payload).hexdigest(),
                "size_bytes":len(payload),
                "license":LICENSE[role] or "BSD-3-Clause",
            }

    def test_only_exact_trusted_host_bundle_granted_without_claiming_dcp(self):
        status=admit_toolchain(self.root,self.expected)
        self.assertEqual(status["status"],
                         "VERIFIED_NATIVE_TOOLCHAIN_NOT_A_DCP")
        self.assertEqual(set(status["roles"]),set(BINARY_NAMES))
        self.assertTrue(status[
            "supports_pinned_cinema_jpeg2000_and_mxf_workers"])
        self.assertFalse(status["runtime_executables_invoked"])
        self.assertFalse(status["calibrated_DCDM_XYZ12_available"])
        self.assertFalse(status["independent_smpte_qc_passed"])
        self.assertFalse(status["dcp_delivered"])
        self.assertFalse(status["ffmpeg_used"])

    def test_missing_tampered_or_symlinked_executable_cannot_be_admitted(self):
        path=self.root/next(iter(self.expected["tools"].values()))[
            "file_name"]
        path.write_bytes(b"BAD")
        with self.assertRaises(PermissionError):
            admit_toolchain(self.root,self.expected)
        path.write_bytes(("trusted-native-cinema-fixture-"+
                          next(iter(BINARY_NAMES.values()))).encode())
        link=self.root/"out_of_bundle"
        link.write_bytes(b"bad")
        if os.name!="nt":
            path.unlink()
            path.symlink_to(link)
            with self.assertRaises(PermissionError):
                admit_toolchain(self.root,self.expected)
        # Untrusted relative bundle roots are never silently resolved.
        with self.assertRaises(PermissionError):
            admit_toolchain(Path("."),self.expected)

    def test_unpinned_manifest_and_unreviewed_deps_are_rejected(self):
        changed={**self.expected,
                 "license_review_sha256":"NOT_VALID"}
        with self.assertRaises(ValueError):
            admit_toolchain(self.root,changed)
        invalid={**self.expected,"tools":{
            **self.expected["tools"],
            "asdcplib_wrap":{
                **self.expected["tools"]["asdcplib_wrap"],
                "license":"ProprietaryUnknown",
            }}}
        with self.assertRaises(PermissionError):
            admit_toolchain(self.root,invalid)

    def test_current_unmastered_png_exr_or_pcm16_are_not_xyz12_dcdm(self):
        doc={
            "format":"nvp.data_first.calibrated_xyz12_dcdm.v1",
            "original_take_sha256":"a"*64,
            "native_publisher_sha256":"b"*64,
            "color_transform_sha256":"c"*64,
            "measured_color_calibration_sha256":"d"*64,
            "picture_raster":[1998,1080],
            "frame_rate":[24,1],
            "picture_components":"XYZ","picture_bit_depth":12,
            "sound_channels":2,"sound_sample_rate":48000,
            "sound_sample_bit_depth":24,
            "native_dcdm_authorized":True,
            "independently_qc_verified":True,
            "source_modified":False,
        }
        proof=require_native_dcdm_source(doc,"a"*64)
        self.assertEqual(proof["status"],"VERIFIED_DCDM_SOURCE_NOT_DCP")
        self.assertFalse(proof["dcp_delivered"])
        for key,value in (
            ("picture_raster",[640,360]),
            ("picture_components","RGB"),
            ("picture_bit_depth",16),
            ("sound_sample_bit_depth",16),
            ("independently_qc_verified",False),
            ("source_modified",True),
        ):
            with self.subTest(key=key):
                with self.assertRaises(RuntimeError):
                    require_native_dcdm_source({**doc,key:value},"a"*64)
        with self.assertRaises(RuntimeError):
            require_native_dcdm_source(doc,"f"*64)


if __name__=="__main__":
    unittest.main()
