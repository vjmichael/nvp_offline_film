"""Synthetic PNG editorial contract test, NOT real Blender/Cycles evidence."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from PIL import Image

from backend.nvp_usd_film01i_ninecam_take import FORMAT as RIG_FORMAT, GRID
from backend.nvp_usd_film01j_ninecam_edit import (
    FilmCameraRoll,validate_coverage_contract,nine_camera_edit_decisions)

T=7056000000

class NineCameraEditorialContractOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory(prefix="nvp-01j-synthetic-contract-")
        cls.root=Path(cls.tmp.name)
        cls.rig={
            "format":RIG_FORMAT,"camera_count":9,
            "original_world_sha256":"a"*64,
            "source_performance_sha256":"b"*64,
            "cameras":[]}
        cls.rolls=[]
        cls.receipt_cache=[]
        for camera_index,(angle,framing) in enumerate(GRID):
            name=f"{angle}_{framing}"
            folder=cls.root/name
            folder.mkdir()
            hashes=[]
            rows=[]
            camera_sha=sha256(f"source-{name}".encode()).hexdigest()
            prim=f"/World/Sets/Stage/Cameras/Cam_{name}"
            cls.rig["cameras"].append({
                "angle":angle,"framing":framing,
                "native_composed_camera_path":prim,
                "camera_shot_sha256":camera_sha})
            for frame in range(720):
                picture=Image.new("RGB",(16,9),(camera_index*20,0,0))
                picture.putpixel((0,0),(frame%256,frame//256,camera_index))
                file=folder/f"frame_{frame:04d}.png"
                picture.save(file,format="PNG")
                hashes.append(sha256(file.read_bytes()).hexdigest())
                rows.append({
                    "actual_native_cycles_image":True,
                    "original_film_tick":frame*T//24,
                    "original_world_sha256":"a"*64,
                    "original_performance_sha256":"b"*64,
                    "original_camera_shot_sha256":camera_sha,
                    "original_camera_path":prim,
                    "original_actor_state_sha256":sha256(
                        f"same-native-performer-at-{frame}".encode()).hexdigest(),
                    "rendered_png_sha256":hashes[-1]})
            receipt=cls.root/f"{name}.json"
            receipt.write_text(json.dumps(rows),"utf8")
            cls.receipt_cache.append(rows)
            cls.rolls.append(FilmCameraRoll(angle,framing,folder,receipt))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_nine_720_frame_source_rolls_and_nine_real_editor_cut_contracts(self):
        report=validate_coverage_contract(self.rig,self.rolls)
        self.assertEqual(report["camera_roll_count"],9)
        self.assertEqual(report["original_coverage_frame_count"],6480)
        self.assertTrue(report["same_actor_state_at_each_tick_across_all_rolls"])
        self.assertTrue(report["contract_only_not_blender_supervisor_attestation"])
        decisions=nine_camera_edit_decisions()
        self.assertEqual(len(decisions),9)
        self.assertEqual(sum(d["source_out_frame"]-d["source_in_frame"]
                             for d in decisions),720)
        self.assertEqual([d["source_in_frame"] for d in decisions],
                         list(range(0,720,80)))
        self.assertEqual(set((d["angle"],d["framing"]) for d in decisions),
                         set(GRID))

    def test_temporal_actor_mismatch_on_second_camera_is_rejected(self):
        receipt=self.rolls[1].native_frame_receipts
        rows=json.loads(receipt.read_text("utf8"))
        rows[479]["original_actor_state_sha256"]="e"*64
        receipt.write_text(json.dumps(rows),"utf8")
        try:
            with self.assertRaises(RuntimeError):
                validate_coverage_contract(self.rig,self.rolls)
        finally:
            rows[479]["original_actor_state_sha256"]=sha256(
                b"same-native-performer-at-479").hexdigest()
            receipt.write_text(json.dumps(rows),"utf8")

    def test_missing_source_picture_prevents_master(self):
        path=self.rolls[8].frames_dir/"frame_0719.png"
        backup=path.read_bytes()
        path.unlink()
        try:
            with self.assertRaises(RuntimeError):
                validate_coverage_contract(self.rig,self.rolls)
        finally:
            path.write_bytes(backup)

if __name__=="__main__":
    unittest.main()
