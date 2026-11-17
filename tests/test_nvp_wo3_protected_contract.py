"""Scoped WO3 admission denials; no synthetic native success claims."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import wave
from backend.nvp_wo3_native_codecs import (
    ApprovedCodecBinary,_approved_arguments,_sha,ProtectedCodecAuthority)
from backend.nvp_wo3_mxf_native import _frame_receipts
from backend.nvp_wo3_independent_essence import (
    _approved_digest_ledger, _hash_bytes, _single_reel_tracks, _read_pcm24)

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

    def test_native_roundtrip_digest_validation_is_not_byte_hashing(self):
        original = ["a"*64, "b"*64]
        expected, sound = _approved_digest_ledger(original, "c"*64, 2)
        original[0] = "d"*64
        self.assertEqual(expected, ("a"*64, "b"*64))
        self.assertEqual(sound, "c"*64)
        self.assertEqual(_hash_bytes(b"PCM"), hashlib.sha256(b"PCM").hexdigest())
        for picture, pcm, frames in (
            (["a"*64], "g"*64, 1),
            (["A"*64], "c"*64, 1),
            ([b"a"*64], "c"*64, 1),
            (["a"*64], b"c"*64, 1),
            (["a"*64], "c"*64, 2),
        ):
            with self.subTest(picture=picture, pcm=pcm), self.assertRaises(PermissionError):
                _approved_digest_ledger(picture, pcm, frames)

    def test_native_roundtrip_rejects_aliased_picture_and_sound(self):
        pic = {"kind": "picture", "asset_id": "p", "filename": "picture.mxf"}
        snd = {"kind": "sound", "asset_id": "s", "filename": "sound.mxf"}
        self.assertEqual(set(_single_reel_tracks([pic, snd])), {"picture", "sound"})
        for bad in ([pic, dict(snd, asset_id="p")],
                    [pic, dict(snd, filename="PICTURE.MXF")],
                    [pic, snd, snd], [pic, pic]):
            with self.subTest(tracks=bad), self.assertRaises(RuntimeError):
                _single_reel_tracks(bad)

    def test_native_roundtrip_rejects_short_actual_pcm_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio"
            samples = bytes(range(6))*2000
            with wave.open(str(audio), "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(3)
                w.setframerate(48000)
                w.writeframes(samples)
            self.assertEqual(_read_pcm24(audio, 1), samples)
            audio.write_bytes(audio.read_bytes()[:-1])
            with self.assertRaisesRegex(RuntimeError, "truncated"):
                _read_pcm24(audio, 1)


if __name__=="__main__":
    unittest.main()
