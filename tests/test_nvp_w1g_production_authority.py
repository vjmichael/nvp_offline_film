"""W1-G production stop/authorization gates are not CI witness flags."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.nvp_w1g_nsis_activation import NativeNSISActivation
from tools.nvp_w1g_production_authority import (
    WindowsCreatorUpgradeApproval, WindowsReleaseWorkerStopEvidence,
)
from tools.nvp_w1g_nsis_recovery import OwnedNSISRecovery
from tools.nvp_w1g_owner_windows_acceptance import _read_owner_pinned_key


class NativeReleaseAuthorityRefusal(unittest.TestCase):
    def test_untyped_human_and_kernel_callbacks_never_enter_production(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            programs=root/"Programs";programs.mkdir()
            film=root/"OriginalFilm";film.mkdir()
            journal=root/"Journal";journal.mkdir()
            owner=OwnedNSISRecovery(
                programs,film,journal,
                native_approve=lambda scope:True,
                os_workers_stopped=lambda:True,test_only_simulation=True)
            with self.assertRaisesRegex(PermissionError,
                    "cannot accept callback/synthetic"):
                NativeNSISActivation(
                    owner,native_authorize=lambda scope:True,
                    os_worker_tree_evidence=lambda source: {
                        "os_provenance":"windows-job-object",
                        "original_runtime_sha256":source,
                        "process_tree_custody_verified":True,
                        "active_windows_jobs":0,
                        "unresolved_worker_jobs":0,
                        "measured_at_unix":__import__("time").time()})
            self.assertFalse((journal/"nsis-activation.json").exists())

    def test_one_native_worker_role_never_satisfies_release_provisioning(self):
        from unittest.mock import patch
        from tools.nvp_w1g_nsis_activation import _require_complete_reviewed_native_roster
        with patch("tools.nvp_w1g_worker_package.verify_native_workers",
                   return_value={"roles":["scene_render"]}):
            with self.assertRaisesRegex(PermissionError,"All five actual"):
                _require_complete_reviewed_native_roster(Path("reviewed-candidate"))
        with patch("tools.nvp_w1g_worker_package.verify_native_workers",
                   return_value={"roles":["original_capture","scene_render",
                                          "editorial","audio","delivery"]}):
            self.assertEqual(_require_complete_reviewed_native_roster(
                Path("reviewed-candidate"))["roles"][0],"original_capture")

    def test_legacy_rollback_owner_refuses_production_lambdas(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            programs=root/"Programs";programs.mkdir()
            films=root/"Films";films.mkdir()
            journal=root/"Journal";journal.mkdir()
            with self.assertRaisesRegex(PermissionError,
                    "cannot accept synthetic callbacks"):
                OwnedNSISRecovery(
                    programs,films,journal,
                    native_approve=lambda scope:True,
                    os_workers_stopped=lambda:True)
            self.assertFalse((journal/"nsis-rollback.json").exists())

    def test_test_simulation_explicitly_separate_from_release(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            programs=root/"Programs";programs.mkdir()
            film=root/"OriginalFilm";film.mkdir()
            journal=root/"Journal";journal.mkdir()
            owner=OwnedNSISRecovery(
                programs,film,journal,
                native_approve=lambda scope:True,
                os_workers_stopped=lambda:True,test_only_simulation=True)
            tool=NativeNSISActivation(
                owner,native_authorize=lambda scope:True,
                os_worker_tree_evidence=lambda source: {
                    "os_provenance":"windows-job-object",
                    "original_runtime_sha256":source,
                    "process_tree_custody_verified":True,
                    "active_windows_jobs":0,
                    "unresolved_worker_jobs":0,
                    "measured_at_unix":__import__("time").time(),
                    "test_fixture_only_not_kernel_evidence":True},
                test_only_simulation=True)
            self.assertTrue(tool.test_only_simulation)


    def test_signed_review_is_required_at_preparation_not_only_activation(self):
        # The helper runs before the preparation journal may be written.
        # Tests deliberately provide no legal review or signed package.
        activation=object.__new__(NativeNSISActivation)
        activation.test_only_simulation=False
        activation.pinned_reviewer_public_key=None
        with self.assertRaisesRegex(PermissionError,"owner-pinned"):
            activation._require_signed_review({"native_worker_manifest_verified":True})
        activation.pinned_reviewer_public_key=b"k"*32
        with self.assertRaisesRegex(PermissionError,"reviewed compiled native workers"):
            activation._require_signed_review({})
        with self.assertRaises(PermissionError):
            activation._require_signed_review({
                "native_worker_manifest_verified":True,
                "platform":"windows-amd64", "files":{"NVP.exe":{
                    "bytes":100, "sha256":"a"*64}},
                "app_sha256":"a"*64})

    def test_reviewer_key_must_be_external_to_mutable_release_roots(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            programs=root/"Programs";programs.mkdir()
            films=root/"Films";films.mkdir()
            journal=root/"Journal";journal.mkdir()
            workspace=root/"Workspace";workspace.mkdir()
            for forbidden in (programs,films,journal,workspace):
                key=forbidden/"reviewer.pub"
                key.write_bytes(b"k"*32)
                with self.assertRaisesRegex(PermissionError,"cannot reside"):
                    _read_owner_pinned_key(key,forbidden_roots=(
                        programs,films,journal,workspace))
            external=root/"ExternalTrust";external.mkdir()
            key=external/"reviewer.pub"
            key.write_bytes(b"q"*32)
            self.assertEqual(_read_owner_pinned_key(key,
                forbidden_roots=(programs,films,journal,workspace)),b"q"*32)
            with self.assertRaisesRegex(PermissionError,"absolute"):
                _read_owner_pinned_key(Path("relative.pub"),
                    forbidden_roots=(programs,films,journal,workspace))

    def test_read_only_windows_inspection_does_not_require_signing_key(self):
        import os
        if os.name!="nt":
            self.skipTest("Real Windows authority objects required")
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            programs=root/"Programs";programs.mkdir()
            films=root/"Films";films.mkdir()
            journal=root/"Journal";journal.mkdir()
            workspaces={}
            for name in WindowsReleaseWorkerStopEvidence.REQUIRED_DOMAINS:
                folder=root/name
                folder.mkdir()
                workspaces[name]=folder
            human=WindowsCreatorUpgradeApproval()
            kernel=WindowsReleaseWorkerStopEvidence(
                programs/"NVP",worker_workspaces=workspaces)
            owner=OwnedNSISRecovery(
                programs,films,journal,
                native_approve=human,os_workers_stopped=kernel)
            inspection=NativeNSISActivation(
                owner,native_authorize=human,
                os_worker_tree_evidence=kernel,
                pinned_reviewer_public_key=None)
            self.assertIsNone(inspection.pinned_reviewer_public_key)
            with self.assertRaisesRegex(PermissionError,"owner-pinned"):
                inspection._require_signed_review({})

    def test_no_production_windows_authority_on_linux(self):
        import os
        if os.name=="nt":
            self.skipTest("Separate physical Windows session acceptance")
        with self.assertRaises(RuntimeError):
            WindowsCreatorUpgradeApproval()
        with self.assertRaises(RuntimeError):
            WindowsReleaseWorkerStopEvidence(Path("/tmp/unknown"),
                worker_workspaces={name:Path("/tmp")/name
                                   for name in WindowsReleaseWorkerStopEvidence.REQUIRED_DOMAINS})


if __name__ == "__main__":
    unittest.main()
