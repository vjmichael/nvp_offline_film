"""Actual Windows Job Blender/Cycles test: reviewed OpenUSD UV/PBR material source.

PUBLIC synthetic original UV-mapped set only, not confidential private film,
not an installed user job. Native production SCM/cgroup authorization remains
an independently accepted boundary.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image
from backend.nvp_blender_worker import (
    BlenderWorkerSupervisor,BlenderOperation,sha_file)
from test_nvp_p1f_reviewed_pbr_materials_native import ReviewedNativePBRMaterials


@unittest.skipUnless(sys.platform=="win32" and
                     os.environ.get("NVP_PUBLIC_SYNTHETIC_CI")=="1" and
                     os.environ.get("NVP_TEST_BLENDER"),
                     "Only the explicitly public reviewed material Windows native worker fixture")
class NativeReviewMaterialCycles(unittest.TestCase):
    def test_actual_original_uv_png_material_cycles_and_restart(self):
        exe=Path(os.environ["NVP_TEST_BLENDER"]).resolve()
        self.assertTrue(exe.is_file())
        version=subprocess.run(
            [str(exe),"-b","--version"],capture_output=True,
            text=True,timeout=30,check=True).stdout.splitlines()[0]
        self.assertTrue(version.startswith("Blender "))
        fixture=ReviewedNativePBRMaterials(
            "test_genuine_usd_uv_and_four_png_rights_review_survives_restart")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.import_location()
        fixture.publish()
        environment,_=fixture.assets.open(fixture.pid,"original_set",1)
        material=fixture.materials.open(fixture.pid,"original_brick")
        doc=material["data"]
        with tempfile.TemporaryDirectory(prefix="nvp-p1f-pbr-cycles-") as temp:
            root=Path(temp)/"supervisor"
            worker=BlenderWorkerSupervisor(
                root,blender_executable=exe,
                blender_sha256=sha_file(exe),blender_version=version)
            job="public_uv_pbr_original_0"
            directory=root/job
            directory.mkdir()
            source=fixture.index.get_blob(
                fixture.pid,environment["data"]["layer_sha256"])
            script=(Path(__file__).resolve().parents[1]/
                    "tools"/"nvp_p1f_pbr_environment_worker.py")
            sources={
                "fixed_pbr_worker.py":script.read_bytes(),
                "original_location.usda":source,
            }
            for slot in doc["textures"]:
                sources["map_"+slot+".png"]=fixture.materials.original_texture_bytes(
                    fixture.pid,"original_brick",slot)
            manifest={
                "format":"nvp.p1f.fixed.reviewed_uv_pbr_cycles_preview.v1",
                "original_environment_sha256":sha256(source).hexdigest(),
                "environment_document_sha256":environment["document_sha256"],
                "material_set_document_sha256":material["document_sha256"],
                "material_path":doc["material_path"],"bindings":doc["bindings"],
                "images":doc["textures"],
                "width":320,"height":180,"samples":8,
            }
            sources["material_plan.json"]=json.dumps(
                manifest,sort_keys=True,separators=(",",":")).encode("ascii")
            for filename,original in sources.items():
                with (directory/filename).open("xb") as out:
                    out.write(original)
            operation=BlenderOperation(
                job_id=job,script="fixed_pbr_worker.py",
                script_sha256=sha256(sources["fixed_pbr_worker.py"]).hexdigest(),
                inputs={name:sha256(raw).hexdigest()
                        for name,raw in sources.items()
                        if name!="fixed_pbr_worker.py"},
                outputs={
                    "material_preview.png":"png",
                    "material_audit.json":"json_audit",
                },
                arguments={
                    "--plan":"material_plan.json",
                    "--take":"original_location.usda",
                    "--output":"material_preview.png",
                    "--audit":"material_audit.json",
                },
                timeout_seconds=240,memory_limit_mb=4096,
                require_linux_cgroup_v2=False,
                require_private_isolation=False)
            result=worker.run(operation)
            if result["state"]!="SUCCEEDED":
                stderr=(directory/"worker_stderr.log")
                details=stderr.read_text("utf8",errors="replace")[-10000:] if stderr.exists() else ""
                self.fail("Actual reviewed UV/PBR Cycles preview failed: "+
                          repr(result)+"\n"+details)
            self.assertEqual(worker.verify_completed(job)["state"],"SUCCEEDED")
            audit=json.loads((directory/"material_audit.json").read_text("ascii"))
            self.assertTrue(audit["passed"])
            self.assertEqual(audit["render_engine"],"CYCLES")
            self.assertEqual(audit["material_set_document_sha256"],
                             material["document_sha256"])
            self.assertEqual(audit["source_environment_sha256"],
                             sha256(source).hexdigest())
            self.assertEqual(audit["source_material_path"],
                             "/Asset/Looks/Brick")
            self.assertEqual(audit["actual_imported_uv_meshes"],["Wall"])
            self.assertEqual(set(audit["actual_pbr_channels"]),set(fixture.maps))
            for name,info in audit["actual_pbr_channels"].items():
                self.assertEqual(info["sha256"],doc["textures"][name]["sha256"])
            preview=directory/"material_preview.png"
            self.assertEqual(sha_file(preview),audit["png_sha256"])
            with Image.open(preview) as image:
                image.load()
                self.assertEqual(image.format,"PNG")
                self.assertEqual(image.size,(320,180))
                self.assertTrue(any(hi>lo for lo,hi in
                                    image.convert("RGB").getextrema()))
            restarted=BlenderWorkerSupervisor(
                root,blender_executable=exe,
                blender_sha256=sha_file(exe),blender_version=version)
            self.assertEqual(restarted.verify_completed(job)["state"],"SUCCEEDED")
            with self.assertRaisesRegex(RuntimeError,"already registered"):
                restarted.run(operation)
            self.assertEqual(fixture.materials.open(
                fixture.pid,"original_brick")["document_sha256"],
                material["document_sha256"])


if __name__=="__main__":
    unittest.main()
