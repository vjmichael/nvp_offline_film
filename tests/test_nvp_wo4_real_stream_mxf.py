"""WO4 real native disk audio→CineCert SMPTE sound MXF→unwrapped PCM.

Only runs when reviewed native binaries are installed. Distinct from the
existing short-reel in-memory picture/sound acceptance. The MXF itself is
never materialized as a Python bytes object in this path.
"""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
import wave

from backend.nvp_wo3_native_codecs import ApprovedCodecBinary
from backend.nvp_wo4_pcm_stream import stream_master_pcm24_candidate
from backend.nvp_wo4_mxf_stream import wrap_streamed_pcm_mxf


@unittest.skipUnless(
    all(os.environ.get(name) for name in (
        "NVP_NATIVE_ASDCP_WRAP","NVP_NATIVE_ASDCP_INFO",
        "NVP_NATIVE_ASDCP_UNWRAP")),
    "Actual native CineCert executables required")
class RealStreamedCinemaSound(unittest.TestCase):
    def binary(self,var,product):
        path=Path(os.environ[var]).resolve(strict=True)
        return ApprovedCodecBinary(
            path,sha256=sha256(path.read_bytes()).hexdigest(),product=product)

    def test_disk_streamed_pcm24_mxf_and_full_unwrap(self):
        with TemporaryDirectory(prefix="nvp-wo4-native-stream-") as temp:
            root=Path(temp).resolve()
            output=root/"export"
            output.mkdir()
            raw=root/"approved_source.pcm"
            # Three 24Hz frames x 2000 samples x stereo x signed PCM24.
            samples=(b"\x00\x00\x00\x15\x00\x00\x00\x00\x00"
                     b"\xf0\xff\xff")
            payload=samples*3000
            raw.write_bytes(payload)
            original=sha256(payload).hexdigest()
            wave_candidate=stream_master_pcm24_candidate(
                raw,source_sha256=original,
                original_take_sha256="a"*64,cinema_frames=3,
                channel_layout="stereo",output_root=output,
                approve=lambda scope:scope["source_sha256"]==original)
            wrapper=self.binary("NVP_NATIVE_ASDCP_WRAP","ASDCP-asdcp_wrap")
            info=self.binary("NVP_NATIVE_ASDCP_INFO","ASDCP-asdcp_info")
            unwrap=self.binary("NVP_NATIVE_ASDCP_UNWRAP","ASDCP-asdcp_unwrap")
            result=wrap_streamed_pcm_mxf(
                wrapper,info,wave_candidate,output_root=output)
            self.assertEqual(result["status"],
                             "STREAMED_NATIVE_SOUND_MXF_PUBLISHED")
            self.assertFalse(result["production_dcp_accepted"])
            self.assertFalse(result["whole_mxf_loaded_into_ram"])
            self.assertEqual(result["master_pcm_sha256"],original)
            self.assertEqual(raw.read_bytes(),payload)
            with TemporaryDirectory(prefix="nvp-wo4-unwrap-") as tmp:
                stage=Path(tmp)
                (stage/"sound.mxf").hardlink_to(Path(result["destination"]))
                unwrap.run(["-d","3","sound.mxf","audio"],cwd=stage)
                with wave.open(str(stage/"audio"),"rb") as reader:
                    self.assertEqual(reader.getframerate(),48000)
                    self.assertEqual(reader.getsampwidth(),3)
                    self.assertEqual(reader.getnchannels(),2)
                    self.assertEqual(reader.getnframes(),6000)
                    decoded=reader.readframes(reader.getnframes())
                self.assertEqual(sha256(decoded).hexdigest(),original)
            print("WO4_REAL_DISK_PCM_TO_NATIVE_MXF:",{
                "source_sha256":original,
                "sound_mxf_sha256":result["mxf_file_sha256"],
                "bytes":result["mxf_file_bytes"],
                "full_unwrap_pcm24_identical":True,
                "whole_sound_mxf_ram_loaded":False,
                "production_dcp_accepted":False},flush=True)


if __name__=="__main__":
    unittest.main()
