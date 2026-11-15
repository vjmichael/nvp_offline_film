"""CONV-01/03: W1-G release custody + G03 AppContainer source convergence.

The old W1-G process launcher and G03 creator UI had diverged. These source
contract tests verify the ONE currently integrated host path reserves the
release-wide slot and binds the original journal to kernel AppContainer
launch; failures revoke the slot. OS custody remains an independent physical
Windows/SCM/Job/WFP and Linux delegated-cgroup acceptance gate.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch, sentinel
import sys

from backend import nvp_worker_containment as host
from backend import nvp_w1g_release_gate as release
from backend import nvp_g03_windows_appcontainer as sandbox


class _OriginalSlot:
    def __init__(self):
        self.acquired=0
        self.released=0

    def acquire(self):
        self.acquired+=1
        return self

    def release(self):
        self.released+=1


class CrossBranchNativeSecurityConvergence(TestCase):
    def setUp(self):
        self.command=[str(Path(sys.executable).resolve())]
        self.cwd=str(Path.cwd().resolve())
        self.args={
            "cwd":self.cwd,"stdout":None,"stderr":None,
            "memory_mb":256}

    def test_w1g_release_slot_and_journal_are_passed_to_real_appcontainer_boundary(self):
        slot=_OriginalSlot()
        original_journal=sentinel.original_journal
        received=[]
        def native_launch(command,**kwargs):
            received.append((command,kwargs))
            return sentinel.contained_process
        with (
            patch.object(host,"os",SimpleNamespace(name="nt")),
            patch.object(release,"WindowsWorkerLifetimeSlot",return_value=slot),
            patch.object(release,"OriginalWindowsLaunchJournal",
                return_value=original_journal) as journal,
            patch.object(sandbox,"launch_appcontainer",side_effect=native_launch)
        ):
            proc=host.launch_contained(
                self.command,**self.args,
                env={"NVP_SOURCE_ISOLATED":"1"},
                windows_appcontainer_required=True,
                appcontainer_code_roots=(self.cwd,),
                appcontainer_code_files=(self.command[0],))
        self.assertIs(proc,sentinel.contained_process)
        self.assertEqual(slot.acquired,1)
        self.assertEqual(slot.released,0)
        journal.assert_called_once_with(self.command)
        self.assertEqual(len(received),1)
        args,kw=received[0]
        self.assertEqual(args,self.command)
        self.assertEqual(kw["cwd"],self.cwd)
        self.assertIs(kw["release_slot"],slot)
        self.assertIs(kw["original_journal"],original_journal)
        self.assertEqual(kw["env"],{"NVP_SOURCE_ISOLATED":"1"})
        self.assertEqual(kw["code_roots"],(self.cwd,))
        self.assertEqual(kw["code_files"],(self.command[0],))
        self.assertEqual(kw["memory_mb"],256)

    def test_appcontainer_failure_releases_w1g_slot_without_uncontained_fallback(self):
        slot=_OriginalSlot()
        with (
            patch.object(host,"os",SimpleNamespace(name="nt")),
            patch.object(release,"WindowsWorkerLifetimeSlot",return_value=slot),
            patch.object(release,"OriginalWindowsLaunchJournal",
                return_value=sentinel.original_journal),
            patch.object(sandbox,"launch_appcontainer",
                side_effect=RuntimeError("kernel profile unavailable")) as launch,
            patch.object(host,"_launch_windows",
                side_effect=AssertionError("Unsafe generic Job fallback")) as fallback
        ):
            with self.assertRaisesRegex(RuntimeError,"kernel profile unavailable"):
                host.launch_contained(
                    self.command,**self.args,
                    windows_appcontainer_required=True)
        self.assertEqual(slot.acquired,1)
        self.assertEqual(slot.released,1)
        launch.assert_called_once()
        fallback.assert_not_called()

    def test_failed_journal_preflight_releases_slot_before_appcontainer(self):
        slot=_OriginalSlot()
        with (
            patch.object(host,"os",SimpleNamespace(name="nt")),
            patch.object(release,"WindowsWorkerLifetimeSlot",return_value=slot),
            patch.object(release,"OriginalWindowsLaunchJournal",
                side_effect=PermissionError("unreviewed original launch")),
            patch.object(sandbox,"launch_appcontainer") as launch
        ):
            with self.assertRaisesRegex(PermissionError,"unreviewed original"):
                host.launch_contained(
                    self.command,**self.args,
                    windows_appcontainer_required=True)
        self.assertEqual(slot.acquired,1)
        self.assertEqual(slot.released,1)
        launch.assert_not_called()

    def test_no_kernel_or_unsupervised_private_source_is_never_authorized(self):
        with (
            patch.object(host,"os",SimpleNamespace(name="posix")),
            patch.object(host.subprocess,"Popen",
                side_effect=AssertionError("Uncontained process launched")) as spawn
        ):
            with self.assertRaisesRegex(RuntimeError,"independent Windows kernel"):
                host.launch_contained(
                    self.command,**self.args,
                    windows_appcontainer_required=True)
            with self.assertRaisesRegex(PermissionError,"real kernel isolation"):
                host.launch_contained(
                    self.command,**self.args,
                    appcontainer_code_roots=(self.cwd,))
            with self.assertRaisesRegex(RuntimeError,"kernel whole-tree custody"):
                host.launch_contained(
                    self.command,**self.args,
                    private_isolation_required=True)
            with self.assertRaisesRegex(ValueError,"Invalid native worker environment"):
                host.launch_contained(
                    self.command,**self.args,
                    env={"SAFE":"bad\0value"})
            spawn.assert_not_called()


    def test_original_manual_security_gates_refuse_empty_suite_or_cancellation(self):
        # Independent gate 1 already refused zero discovered tests. The
        # historical SEC-06 Windows phase, W1-G and compiled-native phases
        # must not silently pass missing negative assertions either.
        root=Path(__file__).resolve().parents[1]/".github"/"workflows"
        requirements={
            "nvp-sec06-independent-gate1-20261112.yml":2,
            "nvp-int02c-w1g-native-matrix.yml":2,
            "nvp-w1g-compiled-workers.yml":3,
        }
        for workflow,minimum in requirements.items():
            with self.subTest(workflow=workflow):
                source=(root/workflow).read_text(encoding="utf-8")
                self.assertGreaterEqual(source.count("countTestCases()"),minimum)
                self.assertNotIn("cancel-in-progress: true",source)
                self.assertIn("test -f",source)
                self.assertIn("Test-Path",source)


if __name__=="__main__":
    import unittest
    unittest.main()
