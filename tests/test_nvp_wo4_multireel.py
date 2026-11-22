"""WO4 metadata-only feature planner and file-backed multi-reel structural tests.

Structural fixtures intentionally use dummy MXF bytes. This test does not
claim genuine decoder/physical DCI acceptance or 2-hour throughput.
"""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest
from backend.nvp_w1g_encrypted_source import require_efs_stage

from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo4_multireel import publish_multireel_dcp
from backend.nvp_wo4_resource_budget import plan_feature,admit_disk,require_stage_space
from backend.nvp_temporal_ledger import TICKS_PER_SECOND


class FeatureResourcePlannerTest(unittest.TestCase):
    def test_two_and_three_hour_exact_film_time(self):
        for hours in (2,3):
            with self.subTest(hours=hours):
                result=plan_feature(frames=hours*3600*24,
                                    profile="2K_FLAT_24")
                self.assertEqual(result["reel_count"],hours*12)
                self.assertEqual(result["end_tick"],hours*3600*TICKS_PER_SECOND)
                self.assertTrue(all(3<=r["frame_count"]<=7200
                                    for r in result["reels"]))
                self.assertEqual(sum(r["frame_count"] for r in result["reels"]),
                                 hours*3600*24)
                self.assertFalse(result["all_frames_loaded_into_ram"])
                self.assertFalse(result["throughput_benchmarked"])

    def test_reel_partition_7201_frames_has_no_one_frame_tail(self):
        result=plan_feature(frames=7201,profile="4K_FLAT_24")
        self.assertEqual(len(result["reels"]),2)
        self.assertEqual([r["frame_count"] for r in result["reels"]],
                         [3601,3600])
        self.assertEqual(result["reels"][0]["end_tick"],
                         result["reels"][1]["start_tick"])

    def test_stage_admission_refuses_low_disk_before_writing_files(self):
        with TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            with self.assertRaises(OSError):
                require_stage_space(root,500*1024*1024,
                                    available_bytes=100*1024*1024)
            accepted=require_stage_space(root,500*1024*1024,
                                    available_bytes=700*1024*1024)
            self.assertEqual(accepted["status"],"ADMITTED")
            self.assertFalse(accepted["quota_enforced_by_os"])

    def test_bounded_raster_and_low_disk_refusal(self):
        with TemporaryDirectory() as temp:
            plan=plan_feature(frames=3*3600*24,profile="4K_SCOPE_24",
                              channels=8)
            denied=admit_disk(plan,Path(temp).resolve(),available_bytes=1024**3)
            self.assertEqual(denied["status"],"INSUFFICIENT_DISK")
            self.assertGreater(denied["required_bytes"],1024**3)
            accepted=admit_disk(
                plan,Path(temp).resolve(),
                available_bytes=denied["required_bytes"])
            self.assertEqual(accepted["status"],"ADMITTED")
            self.assertFalse(accepted["started_encoding"])


    def test_forged_capacity_plan_and_synthetic_disk_check(self):
        plan=plan_feature(frames=7201,profile="4K_FLAT_24")
        with TemporaryDirectory() as temp:
            root=Path(temp).resolve()
            forged=dict(plan,estimated_upper_scratch_bytes=1)
            with self.assertRaises(PermissionError):
                admit_disk(forged,root,available_bytes=2**40)
            result=admit_disk(plan,root,available_bytes=2**40)
            self.assertFalse(result["native_disk_checked"])


class FileBackedMultiReelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        require_efs_stage(self.root)
        self.output=self.root/"exports"
        self.output.mkdir()
        self.ids={k:str(uuid4()) for k in ("cpl","pkl","assetmap")}
        self.reels=[]
        start=0
        for i,frames in enumerate((3,5)):
            item={"start_tick":start,
                  "end_tick":start+frames*(TICKS_PER_SECOND//24),
                  "frames":frames,"reel_uuid":str(uuid4())}
            start=item["end_tick"]
            for kind in ("picture","sound"):
                file=self.root/f"{kind}-{i}.mxf"
                data=(f"FAKE-{kind}-{i}-only-structural".encode())*100
                file.write_bytes(data)
                item[kind]={
                    "file_path":str(file),
                    "file_sha256":sha256(data).hexdigest(),
                    "file_bytes":len(data),
                    "asset_uuid":str(uuid4()),"kind":kind,
                    "source_take_sha256":"a"*64,"frame_count":frames,
                    "edit_rate":[24,1],"source_modified":False,
                    "production_dcp_accepted":False,
                    **({"profile":"2K_FLAT_24"} if kind=="picture" else {})}
            self.reels.append(item)

    def publish(self,**change):
        settings=dict(reels=self.reels,ids=self.ids,
            title="Original Multi Reel Film",profile="2K_FLAT_24",
            output_root=self.output,check_cancel=lambda:False,approve=lambda _:True,
            source_take_sha256='a'*64,mastering_decision_sha256='b'*64)
        settings.update(change)
        return publish_multireel_dcp(**settings)

    def test_genuine_smpte_multireel_xml_structure_and_hashes(self):
        original={part[kind]["file_path"]:sha256(
                    Path(part[kind]["file_path"]).read_bytes()).hexdigest()
                  for part in self.reels for kind in ("picture","sound")}
        receipt=self.publish()
        report=inspect_dcp_structure(receipt["destination"])
        self.assertEqual(report["status"],"STRUCTURE_AND_SHA_VERIFIED")
        self.assertEqual(report["reel_count"],2)
        self.assertEqual(report["reel_durations"],[3,5])
        self.assertEqual(receipt["total_frames"],8)
        self.assertEqual(receipt["reel_count"],2)
        self.assertEqual(len(report["tracks"]),4)
        self.assertFalse(receipt["whole_feature_in_ram"])
        self.assertFalse(receipt["production_dcp_accepted"])
        for file,expected in original.items():
            self.assertEqual(sha256(Path(file).read_bytes()).hexdigest(),expected)
        self.assertEqual(len(list(self.output.iterdir())),1)

    def test_gapped_or_reordered_reels_refused_before_export(self):
        broken=[dict(x) for x in self.reels]
        broken[1]["start_tick"]+=TICKS_PER_SECOND
        with self.assertRaises(PermissionError):
            self.publish(reels=broken)
        with self.assertRaises(PermissionError):
            self.publish(reels=self.reels[::-1])
        self.assertEqual(list(self.output.iterdir()),[])

    def test_source_sha_mutation_and_duplicate_ids_refused(self):
        Path(self.reels[0]["picture"]["file_path"]).write_bytes(b"bad")
        with self.assertRaises(PermissionError):
            self.publish()
        self.assertFalse(list(self.output.iterdir()))
        # Also reject duplicate asset identities even if the bytes agree.
        with self.assertRaises(PermissionError):
            self.publish(reels=[self.reels[0],self.reels[0]])

    def test_cancel_keeps_nonpublished_partial_stage_for_review(self):
        calls=[0]
        def stop():
            calls[0]+=1
            return calls[0]>2
        with self.assertRaises(InterruptedError):
            self.publish(check_cancel=stop)
        self.assertTrue((self.output/(
            ".nvp-feature-stage-"+self.ids["cpl"])).is_dir())
        self.assertFalse((self.output/(
            "DCP_FEATURE_"+self.ids["cpl"])).exists())
        with self.assertRaises(FileExistsError):
            self.publish()


    def test_export_denial_and_cross_take_track_refused(self):
        result=self.publish(approve=lambda _:False)
        self.assertEqual(result["status"],"DENIED")
        self.assertEqual(list(self.output.iterdir()),[])
        self.reels[1]["sound"]["source_take_sha256"]="c"*64
        with self.assertRaises(PermissionError):
            self.publish()
        self.assertEqual(list(self.output.iterdir()),[])


if __name__=="__main__":
    unittest.main()
