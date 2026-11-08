"""FILM02-03B native AVI decoder unit tests with clearly FAKE throwaway fixtures.

These fixtures test the index, JPEG decoder, PCM clock and tamper refusal.
They are NOT the 720 genuine Cycles film. The production entrypoint still
requires three real source shots and six independent Blender readbacks.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
import wave

from PIL import Image

from backend.nvp_film01_native_avi import _chunk, _header, _encode_jpeg_verified
from tools.nvp_film02_avi_independent_readback import (
    scan_actual_movie, audit_original_film,
)


def create_disposable_mock_film(root):
    """Only a synthetically colored three-frame *test*, never actual art."""
    video=Path(root)/"fixture_only_not_original_film.avi"
    sound=Path(root)/"fixture_only_not_original_film.wav"
    sounds = []
    jpeg = []
    for n in range(3):
        frame=Image.new("RGB",(640,360),
                        (40+40*n,55+20*n,65+30*n))
        out=BytesIO()
        frame.save(out, format="PNG")
        jpeg.append(_encode_jpeg_verified(out.getvalue()))
        sounds.append(struct.pack("<"+"h"*2000,
                                  *(500+n*50+i%20 for i in range(2000))))
    with wave.open(str(sound),"wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"".join(sounds))
    entries=[]
    with video.open("wb") as stream:
        stream.write(b"RIFF"+b"\0"*4+b"AVI ")
        stream.write(_header(3))
        movi=stream.tell()
        stream.write(b"LIST"+b"\0"*4+b"movi")
        for n in range(3):
            for tag,payload in ((b"00dc",jpeg[n]),(b"01wb",sounds[n])):
                offset=stream.tell()-(movi+8)
                stream.write(_chunk(tag,payload))
                entries.append((tag,0x10,offset,len(payload)))
        end=stream.tell()
        stream.seek(movi+4)
        stream.write(struct.pack("<I",end-movi-8))
        stream.seek(end)
        stream.write(_chunk(b"idx1",b"".join(
            struct.pack("<4sIII",*row) for row in entries)))
        end=stream.tell()
        stream.seek(4)
        stream.write(struct.pack("<I",end-8))
    return video,sound


class IndependentOriginalFilmDecoderContracts(unittest.TestCase):
    def test_disposable_mock_RIFF_MJPEG_PCM_is_independently_decoded(self):
        with TemporaryDirectory() as d:
            video,sound=create_disposable_mock_film(d)
            result=scan_actual_movie(
                video,sound,expected_frames=3,
                director_frames=[0,1,2])
            self.assertEqual(result["frame_count"],3)
            self.assertEqual(len(result["decoded_contact_frames"]),3)
            self.assertEqual(len(result["frames"]),3)
            self.assertEqual(result["wav_sha256"],sha256(sound.read_bytes()).hexdigest())
            self.assertEqual(result["movie_sha256"],sha256(video.read_bytes()).hexdigest())
            for n,frame in enumerate(result["frames"]):
                self.assertEqual(frame["frame_zero"],n)
                self.assertTrue(frame["actual_MJPEG_sha256"])
                self.assertTrue(frame["original_PCM16_sha256"])
                self.assertIsNotNone(frame["audio_rms_dbfs"])
            self.assertNotEqual(
                result["frames"][0]["mean_luma_8bit"],
                result["frames"][1]["mean_luma_8bit"])

    def test_corrupt_index_cannot_pass_even_when_container_RIFF_size_is_valid(self):
        with TemporaryDirectory() as d:
            video,sound=create_disposable_mock_film(d)
            altered=bytearray(video.read_bytes())
            pos=altered.rfind(b"idx1")
            self.assertGreater(pos,0)
            # First entry offset is at +8(index header)+8(tag, flags).
            struct.pack_into("<I",altered,pos+16,2048)
            video.write_bytes(altered)
            with self.assertRaises(RuntimeError):
                scan_actual_movie(video,sound,expected_frames=3, director_frames=[])

    def test_truncated_and_wrong_audio_fail_closed(self):
        with TemporaryDirectory() as d:
            video,sound=create_disposable_mock_film(d)
            with wave.open(str(sound),"rb") as original:
                b=original.readframes(6000)
            with wave.open(str(sound),"wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(48000)
                out.writeframes(b[:-2])
            with self.assertRaises(RuntimeError):
                scan_actual_movie(video,sound,expected_frames=3, director_frames=[])
        with TemporaryDirectory() as d:
            video,sound=create_disposable_mock_film(d)
            with wave.open(str(sound),"rb") as original:
                b=bytearray(original.readframes(6000))
            b[10] ^= 1
            with wave.open(str(sound),"wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(48000)
                out.writeframes(b)
            with self.assertRaises(PermissionError):
                scan_actual_movie(video,sound,expected_frames=3, director_frames=[])

    def test_synthetic_fixture_cannot_be_falsely_published_as_original_Cycles_film(self):
        with TemporaryDirectory() as d:
            video,sound=create_disposable_mock_film(d)
            with self.assertRaises((FileNotFoundError,PermissionError,RuntimeError)):
                audit_original_film(Path(d)/"missing-real-Cycles-shots",
                                    Path(d)/"missing-original-project",
                                    Path(d)/"missing-frozen-handoff",
                                    Path(d)/"missing-original-review",
                                    Path(d)/"not-an-approved-original-film")


if __name__=="__main__":
    unittest.main()
