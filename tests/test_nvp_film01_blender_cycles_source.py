"""NVP FILM01: prove original OpenUSD donut/cube/sphere -> Blender source custody.

These are *pre-render* negative/source tests and must never be misreported
as genuine Blender shadow/reflection evidence. A separate native Blender
5.2 Cycles workflow executes the process and decodes the real images.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor,sha_file
from backend.nvp_film_index import FilmIndex
from tools.nvp_film01_donut_light_probe import build_frozen_donut_source
from tools.nvp_film01_blender_cycles_acceptance import (
    original_take_manifest,stage_original_cycles_worker,_json,
    FORMAT,BATCH_FRAMES)


class BlenderFrozenObjectActorSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory()
        cls.root=Path(cls.tmp.name).resolve()
        cls.source=build_frozen_donut_source(cls.root/"real_frozen_original_take")
        cls.body=original_take_manifest(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_source_is_exact_frozen_3_actor_openusd_from_FilmIndex(self):
        m=self.body
        self.assertEqual(m["format"],FORMAT)
        self.assertEqual(m["source_take_sha256"],
                         self.source["take_sha256"])
        self.assertEqual(m["scene_sha256"],self.source["scene_sha256"])
        self.assertEqual(m["torus_mesh_sha256"],
                         self.source["torus_source_mesh_sha256"])
        self.assertEqual(len(m["donut_vertices"]),504)
        self.assertEqual(len(m["donut_triangles"]),1008)
        self.assertEqual(m["original_actor_roles"],{
            "donut":"actor","box":"actor","sphere":"actor"})
        self.assertEqual(len(m["frames"]),BATCH_FRAMES)
        self.assertEqual(m["frame_rate"],24)
        for i,f in enumerate(m["frames"]):
            self.assertEqual(f["frame_zero"],i)
            self.assertEqual(f["film_tick"],str(294000000*i))
            self.assertEqual(set(f["actors"]),{"donut","box","sphere"})
            self.assertEqual(f["actors"]["sphere"][:2],[0.,0.])
            self.assertAlmostEqual(f["actors"]["box"][2],-2.2)
            self.assertGreater(len(f["frozen_scene_snapshot_sha256"]),60)
        self.assertLess(m["frames"][0]["actors"]["box"][0],-2)
        self.assertAlmostEqual(m["frames"][24]["actors"]["box"][0],0,places=3)
        self.assertGreater(m["frames"][48]["actors"]["box"][0],2)
        self.assertLess(m["frames"][0]["actors"]["sphere"][2],-3)
        self.assertGreater(m["frames"][48]["actors"]["sphere"][2],0)
        self.assertEqual(
            self.source["index"].read_revision(
                self.source["project_id"],"DonutLightingTake",1)[
                    "document_sha256"],
            m["source_take_sha256"])

    def test_typed_blender_stage_uses_original_digest_and_fixed_first_party_script(self):
        worker=BlenderWorkerSupervisor(
            self.root/"staged_native_worker_only",
            # An inert preflight *test* binary path is sufficient for
            # staging but NEVER invoked or represented as real Blender.
            blender_executable=Path(__file__).resolve(),
            blender_sha256=sha_file(Path(__file__).resolve()),
            blender_version="Blender Preflight-Only-Test")
        op,packet,job=stage_original_cycles_worker(
            self.source,worker,memory_mb=3072)
        self.assertEqual(packet["source_sha256"],
                         sha256(_json(self.body)).hexdigest())
        self.assertEqual(packet["source"],self.body)
        self.assertEqual(op.outputs,{
            "scene.blend":"blend","audit.json":"json_audit",
            "neutral_024.png":"png","silver_024.png":"png",
            "gold_024.png":"png","fixed_summer_3pm_024.png":"png"})
        self.assertEqual(op.arguments["--manifest"],"source.json")
        self.assertEqual(op.arguments["--out"],"frames")
        self.assertEqual(op.memory_limit_mb,3072)
        self.assertEqual(op.timeout_seconds,600)
        self.assertTrue((job/"source.json").is_file())
        self.assertEqual(sha_file(job/"trusted_cycles_donut.py"),
                         op.script_sha256)
        self.assertFalse((job/"scene.blend").exists())
        self.assertFalse((job/"audit.json").exists())
        self.assertFalse((job/"frames").exists())
        with self.assertRaises(FileExistsError):
            stage_original_cycles_worker(self.source,worker,memory_mb=3072)

    def test_frozen_take_manifest_rejects_non_authoritative_mesh_source(self):
        old=self.source["geometry"]["mesh_points"][3][0]
        self.source["geometry"]["mesh_points"][3][0]=old+.1
        try:
            with self.assertRaises((PermissionError,RuntimeError)):
                original_take_manifest(self.source)
        finally:
            self.source["geometry"]["mesh_points"][3][0]=old


if __name__=="__main__":
    unittest.main()
