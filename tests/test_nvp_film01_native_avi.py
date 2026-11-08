"""Independent AVI RIFF/index/JPEG/PCM verification on ACTUAL OpenUSD pixels.

The source frames come from NVP's real authored three-Take 30s film.
Only first six frames are rendered here for bounded CI. The separate
FILM01 full-render job must render and validate all 720 frames.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import unittest
import wave
from zipfile import ZipFile

from PIL import Image

from backend.nvp_film01_native_avi import mux_original_native_avi,FORMAT
from tools.nvp_film01_original_30s import (
    write_original_30s_source,render_original_30s_review)


def _chunks(blob,start,end):
    pos=start
    while pos<end:
        if pos+8>end:
            raise AssertionError("AVI has trailing unparsed bytes")
        kind,length=struct.unpack_from("<4sI",blob,pos)
        body=pos+8
        after=body+length
        if after>end:
            raise AssertionError("AVI chunk overruns container")
        yield (kind,pos,body,after)
        pos=after+(length%2)
    if pos!=end:
        raise AssertionError("AVI padding did not end at container boundary")


def inspect_avi_independently(path,source_zip,expected_count):
    """Read the produced RIFF media in strict original frame/time order.

    This is a structurally independent reader, not the same mux writer.
    A real Windows/VLC device decode is still a separate acceptance gate.
    """
    blob=Path(path).read_bytes()
    assert blob[:4]==b"RIFF" and blob[8:12]==b"AVI "
    assert struct.unpack_from("<I",blob,4)[0]==len(blob)-8
    top=list(_chunks(blob,12,len(blob)))
    hdrl=next(x for x in top
              if x[0]==b"LIST" and blob[x[2]:x[2]+4]==b"hdrl")
    movi=next(x for x in top
              if x[0]==b"LIST" and blob[x[2]:x[2]+4]==b"movi")
    idx=next(x for x in top if x[0]==b"idx1")
    avih=next(x for x in _chunks(blob,hdrl[2]+4,hdrl[3])
              if x[0]==b"avih")
    details=struct.unpack("<IIIIIIIIII4I",blob[avih[2]:avih[3]])
    assert details[0]==round(1_000_000/24)
    assert details[4]==expected_count
    assert details[6]==2 and details[8:10]==(640,360)
    assert details[3]&0x10 and details[3]&0x100
    members=list(_chunks(blob,movi[2]+4,movi[3]))
    assert len(members)==2*expected_count
    offsets=[]
    picture_types=[]
    decoded_audio=bytearray()
    for frame in range(expected_count):
        video=members[frame*2]
        audio=members[frame*2+1]
        assert video[0]==b"00dc" and audio[0]==b"01wb"
        jpg=blob[video[2]:video[3]]
        assert jpg.startswith(b"\xff\xd8") and jpg.endswith(b"\xff\xd9")
        with Image.open(BytesIO(jpg)) as image:
            image.load()
            assert image.format=="JPEG" and image.size==(640,360)
            picture_types.append(image.format)
        pcm=blob[audio[2]:audio[3]]
        assert len(pcm)==4000
        decoded_audio.extend(pcm)
        offsets.extend(((b"00dc",video),(b"01wb",audio)))
    index=blob[idx[2]:idx[3]]
    assert len(index)==16*len(offsets)
    for n,(tag,member) in enumerate(offsets):
        itag,flags,offset,size=struct.unpack_from("<4sIII",index,n*16)
        assert itag==tag
        assert flags&0x10
        assert offset==member[1]-(movi[1]+8)
        assert size==member[3]-member[2]
    with ZipFile(source_zip) as original:
        with wave.open(BytesIO(original.read(
                "audio/original_source_review_48k_mono.wav")),"rb") as pcm:
            assert pcm.getframerate()==48000
            assert pcm.getnchannels()==1
            assert pcm.getsampwidth()==2
            assert pcm.getnframes()==2000*expected_count
            assert pcm.readframes(2000*expected_count)==bytes(decoded_audio)
    return {"frames_decoded":len(picture_types),
            "original_pcm_samples":len(decoded_audio)//2,
            "video_codec":"MJPEG","audio_codec":"PCM16LE",
            "container":"RIFF AVI","exact_sound_matches_source":True}


class NativeOriginalPlayableMovie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory()
        cls.root=Path(cls.temp.name).resolve()
        cls.source=cls.root/"short_source"
        write_original_30s_source(cls.source,approve_test_only=True)
        cls.zip=cls.root/"real_six_frames_and_wav.zip"
        render_original_30s_review(cls.source,cls.zip,max_frames=6)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_nvp_png_and_wav_become_playable_indexed_mjpeg_pcm_avi(self):
        path=self.root/"real-six-frame-audition.avi"
        report=mux_original_native_avi(
            self.zip,path,expected_frames=6)
        self.assertEqual(report["format"],FORMAT)
        self.assertEqual(report["frames"],6)
        self.assertTrue(report["playable_avi_container_written"])
        self.assertFalse(report["external_player_verified"])
        self.assertFalse(report["dci_cinema_mastered"])
        self.assertFalse(report["creative_quality_approved"])
        independent=inspect_avi_independently(path,self.zip,6)
        self.assertEqual(independent["frames_decoded"],6)
        self.assertEqual(independent["original_pcm_samples"],12000)
        self.assertTrue(independent["exact_sound_matches_source"])
        with self.assertRaises(PermissionError):
            mux_original_native_avi(self.zip,path,expected_frames=6)

    def test_rejects_fake_duration_and_missing_original_verified_manifest(self):
        with self.assertRaises(PermissionError):
            mux_original_native_avi(
                self.zip,self.root/"fake-full.avi",expected_frames=720)
        self.assertFalse((self.root/"fake-full.avi").exists())


if __name__=="__main__":
    unittest.main()
