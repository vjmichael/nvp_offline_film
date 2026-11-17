"""CONV-12 Windows-only: fail-closed native private Blender/AppContainer bridge.

Source-contract checks do not certify installed Blender pixel output. Native
AppContainer/EFS/Job proof remains an independent required release gate.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import backend.nvp_blender_worker as worker


@unittest.skipUnless(sys.platform=="win32","NVP Linux native testing suspended")
class WindowsPrivateBlenderBridgeContract(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nvp-conv12-win-private-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.program_files=self.root/"Program Files"
        self.binary_root=self.program_files/"Blender Foundation"/"Blender 5"
        self.binary_root.mkdir(parents=True)
        self.binary=self.binary_root/"blender.exe"
        self.binary.write_bytes(b"REVIEWED-TEST-ONLY-NOT-A-BLENDER-EXECUTABLE")
        self.job=self.root/"NVP private job"
        self.job.mkdir()
        (self.job/"render.py").write_text("# signed worker path fixture",encoding="utf8")
        (self.job/"source.usda").write_bytes(b"#usda 1.0\n")

    def allow_registry(self):
        # Deterministic HKLM response; never gives the test actual elevated rights.
        return patch("winreg.QueryValueEx",
                     return_value=(str(self.program_files),1))

    def test_deny_arbitrary_user_installed_blender_even_with_matching_checksum(self):
        other=self.root/"Downloads"/"blender.exe"
        other.parent.mkdir()
        other.write_bytes(b"UNREVIEWED-PATH")
        with self.allow_registry(),patch(
                "backend.nvp_w1g_encrypted_source.verify_efs_inputs") as efs:
            with self.assertRaisesRegex(PermissionError,"HKLM Program Files"):
                worker._windows_private_blender_code_root(
                    other,self.job,"render.py",{"source.usda":"0"*64})
        efs.assert_not_called()

    def test_require_actual_efs_on_worker_directory_and_every_source_input(self):
        with self.allow_registry(),patch(
                "backend.nvp_w1g_encrypted_source.verify_efs_inputs",
                side_effect=PermissionError("No Windows EFS")):
            with self.assertRaisesRegex(PermissionError,"No Windows EFS"):
                worker._windows_private_blender_code_root(
                    self.binary,self.job,"render.py",{"source.usda":"0"*64})

    def test_allow_only_reviewed_install_root_after_evidence_is_verified(self):
        with self.allow_registry(),patch(
                "backend.nvp_w1g_encrypted_source.verify_efs_inputs",
                return_value=True) as efs:
            root=worker._windows_private_blender_code_root(
                self.binary,self.job,"render.py",{"source.usda":"0"*64})
        self.assertEqual(root,self.binary_root.resolve())
        self.assertEqual(efs.call_count,1)
        names=efs.call_args.kwargs["names"]
        self.assertEqual(set(names),{"render.py","source.usda"})

    def test_supervisor_dispatch_requires_real_appcontainer_not_plain_job(self):
        node=ast.parse(textwrap.dedent(
            inspect.getsource(worker.BlenderWorkerSupervisor._run_worker)))
        launches=[n for n in ast.walk(node)
                  if isinstance(n,ast.Call) and
                  isinstance(n.func,ast.Name) and n.func.id=="launch_contained"]
        self.assertGreaterEqual(len(launches),2)
        secure=[n for n in launches
                if any(k.arg=="windows_appcontainer_required" and
                       isinstance(k.value,ast.Constant) and k.value.value is True
                       for k in n.keywords)]
        self.assertEqual(len(secure),1)
        secure_args={k.arg:k.value for k in secure[0].keywords}
        self.assertIs(secure_args["private_isolation_required"].value,False)
        self.assertIs(secure_args["linux_cgroup_tree_required"].value,False)
        self.assertIn("appcontainer_code_roots",secure_args)
        source=inspect.getsource(worker.BlenderWorkerSupervisor._run_worker)
        self.assertIn("windows-appcontainer-with-zero-network-capabilities",source)
        self.assertIn('raise RuntimeError("Native private Blender lacks proved Windows AppContainer identity")',source)


if __name__=="__main__":
    unittest.main()
