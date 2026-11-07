"""Release codec staging guard tests; never trust self-pinned runtime folder."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from tools.nvp_wo5_release_codecs import (
    EXES,stage_bundle,verify_bundle,write_compiled_pin)

class NativeCodecReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.source=self.root/"source"
        self.source.mkdir()
        self.files={}
        for role,name in EXES.items():
            file=self.source/name
            file.write_bytes((name+"-reviewed").encode()*30)
            self.files[role]=file
        self.openjpeg=self.source/"COPYING_OPENJPEG"
        self.openjpeg.write_bytes(b"BSD-2-Clause upstream notice: fixture only\n"*12)
        self.asdcp=self.source/"COPYING_ASDCP"
        self.asdcp.write_bytes(b"BSD-3-Clause upstream notice: fixture only\n"*12)
        self.bundle=self.root/"sealed"

    def stage(self):
        return stage_bundle(self.bundle,self.files,
                            self.openjpeg,self.asdcp)

    def test_verified_legal_notice_and_embedded_manifest_pin(self):
        out=self.stage()
        self.assertEqual(out["tool_count"],5)
        self.assertEqual(len(out["manifest_sha256"]),64)
        pin=self.root/"build_pin.py"
        source=write_compiled_pin(pin,out["manifest_sha256"])
        self.assertIn(out["manifest_sha256"],source)
        verified=verify_bundle(self.bundle,out["manifest_sha256"])
        self.assertEqual(verified["status"],
            "RELEASE_CODEC_BUNDLE_PIN_AND_LICENSE_VERIFIED")
        self.assertFalse(verified["installed_windows_webview2_playback_verified"])

    def test_tampered_notice_binary_or_self_replaced_manifest_fails(self):
        out=self.stage()
        self.assertRaises(PermissionError,verify_bundle,self.bundle,"a"*64)
        notice=self.bundle/"asdcplib.BSD-3-Clause.LICENSE"
        notice.write_bytes(b"attacker changed license notice")
        self.assertRaises(PermissionError,verify_bundle,
                          self.bundle,out["manifest_sha256"])

    def test_reject_unapproved_binary_name_link_and_partial_toolset(self):
        self.files["asdcp-info"]=self.files["asdcp-wrap"]
        with self.assertRaises(PermissionError):self.stage()
        self.files.pop("asdcp-info")
        with self.assertRaises(PermissionError):self.stage()
        self.files["asdcp-info"]=self.source/"asdcp-info.exe"
        self.files["asdcp-info"].unlink()
        self.files["asdcp-info"].mkdir()
        with self.assertRaises(PermissionError):self.stage()

    def test_no_runtime_self_pinning(self):
        self.assertRaises(PermissionError,write_compiled_pin,
                          self.root/"new.py","")
        self.assertRaises(PermissionError,write_compiled_pin,
                          self.root/"new.py","not-a-sha")
        out=self.stage()
        # Rehashing a user-controlled manifest into a new manifest pin must
        # NEVER occur when opening the finished-film viewer.
        self.assertRaises(PermissionError,verify_bundle,
                          self.bundle,sha256(b"untrusted").hexdigest())
if __name__=="__main__":unittest.main()
