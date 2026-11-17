"""CONV-12 genuine Windows protected 90 x 8 selected-view Cycles acceptance.

ONLY runs when the dedicated Windows workflow opts in. Uses actual native
OpenUSD source, OS EFS, an installed hash-pinned Blender executable, the
production AppContainer/SCM/Job-owned supervisor, and 720 real Cycles PNGs.
No patched worker, mock media, simulated successful receipts, or public-only
containment fallback is permitted. Director tokens are CI fixture approvals,
NOT evidence of a human creator approving a private real-world film.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from backend.nvp_blender_worker import BlenderOperation, BlenderWorkerSupervisor,sha_file
from backend.nvp_usd_film01m_director_camera_bank import DirectorCameraBank
from backend.nvp_usd_film01p_source_multicam_edl import even_camera_coverage_edl
from backend.nvp_usd_film01q_selected_view_edit import OriginalSelectedViewEdit
from backend.nvp_usd_film01q_selected_view_host import ReviewedSelectedViewFilm,chunk_job_id
from backend.nvp_w1g_encrypted_source import require_efs_stage,verify_efs_inputs
from backend.nvp_w1g_release_gate import inspect_original_process_journals
from backend.nvp_usd_film01o_original_camera_roll_source import STAGE,MANIFEST,file_sha

RUN_REAL = (
    sys.platform == "win32" and os.name == "nt"
    and os.environ.get("NVP_CONV12_REAL_PROTECTED_720") == "1"
    and bool(os.environ.get("NVP_CONV12_PINNED_BLENDER"))
)


@unittest.skipUnless(RUN_REAL,"Requires genuine Windows EFS/AppContainer and pinned Blender")
class RealProtectedSelected720Windows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_nvp_usd_film01i_ninecam_take import NineCameraOriginalFilmSource
        cls.fixture = NineCameraOriginalFilmSource
        cls.fixture.setUpClass()
        try:
            cls.index=cls.fixture.index
            cls.pid=cls.fixture.pid
            cls.bank_id="CONV12OriginalNineDirector"
            cls.edit_id="CONV12OriginalSelectedEdit"
            cls.take_id="OneThirtySecondWorldTake"
            binary=Path(os.environ["NVP_CONV12_PINNED_BLENDER"]).resolve(strict=True)
            if binary.is_symlink() or not binary.is_file() or binary.name.lower()!="blender.exe":
                raise PermissionError("A reviewed native Blender installation is mandatory")
            # Version query is performed before creating any derived film source.
            probe=subprocess.run([str(binary),"-b","--version"],
                capture_output=True,text=True,timeout=35,check=True)
            cls.version=probe.stdout.splitlines()[0]
            if not cls.version.startswith("Blender "):
                raise RuntimeError("Genuine installed Blender version unavailable")
            cls.binary=binary
            cls.binary_sha=sha_file(binary)
            cls.worker_root=cls.fixture.root/"conv12_windows_private_workers"
            cls.supervisor=BlenderWorkerSupervisor(
                cls.worker_root,blender_executable=binary,
                blender_sha256=cls.binary_sha,blender_version=cls.version)
            cls.bank=DirectorCameraBank(
                cls.index,verify_director_action=lambda event,scope:
                    event=="fixture-director-bank" and
                    scope["operation"]=="nvp.film.director_camera_bank_revision.v1")
            cls.edits=OriginalSelectedViewEdit(
                cls.index,verify_director_action=lambda event,scope:
                    event=="fixture-director-edit" and
                    scope["operation"]=="nvp.film01q.publish_selected_view_edit.v1")
            cls.bank.create_standard_nine_preset(
                cls.pid,cls.bank_id,
                original_nine_rig_id="OnePerformanceNineCamBank",
                director_event="fixture-director-bank")
            nine=cls.bank.verify(cls.pid,cls.bank_id,1)
            cls.cameras=[c["camera_id"] for c in nine["cameras"]]
            cls.edits.create(
                cls.pid,cls.edit_id,camera_bank_id=cls.bank_id,
                camera_bank_revision=1,
                cuts=even_camera_coverage_edl(cls.cameras),
                director_event="fixture-director-edit")
            cls.accepted_creative=set()
            cls.accepted_execution=set()
            cls.creative_scopes={}
            cls.execution_scopes={}
            cls.host=ReviewedSelectedViewFilm(
                cls.index,cls.supervisor,
                verify_director_action=cls._approve_director,
                verify_native_execution=cls._approve_execution,
                prove_process_custody=cls._independent_recovery,
                render_quality="technical_smoke")
            cls.take_sha=cls.index.read_revision(cls.pid,cls.take_id,1)["document_sha256"]
        except BaseException:
            cls.fixture.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"fixture"):
            cls.fixture.tearDownClass()

    @classmethod
    def _approve_director(cls,event,scope):
        operation=scope.get("operation")
        if operation=="nvp.film01q.export_verified_source_selected_picture.v1":
            if event!="fixture-director-export-after-720-native-frames":
                return False
            if event in cls.accepted_creative:
                return False
            cls.accepted_creative.add(event)
            return (scope.get("native_verified_frames")==720
                    and scope.get("native_verified_chunks")==90)
        if operation!="nvp.render.usd_film01q_selected_source_chunk.v1":
            return False
        start,attempt=scope["start_frame"],scope["attempt"]
        expected=f"fixture-director-{start:04d}-attempt-{attempt}"
        if (event!=expected or event in cls.accepted_creative or
                scope.get("frame_count")!=8 or
                scope.get("native_worker_job_id") is None):
            return False
        cls.accepted_creative.add(event)
        cls.creative_scopes[(start,attempt)]=dict(scope)
        return True

    @classmethod
    def _approve_execution(cls,event,scope):
        if scope.get("operation")!="nvp.worker.usd_film01q_native_cycles_execution.v1":
            return False
        start,attempt=scope["start_frame"],scope["attempt"]
        expected=f"fixture-native-execution-{start:04d}-attempt-{attempt}"
        if (event!=expected or event in cls.accepted_execution or
                event in cls.accepted_creative or
                scope.get("frame_count")!=8 or
                scope.get("requires_kernel_private_isolation") is not True or
                scope.get("requires_strict_process_tree_custody") is not True or
                scope.get("require_encrypted_source_storage") is not True):
            return False
        cls.accepted_execution.add(event)
        cls.execution_scopes[(start,attempt)]=dict(scope)
        return True

    @classmethod
    def _independent_recovery(cls,job_id):
        # The OS-owned W1-G launch journal proves the real kernel Job tree
        # was reaped. An NVP worker's own state or a stale PID alone is NOT
        # recovery authority.
        evidence=inspect_original_process_journals()
        state=cls.supervisor.inspect(job_id)
        return (evidence["unresolved_original_native_launches"]==0
            and evidence["original_windows_launch_journals_verified"]>=1
            and state["state"] in ("CANCELLED","FAILED","TIMED_OUT")
            and state.get("worker_pid") is not None)

    @staticmethod
    def _tokens(start,attempt):
        return {
            "director_event":f"fixture-director-{start:04d}-attempt-{attempt}",
            "native_execution_event":f"fixture-native-execution-{start:04d}-attempt-{attempt}",
        }

    def test_01_real_appcontainer_cancel_and_durable_recovery(self):
        # OS-owned running Blender with pinned encrypted worker script; no
        # emitted pixels or fake success receipt from this cancellation test.
        # An actual cancelled worker is never returned as delivered.
        jobdir=self.worker_root/"conv12_cancel_probe"
        jobdir.mkdir(mode=0o700)
        require_efs_stage(jobdir)
        script=jobdir/"cancel_me.py"
        script.write_text("import time\ntime.sleep(120)\n",encoding="utf8")
        source=jobdir/"source.usda"
        source.write_bytes(b"#usda 1.0\n")
        verify_efs_inputs(jobdir,names=("cancel_me.py","source.usda"))
        op=BlenderOperation(
            job_id="conv12_cancel_probe",script="cancel_me.py",
            script_sha256=sha_file(script),
            inputs={"source.usda":sha_file(source)},
            outputs={"audit.json":"json_audit"},
            arguments={"--audit":"audit.json"},
            memory_limit_mb=2048,timeout_seconds=240,
            require_linux_cgroup_v2=True,require_private_isolation=True)
        with ThreadPoolExecutor(max_workers=1) as pool:
            done=pool.submit(self.supervisor.run,op)
            started=False
            deadline=time.monotonic()+90
            while time.monotonic()<deadline and not done.done():
                try:
                    status=self.supervisor.inspect("conv12_cancel_probe")
                except KeyError:
                    status={}
                if status.get("state")=="RUNNING":
                    started=True
                    break
                time.sleep(.1)
            self.assertTrue(started,"Real AppContainer Blender did not begin a kernel-owned job")
            self.assertTrue(self.supervisor.cancel("conv12_cancel_probe"))
            status=done.result(timeout=60)
        self.assertEqual(status["state"],"CANCELLED")
        self.assertGreater(inspect_original_process_journals()[
            "original_windows_launch_journals_verified"],0)
        reopened=BlenderWorkerSupervisor(
            self.worker_root,blender_executable=self.binary,
            blender_sha256=self.binary_sha,blender_version=self.version)
        self.assertEqual(reopened.recover_interrupted(),[])
        self.assertEqual(reopened.inspect(op.job_id)["state"],"CANCELLED")
        with self.assertRaises(RuntimeError):
            reopened.run(op)
        with self.assertRaises(RuntimeError):
            reopened.verify_completed(op.job_id)
        print("CONV12_PRIVATE_WIN_REAL_APPCONTAINER_CANCEL_RESTART_DENIAL_PASS",flush=True)

    def test_02_render_all_90_chunks_and_verify_all_720_native_pngs(self):
        # This test deliberately has no partial acceptance: one refused,
        # missing or unverified chunk FAILS the entire original 720-frame gate.
        _,source,self_plan=self.host.source_plan(self.pid,self.edit_id,1)
        self.assertEqual(len(self_plan["plan"]["frames"]),720)
        self.assertEqual(len(self_plan["plan"]["chunks"]),90)
        self.assertFalse(self_plan["plan"]["cycles_pixels_rendered"])
        srcdir=self.host._original.source(self.pid,self.bank_id,1)[0]
        verify_efs_inputs(srcdir,names=(STAGE,MANIFEST))
        original_sha=self_plan["plan"]["original_performance_sha256"]
        existing_take=self.index.read_revision(self.pid,self.take_id,1)["document_sha256"]
        self.assertEqual(existing_take,self.take_sha)
        expected_job_hashes=[]
        for start in range(0,720,8):
            approved=self._tokens(start,1)
            completed=self.host.run_chunk(
                self.pid,self.edit_id,revision=1,start=start,
                attempt=1,**approved)
            self.assertEqual(completed["state"],
                             "REVERIFIED_NATIVE_SELECTED_FRAMES")
            self.assertEqual(completed["native_selected_views_rendered"],8)
            job_id=completed["job_id"]
            record=self.supervisor.verify_completed(job_id)
            self.assertEqual(record["state"],"SUCCEEDED")
            task=self.supervisor.root/job_id
            verify_efs_inputs(task,names=(
                "source.usda","source.json","plan.json","chunk.json",
                "nvp_usd_film01q_blender_selected_views.py",
                "nvp_usd_film01m_camera_ray_mask.py",
                "nvp_usd_film01r_quality.py"))
            audit=json.loads((task/"audit.json").read_text("utf8"))
            self.assertTrue(audit["passed"])
            self.assertEqual(audit["native_rendered_frames"],8)
            self.assertEqual(len(audit["selected_view_frames"]),8)
            self.assertEqual(audit["original_performance_sha256"],original_sha)
            self.assertEqual(audit["native_blender_version"],
                             self.version.removeprefix("Blender "))
            for row in audit["selected_view_frames"]:
                img=task/row["rendered_png_file"]
                self.assertEqual(file_sha(img),row["rendered_png_sha256"])
            expected_job_hashes.append({
                "job_id":job_id,"start_frame":start,
                "audit_sha256":file_sha(task/"audit.json"),
                "png_sha256":[x["rendered_png_sha256"] for x in
                              audit["selected_view_frames"]]})
            if start%80==0:
                print(f"CONV12_PRIVATE_WIN_NATIVE_PROGRESS frames={start+8}/720",flush=True)
        self.assertEqual(len(expected_job_hashes),90)
        self.assertEqual(len([v for x in expected_job_hashes
                              for v in x["png_sha256"]]),720)
        reopened=BlenderWorkerSupervisor(
            self.worker_root,blender_executable=self.binary,
            blender_sha256=self.binary_sha,blender_version=self.version)
        self.assertEqual(reopened.recover_interrupted(),[])
        verify=ReviewedSelectedViewFilm(
            self.index,reopened,
            verify_director_action=lambda *_:False,
            verify_native_execution=lambda *_:False,
            prove_process_custody=lambda *_:False,
            render_quality="technical_smoke")
        progress=verify.progress(self.pid,self.edit_id,revision=1)
        self.assertTrue(progress["finished"])
        self.assertEqual(progress["native_completed_chunks"],90)
        self.assertEqual(progress["rendered_selected_frames_verified"],720)
        self.assertEqual(progress["blocked_interrupted_native_jobs"],[])
        with self.assertRaises(PermissionError):
            verify.gather(self.pid,self.edit_id,revision=1,
                output_directory=self.fixture.root/"no_director_export",
                director_event="denied")
        exported=self.fixture.root/"conv12_director_exported_720"
        gathered=self.host.gather(
            self.pid,self.edit_id,revision=1,output_directory=exported,
            director_event="fixture-director-export-after-720-native-frames")
        self.assertEqual(gathered["native_verified_chunks"],90)
        self.assertEqual(gathered["native_verified_frames"],720)
        self.assertFalse(gathered["director_picture_approved"])
        self.assertEqual(len(list(exported.glob("frame_????.png"))),720)
        self.assertEqual(self.index.read_revision(
            self.pid,self.take_id,1)["document_sha256"],self.take_sha)
        custody=inspect_original_process_journals()
        self.assertEqual(custody["unresolved_original_native_launches"],0)
        # Export only non-sensitive public-fixture audit digests. Never make
        # a private source film or PNG dataset a CI artifact.
        evidence={
            "format":"nvp.conv12.real_protected_windows_720_cycles.v1",
            "full_720_real_native_selected_pngs_verified":True,
            "native_exact_eight_frame_chunks":90,
            "source_film_fps":24,
            "camera_count":len(self.cameras),
            "original_performance_sha256":original_sha,
            "original_take_sha256":self.take_sha,
            "original_blender_version":self.version,
            "pinned_blender_executable_sha256":self.binary_sha,
            "native_windows_appcontainer_job_journals_verified":
                custody["original_windows_launch_journals_verified"],
            "native_windows_unresolved_process_journals":0,
            "gather_receipt_sha256":file_sha(exported/"gather_receipt.json"),
            "per_chunk_native_receipts":expected_job_hashes,
            "source_cache_efs_verified":True,
            "each_native_chunk_efs_verified":True,
            "native_cancellation_and_recovery_test_separate":True,
            "actual_human_director_approval":False,
            "physical_radeon_tested":False,
            "uses_ffmpeg":False,
        }
        location=os.environ.get("NVP_CONV12_EVIDENCE_PATH")
        if location:
            dest=Path(location)
            if dest.is_symlink() or dest.exists():
                raise FileExistsError("Do not overwrite CONV-12 native evidence")
            with dest.open("x",encoding="utf8") as f:
                json.dump(evidence,f,sort_keys=True,indent=2)
                f.flush();os.fsync(f.fileno())
        print(
            "CONV12_PRIVATE_WIN_REAL_90x8_BLENDER_CYCLES_720_NATIVE_PNG_ACCEPTANCE_PASS "
            "windows_kernel_appcontainer=1 efs=1 frames=720 chunks=90",flush=True)


if __name__=="__main__":
    unittest.main()
