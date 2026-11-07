"""WO5 source-pinned decoder admission: no JS-selected native binaries."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import unittest

from backend.nvp_wo5_codec_binding import (
    desktop_finished_decoder_provider,pinned_codec_pair)
from backend.nvp_wo3_codec_bundle_provenance import FORMAT,REQUIRED

class ReviewCodecAdmissionTests(unittest.TestCase):
    def test_no_binary_from_browser_or_ambient_developer_mode(self):
        with patch.dict(os.environ,{
                "NVP_NATIVE_ASDCP_UNWRAP":"/tmp/untrusted-client",
                "NVP_WO5_DEV_FINISHED_DECODER":""},clear=False):
            self.assertIsNone(desktop_finished_decoder_provider(Path.cwd()))

    def test_developer_mode_requires_exact_pinned_executable_hashes(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            unwrap=root/"asdcp-unwrap"
            decoder=root/"opj_decompress"
            unwrap.write_bytes(b"Reviewed dev asdcplib bytes")
            decoder.write_bytes(b"Reviewed dev OpenJPEG bytes")
            spec={
                "NVP_WO5_DEV_FINISHED_DECODER":"explicit-local-only",
                "NVP_NATIVE_ASDCP_UNWRAP":str(unwrap),
                "NVP_NATIVE_ASDCP_UNWRAP_SHA256":sha256(unwrap.read_bytes()).hexdigest(),
                "NVP_NATIVE_OPENJPEG_DECODE":str(decoder),
                "NVP_NATIVE_OPENJPEG_DECODE_SHA256":sha256(decoder.read_bytes()).hexdigest(),
            }
            with patch.dict(os.environ,spec):
                provider=desktop_finished_decoder_provider(root)
                self.assertTrue(callable(provider))
                codecs=provider()
                self.assertEqual([c.product for c in codecs],
                   ["ASDCP-asdcp_unwrap","OpenJPEG-opj_decompress"])
                decoder.write_bytes(b"Replaced executable")
                with self.assertRaises(PermissionError):
                    provider()
            spec["NVP_NATIVE_OPENJPEG_DECODE_SHA256"]="f"*64
            with patch.dict(os.environ,spec):
                with self.assertRaises(PermissionError):
                    desktop_finished_decoder_provider(root)()

    def test_release_bundle_requires_manifest_hash_and_legal_notice(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            manifest={"format":FORMAT,"tools":{}}
            for label,(product,license_name) in REQUIRED.items():
                binary=root/(label.replace("-","_")+".bin")
                notice=root/(label.replace("-","_")+".LICENSE")
                binary.write_bytes(b"x"*300)
                notice.write_bytes(b"license"*40)
                manifest["tools"][label]={
                    "product":product,"license":license_name,
                    "filename":binary.name,"sha256":sha256(binary.read_bytes()).hexdigest(),
                    "license_notice":notice.name,
                    "license_sha256":sha256(notice.read_bytes()).hexdigest(),
                }
            digest=sha256(json.dumps(manifest,sort_keys=True,
                separators=(",",":"),ensure_ascii=True).encode("ascii")).hexdigest()
            (root/"nvp-codec-manifest.json").write_text(json.dumps(manifest,sort_keys=True,separators=(",",":"),ensure_ascii=True),encoding="ascii")
            with self.assertRaises(PermissionError):
                pinned_codec_pair(root,manifest,"f"*64)
            unwrap,decoder=pinned_codec_pair(root,manifest,digest)
            self.assertEqual(unwrap.product,"ASDCP-asdcp_unwrap")
            self.assertEqual(decoder.product,"OpenJPEG-opj_decompress")
            (root/manifest["tools"]["asdcp-unwrap"]["license_notice"]).write_bytes(
                b"changed")
            with self.assertRaises(PermissionError):
                pinned_codec_pair(root,manifest,digest)

if __name__=="__main__":
    unittest.main()
