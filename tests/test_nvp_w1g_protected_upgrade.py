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
                os_workers_stopped=lambda:True)
            owner.prepare()
            result=owner.rollback()
            self.assertEqual(result["status"],"NSIS_PREVIOUS_PROGRAM_RESTORED")
            self.assertTrue((programs/"NVP.failed"/"NVP.exe").exists())
            self.assertEqual((films/"immutable.scene").read_bytes(),b"original film")
            self.assertEqual(owner.reconcile()["state"],"ROLLED_BACK")

    def test_unknown_worker_custody_and_film_tamper_block_replacement(self):
        with TemporaryDirectory() as temp:
            programs,films,journal=self.roots(Path(temp))
            owner=OwnedNSISRecovery(programs,films,journal,
                native_approve=lambda scope:True,os_workers_stopped=lambda:False)
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
                os_workers_stopped=lambda:True)
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
                os_workers_stopped=lambda:True)
            receipt=quarantine_failed_stage(owner)
            self.assertEqual(receipt["status"],
                             "NSIS_FAILED_CANDIDATE_PRESERVED")
            self.assertFalse((programs/"NVP.pending").exists())
            self.assertTrue((programs/"NVP"/"NVP.exe").is_file())
            self.assertEqual((films/"immutable.scene").read_bytes(),b"original film")


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
                independent_os_custody=lambda scope,child: {
                    "process_tree_custody_verified":False,
                    "os_provenance":"windows-job-object",
                    "worker_pid":child.pid})
            with patch("backend.nvp_w1g_protected_native_worker.launch_contained",
                       side_effect=fake_launch):
                with self.assertRaisesRegex(RuntimeError,"custody"):
                    process.run("scene_render","Project01",
                                {"role":"scene_render","project_id":"Project01"})
            journals=list(runtime.glob("*/journal.json"))
            self.assertEqual(len(journals),1)
            self.assertEqual(json.loads(journals[0].read_text())["state"],
                             "FAILED_UNVERIFIED")
