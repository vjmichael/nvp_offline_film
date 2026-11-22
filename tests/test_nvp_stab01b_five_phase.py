"""NVP-STAB-01B: original, persisted G04->G08 source-to-movie acceptance.

This exercises real OpenUSD, immutable Take/PCM, the fixed native G08 worker,
independent AVI verification, and durable SQLite state. PCM bytes are a clearly
identified deterministic TEST FIXTURE, not evidence of a hardware microphone.
A test unlock is not native UI consent. No LTX/model or physical installer
acceptance is asserted by this suite.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import tempfile
import time
import unittest
import uuid

from backend.nvp_studio import Studio
from backend.nvp_g04_preproduction import G04Preproduction, NOTE_FIELDS
from backend.nvp_g05_scene_authoring import G05SceneAuthoring
from backend.nvp_g06_filming import G06Filming
from backend.nvp_g07_edit import G07Editor
from backend.nvp_g08_export import G08MovieExporter
from backend.nvp_g03_live_store import LiveFilmStore
from backend.nvp_project_access import ProjectAccess


class OriginalFivePhaseNativeAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nvp-stab01b-native-")
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "nvp_studio.sqlite3"
        self.studio = Studio(self.db)
        self.access = ProjectAccess(self.db)
        self.sealed = LiveFilmStore(Path(self.tmp.name) / "sealed")
        self.exporter = G08MovieExporter(
            self.studio, access=lambda: self.access,
            protected_movie=lambda: self.sealed)

    def wait_for(self, pid, job_id, token, terminal, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.exporter.read(pid, job_id, token)
            if state["status"] in {"completed", "cancelled", "failed", "interrupted"}:
                # The production host deliberately redacts worker failures.
                # Retain ONLY the worker exception class in this CI assertion
                # so a native failure can be diagnosed before test cleanup;
                # never echo original source paths, screenplay or PCM.
                worker_classes = []
                if state["status"] != terminal:
                    folder = self.db.parent / "nvp_g08_exports" / pid
                    for action in ("render", "verify"):
                        log = folder / (job_id + "." + action + ".log")
                        if log.is_file() and not log.is_symlink():
                            for line in log.read_text(
                                    encoding="utf8", errors="replace").splitlines():
                                prefix = "NVP native export did not complete: "
                                if line.startswith(prefix):
                                    worker_classes.append(
                                        action + ":" + line[len(prefix):][:64])
                # Test-only failure reproduction: the released worker intentionally
                # redacts exception messages. Capture only checked-in Python
                # basename/function/line numbers, never source path or content.
                # Do not change the renderer or production worker before a
                # concrete failing callsite is available.
                reproduction = "not-attempted"
                if state["status"] == "failed" and terminal == "completed":
                    import io
                    import traceback
                    from backend.nvp_g08_native_avi import render_film
                    try:
                        actual = G07Editor(Studio(self.db)).native_assembly(
                            pid, state["edit_revision"])
                        render_film(actual, io.BytesIO())
                        reproduction = "in-process-render-passed; investigate-child-only-path"
                    except BaseException as exc:
                        calls = []
                        for frame in traceback.extract_tb(exc.__traceback__):
                            basename = Path(frame.filename).name
                            if basename.startswith("nvp_") or basename == "test_nvp_stab01b_five_phase.py":
                                calls.append(f"{basename}:{frame.name}:{frame.lineno}")
                        reproduction = {
                            "exception_class": type(exc).__name__,
                            "source_callsites": calls[-8:],
                        }
                self.assertEqual(state["status"], terminal, {
                    "job": state,
                    "native_worker_exception_classes": worker_classes,
                    "safe_in_process_render_diagnostic": reproduction})
                return state
            time.sleep(0.2)
        self.fail("Original native export did not reach a terminal state")

    def test_one_original_movie_with_approval_rejection_cancel_reopen_and_export(self):
        # 1. Script OPTIONAL: one real persisted, idea-led film project.
        created = self.studio.create_project(
            "One Original Valley", "ROCIO studies the valley at dawn.")
        pid = created["id"]
        self.assertEqual(created["screenplay"], "")
        g04 = G04Preproduction(self.studio)
        start = g04.view(pid)
        self.assertEqual(start["mode"], "idea")
        self.assertEqual(len(start["scenes"]), 1)
        scene_id = start["scenes"][0]["id"]
        notes = {name: "" for name in NOTE_FIELDS}
        notes.update(location="Valley meadow", time_of_day="dawn",
                     weather="clear", performers="ROCIO",
                     action="ROCIO walks toward a small greenhouse.")
        planned = g04.save_scene(pid, scene_id, notes, 0, 0)
        scene = planned["scenes"][0]
        source_sha = scene["source_sha256"]
        actor_id = scene["cast"][0]["actor_id"]
        self.assertTrue(actor_id.startswith("ACT_"))

        # 2. Set Up Scenes: draft cannot authorize filming; creator approval
        # publishes a different, independently reopenable OpenUSD revision.
        g05 = G05SceneAuthoring(self.studio)
        draft = g05.generate(pid, scene_id, 0)
        self.assertEqual(draft["status"], "draft")
        g06 = G06Filming(self.studio)
        with self.assertRaises(RuntimeError):
            g06.freeze_take(pid, scene_id, 0)
        approved = g05.approve(pid, scene_id, draft["revision"])
        self.assertEqual(approved["status"], "approved")
        stage = g05.native_stage(pid, scene_id)
        self.assertEqual(stage["source_sha256"], source_sha)
        self.assertEqual(sha256(stage["usd_bytes"]).hexdigest(), stage["usd_sha256"])
        self.assertTrue(any(o["actor_id"] == actor_id for o in approved["objects"]))

        # 3. Film Scenes: the trusted-host PCM ingress stores actual bytes.
        # This sample fixture is NOT captured by a real ADC/microphone.
        performance = g06.set_duration(pid, scene_id, "5", 0)
        pcm = bytes.fromhex("2000") * 4800   # 0.1 s, 48 kHz PCM16LE mono
        recorded = g06.record_native_audio(pid, scene_id, actor_id, pcm)
        take = g06.freeze_take(pid, scene_id, performance["work_revision"],
                               (recorded["clip_id"],))
        self.assertTrue(take["frozen"])
        original_take_sha = take["digest"]

        # Reconstruct from the real on-disk DB, not retained Python objects.
        restarted = Studio(self.db)
        native = G06Filming(restarted).native_take(pid, take["take_id"])
        self.assertEqual(native["take_sha256"], original_take_sha)
        self.assertEqual(native["original_scene_sha256"], stage["usd_sha256"])
        self.assertEqual(native["original_audio"][0]["clip_id"], recorded["clip_id"])
        self.assertEqual(native["original_audio"][0]["emitter_actor_id"], actor_id)
        self.assertEqual(native["original_audio"][0]["pcm16le"], pcm)
        self.assertEqual(native["original_audio"][0]["pcm_sha256"], sha256(pcm).hexdigest())
        self.assertEqual(G04Preproduction(restarted).view(pid)["scenes"][0]["source_sha256"],
                         source_sha)

        # 4. Edit Film: actual source-referenced EDL, stale revision rejected.
        editor = G07Editor(restarted)
        appended = editor.mutate(pid, 0, "append", {"take_id": take["take_id"]})
        self.assertEqual(appended["clips"][0]["take_sha256"], original_take_sha)
        clip_id = appended["clips"][0]["id"]
        with self.assertRaises(RuntimeError):
            editor.mutate(pid, 0, "note", {"clip_id": clip_id, "note": "stale"})
        self.assertEqual(editor.view(pid)["revision"], appended["revision"])

        # 5. Export Film: native host authorization is tested, not assumed.
        self.access.protect(pid, "fixture-only-director-passphrase")
        with self.assertRaises(PermissionError):
            self.access.unlock(pid, "wrong-fixture-director-passphrase")
        token = self.access.unlock(pid, "fixture-only-director-passphrase")
        with self.assertRaises(PermissionError):
            self.exporter.prepare(pid, appended["revision"], "wrong-host-token")

        # Exercise genuine cancellation on a 5-second native export before
        # making the final shorter edit. No mocked worker or fake receipt.
        cancelling = self.exporter.prepare(pid, appended["revision"], token)
        cancelled = self.exporter.cancel(pid, cancelling["id"], token)
        self.assertEqual(cancelled["status"], "cancelled")
        self.wait_for(pid, cancelling["id"], token, "cancelled")

        trimmed = editor.mutate(pid, appended["revision"], "trim", {
            "clip_id": clip_id, "in_seconds": "0", "out_seconds": "1"})
        self.assertEqual(trimmed["duration_seconds"], 1.0)
        self.assertEqual(trimmed["clips"][0]["take_sha256"], original_take_sha)

        # A separate host object sees the authoritative newly saved edit.
        self.assertEqual(G07Editor(Studio(self.db)).view(pid)["revision"],
                         trimmed["revision"])
        assembly = editor.native_assembly(pid, trimmed["revision"])
        self.assertEqual(assembly["edit_revision"], trimmed["revision"])
        self.assertEqual(assembly["all_source_take_count"], 1)
        self.assertEqual(assembly["original_takes"][take["take_id"]]["take_sha256"],
                         original_take_sha)
        self.assertEqual(assembly["original_takes"][take["take_id"]]["audio"][0]["pcm_sha256"],
                         sha256(pcm).hexdigest())

        job = self.exporter.prepare(pid, trimmed["revision"], token)
        result = self.wait_for(pid, job["id"], token, "completed")
        self.assertTrue(result["verified"])
        self.assertEqual(result["frames_total"], 24)
        self.assertTrue(result["sound_quality"]["actual_pcm_verified"])
        delivered = self.exporter.movie_path(pid, job["id"], token)
        raw = delivered.read_bytes()
        self.assertTrue(raw.startswith(b"RIFF"))
        self.assertIn(b"AVI ", raw[:16])
        self.assertEqual(sha256(raw).hexdigest(), result["output_sha256"])
        self.assertEqual(result["edit_revision"], trimmed["revision"])

        # Original Take/PCM and the successfully verified film survive reopen.
        after = G06Filming(Studio(self.db)).native_take(pid, take["take_id"])
        self.assertEqual(after["take_sha256"], original_take_sha)
        self.assertEqual(after["original_audio"][0]["pcm16le"], pcm)
        self.assertEqual(G08MovieExporter(
            Studio(self.db), access=lambda: self.access,
            protected_movie=lambda: self.sealed).movie_path(pid, job["id"], token),
            delivered)

        # Durable journal crash-state reconciliation, distinct from a real
        # machine hard-kill (which requires the separate OS acceptance).
        interrupted_id = uuid.uuid4().hex
        with self.studio._connection() as db:
            db.execute("""INSERT INTO g08_export_jobs
                (id,project_id,edit_revision,edit_sha256,look_sha256,
                 actors_sha256,acoustics_sha256,finishing_sha256,
                 expected_frames,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,'queued',datetime('now'),datetime('now'))""",
                (interrupted_id,pid,trimmed["revision"],
                 assembly["edit_document_sha256"],
                 assembly["production_looks_sha256"],
                 assembly["actor_performances_sha256"],
                 assembly["acoustic_looks_sha256"],
                 assembly["finishing_sha256"],24))
        reopened_exporter = G08MovieExporter(
            Studio(self.db), access=lambda: self.access,
            protected_movie=lambda: self.sealed)
        reopened_exporter.reconcile()
        state = reopened_exporter.read(pid, interrupted_id, token)
        self.assertEqual(state["status"], "interrupted")
        self.assertFalse(state["verified"])
        self.assertIsNone(state["download_url"])
        self.assertEqual(sha256(delivered.read_bytes()).hexdigest(),
                         result["output_sha256"])


if __name__ == "__main__":
    unittest.main()
