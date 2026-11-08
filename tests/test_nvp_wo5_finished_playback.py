"""WO5 finished film viewer: exact master essence, sound/time and native grants.

The real wrapper+OpenJPEG codec E2E must run separately with published
multi-reel DCP fixtures. This suite tests native session/IPC correctness
and verifies real PNG and PCM conversion, not an invented theatrical pass.
"""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import base64
import unittest
import wave

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_wo4_feature_journal import FeatureJournal,FRAME_TICKS
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary
from backend.nvp_wo5_finished_playback import (
    FORMAT,RATE,SAMPLES_PER_FRAME,Reel,FinishedFilmPlayer,
    _display_png,_stereo_pcm16,locate_reel,_fingerprint)

class TimelineAndPixelTests(unittest.TestCase):
    def test_global_film_time_crosses_reel_without_gap(self):
        with TemporaryDirectory() as tmp:
            f=Path(tmp)/"real.mxf"
            f.write_bytes(b"real sample")
            stat=_fingerprint(f)
            reels=(
                Reel(0,3,f,f,sha256(f.read_bytes()).hexdigest(),
                     sha256(f.read_bytes()).hexdigest(),"Reel1",("L","R"),stat,stat),
                Reel(3,6,f,f,sha256(f.read_bytes()).hexdigest(),
                     sha256(f.read_bytes()).hexdigest(),"Reel2",("L","R"),stat,stat))
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

class NativePublishedViewerTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()
        self.studio=Studio(self.root/"studio.sqlite3")
        self.pid=self.studio.create_project("Real final review","Original DCP")["id"]
        self.index=FilmIndex(self.studio)
        self.journal=FeatureJournal(self.root/"production")
        self.picture=self.root/"PUBLISHED_picture.mxf"
        self.sound=self.root/"PUBLISHED_sound.mxf"
        self.picture.write_bytes(b"final published picture MXF bytes")
        self.sound.write_bytes(b"final published sound MXF bytes")
        self.codestream=b"J2K-FINAL-CODESTREAM"+b"\x00"*80
        self.expected=sha256(self.codestream).hexdigest()
        picture_sha=sha256(self.picture.read_bytes()).hexdigest()
        sound_sha=sha256(self.sound.read_bytes()).hexdigest()
        self.reels=tuple(
            Reel(n*3,3,self.picture,self.sound,picture_sha,sound_sha,
                 f"Job{n}",("L","R"),_fingerprint(self.picture),
                 _fingerprint(self.sound)) for n in range(2))
        self.audit={"filmindex_feature_receipt_sha256":"a"*64,
                    "ordered_picture_custody_sha256":"b"*64,
                    "frame_count":6}
        # Exact binary identity objects; never use arbitrary JS-supplied path.
        wrapper=self.root/"asdcp-unwrap"
        decoder=self.root/"opj_decompress"
        wrapper.write_bytes(b"pinned wrapper fake fixture")
        decoder.write_bytes(b"pinned decoder fake fixture")
        self.unwrap=ApprovedCodecBinary(
            wrapper,sha256=sha256(wrapper.read_bytes()).hexdigest(),
            product="ASDCP-asdcp_unwrap")
        self.decoder=ApprovedCodecBinary(
            decoder,sha256=sha256(decoder.read_bytes()).hexdigest(),
            product="OpenJPEG-opj_decompress")
        self.prompts=[]
        self.player=FinishedFilmPlayer(
            self.index,self.journal,unwrap=self.unwrap,
            decoder=self.decoder,private_root=self.root/"tmp",
            native_window=lambda:True,
            ask_native=self._approve)
        self.addCleanup(self.player.close)

    def _approve(self,scope):
        self.prompts.append(scope)
        return self.permission

    def open(self,allow=True):
        self.permission=allow
        with patch("backend.nvp_wo5_finished_playback.load_published_reels",
                   return_value=(self.audit,self.reels,"2K_FLAT_24")):
            return self.player.begin(self.pid,"PublishedFeature")

    def test_denied_native_session_cannot_read_any_final_frame(self):
        denied=self.open(False)
        self.assertEqual(denied["status"],"DENIED")
        self.assertEqual(self.prompts[0]["operation"],
                         "nvp.wo5.approve_readonly_finished_mxf_playback.v1")
        self.assertTrue(self.prompts[0]["read_only"])
        with self.assertRaises(PermissionError):
            self.player.frame("injected",0)

    def test_actual_decoded_final_picture_and_pcm_follow_global_reel_boundary(self):
        approved=self.open(True)
        self.assertEqual(approved["status"],"FINISHED_DCP_READONLY_READY")
        self.assertFalse(approved["continuous_real_time_playback_verified"])
        self.assertFalse(approved["production_accepted"])
        ticket=approved["session_id"]
        invocations=[]
        def fake_native(codec,args,*,workdir,check_cancel,timeout):
            self.assertFalse(check_cancel())
            invocations.append((codec.product,args))
            root=Path(workdir)
            if codec.product=="ASDCP-asdcp_unwrap":
                start=int(args[args.index("-f")+1])
                frames=int(args[args.index("-d")+1])
                if args[-1]=="p_":
                    for n in range(frames):
                        (root/f"p_{start+n:06d}.j2c").write_bytes(self.codestream)
                else:
                    with wave.open(str(root/args[-1]),"wb") as out:
                        out.setnchannels(2)
                        out.setsampwidth(3)
                        out.setframerate(RATE)
                        out.writeframes((b"\x00\x00\x40"+b"\x00\x00\x80")*
                                        SAMPLES_PER_FRAME*frames)
            elif codec.product=="OpenJPEG-opj_decompress":
                (root/args[args.index("-o")+1]).write_bytes(
                    b"P6\n1998 1080\n4095\n"+
                    (0x0300).to_bytes(2,"big")*3*(1998*1080))
            return {"exit_code":0}
        with patch("backend.nvp_wo5_finished_playback.run_supervised_codec",
                   side_effect=fake_native),patch(
                   "backend.nvp_wo5_finished_playback._expected_frame_sha",
                   return_value=self.expected),patch(
                   "backend.nvp_wo5_finished_playback.inspect_j2k_header",
                   return_value={"raw_codestream_sha256":self.expected}):
            final=self.player.frame(ticket,3)
            next_reel=self.player.window(ticket,3,2)
            last_first_reel=self.player.window(ticket,2,4)
        self.assertEqual(last_first_reel["frame_count"],1)
        self.assertEqual(last_first_reel["frames"][0]["frame_index"],2)
        self.assertEqual(next_reel["frame_count"],2)
        self.assertEqual(
            [v["audio_start_sample"] for v in next_reel["frames"]],
            [3*SAMPLES_PER_FRAME,4*SAMPLES_PER_FRAME])
        self.assertTrue(last_first_reel["no_reel_crossing"])
        self.assertTrue(next_reel["no_reel_crossing"])
        self.assertFalse(next_reel["production_accepted"])
        self.assertEqual(final["status"],"DECODED_PUBLISHED_FINAL_FRAME")
        self.assertEqual(final["reel_index"],1)
        self.assertEqual(final["reel_frame_index"],0)
        self.assertEqual(final["picture_24fps_film_time_tick"],3*FRAME_TICKS)
        self.assertEqual(final["audio_start_sample"],3*SAMPLES_PER_FRAME)
        self.assertEqual(final["audio_samples"],SAMPLES_PER_FRAME)
        self.assertEqual(len(base64.b64decode(final["stereo_pcm16_base64"])),
                         SAMPLES_PER_FRAME*4)
        self.assertTrue(base64.b64decode(final["picture_png_base64"]).startswith(
            b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(len(invocations),9)
        self.assertEqual(invocations[0][1][1:4],["0","-d","1"])
        self.assertEqual(invocations[2][1][1:4],["0","-d","3"])
        sound_unwraps=[args for product,args in invocations
                       if product=="ASDCP-asdcp_unwrap" and args[-1].startswith("snd_")]
        self.assertEqual(len(sound_unwraps),2)
        self.assertEqual(
            len([args for product,args in invocations
                 if product=="OpenJPEG-opj_decompress"]),4)
        self.assertFalse(final["production_accepted"])
        self.player.stop(ticket)
        self.assertIsNone(self.player._pcm_cache)
        with self.assertRaises(PermissionError):
            self.player.frame(ticket,4)

    def test_pcm_region_boundary_preserves_all_2000_sample_frames(self):
        # Distinct source samples prove that 22..25 never become 22..23
        # or duplicate the first samples of the next 24-frame region.
        ticket=self.open()["session_id"]
        original=self.reels[0]
        reel=Reel(0,48,original.picture,original.sound,
                  original.picture_sha,original.sound_sha,
                  original.job_id,original.channels,
                  original.picture_stat,original.sound_stat)
        unwrap_starts=[]
        def real_pcm_fixture(codec,args,*,workdir,check_cancel,timeout):
            self.assertFalse(check_cancel())
            self.assertEqual(codec.product,"ASDCP-asdcp_unwrap")
            self.assertEqual(args[-1],f"snd_{int(args[args.index(\"-f\")+1]):09d}")
            start=int(args[args.index("-f")+1])
            frames=int(args[args.index("-d")+1])
            unwrap_starts.append((start,frames))
            with wave.open(str(Path(workdir)/args[-1]),"wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(3)
                wav.setframerate(RATE)
                chunks=[]
                for frame in range(start,start+frames):
                    sample=(frame+1).to_bytes(3,"little",signed=True)
                    chunks.append((sample*2)*SAMPLES_PER_FRAME)
                wav.writeframes(b"".join(chunks))
            return {"exit_code":0}
        with TemporaryDirectory(dir=self.root) as temp,patch(
            "backend.nvp_wo5_finished_playback.run_supervised_codec",
            side_effect=real_pcm_fixture):
            sample=self.player._pcm24_window(
                ticket,reel,0,22,4,Path(temp),lambda:False)
            cached=self.player._pcm24_window(
                ticket,reel,0,24,2,Path(temp),lambda:False)
        self.assertEqual(len(sample),4*SAMPLES_PER_FRAME*2*3)
        self.assertEqual(sample[2*SAMPLES_PER_FRAME*6:],cached)
        for i in range(4):
            frame=22+i
            self.assertEqual(
                sample[i*SAMPLES_PER_FRAME*6:i*SAMPLES_PER_FRAME*6+6],
                (frame+1).to_bytes(3,"little",signed=True)*2)
        self.assertEqual(unwrap_starts,[(0,24),(24,24)])
        self.player.stop(ticket)
        self.assertIsNone(self.player._pcm_cache)

    def test_mutated_published_picture_or_sound_refused(self):
        ticket=self.open()["session_id"]
        self.sound.write_bytes(b"mutated")
        with self.assertRaises(PermissionError):
            self.player.frame(ticket,0)

    def test_no_concurrent_sessions_and_no_out_of_range_seek(self):
        ticket=self.open()["session_id"]
        with self.assertRaises(PermissionError):
            self.open()
        with self.assertRaises(ValueError):
            self.player.frame(ticket,6)
        self.player.close()
        with self.assertRaises(PermissionError):
            self.player.frame(ticket,0)

if __name__=="__main__":
    unittest.main()
