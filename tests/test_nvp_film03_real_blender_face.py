"""FILM03-09D.3 actual Blender process render of ORIGINAL native USD actor.

Run only with NVP_FILM03_BLENDER_BIN explicitly set to an installed,
reviewed real Blender executable. Creates an original source USD rig,
composes a TEST-ONLY manually timed mouth/face overlay and independently
reopens the Blender scene. Never claims a genuine MFA speech result.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from pxr import Sdf, Usd, UsdSkel
import test_nvp_film03_facial_rig_compositor as original_fixture
from backend.nvp_blender_worker import (
    BlenderWorkerSupervisor, BlenderOperation, sha_file,
)
from backend.nvp_film03_actor_identity_core import canonical, digest
from backend.nvp_film03_facial_rig_compositor import compose_usd_facial_overlay
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

BLENDER_SCRIPT = Path(__file__).resolve().parents[1] / "tools" / \
    "nvp_film03_real_face_blender_worker.py"
REOPEN_SCRIPT = Path(__file__).resolve().parents[1] / "tools" / \
    "nvp_film03_real_face_blender_reopen.py"


class TrueNativeBlenderFacialRender(unittest.TestCase):
    def test_real_original_usd_actor_renders_and_reopens(self):
        env = os.environ.get("NVP_FILM03_BLENDER_BIN")
        if not env:
            self.skipTest("Dedicated native Blender execution workflow supplies real executable")
        binary = Path(env).resolve(strict=True)
        version = subprocess.run(
            [str(binary), "-b", "--version"],
            capture_output=True, text=True, check=True, timeout=25).stdout.splitlines()[0].strip()
        self.assertTrue(version.startswith("Blender 5.2."), version)
        # Native FilmIndex rig source is a real OpenUSD geometry fixture.
        fixture = original_fixture.RealActorFacialRigAcceptance(
            "test_actual_original_shape_geometry_and_blendshape_sources")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        indexed = fixture.index
        result = fixture.compile()
        self.assertTrue(result["real_native_usd_blendshape_layer_authored"])
        scene, original_stage = OpenUSDSceneBridge(indexed).open(
            fixture.pid, fixture.rig["source_scene_id"],
            fixture.rig["source_scene_revision"])
        overlay = Sdf.Layer.CreateAnonymous("nvp_real_test_face_overlay.usda")
        self.assertTrue(overlay.ImportFromString(
            result["usd_layer_bytes"].decode("utf8")))
        whole = Sdf.Layer.CreateAnonymous("nvp_real_test_face_composition.usda")
        whole.subLayerPaths = [
            overlay.identifier, original_stage.GetRootLayer().identifier]
        stage = Usd.Stage.Open(whole, Usd.Stage.LoadNone)
        stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
        animation = UsdSkel.Animation(
            stage.GetPrimAtPath(fixture.rig["animation_path"]))
        positions = [2000, 7000, 14000]
        weights = []
        for frame, pos in enumerate(positions, 1):
            sequence = animation.GetBlendShapeWeightsAttr().Get(
                Usd.TimeCode(float(pos * 147000)))
            self.assertIsNotNone(sequence)
            weights.append({
                "frame": frame, "pcm_sample": pos,
                "weights": dict(zip(
                    fixture.rig["shape_names"], [float(x) for x in sequence])),
            })
        self.assertNotEqual(weights[0]["weights"], weights[1]["weights"])
        with TemporaryDirectory(prefix="nvp-real-face-render-") as scratch:
            root = Path(scratch)
            store = Path(os.environ.get("NVP_FILM03_FACE_ARTIFACT_DIR",
                                      str(root / "visual-evidence"))).resolve()
            store.mkdir(parents=True, exist_ok=True)
            supervisor = BlenderWorkerSupervisor(
                root / "native-worker", blender_executable=binary,
                blender_sha256=sha_file(binary), blender_version=version)
            work = supervisor.root / "face_render_real"
            work.mkdir(mode=0o700)
            usd = work / "source.usda"
            self.assertTrue(stage.Export(str(usd)))
            source = {
                "project_id": fixture.pid,
                "actor_id": "f" * 32,  # Test-only scene actor marker, not film casting
                "voice_id": "TEST_ONLY_UNSELECTED_VOICE",
                "original_take_sha256": fixture.take["document_sha256"],
                "original_pcm_sha256": sha256(b"TEST_ONLY_NOT_SPEECH").hexdigest(),
                "source_facial_candidate_sha256": result["usd_layer_sha256"],
                "source_usd_sha256": sha_file(usd),
                "source_usd_file": "source.usda",
                "source_mesh_vertex_count": fixture.rig["skinned_vertex_count"],
                "actor_prim_path": fixture.rig["actor_prim_path"],
                "shape_names": fixture.rig["shape_names"],
                "samples": weights,
                "preview_camera_not_editorial": True,
            }
            packet = {
                "format": "nvp.film03.real_usd_face_blender_packet.v1",
                "source": source, "source_sha256": digest(source),
            }
            (work / "source.json").write_bytes(canonical(packet))
            (work / BLENDER_SCRIPT.name).write_bytes(BLENDER_SCRIPT.read_bytes())
            op = BlenderOperation(
                job_id=work.name, script=BLENDER_SCRIPT.name,
                script_sha256=sha_file(work / BLENDER_SCRIPT.name),
                inputs={
                    "source.usda": sha_file(usd),
                    "source.json": sha_file(work / "source.json"),
                },
                outputs={
                    "scene.blend": "blend", "audit.json": "json_audit",
                    "facial_at_1.png": "png", "facial_at_2.png": "png",
                    "facial_at_3.png": "png",
                },
                arguments={
                    "--manifest": "source.json", "--output": "scene.blend",
                    "--audit": "audit.json", "--preview": "facial_at_2.png",
                },
                memory_limit_mb=8192, timeout_seconds=600,
            )
            run = supervisor.run(op)
            self.assertEqual(run["state"], "SUCCEEDED", run)
            supervisor.verify_completed(work.name)
            proof = json.loads((work / "audit.json").read_text("utf8"))
            self.assertEqual(proof["source_usd_sha256"], source["source_usd_sha256"])
            self.assertEqual(proof["source_shape_samples"], weights)
            self.assertTrue(proof["real_original_usd_mesh_imported"])
            self.assertEqual(len(proof["preview_shas"]), 3)
            for image in ("facial_at_1.png", "facial_at_2.png", "facial_at_3.png"):
                self.assertEqual(sha_file(work / image), proof["preview_shas"][image])
            # Fresh, independent real Blender process must reopen and validate
            # its genuine imported USD mesh and the exact facial keyframes.
            reopen = supervisor.root / "face_render_reopen"
            reopen.mkdir(mode=0o700)
            shutil.copyfile(work / "scene.blend", reopen / "scene.blend")
            (reopen / REOPEN_SCRIPT.name).write_bytes(REOPEN_SCRIPT.read_bytes())
            (reopen / "source.json").write_bytes(canonical({
                "source": source,
                "source_blend_sha256": sha_file(reopen / "scene.blend"),
            }))
            proof_op = BlenderOperation(
                job_id=reopen.name, scene="scene.blend",
                script=REOPEN_SCRIPT.name,
                script_sha256=sha_file(reopen / REOPEN_SCRIPT.name),
                inputs={
                    "scene.blend": sha_file(reopen / "scene.blend"),
                    "source.json": sha_file(reopen / "source.json"),
                },
                outputs={"audit.json": "json_audit"},
                arguments={
                    "--manifest": "source.json", "--audit": "audit.json",
                },
                memory_limit_mb=8192, timeout_seconds=600,
            )
            second = supervisor.run(proof_op)
            self.assertEqual(second["state"], "SUCCEEDED", second)
            supervisor.verify_completed(reopen.name)
            reopened = json.loads((reopen / "audit.json").read_text("utf8"))
            self.assertTrue(reopened[
                "three_authored_mouth_face_poses_independently_reopened"])
            self.assertFalse(reopened["director_film_take_approved"])
            # Preserve real output and first-party evidence as visible CI
            # artifacts; not a selected NVP film Take.
            for file in ("scene.blend", "audit.json", "source.usda",
                         "facial_at_1.png", "facial_at_2.png", "facial_at_3.png"):
                shutil.copyfile(work / file, store / file)
            shutil.copyfile(reopen / "audit.json", store / "independent_reopen.json")
            (store / "review_status.json").write_text(json.dumps({
                "source": "Real original USD mesh, test-only phone timings",
                "blender_version": version,
                "real_usd_import": True,
                "real_cycles_renders": 3,
                "real_fresh_blender_reopen": True,
                "real_acoustic_model_executed": False,
                "human_audible_lipsync_accepted": False,
                "director_film_take_approved": False,
            }, indent=2), "utf8")


if __name__ == "__main__":
    unittest.main()
