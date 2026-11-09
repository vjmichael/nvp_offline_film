"""Contract tests: three camera angles, source identities, 720 unique frames, cut order.

These are synthetic PNG/receipt contract tests, NOT genuine Blender pixels.
Native Blender/Cycles per-frame 01E world Take production remains an open gate.
"""
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_usd_film01g_three_shot_conform import (
    FilmShot, FPS, TOTAL_FRAMES, validate_shots, conform_short,
)

T = 7056000000


class ThreeShotConformContract(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="nvp-film01g-")
        self.root = Path(self.temp.name)
        self.shots = []
        world = "a"*64
        # Distinct test-only PNG payloads, NOT a native Blender render.
        # Different PNG-compliant metadata chunks per frame are sufficient
        # to test cryptographic identity without pretending film quality.
        import struct
        import zlib
        def chunk(label, data):
            return struct.pack(">I",len(data))+label+data+struct.pack(
                ">I",zlib.crc32(label+data)&0xffffffff)
        for i,name in enumerate(("establishing","action","detail")):
            folder=self.root/name
            folder.mkdir()
            take_sha=str(i+1)*64
            camera_sha=str(i+4)*64
            camera=f"/World/Set/Camera{i}"
            receipts=[]
            for n in range(240):
                value=bytes([(i*13+n)%256])
                raw=b"\x89PNG\r\n\x1a\n"
                raw+=chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,2,0,0,0))
                raw+=chunk(b"tEXt",f"source_tick={i*10*T+n*T//FPS}".encode())
                raw+=chunk(b"IDAT",zlib.compress(b"\x00"+value*3))
                raw+=chunk(b"IEND",b"")
                frame=folder/f"frame_{n:04d}.png"
                frame.write_bytes(raw)
                receipts.append({
                    "actual_native_cycles_image":True,
                    "original_world_take_sha256":take_sha,
                    "original_camera_shot_sha256":camera_sha,
                    "original_world_sha256":world,
                    "original_camera_path":camera,
                    "original_film_tick":i*10*T+n*T//FPS,
                    "rendered_png_sha256":sha256(raw).hexdigest(),
                })
            receipt_file=self.root/f"{name}.json"
            receipt_file.write_text(json.dumps(receipts),"utf8")
            self.shots.append(FilmShot(name,f"OriginalTake{i}",take_sha,
                camera_sha,world,camera,i*10*T,(i+1)*10*T,folder,receipt_file))

    def tearDown(self):
        self.temp.cleanup()

    def test_three_sequential_angles_and_exact_film_time(self):
        report=validate_shots(self.shots,ticks_per_second=T)
        self.assertEqual(len(report),3)
        self.assertEqual([x["shot"] for x in report],
                         ["establishing","action","detail"])
        self.assertEqual(sum(x["distinct_native_frames"] for x in report),TOTAL_FRAMES)

    def test_repeated_camera_is_not_a_three_angle_short(self):
        shots=self.shots.copy()
        from dataclasses import replace
        shots[2]=replace(shots[2],camera_shot_sha256=shots[1].camera_shot_sha256)
        with self.assertRaises(ValueError):
            validate_shots(shots,ticks_per_second=T)

    def test_cut_gaps_and_reversed_shots_rejected(self):
        from dataclasses import replace
        shots=self.shots.copy()
        shots[1]=replace(shots[1],start_tick=shots[1].start_tick+T)
        with self.assertRaises(ValueError):
            validate_shots(shots,ticks_per_second=T)
        with self.assertRaises(ValueError):
            validate_shots(list(reversed(self.shots)),ticks_per_second=T)

    def test_missing_or_forged_native_frame_rejected(self):
        file=self.shots[1].frames_dir/"frame_0007.png"
        file.write_bytes(b"not a source render")
        with self.assertRaises(PermissionError):
            validate_shots(self.shots,ticks_per_second=T)

    def test_stitched_silent_workprint_requires_real_ffmpeg(self):
        import shutil
        if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            self.skipTest("Native ffmpeg and ffprobe binaries unavailable")
        report=conform_short(self.shots,ticks_per_second=T,
            out_dir=self.root/"workprint",ffmpeg="ffmpeg",ffprobe="ffprobe")
        self.assertEqual(report["shot_count"],3)
        self.assertEqual(report["decoded_original_render_frames"],720)
        self.assertTrue(report["actual_ffmpeg_three_shot_stitch_verified"])
        self.assertTrue(report["silent_picture_workprint_only"])
        self.assertFalse(report["director_visual_approval"])
        self.assertTrue((self.root/"workprint"/"picture_workprint.mkv").is_file())


if __name__=="__main__":
    unittest.main()
