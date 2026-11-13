"""W1-G NSIS rollback and protected native worker source contracts.

These synthetic fixtures verify denial and code paths, not real kernel or
installed Windows execution. Production acceptance needs OS-only evidence.
"""
from hashlib import sha256
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.nvp_w1g_worker_package import (
    FORMAT as WORKER_FORMAT, provision_native_workers,
)
from backend.nvp_w1g_protected_native_worker import ProtectedNativeWorker
from tools.nvp_w1g_nsis_recovery import OwnedNSISRecovery
from test_nvp_e2e01e_package_guard import make_pe


class NativeInstallerRecoveryContracts(unittest.TestCase):
    def roots(self, base):
        programs=base/"Programs"
        programs.mkdir()
        films=base/"OriginalFilms"
        films.mkdir()
        (films/"immutable.scene").write_bytes(b"original film")
        journal=base/"UpgradeRecovery"
        journal.mkdir()
        for name in ("NVP","NVP.previous"):
            target=programs/name
            target.mkdir()
            make_pe(target/"NVP.exe")
            (target/"nvp-alpha-install.marker").write_bytes(b"NVP-ALPHA-INSTALL-v1")
            (target/"nvp-alpha-version.txt").write_text(
                "0.1.1" if name=="NVP" else "0.1.0")
        # Distinct, valid x64 PE contents for new and previous executable.
        exe=programs/"NVP"/"NVP.exe"
        with exe.open("ab") as out:
            out.write(b"new version")
        return programs, films, journal

    def test_rollback_parks_new_exe_and_preserves_original_movie(self):
        with TemporaryDirectory() as temp:
            programs,films,journal=self.roots(Path(temp))
            owner=OwnedNSISRecovery(programs,films,journal,
                native_approve=lambda scope:scope["operation"]=="nvp.w1g.nsis.rollback.v1",
                os_workers_stopped=lambda:True,test_only_simulation=True)
            owner.prepare()
            # Synthetic PE fixtures are NOT genuine NSIS registrations.
            # Exercise file rollback while simulating only that registry
            # boundary; the actual Windows NSIS matrix tests real HKCU.
            with patch("tools.nvp_w1g_nsis_activation._update_registration"), \
                 patch("tools.nvp_w1g_nsis_activation._registry_version",
                       return_value="0.1.0"):
                result=owner.rollback()
            self.assertEqual(result["status"],"NSIS_PREVIOUS_PROGRAM_RESTORED")
            self.assertTrue((programs/"NVP.failed"/"NVP.exe").exists())
            self.assertEqual((films/"immutable.scene").read_bytes(),b"original film")
            self.assertEqual(owner.reconcile()["state"],"ROLLED_BACK")

    def test_unknown_worker_custody_and_film_tamper_block_replacement(self):
        with TemporaryDirectory() as temp:
            programs,films,journal=self.roots(Path(temp))
            owner=OwnedNSISRecovery(programs,films,journal,
                native_approve=lambda scope:True,os_workers_stopped=lambda:False,test_only_simulation=True)
            owner.prepare()
            with self.assertRaises(PermissionError):
                owner.rollback()
            self.assertTrue((programs/"NVP.previous"/"NVP.exe").exists())
            (films/"immutable.scene").write_bytes(b"modified")
            with self.assertRaisesRegex(RuntimeError,"original films changed"):
                owner.rollback()



    def test_only_independently_accepted_upgrade_may_archive_previous_program(self):
        from tools.nvp_w1g_nsis_closeout import archive_accepted_previous
        with TemporaryDirectory() as temp:
            programs,films,journal=self.roots(Path(temp))
            owner=OwnedNSISRecovery(
                programs,films,journal,native_approve=lambda scope:True,
                os_workers_stopped=lambda:True,test_only_simulation=True)
            with self.assertRaisesRegex(RuntimeError,"not been accepted"):
                archive_accepted_previous(owner,lambda scope: {
                    "current_runtime_sha256":scope["current_sha256"],
                    "installed_launch_verified":True,
                    "restart_verified":False,
                    "original_films_verified":True})
            self.assertTrue((programs/"NVP.previous").is_dir())
            done=archive_accepted_previous(owner,lambda scope: {
                "current_runtime_sha256":scope["current_sha256"],
                "installed_launch_verified":True,
                "restart_verified":True,
                "original_films_verified":True})
            self.assertEqual(done["status"],
                             "NSIS_PREVIOUS_VERSION_PRESERVED_IN_HISTORY")
            self.assertFalse((programs/"NVP.previous").exists())
            self.assertEqual((films/"immutable.scene").read_bytes(),b"original film")

    def test_failed_nsis_stage_quarantined_without_deleting_originals(self):
        from tools.nvp_w1g_nsis_closeout import quarantine_failed_stage
        with TemporaryDirectory() as temp:
            programs,films,journal=self.roots(Path(temp))
            (programs/"NVP.previous").rename(programs/"NVP.pending")
            owner=OwnedNSISRecovery(
                programs,films,journal,native_approve=lambda scope:True,
                os_workers_stopped=lambda:True,test_only_simulation=True)
            receipt=quarantine_failed_stage(owner)
            self.assertEqual(receipt["status"],
                             "NSIS_FAILED_CANDIDATE_PRESERVED")
            self.assertFalse((programs/"NVP.pending").exists())
            self.assertTrue((programs/"NVP"/"NVP.exe").is_file())
            self.assertEqual((films/"immutable.scene").read_bytes(),b"original film")


    def test_native_nsis_activation_refuses_stale_or_busy_worker_evidence(self):
        import time
        from tools.nvp_w1g_nsis_activation import NativeNSISActivation
        with TemporaryDirectory() as temp:
            programs, films, journal=self.roots(Path(temp))
            owner=OwnedNSISRecovery(
                programs,films,journal,native_approve=lambda scope:True,
                os_workers_stopped=lambda:True,test_only_simulation=True)
            def invalid_kernel(sha):
                return {"os_provenance":"windows-job-object",
                        "original_runtime_sha256":sha,
                        "process_tree_custody_verified":True,
                        "active_windows_jobs":1,
                        "unresolved_worker_jobs":0,
                        "measured_at_unix":time.time()-120}
            activation=NativeNSISActivation(
                owner,native_authorize=lambda scope:True,
                os_worker_tree_evidence=invalid_kernel,
                test_only_simulation=True)
            with self.assertRaisesRegex(PermissionError,"kernel stop receipt"):
                activation._kernel_empty("a"*64)

