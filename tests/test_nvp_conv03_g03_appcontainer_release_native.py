"""CONV-03/04: original W1-G release fencing survives G03 AppContainer routing.

These are portable *dispatch/negative* checks, not independently witnessed
Windows SCM/WFP/AppContainer kernel results. Native physical acceptance remains
mandatory. Tests must not mint a real release slot on Windows.
"""
from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from unittest import TestCase
import sys

import backend.nvp_worker_containment as containment


def _dispatch(**extra):
    return containment.launch_contained(
        [str(Path(sys.executable).resolve()), "--version"],
        cwd=str(Path.cwd()), stdout=None, stderr=None, memory_mb=1024,
        **extra,
    )


class OriginalAppContainerReleaseDispatch(TestCase):
    def test_appcontainer_flags_do_not_silently_downgrade_or_mix_linux_private_contract(self):
        with self.assertRaisesRegex(ValueError, "AppContainer requirement"):
            _dispatch(windows_appcontainer_required="yes")
        with self.assertRaisesRegex(PermissionError, "source grants require real kernel"):
            _dispatch(appcontainer_code_roots=[Path.cwd()])
        with self.assertRaisesRegex(ValueError, "Invalid native worker environment"):
            _dispatch(env={"BAD\\0KEY": "value"})
        with self.assertRaisesRegex(RuntimeError, "independent Windows kernel boundary"):
            _dispatch(windows_appcontainer_required=True,
                      linux_cgroup_tree_required=True)
        with self.assertRaisesRegex(RuntimeError, "independent Windows kernel boundary"):
            _dispatch(windows_appcontainer_required=True,
                      private_isolation_required=True)

    def test_original_appcontainer_dispatch_holds_release_slot_and_journal(self):
        observed = []
        class Slot:
            def acquire(self):
                observed.append("slot")
                return self
            def release(self):
                observed.append("release")
        class Journal:
            def __init__(self, command):
                observed.append(("journal", tuple(command)))
        native = ModuleType("backend.nvp_w1g_release_gate")
        native.WindowsWorkerLifetimeSlot = Slot
        native.OriginalWindowsLaunchJournal = Journal
        isolated = ModuleType("backend.nvp_g03_windows_appcontainer")
        result = object()
        def launch_appcontainer(command, **kwargs):
            observed.append("launch")
            self.assertIsNotNone(kwargs["release_slot"])
            self.assertIsInstance(kwargs["original_journal"], Journal)
            self.assertEqual(kwargs["env"], {"PROTECTED": "true"})
            self.assertEqual(kwargs["code_roots"], [Path.cwd()])
            self.assertEqual(kwargs["code_files"], [Path(sys.executable)])
            return result
        isolated.launch_appcontainer = launch_appcontainer
        with patch.object(containment, "os", SimpleNamespace(name="nt")), patch.dict(
                sys.modules, {native.__name__: native, isolated.__name__: isolated}):
            self.assertIs(_dispatch(windows_appcontainer_required=True,
                                    appcontainer_code_roots=[Path.cwd()],
                                    appcontainer_code_files=[Path(sys.executable)],
                                    env={"PROTECTED": "true"}), result)
        self.assertEqual([v if isinstance(v, str) else v[0] for v in observed], [
            "slot", "journal", "launch"])
        self.assertNotIn("release", observed)

    def test_failed_appcontainer_kernel_launch_releases_slot_without_false_acceptance(self):
        observed = []
        class Slot:
            def acquire(self):
                observed.append("acquire")
                return self
            def release(self):
                observed.append("release")
        class Journal:
            def __init__(self, command):
                observed.append("PREPARED")
        native = ModuleType("backend.nvp_w1g_release_gate")
        native.WindowsWorkerLifetimeSlot = Slot
        native.OriginalWindowsLaunchJournal = Journal
        isolated = ModuleType("backend.nvp_g03_windows_appcontainer")
        def fail(*_, **__):
            observed.append("kernel_failure")
            raise PermissionError("Original AppContainer kernel refused")
        isolated.launch_appcontainer = fail
        with patch.object(containment, "os", SimpleNamespace(name="nt")), patch.dict(
                sys.modules, {native.__name__: native, isolated.__name__: isolated}):
            with self.assertRaisesRegex(PermissionError, "kernel refused"):
                _dispatch(windows_appcontainer_required=True)
        self.assertEqual(observed, ["acquire", "PREPARED", "kernel_failure", "release"])


if __name__ == "__main__":
    import unittest
    unittest.main()
