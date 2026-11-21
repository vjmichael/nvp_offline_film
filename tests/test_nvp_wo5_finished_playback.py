"""Original WO5 source contracts, actual Windows EFS read leases and synthetic
PCM region fixtures. Real published-MXF playback is tested separately.
"""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
from io import BytesIO
import os
import unittest
import wave
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_wo4_feature_journal import FeatureJournal,FRAME_TICKS
from backend.nvp_w1g_encrypted_source import require_efs_stage
from backend.nvp_wo5_finished_playback import (
    FORMAT,RATE,SAMPLES_PER_FRAME,Reel,FinishedFilmPlayer,
    _display_png,_stereo_pcm16,locate_reel,_locked_media,
    _pcm_region_window,_region_ledger,_read_verified_pcm24)

class TimelineAndPixelTests(unittest.TestCase):
    def test_global_film_time_crosses_reel_without_gap(self):
        reels=(SimpleNamespace(first=0,frames=3),SimpleNamespace(first=3,frames=6))
        self.assertEqual(locate_reel(reels,0),(0,0))
        self.assertEqual(locate_reel(reels,2),(0,2))
        self.assertEqual(locate_reel(reels,3),(1,0))
        self.assertEqual(locate_reel(reels,8),(1,5))
        for index in (-1,9,True,0.2):
            with self.subTest(index=index),self.assertRaises(ValueError):
                locate_reel(reels,index)

    def test_real_dci_xyz12_frame_becomes_nonempty_bounded_png(self):
        # Authored 2K XYZ12 content, *not* a simulated PNG input to decoder.
        xyz=(0x300).to_bytes(2,"big")*3*(1998*1080)
        png,size=_display_png(xyz,"2K_FLAT_24")
        self.assertEqual(png[:8],b"\x89PNG\r\n\x1a\n")
        self.assertGreater(len(png),100)
        self.assertLess(len(png),3*1024*1024)
        self.assertLessEqual(size[0],1024)
        with self.assertRaises(PermissionError):
            _display_png(xyz[:-2],"2K_FLAT_24")

    def test_unsampled_xyz12_word_cannot_hide_in_preview_decimation(self):
        # The full 2K XYZ image is sampled every second pixel for the
        # GUI. A native decoder must not hide invalid 12-bit essence in
        # those discarded positions.
        width,height=1998,1080
        original=bytearray((0x0300).to_bytes(2,"big")*3*(width*height))
        # x=1, y=1 is NOT included in raw[::2,::2].
        offset=((width+1)*3)*2
        self.assertEqual(int.from_bytes(original[offset:offset+2],"big"),0x300)
        original[offset:offset+2]=(0x1000).to_bytes(2,"big")
        with self.assertRaisesRegex(PermissionError,"XYZ12"):
            _display_png(bytes(original),"2K_FLAT_24")
        # Keep the existing test for an entirely valid full-resolution
        # DCP preview; both sampled and unsampled pixels are now audited.

    def test_mastered_pcm24_downmix_exact_48k_samples(self):
        # 24bit source actual values, converted only for the device preview.
        pcm=(b"\x00\x00\x40"+b"\x00\x00\x80")*SAMPLES_PER_FRAME
        stereo=_stereo_pcm16(pcm,("L","R"))
        self.assertEqual(len(stereo),SAMPLES_PER_FRAME*4)
        import struct
        left,right=struct.unpack_from("<hh",stereo,0)
        self.assertTrue(16000<left<17000)
        self.assertEqual(right,-32767)
        with self.assertRaises(PermissionError):
            _stereo_pcm16(pcm[:-1],("L","R"))
        with self.assertRaises(PermissionError):
            _stereo_pcm16(pcm,("R","L"))


class RegionAndAdmissionTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        require_efs_stage(self.root)

    def _sample(self,frame,channels):
        return b"".join((frame*16+ch).to_bytes(3,"little",signed=True)
                        for ch in range(channels))*SAMPLES_PER_FRAME

    def _test_boundary(self,frames,channels):
        observed=[]
        cache={}
        order=("L","R") if channels==2 else ("L","R","C","LFE","Ls","Rs")
        source=b"".join(self._sample(fr,channels) for fr in range(frames))
        wav_path=self.root/"approved.wav"
        with wave.open(str(wav_path),"wb") as out:
            out.setnchannels(channels);out.setsampwidth(3);out.setframerate(RATE)
            out.writeframes(source)
        wav=wav_path.read_bytes()
        reel=SimpleNamespace(frames=frames,channels=order,wav_sha=sha256(wav).hexdigest(),
                             wav_bytes=len(wav),pcm_sha=sha256(source).hexdigest())
        with _locked_media(wav_path) as (stream,_):
            ledger=_region_ledger(stream,reel,lambda:False)
            with self.assertRaises((OSError,PermissionError)):
                with wav_path.open("r+b"):
                    pass
        def region(first,length):
            if first not in cache:
                observed.append((first,length))
                path=self.root/"audio"
                with wave.open(str(path),"wb") as out:
                    out.setnchannels(channels);out.setsampwidth(3);out.setframerate(RATE)
                    out.writeframes(b"".join(self._sample(fr,channels) for fr in range(first,first+length)))
                pcm=_read_verified_pcm24(path,order,length)
                self.assertEqual(ledger[first],(length,sha256(pcm).hexdigest()))
                path.unlink()
                cache[first]=pcm
            return cache[first]
        bpf=channels*3*SAMPLES_PER_FRAME
        actual=_pcm_region_window(22,4,frames,region,bpf)
        tail=_pcm_region_window(24,2,frames,region,bpf)
        self.assertEqual(actual,source[22*bpf:26*bpf])
        self.assertEqual(tail,actual[2*bpf:])
        self.assertEqual(observed,[(0,24),(24,min(frames-24,24))])
        for i in range(4):
            self.assertEqual(actual[i*bpf:i*bpf+channels*3],self._sample(22+i,channels)[:channels*3])

    def test_pcm_region_boundary_preserves_all_2000_sample_frames(self):
        self._test_boundary(48,2)

    def test_partial_terminal_pcm_region_and_5_1_channels_preserve_samples(self):
        self._test_boundary(26,6)

    def test_incomplete_region_refused_not_padded(self):
        with self.assertRaises(PermissionError):
            _pcm_region_window(22,4,26,lambda *_:b"x",36000)

    def test_approved_wav_digest_and_exact_channels_required(self):
        reel=SimpleNamespace(frames=3,channels=("L","R"),wav_sha="a"*64,
                             wav_bytes=3,pcm_sha="b"*64)
        with self.assertRaises(PermissionError):
            _region_ledger(BytesIO(b"bad"),reel,lambda:False)

    def test_untrusted_browser_cannot_construct_player(self):
        with self.assertRaises(PermissionError):
            FinishedFilmPlayer({}, {}, codec_factory=lambda *_:None,native_window=lambda:True,
                               ask_native=lambda _:True,host_revoked=lambda:False)

    def test_denied_native_session_and_wrong_project_cannot_read(self):
        studio=Studio(self.root/"studio.sqlite3")
        pid=studio.create_project("Review","Original")["id"]
        index=FilmIndex(studio)
        journal=FeatureJournal(self.root/"production")
        def checked_codecs(project,check):
            self.assertEqual(project,pid)
            host=SimpleNamespace(project_id=pid,cancel=check,pin="b"*64)
            return tuple(SimpleNamespace(product=role,sha256="c"*64,authority=host)
                         for role in ("ASDCP-asdcp_unwrap","OpenJPEG-opj_decompress"))
        player=FinishedFilmPlayer(index,journal,codec_factory=checked_codecs,
                        native_window=lambda:True,ask_native=lambda _:False,host_revoked=lambda:False)
        self.addCleanup(player.close)
        reels=(SimpleNamespace(frames=3,receipt_sha="d"*64),)
        with patch("backend.nvp_wo5_finished_playback.load_published_reels",
                   return_value=("a"*64,reels,"2K_FLAT_24",{})),patch(
                   "backend.nvp_wo5_finished_playback.common_codec_authority",
                   side_effect=lambda a,b:a.authority):
            self.assertEqual(player.begin(pid,"Feature")["status"],"DENIED")
        with self.assertRaises(PermissionError):
            player.frame("injected",0)


if __name__=="__main__":
    unittest.main()
