"""NVP-MASTER-01A: real >20s verified native AV assembly, not AI-generation acceptance."""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from unittest.mock import patch
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_longform_review import (
    MIN_FRAMES, MAX_FRAMES, assemble_review, index_technical_reel,
    probe_reel, reopen_review, _verify_packet_clock,
)


def require(name):
    result = shutil.which(name)
    if result is None:
        raise unittest.SkipTest("Real native " + name + " required")
    return result


def make_prores_with_pcm24(ffmpeg, target: Path, *, seconds=12, width=160,
                           color="blue", tone=330):
    process = subprocess.run([
        ffmpeg,"-nostdin","-hide_banner","-loglevel","error","-xerror", "-y",
        "-f","lavfi","-i",f"color=c={color}:s={width}x90:r=24:d={seconds}",
        "-f","lavfi","-i",f"sine=frequency={tone}:sample_rate=48000:duration={seconds}",
        "-map","0:v:0","-map","1:a:0",
        "-c:v","prores_ks","-profile:v","3","-pix_fmt","yuv422p10le",
        "-frames:v",str(seconds*24),"-c:a","pcm_s24le","-ar","48000","-ac","2",
        "-f","mov",str(target)
    ], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
       timeout=180, check=False)
    if process.returncode:
        raise RuntimeError(process.stderr.decode("utf-8","replace")[-1500:])


class LongFormNativeReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg = require("ffmpeg")
        cls.ffprobe = require("ffprobe")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nvp-master01a-")
        self.root = Path(self.temp.name)
        self.db = self.root / "studio.sqlite3"
        self.studio = Studio(self.db)
        self.index = FilmIndex(self.studio)
        self.pid = self.studio.create_project("Short Film","Native technical review")['id']

    def tearDown(self):
        self.temp.cleanup()

    def reel(self, number, *, seconds=12, width=160):
        path=self.root/f"source{number}.mov"
        make_prores_with_pcm24(self.ffmpeg,path,seconds=seconds,width=width,
                               color=["blue","green","red","yellow"][number],
                               tone=330+100*number)
        media=self.index.put_media_file(self.pid,path,"video/quicktime")
        producer_id=f"source{number}"
        self.index.register_revision(self.pid,producer_id,"presentation",{
            "format":"nvp.master01a.external_technical_source.v1",
            "frames":seconds*24,"movie_sha256":media["sha256"],
            "creator_approved_final_master":False,"dcp_delivered":False,
        },expected_revision=0,dependencies=[])
        reel_id=f"reel{number}"
        created=index_technical_reel(self.index,self.pid,reel_id,producer_id,1)
        self.assertFalse(created["creator_approved_final_master"])
        return {"object_id":reel_id,"revision":1}

    def test_three_real_twelve_second_reels_create_verified_36s_av_with_restart(self):
        refs=[self.reel(n) for n in range(3)]
        result=assemble_review(self.index,self.pid,"longreview",refs)
        self.assertEqual(result["status"],"VERIFIED_TECHNICAL_REVIEW_UNAPPROVED")
        self.assertEqual(result["frames"], 864)
        self.assertEqual(result["duration_seconds"],36)
        self.assertFalse(result["creator_approved_final_master"])
        before=self.index.read_revision(self.pid,"longreview",1)
        self.assertEqual(len(before["dependencies"]),3)
        self.assertTrue(before["data"]["stream_copy_evidence"]["all_video_packets_identical"])
        self.assertTrue(before["data"]["stream_copy_evidence"]["all_audio_samples_identical"])
        self.assertEqual(len(before["data"]["stream_copy_evidence"]["decoded_pcm24_sha256"]),64)
        # The entire resulting media survives a new Studio/FilmIndex instance.
        reopened=FilmIndex(Studio(self.db))
        proof=reopen_review(reopened,self.pid,"longreview")
        self.assertEqual(proof["frames"],864)
        self.assertEqual(proof["duration_seconds"],36)
        self.assertTrue(Path(proof["path"]).is_file())
        self.assertEqual(proof["movie_sha256"],hashlib.sha256(
            Path(proof["path"]).read_bytes()).hexdigest())
        self.assertEqual(probe_reel(Path(proof["path"]),ffprobe=self.ffprobe)["audio_samples"],
                         36*48000)
        # Tampering cannot be mistaken for the previously verified review.
        with open(proof["path"],"r+b") as blob:
            blob.seek(1024)
            b=blob.read(1)
            blob.seek(1024)
            blob.write(bytes([b[0]^1]))
        with self.assertRaisesRegex(RuntimeError,"integrity"):
            reopen_review(FilmIndex(Studio(self.db)),self.pid,"longreview")

    def test_rejects_short_duration_and_duplicate_or_unsafe_references(self):
        a=self.reel(0,seconds=1)
        b=self.reel(1,seconds=1)
        with self.assertRaisesRegex(ValueError,"at least 30 seconds"):
            assemble_review(self.index,self.pid,"too_short",[a,b])
        with self.assertRaisesRegex(ValueError,"Repeated reel"):
            assemble_review(self.index,self.pid,"duplicate",[a,a])
        with self.assertRaises((KeyError,ValueError)):
            assemble_review(self.index,self.pid,"wrong_project",[
                {"object_id":"not_a_reel","revision":1},b])
        with self.assertRaisesRegex(ValueError,"exactly"):
            assemble_review(self.index,self.pid,"extra_arg",[{**a,"path":"C:/forged.mov"},b])
        self.assertEqual(self.index.list_objects(self.pid,kind="master"),[])
        self.assertFalse(any(x["object_id"] == "too_short" for x in
                         self.index.list_objects(self.pid)))

    def test_incompatible_raster_rejected_before_output(self):
        a=self.reel(0,seconds=12,width=160)
        b=self.reel(1,seconds=12,width=128)
        with self.assertRaisesRegex(RuntimeError,"dimensions incompatible"):
            assemble_review(self.index,self.pid,"wrong_raster",[a,b])
        self.assertFalse(any(x["object_id"]=="wrong_raster" for x in
                             self.index.list_objects(self.pid)))

    def test_exact_sixty_second_ceiling_uses_three_bounded_20s_reels(self):
        refs = [self.reel(n, seconds=20) for n in range(3)]
        result = assemble_review(self.index, self.pid, "one_minute", refs)
        self.assertEqual(result["frames"], MAX_FRAMES)
        self.assertEqual(result["duration_seconds"], 60)
        self.assertEqual(reopen_review(self.index, self.pid, "one_minute")["frames"], MAX_FRAMES)

    def test_source_corruption_refused_before_assembly(self):
        refs = [self.reel(n, seconds=12) for n in range(3)]
        original = self.index.read_revision(self.pid, "reel1", 1)
        checked = self.index.verify_media_file(self.pid, original["data"]["movie_sha256"])
        with open(checked["path"], "r+b") as blob:
            blob.seek(900)
            old = blob.read(1)
            blob.seek(900)
            blob.write(bytes([old[0] ^ 1]))
        with self.assertRaisesRegex(RuntimeError, "integrity"):
            assemble_review(self.index, self.pid, "bad_source", refs)
        self.assertFalse(any(x["object_id"] == "bad_source" for x in
                             self.index.list_objects(self.pid)))

    def test_packet_time_gaps_are_rejected_even_if_total_frames_seem_valid(self):
        broken = {"streams": [{"time_base": "1/48000"}], "packets": [
            {"pts": 0, "duration": 1024},
            {"pts": 2048, "duration": 1024},
        ]}
        with patch("backend.nvp_longform_review._native", return_value=json.dumps(broken).encode()):
            with self.assertRaisesRegex(RuntimeError, "timestamps are not contiguous"):
                _verify_packet_clock(self.root / "not_read.mov", ffprobe="ffprobe",
                                     selector="a:0", expected_seconds=Fraction(3072, 48000))

    def test_reel_must_be_based_on_existing_indexed_media(self):
        with self.assertRaises(KeyError):
            index_technical_reel(self.index,self.pid,"some_reel","missing",1)
        src=self.index.register_revision(self.pid,"not_video","asset",{
            "format":"nvp.master01a.not_video.v1"},expected_revision=0)
        with self.assertRaisesRegex(ValueError,"presentation/master"):
            index_technical_reel(self.index,self.pid,"not_reel","not_video",1)
        self.assertEqual(src["revision"],1)
        self.assertEqual(self.index.list_objects(self.pid,kind="master"),[])


if __name__=="__main__":
    unittest.main()