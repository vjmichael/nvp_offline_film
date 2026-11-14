"""CONV-11 production proof denials, not physical Blender acceptance.

Source-only PCM/PNG fixtures must never authorize a protected reel.
A forged JSON with impressive-looking SHA strings cannot replace the
original independently reopened BlenderWorkerSupervisor job journal.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from backend.nvp_int02_cycles_renderer import NativeCyclesOriginalRenderer
from backend.nvp_p2_bounded_film_reel import NativeFilmReelBatch
from backend.nvp_p2_longform_source_plan import NativeLongformFilmPlan


class OriginalProductionReceiptDenials(unittest.TestCase):
    def test_protected_bounded_reel_requires_independent_native_journal_verifier(self):
        fake_planner=object.__new__(NativeLongformFilmPlan)
        with self.assertRaisesRegex(PermissionError,"native journal"):
            NativeFilmReelBatch(
                fake_planner,native_creator_approval=lambda *_:True,
                render_png=lambda **_:b"png",require_protected_worker=True)

    def test_protected_renderer_refuses_receipt_without_original_job_directory(self):
        with TemporaryDirectory() as tmp:
            renderer=object.__new__(NativeCyclesOriginalRenderer)
            renderer.project_id="OriginalFilmProject"
            renderer.supervisor=SimpleNamespace(
                root=Path(tmp),
                verify_completed=lambda job: {
                    "state":"SUCCEEDED","spec_sha256":"a"*64})
            renderer.require_encrypted_scratch=False
            renderer.script_sha="b"*64
            forged={
                "format":"nvp.int02.real_native_cycles_frame_receipt.v1",
                "project_id":"OriginalFilmProject",
                "chunk_id":"OriginalFiniteChunk",
                "approved_plan_sha256":"c"*64,
                "source_take_sha256":"d"*64,
                "source_shot_sha256":None,
                "source_tick":"0",
                "camera_path":"/World/Camera",
                "job_id":"int02_"+"1"*40,
                "job_spec_sha256":"a"*64,
                "png_sha256":"e"*64,
                "audit_sha256":"f"*64,
                "native_cycles_render_verified":True,
                "private_worker_required":True,
                "independent_blend_reopen_verified":False,
                "film_master_approved":False,
            }
            with self.assertRaisesRegex(RuntimeError,"journal folder missing"):
                renderer.verify_native_worker_receipt(forged)
            forged["job_id"]="unsupervised_blender"
            with self.assertRaises(PermissionError):
                renderer.verify_native_worker_receipt(forged)

    def test_protected_reel_rejects_noncallable_receipt_verifier(self):
        fake_planner=object.__new__(NativeLongformFilmPlan)
        with self.assertRaises(TypeError):
            NativeFilmReelBatch(
                fake_planner,native_creator_approval=lambda *_:True,
                render_png=lambda **_:b"png",require_protected_worker=True,
                native_worker_verifier=True)


if __name__ == "__main__":
    unittest.main()
