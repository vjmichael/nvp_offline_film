"""Actual PCM/WAV and clock fixtures; Windows EFS qualification is separate."""
from hashlib import sha256
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import wave
import os

from backend import nvp_wo4_longfilm_audio as audio
from backend import nvp_wo4_loudness_stream as loudness
from backend import nvp_wo4_pcm_stream as legacy
from backend.nvp_wo4_pcm_master import master_pcm24_candidate
from backend.nvp_wo4_loudness import measure_pcm24_loudness


def local_identity(path, *, directory=False):
    path=Path(path)
    if path.is_symlink() or not (path.is_dir() if directory else path.is_file()):
        raise PermissionError("Linked or missing fixture")
    st=path.stat();return st.st_dev,st.st_ino


class LayoutTests(unittest.TestCase):
    def test_exact_extended_clock_and_riff_bound(self):
        for hours in (0.5,1,3,6,8,12,24):
            for kind in ("stereo","5.1","7.1"):
                frames=int(hours*3600*24);layout=audio.AudioReels(frames,kind)
                cursor=0
                for i in range(layout.count):
                    row=layout.at(i)
                    self.assertEqual(row["first_sample"],cursor)
                    self.assertLessEqual(row["sample_count"]*layout.stride,audio.MAX_RIFF_PCM_BYTES)
                    cursor+=row["sample_count"]
                self.assertEqual(cursor,frames*2000)
                self.assertEqual(layout.source_bytes,cursor*layout.stride)
        self.assertGreater(audio.AudioReels(8*3600*24,"stereo").source_bytes,2**32)

    def test_balanced_partial_and_large_header(self):
        layout=audio.AudioReels(13,"7.1",6)
        self.assertEqual([layout.at(i)["frame_count"] for i in range(layout.count)],[5,4,4])
        with self.assertRaises(ValueError):audio.AudioReels(4,"stereo",3)
        with self.assertRaises(ValueError):audio.AudioReels(audio.MAX_TOTAL_FRAMES+1,"stereo")
        with self.assertRaises(ValueError):audio._header(2**32,6)
        large=audio.AudioReels(300000,"7.1",144000)
        self.assertLess(large.maximum,144000)
        for i in range(large.count):
            header=audio._header(large.at(i)["sample_count"],large.stride)
            self.assertEqual(len(header),44)


