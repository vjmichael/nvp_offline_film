"""Synthetic contract tests only: NOT evidence of native Blender renders."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend.nvp_usd_film01h_multicam import CameraRoll,verify_multicam,prepare_multicam_edit

T=7056000000

class MultiCameraSourceContract(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.rolls=[]
        for a,angle in enumerate(("wide","side","detail")):
            folder=self.root/angle
            folder.mkdir()
            proofs=[]
            for i in range(720):
                # Deliberately synthetic, non-image bytes. The verification
                # contract checks source integrity, not photoreal image quality.
                payload=f"SYNTHETIC_ONLY_{angle}_{i}".encode()
                (folder/f"frame_{i:04d}.png").write_bytes(payload)
                proofs.append({"actual_native_cycles_image":True,
                    "original_world_sha256":"a"*64,
                    "original_performance_sha256":"b"*64,
                    "original_camera_shot_sha256":str(a+1)*64,
                    "original_camera_path":f"/World/Cameras/{angle}",
                    "original_film_tick":i*T//24,
                    "original_actor_state_sha256":sha256(
                        f"actor-performance-at-{i}".encode()).hexdigest(),
                    "rendered_png_sha256":sha256(payload).hexdigest()})
            receipts=self.root/f"{angle}.json"
            receipts.write_text(json.dumps(proofs),"utf8")
            self.rolls.append(CameraRoll(angle,f"/World/Cameras/{angle}",
                str(a+1)*64,"a"*64,"b"*64,folder,receipts))

    def tearDown(self):
        self.tmp.cleanup()

    def test_three_cameras_record_all_720_shared_ticks_and_edit_three_cuts(self):
        result=verify_multicam(self.rolls,ticks_per_second=T)
        self.assertEqual(result["total_frame_receipts_checked"],2160)
        self.assertTrue(result["all_camera_actor_states_identical_per_tick"])
        cut=prepare_multicam_edit(self.rolls,ticks_per_second=T,out_dir=self.root/"edit")
        self.assertEqual([s["first_source_frame"] for s in cut["cuts"]],[0,240,480])
        self.assertEqual(cut["output_frames"],720)
        self.assertFalse(cut["playable_film_created"])

    def test_wrong_actor_state_in_second_angle_fails(self):
        path=self.rolls[1].receipts
        rows=json.loads(path.read_text("utf8"))
        rows[240]["original_actor_state_sha256"]="e"*64
        path.write_text(json.dumps(rows))
        with self.assertRaises(PermissionError):
            verify_multicam(self.rolls,ticks_per_second=T)

    def test_duplicate_camera_or_independent_performance_fails(self):
        for key,value in (("camera_prim",self.rolls[0].camera_prim),
                          ("original_world_sha256","e"*64),
                          ("original_performance_sha256","c"*64)):
            rows=self.rolls.copy()
            rows[2]=replace(rows[2],**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):
                verify_multicam(rows,ticks_per_second=T)

    def test_missing_frame_and_wrong_time_fail(self):
        rows=json.loads(self.rolls[0].receipts.read_text("utf8"))
        rows[479]["original_film_tick"]+=1
        self.rolls[0].receipts.write_text(json.dumps(rows))
        with self.assertRaises(PermissionError):
            verify_multicam(self.rolls,ticks_per_second=T)
        rows[479]["original_film_tick"]-=1
        self.rolls[0].receipts.write_text(json.dumps(rows))
        (self.rolls[2].frames/"frame_0500.png").unlink()
        with self.assertRaises(ValueError):
            verify_multicam(self.rolls,ticks_per_second=T)
if __name__=="__main__":
    unittest.main()
