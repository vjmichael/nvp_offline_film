"""FILM02-02 source/worker contract tests, NOT an actual 720-frame render."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_blender_worker import BlenderWorkerSupervisor, sha_file
from tools.nvp_film01_original_30s import write_original_30s_source
from tools.nvp_film02_blender_handoff import build_handoff
from tools.nvp_film02_blender_cycles_acceptance import (
    BATCH, PACKET_FORMAT, OUT_FIELDS, _digest, source_packet,
    stage_chunk, validate_packet, run_original_shot,
)


class Original30sSupervisedCyclesSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.source = cls.root / "original"
        write_original_30s_source(cls.source, approve_test_only=True)
        cls.plan = build_handoff(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_three_shots_are_chunks_of_same_immutable_original_edit(self):
        self.assertEqual(len(self.plan["frames"]), 720)
        packets = []
        for shot in range(3):
            for start in range(240 * shot, 240 * (shot + 1), BATCH):
                packet = source_packet(self.plan, shot, start, start + BATCH)
                self.assertEqual(packet["format"], PACKET_FORMAT)
                original = validate_packet(self.plan, packet)
                self.assertEqual(original["first_frame"], start)
                self.assertEqual(original["stop_frame"], start + BATCH)
                self.assertEqual(len(original["frames"]), BATCH)
                self.assertEqual(original["parent_manifest_sha256"],
                                 self.plan["manifest_sha256"])
                self.assertEqual(original["source_edit_sha256"],
                                 self.plan["source_edit_sha256"])
                self.assertEqual(original["take_sha256"],
                                 self.plan["shots"][shot]["take_sha256"])
                packets.append(packet)
        self.assertEqual(len(packets), 30)
        self.assertEqual(len(set(p["source_sha256"] for p in packets)), 30)
        self.assertEqual(sorted({p["source"]["shot_number"] for p in packets}),
                         [0, 1, 2])
        self.assertEqual([packets[k]["source"]["first_frame"]
                          for k in (0, 10, 20)], [0, 240, 480])
        self.assertEqual([packets[k]["source"]["stop_frame"]
                          for k in (9, 19, 29)], [240, 480, 720])

    def test_reject_cross_cut_tampering_even_with_matching_recomputed_digest(self):
        with self.assertRaises(ValueError):
            source_packet(self.plan, 0, 238, 242)
        with self.assertRaises(ValueError):
            source_packet(self.plan, 1, 239, 241)
        for alter in (
            lambda obj: obj["source"].__setitem__("shot_number", 2),
            lambda obj: obj["source"]["frames"][0].__setitem__(
                "source_film_tick", "999"),
            lambda obj: obj["source"]["assets"]["EngineerDonut"].__setitem__(
                "source_document_sha256", "0"*64),
            lambda obj: obj["source"].__setitem__(
                "creator_approved_for_release", True),
        ):
            packet = deepcopy(source_packet(self.plan, 0, 0, 24))
            alter(packet)
            packet["source_sha256"] = _digest(packet["source"])
            with self.assertRaises((PermissionError, ValueError)):
                validate_packet(self.plan, packet)

    def test_reuses_existing_sha_pinned_BlenderOperation_never_executes(self):
        executable = Path(__file__).resolve()
        worker = BlenderWorkerSupervisor(
            self.root / "worker-only",
            blender_executable=executable,
            blender_sha256=sha_file(executable),
            blender_version="Blender Contract-Test-Only")
        op, packet, job, resumed = stage_chunk(
            self.plan, worker, 2, 480, 504)
        self.assertFalse(resumed)
        self.assertEqual(op.outputs, OUT_FIELDS)
        self.assertEqual(op.arguments["--out"], "frames")
        self.assertEqual(op.arguments["--manifest"], "source.json")
        self.assertEqual(op.timeout_seconds, 600)
        self.assertEqual(op.memory_limit_mb, 3072)
        self.assertTrue((job / "trusted_film02_cycles.py").is_file())
        self.assertEqual(sha_file(job / "trusted_film02_cycles.py"),
                         op.script_sha256)
        self.assertTrue((job / "source.json").is_file())
        self.assertFalse((job / "scene.blend").exists())
        self.assertFalse((job / "audit.json").exists())
        new, same, folder, resumed = stage_chunk(
            self.plan, worker, 2, 480, 504)
        self.assertTrue(resumed)
        self.assertEqual(new.canonical(), op.canonical())
        self.assertEqual(packet, same)
        self.assertEqual(job, folder)
        with self.assertRaises(PermissionError):
            run_original_shot(self.source, self.root / "missing-manifest",
                              self.root / "disallowed", executable,
                              shot_no=0, ci_test_consent=False)

    def test_worker_is_an_externally_licensed_reviewed_Blender_only_script(self):
        trusted = Path(__file__).resolve().parents[1] / "tools" / "nvp_film02_blender_cycles_worker.py"
        script = trusted.read_text("utf8")
        self.assertIn("SPDX-License-Identifier: GPL-2.0-or-later", script)
        self.assertIn("import bpy", script)
        for forbidden in ("import subprocess", "import requests", "import socket",
                          "from backend.", "from tools.", "os.system(", "eval(",
                          "exec("):
            self.assertNotIn(forbidden, script)
        compile(script, str(trusted), "exec")


if __name__ == "__main__":
    unittest.main()
