"""01R: only source-reviewed Cycles jobs may exceed the normal 600s cap."""
from pathlib import Path
import sys
import tempfile
import unittest

from backend.nvp_blender_worker import BlenderOperation,BlenderWorkerSupervisor,sha_file
from backend.nvp_usd_film01r_quality import (
    reviewed_quality,quality_hash)
from backend.nvp_usd_film01o_original_camera_roll_source import canonical

REQUIRED=[
    "source.usda","source.json","chunk.json","plan.json",
    "nvp_usd_film01r_quality.py",
    "nvp_usd_film01m_camera_ray_mask.py"]


class ReviewedLongFilmWorkerAdmission(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nvp-01r-cycles-timeout-")
        self.root=Path(self.temp.name)
        self.supervisor=BlenderWorkerSupervisor(
            self.root,blender_executable=sys.executable,
            blender_sha256=sha_file(sys.executable),
            blender_version="Blender 5.2.3")
    def tearDown(self):
        self.temp.cleanup()

    def prepare(self,profile_name,*,job_id="FilmLong",script_name=
                "nvp_usd_film01q_blender_selected_views.py",
                fake_profile_sha=False,mem_override=None):
        job=self.root/job_id
        job.mkdir(exist_ok=True)
        (job/script_name).write_text("# fixed test reviewed worker\n","utf8")
        profile=reviewed_quality(profile_name)
        plan={
            "render_profile":profile,
            "render_profile_sha256":(
                "f"*64 if fake_profile_sha else quality_hash(profile))}
        for name in REQUIRED:
            data=canonical(plan) if name=="plan.json" else b"fixed native input"
            (job/name).write_bytes(data)
        return BlenderOperation(
            job_id=job_id,script=script_name,
            script_sha256=sha_file(job/script_name),
            inputs={name:sha_file(job/name) for name in REQUIRED},
            outputs={"frame_0000.png":"png"},
            arguments={"--manifest":"chunk.json"},
            timeout_seconds=profile["timeout_seconds"],
            memory_limit_mb=mem_override or profile["max_worker_ram_mb"])

    def test_trusted_selected_source_720p_job_admitted_without_execution(self):
        op=self.prepare("final_720p")
        result=self.supervisor._validate(op)
        self.assertEqual(result[0],self.root/"FilmLong")
        self.assertEqual(op.timeout_seconds,1800)
        self.assertEqual(op.memory_limit_mb,6144)

    def test_normal_blender_worker_must_keep_original_600s_limit(self):
        op=self.prepare("final_720p",script_name="unrelated_worker.py")
        with self.assertRaises(PermissionError):
            self.supervisor._validate(op)

    def test_fake_profile_or_memory_override_denied(self):
        op=self.prepare("final_720p",fake_profile_sha=True)
        with self.assertRaises(PermissionError):
            self.supervisor._validate(op)
        op=self.prepare("final_720p",job_id="BadRAM",mem_override=4096)
        with self.assertRaises(PermissionError):
            self.supervisor._validate(op)

    def test_technical_smoke_remains_bounded_below_600(self):
        op=self.prepare("technical_smoke")
        self.assertEqual(op.timeout_seconds,600)
        self.supervisor._validate(op)

if __name__=="__main__":
    unittest.main()
