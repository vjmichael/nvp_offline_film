"""WO5 negative admission contracts. Actual decoder pair exercised in native pilot."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from backend.nvp_wo5_codec_binding import pinned_codec_pair,desktop_finished_decoder_provider


class ReviewCodecAdmissionTests(unittest.TestCase):
    def test_no_decoder_from_ambient_environment(self):
        with patch.dict(os.environ,{"NVP_WO5_DEV_FINISHED_DECODER":"explicit-local-only",
                                    "NVP_NATIVE_ASDCP_UNWRAP":"untrusted.exe"}):
            self.assertIsNone(desktop_finished_decoder_provider(Path.cwd()))

    def test_valid_manifest_does_not_grant_native_authority(self):
        with TemporaryDirectory() as tmp:
            for pin in ("a"*64,"incorrect"):
                with self.assertRaises(PermissionError):
                    pinned_codec_pair(Path(tmp).resolve(),{},pin,authority=None,
                                      project_id="p",check_cancel=lambda:False)

    def test_release_unpinned_or_no_factory_disabled(self):
        with patch("backend.nvp_wo5_codec_binding.sys.frozen",True,create=True):
            with patch("backend.nvp_wo5_codec_binding.RELEASE_CODEC_MANIFEST_SHA256",""):
                self.assertIsNone(desktop_finished_decoder_provider(Path.cwd(),
                    authority_factory=lambda *_:self.fail("Unpinned release invoked factory")))
            with patch("backend.nvp_wo5_codec_binding.RELEASE_CODEC_MANIFEST_SHA256","a"*64):
                self.assertIsNone(desktop_finished_decoder_provider(Path.cwd()))


if __name__=="__main__":
    unittest.main()