class PortableFiles(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve();self.source=self.root/"source.pcm";self.out=self.root/"out";self.out.mkdir()
        for module in (audio,loudness,legacy):
            p=patch.object(module,"_protected_path",side_effect=local_identity);p.start();self.addCleanup(p.stop)
        self.raw=b"".join(int(500000*math.sin(2*math.pi*1000*i/48000)).to_bytes(3,"little",signed=True)*2
                           for i in range(24000))
        self.source.write_bytes(self.raw)

    def make(self,**kw):
        params=dict(source_sha256=sha256(self.raw).hexdigest(),original_take_sha256="a"*64,
                    cinema_frames=12,channel_layout="stereo",output_root=self.out,approve=lambda _:True,
                    max_reel_frames=5)
        params.update(kw);return audio.master_partitioned_pcm24(self.source,**params)

    def test_real_reels_gain_parity_and_continuous_loudness(self):
        receipt=self.make(gain_numerator=1,gain_denominator=2)
        proof=audio.verify_partitioned_pcm24(receipt)
        self.assertEqual((proof["reel_count"],proof["sample_count"]),(3,24000))
        folder=Path(receipt["destination"]);joined=b""
        for i in range(3):
            with wave.open(str(folder/f"PCM24_{i:06d}.wav"),"rb") as reader:
                self.assertEqual((reader.getnframes(),reader.getframerate(),reader.getsampwidth()),(8000,48000,3))
                joined+=reader.readframes(reader.getnframes())
        original=master_pcm24_candidate(self.raw,source_sha256=sha256(self.raw).hexdigest(),
            original_take_sha256="a"*64,cinema_frames=12,channel_layout="stereo",
            gain_numerator=1,gain_denominator=2,creator_approved=True)
        self.assertEqual(sha256(joined).hexdigest(),original["master_pcm_sha256"])
        first=measure_pcm24_loudness(original);second=audio.measure_partitioned_pcm24_loudness(receipt)
        self.assertTrue(second["measured"]);self.assertAlmostEqual(first["lufs"],second["lufs"],places=5)
        self.assertEqual(first["block_count"],second["block_count"])
        self.assertFalse(second["block_history_materialized"])
        self.assertFalse(receipt["production_audio_accepted"])
        self.assertEqual(self.source.read_bytes(),self.raw)
        self.assertFalse(any(p.name.startswith(".nvp-pcm-reels-") for p in self.out.iterdir()))

    def test_legacy_stream_loudness_parity(self):
        rec=legacy.stream_master_pcm24_candidate(self.source,source_sha256=sha256(self.raw).hexdigest(),
            original_take_sha256="a"*64,cinema_frames=12,channel_layout="stereo",
            output_root=self.out,approve=lambda _:True)
        # _hash_stream resolves its own module's protected-path guard.
        result=loudness.measure_streamed_pcm24_loudness(rec)
        expected=audio.measure_partitioned_pcm24_loudness(self.make())
        self.assertAlmostEqual(result["lufs"],expected["lufs"],places=6)
        self.assertEqual(result["block_count"],expected["block_count"])

    def test_denial_clipping_and_source_mutation_leave_no_output(self):
        self.assertEqual(self.make(approve=lambda _:False)["status"],"DENIED")
        def change(_):
            self.source.write_bytes(bytes(len(self.raw)));return True
        with self.assertRaises(PermissionError):self.make(approve=change)
        self.raw=(8388607).to_bytes(3,"little",signed=True)*48000
        self.source.write_bytes(self.raw)
        with self.assertRaisesRegex(ValueError,"clips"):self.make(gain_numerator=2)
        self.assertEqual(list(self.out.iterdir()),[])

    def test_cancel_during_mastering_and_no_clobber(self):
        calls=0;armed=False
        def approve(_):
            nonlocal armed
            armed=True;return True
        def cancelled():
            nonlocal calls
            if armed:calls+=1
            return calls>3
        with self.assertRaises(InterruptedError):self.make(approve=approve,cancelled=cancelled)
        self.assertEqual(list(self.out.iterdir()),[])
        with patch.object(audio.uuid,"uuid4") as uid:
            uid.return_value.hex="0"*32
            occupied=self.out/("PCM24_REELS_"+"0"*32);occupied.mkdir();(occupied/"original").write_bytes(b"keep")
            with self.assertRaises(FileExistsError):self.make()
            self.assertEqual((occupied/"original").read_bytes(),b"keep")
            self.assertEqual(list(self.out.iterdir()),[occupied])

    def test_reel_and_manifest_tail_tamper(self):
        rec=self.make();folder=Path(rec["destination"]);last=folder/"PCM24_000002.wav"
        original=last.read_bytes();last.write_bytes(original[:-1]+bytes([original[-1]^1]))
        with self.assertRaises(PermissionError):audio.verify_partitioned_pcm24(rec)
        last.write_bytes(original);rows=folder/"reels.jsonl";raw=rows.read_bytes();rows.write_bytes(raw+b"{}\n")
        with self.assertRaises(RuntimeError):audio.verify_partitioned_pcm24(rec)
        rows.write_bytes(raw);(folder/"unapproved.wav").write_bytes(b"x")
        with self.assertRaises(RuntimeError):audio.verify_partitioned_pcm24(rec)

    def test_finite_bridge_real_guard_and_exact_source_slice(self):
        from backend import nvp_wo4_supervised_sound as sound
        from backend import nvp_wo4_mxf_stream as mxf
        rec=self.make(gain_numerator=1,gain_denominator=2)
        with self.assertRaises(PermissionError):
            audio.finite_reel_candidate(rec,1,expected_first_frame=0,expected_frame_count=4)
        candidate=audio.finite_reel_candidate(rec,1,expected_first_frame=4,expected_frame_count=4)
        self.assertEqual(candidate["source_pcm_sha256"],sha256(self.raw[8000*6:16000*6]).hexdigest())
        self.assertEqual(candidate["partitioned_manifest_sha256"],rec["manifest_sha256"])
        with patch.object(sound,"_protected_path",side_effect=local_identity), patch.object(mxf,"_protected_path",side_effect=local_identity):
            self.assertEqual(sound._read_guarded_sound(candidate,4,"a"*64),Path(candidate["destination"]))
            with self.assertRaises(PermissionError):sound._read_guarded_sound(candidate,4,"b"*64)
        self.assertFalse(candidate["production_audio_accepted"])

    @unittest.skipUnless(os.name=="posix", "sparse fixture avoids allocating large Windows file")
    def test_sparse_large_file_cancellable_before_approval(self):
        layout=audio.AudioReels(6*3600*24,"stereo")
        with self.source.open("wb") as f:f.truncate(layout.source_bytes)
        self.assertGreater(self.source.stat().st_size,2**32)
        called=[]
        with self.assertRaises(InterruptedError):
            self.make(cinema_frames=layout.frames,max_reel_frames=7200,
                      approve=lambda s:called.append(s) or True,cancelled=lambda:True)
        self.assertFalse(called);self.assertEqual(list(self.out.iterdir()),[])

    def test_loudness_second_pass_detects_changed_pcm(self):
        n=0
        def factory():
            nonlocal n
            n+=1
            raw=self.raw if n==1 else self.raw[:-1]+bytes([self.raw[-1]^1])
            for i in range(0,len(raw),4096*6):yield raw[i:i+4096*6]
        with self.assertRaises(PermissionError):loudness.measure_bounded_packets(factory,("L","R"),24000,sha256(self.raw).hexdigest())
        self.assertEqual(n,2)


@unittest.skipUnless(os.name=="nt","native Windows EFS required")
class NativeEFS(unittest.TestCase):
    def test_actual_efs_atomic_reels_and_reopen(self):
        from backend.nvp_w1g_encrypted_source import require_efs_stage,_efs_status
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();require_efs_stage(root)
            source=root/"original.pcm";out=root/"out";out.mkdir();require_efs_stage(out)
            raw=(1234).to_bytes(3,"little",signed=True)*24000;source.write_bytes(raw)
            rec=audio.master_partitioned_pcm24(source,source_sha256=sha256(raw).hexdigest(),
                original_take_sha256="a"*64,cinema_frames=6,channel_layout="stereo",
                output_root=out,max_reel_frames=3,approve=lambda _:True)
            folder=Path(rec["destination"])
            self.assertTrue(_efs_status(folder));self.assertTrue(all(_efs_status(p) for p in folder.iterdir()))
            self.assertEqual(audio.verify_partitioned_pcm24(rec)["sample_count"],12000)
            self.assertFalse(rec["production_audio_accepted"])


if __name__=="__main__":unittest.main()