class ActualKernelCustodyContractTests(unittest.TestCase):
    def test_unowned_child_cannot_masquerade_as_os_contained_worker(self):
        from backend.nvp_w1g_kernel_custody import verified_native_worker_exit
        class UnownedPid:
            pid=7031
            def poll(self):return 0
            def close(self):return None
        with self.assertRaises(RuntimeError):
            verified_native_worker_exit(UnownedPid())

class ProtectedBinaryExecutionContracts(unittest.TestCase):
    def setup_roster(self,base):
        bundle=base/"bundle"
        bundle.mkdir()
        runtime=base/"runtime"
        runtime.mkdir()
        trusted=base/"trusted"
        trusted.mkdir()
        make_pe(trusted/"render.exe",subsystem=3)
        exe=trusted/"render.exe"
        roster={
            "format":WORKER_FORMAT,"platform":"windows-amd64",
            "workers":[{"role":"scene_render","filename":"render.exe",
                        "sha256":sha256(exe.read_bytes()).hexdigest()}]}
        provision_native_workers(trusted,bundle,roster)
        return bundle,runtime

    def test_original_source_set_is_explicit_finite_and_before_approval(self):
        with TemporaryDirectory() as temp:
            bundle,runtime=self.setup_roster(Path(temp))
            approvals=[]
            process=ProtectedNativeWorker(
                bundle,runtime,platform="windows-amd64",
                native_approve=lambda scope:approvals.append(scope) or False,
                independent_verify=lambda scope,result,directory:True,
                independent_os_custody=lambda scope,receipt:True)
            plan={"role":"scene_render","project_id":"Project01"}
            with self.assertRaisesRegex(PermissionError,"complete finite sealed source"):
                process.run("scene_render","Project01",plan,
                    sealed_inputs={"source.pcm":b"forged"})
            with self.assertRaisesRegex(PermissionError,"complete finite sealed source"):
                process.run("scene_render","Project01",plan,
                    sealed_inputs={"scene.txt":b""})
            with self.assertRaisesRegex(ValueError,"injected authority"):
                process.run("scene_render","Project01",
                    {**plan,"input_sha256":{"scene.txt":"wrong"}},
                    sealed_inputs={"scene.txt":b"64 48\n"})
            self.assertEqual(approvals,[])
            with self.assertRaisesRegex(PermissionError,"creator refused"):
                process.run("scene_render","Project01",plan,
                    sealed_inputs={"scene.txt":b"64 48\n"})
            self.assertEqual(len(approvals),1)
            self.assertEqual(approvals[0]["input_sha256"],{
                "scene.txt":sha256(b"64 48\n").hexdigest()})
            self.assertEqual(list(runtime.iterdir()),[])

    @unittest.skipUnless(__import__("os").name=="nt",
                         "Real Windows EFS denial path")
    def test_real_windows_efs_failure_writes_no_original_source(self):
        with TemporaryDirectory() as temp:
            bundle,runtime=self.setup_roster(Path(temp))
            process=ProtectedNativeWorker(
                bundle,runtime,platform="windows-amd64",
                native_approve=lambda scope:True,
                independent_verify=lambda scope,result,directory:True,
                independent_os_custody=lambda scope,receipt:True)
            with patch("backend.nvp_w1g_encrypted_source.require_efs_stage",
                       side_effect=PermissionError("EFS worker source unavailable")):
                with self.assertRaisesRegex(PermissionError,"EFS worker source"):
                    process.run("scene_render","Project01",
                        {"role":"scene_render","project_id":"Project01"},
                        sealed_inputs={"scene.txt":b"64 48\n"})
            dirs=list(runtime.iterdir())
            self.assertEqual(len(dirs),1)
            self.assertEqual(list(dirs[0].iterdir()),[])

    def test_os_custody_required_even_when_worker_exits_successfully(self):
        class Child:
            pid=7031
            def wait(self,timeout=None):return 0
            def poll(self):return 0
            def close(self):return None
            def terminate_tree(self):return None
        with TemporaryDirectory() as temp:
            bundle,runtime=self.setup_roster(Path(temp))
            def fake_launch(command,*,cwd,stdout,stderr,memory_mb,
                            linux_cgroup_tree_required):
                self.assertTrue(linux_cgroup_tree_required)
                sealed=Path(command[-1])
                plan=sealed.read_bytes()
                obj=json.loads(plan)
                result={"job_id":obj["job_id"],"project_id":obj["project_id"],
                        "plan_sha256":sha256(plan).hexdigest()}
                (Path(cwd)/"result.json").write_text(json.dumps(result))
                return Child()
            process=ProtectedNativeWorker(
                bundle,runtime,platform="windows-amd64",
                native_approve=lambda scope:True,
                independent_verify=lambda scope,result,directory:True,
                independent_os_custody=lambda scope,receipt: True)
            # Synthetic unowned-PID fixture: EFS is separately tested
            # against actual Windows fail-closed admission, never claimed
            # as physical encrypted-source acceptance by these mock files.
            with patch("backend.nvp_w1g_protected_native_worker.launch_contained",
                       side_effect=fake_launch), patch(
                       "backend.nvp_w1g_encrypted_source.require_efs_stage",
                       return_value={"encrypted_at_rest_verified":False}), patch(
                       "backend.nvp_w1g_encrypted_source.verify_efs_inputs",
                       return_value=True):
                with self.assertRaises(RuntimeError):
                    process.run("scene_render","Project01",
                                {"role":"scene_render","project_id":"Project01"},
                                sealed_inputs={"scene.txt":b"64 48\n"})
            journals=list(runtime.glob("*/journal.json"))
            self.assertEqual(len(journals),1)
            self.assertEqual(json.loads(journals[0].read_text())["state"],
                             "FAILED_UNVERIFIED")
