"""WO4 stream-MXF custody tests use deliberately MOCKED codec boundaries.

These are negative filesystem/source-immutability tests; they do not claim
real MXF, asdcplib or DCI acceptance. Actual native unwrap has a separate CI.
"""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_wo3_native_codecs import ApprovedCodecBinary
from backend.nvp_wo4_pcm_stream import stream_master_pcm24_candidate
from backend.nvp_wo4_mxf_stream import wrap_streamed_pcm_mxf


def fake_codec(product):
    codec=ApprovedCodecBinary.__new__(ApprovedCodecBinary)
    codec.product=product
    codec.sha256="a"*64
    return codec


class NativeWorkerSourceIsolation(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name).resolve()
        self.out=root/"export"
        self.out.mkdir()
        self.source=root/"original.pcm"
        original=(b"\x01\x00\x00\x02\x00\x00")*6000
        self.source.write_bytes(original)
        self.stream=stream_master_pcm24_candidate(
            self.source,source_sha256=sha256(original).hexdigest(),
            original_take_sha256="a"*64,cinema_frames=3,
            channel_layout="stereo",output_root=self.out,
            approve=lambda _:True)
        self.wav=Path(self.stream["destination"])
        self.approved=self.wav.read_bytes()
        self.wrapper=fake_codec("ASDCP-asdcp_wrap")
        self.info=fake_codec("ASDCP-asdcp_info")

    def test_malicious_codec_changes_only_private_copy_then_fails_closed(self):
        # A reviewed executable can still have bugs; ensure a write by the
        # child to its input cannot touch the approved original WAV inode.
        def adversarial_run(args,*,cwd,timeout):
            directory=Path(cwd)
            (directory/"master.wav").write_bytes(b"MUTATED_BY_CODEC")
            (directory/"sound.mxf").write_bytes(b"M"*200)
            return {"exit_code":0}
        self.wrapper.run=adversarial_run
        with patch("backend.nvp_wo4_mxf_stream._read_info",
                   return_value=({},{})), patch(
                   "backend.nvp_wo4_mxf_stream._verify_info",
                   return_value=None):
            with self.assertRaises(PermissionError):
                wrap_streamed_pcm_mxf(
                    self.wrapper,self.info,self.stream,output_root=self.out)
        self.assertEqual(self.wav.read_bytes(),self.approved)
        self.assertEqual(sha256(self.wav.read_bytes()).hexdigest(),
                         self.stream["wav_file_sha256"])
        self.assertFalse(any(x.name.startswith("SoundMXF_")
                             for x in self.out.iterdir()))
        self.assertFalse(any(x.name.startswith(".nvp-wo4-mxf-")
                             for x in self.out.iterdir()))

    def test_forged_or_modified_stream_wav_refused_before_native_worker(self):
        self.wrapper.run=lambda *a,**kw: self.fail(
            "Native worker must never run for corrupted WAV")
        self.wav.write_bytes(self.approved[:-3]+b"\x00\x00\x00")
        with self.assertRaises(PermissionError):
            wrap_streamed_pcm_mxf(
                self.wrapper,self.info,self.stream,output_root=self.out)


if __name__=="__main__":
    unittest.main()
