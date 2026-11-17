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

    def test_production_p1f_encrypts_before_first_original_source_write(self):
        from backend.nvp_p1f_cycles_picture_sound import P1FOriginalPictureSound
        source=inspect.getsource(P1FOriginalPictureSound.render_frame)
        self.assertIn('if os.name=="nt":',source)
        self.assertIn('require_efs_stage(jobdir)',source)
        self.assertLess(source.index('require_efs_stage(jobdir)'),
                        source.index('_add_file(jobdir/"fixed_cycles.py"'))
        self.assertLess(source.index('require_efs_stage(jobdir)'),
                        source.index('_add_file(jobdir/"original.usda"'))
        self.assertLess(source.index('require_efs_stage(jobdir)'),
                        source.index('_add_file(jobdir/"original_pcm.wav"'))
        self.assertIn('require_private_isolation=True',source)
        self.assertIn('require_linux_cgroup_v2=True',source)
        self.assertIn('prove_private_kernel_boundary(self.supervisor.root)',source)

    def test_native_acl_is_limited_to_reviewed_runtime_and_one_job(self):
        from backend.nvp_g03_windows_appcontainer import _grant_scoped_access
        sid="S-1-15-2-1-2-3-4-5-6-7"
        grants=[]
        reviewed_file=self.binary_root/"reviewed.dll"
        with patch("backend.nvp_g03_windows_appcontainer._acl") as acl:
            _grant_scoped_access(self.job,[self.binary_root],
                                 [reviewed_file],sid,grants)
        self.assertEqual([c.args[0] for c in acl.call_args_list],
                         [self.binary_root,reviewed_file,self.job])
        self.assertEqual(grants,[(self.binary_root,True),
                                 (reviewed_file,False),(self.job,False)])
        self.assertEqual([c.args[2] for c in acl.call_args_list],
                         ["(OI)(CI)RX","R","(OI)(CI)M"])
        self.assertNotIn(self.program_files,[c.args[0] for c in acl.call_args_list])
        self.assertNotIn(self.root,[c.args[0] for c in acl.call_args_list])

    def test_failed_recursive_acl_is_registered_for_cleanup_and_not_ignored(self):
        from backend.nvp_g03_windows_appcontainer import (
            _grant_scoped_access,AppContainerFailure)
        grants=[]
        with patch("backend.nvp_g03_windows_appcontainer._acl",
                   side_effect=AppContainerFailure("denied")):
            with self.assertRaisesRegex(AppContainerFailure,"denied"):
                _grant_scoped_access(self.job,[self.binary_root],[],
                                     "S-1-15-2-1-2-3-4-5-6-7",grants)
        self.assertEqual(grants,[(self.binary_root,True)])

    def test_acl_denial_includes_original_path_and_native_diagnostic(self):
        from backend.nvp_g03_windows_appcontainer import _acl,AppContainerFailure
        from types import SimpleNamespace
        failure=SimpleNamespace(returncode=5,stdout="",stderr="Access is denied.")
        with patch("backend.nvp_g03_windows_appcontainer.subprocess.run",
                   return_value=failure):
            with self.assertRaises(AppContainerFailure) as observation:
                _acl(self.binary_root,"S-1-15-2-1-2-3-4-5-6-7","RX")
        self.assertIn(str(self.binary_root),str(observation.exception))
        self.assertIn("exit=5",str(observation.exception))
        self.assertIn("Access is denied.",str(observation.exception))

    def test_acl_success_summary_with_zero_failed_files_is_accepted(self):
        from backend.nvp_g03_windows_appcontainer import _acl
        from types import SimpleNamespace
        result=SimpleNamespace(returncode=0,stderr="",
            stdout="processed file: installed Blender\n"
                   "Successfully processed 4321 files; Failed processing 0 files\n")
        with patch("backend.nvp_g03_windows_appcontainer.subprocess.run",
                   return_value=result) as command:
            _acl(self.binary_root,"S-1-15-2-1-2-3-4-5-6-7","(OI)(CI)RX",
                 recursive=True)
        self.assertEqual(command.call_args.args[0],
            ["icacls.exe",str(self.binary_root),"/grant",
             "*S-1-15-2-1-2-3-4-5-6-7:(OI)(CI)RX","/T"])

    def test_acl_partial_or_unverifiable_result_is_refused_even_with_zero_exit(self):
        from backend.nvp_g03_windows_appcontainer import _acl,AppContainerFailure
        from types import SimpleNamespace
        cases=[
            (0,"Successfully processed 4 files; Failed processing 1 files",""),
            (0,"processed file: installed Blender",""),
            (0,"Successfully processed 0 files; Failed processing 0 files",""),
            (0,"Successfully processed 1 files; Failed processing 0 files",
               "Access is denied."),
            (5,"Successfully processed 1 files; Failed processing 0 files",""),
            (0,"Successfully processed 1 files; Failed processing 0 files\n"
               "Successfully processed 2 files; Failed processing 1 files",""),
        ]
        for rc,stdout,stderr in cases:
            with self.subTest(exit=rc,stdout=stdout,stderr=stderr),patch(
                    "backend.nvp_g03_windows_appcontainer.subprocess.run",
                    return_value=SimpleNamespace(returncode=rc,stdout=stdout,
                                                 stderr=stderr)):
                with self.assertRaisesRegex(AppContainerFailure,"DACL operation failed"):
                    _acl(self.binary_root,"S-1-15-2-1-2-3-4-5-6-7","RX")

    def test_appcontainer_environment_uses_os_paths_and_never_parent_secrets(self):
        import os
        from backend.nvp_g03_windows_appcontainer import _native_environment
        windows=self.root/"Windows"
        system=windows/"System32"
        local=self.root/"Account Local"
        profile=local/"Packages"/"NVP-Film-fixture"/"AC"
        system.mkdir(parents=True)
        profile.mkdir(parents=True)
        with patch.dict(os.environ,{"NVP_SECRET_API_KEY":"DO-NOT-COPY",
                    "PATH":r"C:\Untrusted",
                    "LOCALAPPDATA":r"C:\WrongAccount",
                    "SYSTEMROOT":r"C:\FakeWindows"}),patch(
                "backend.nvp_g03_windows_appcontainer._host_windows_paths",
                return_value=(str(windows),str(system),str(local))):
            block=_native_environment(None,self.job,profile,None)
            explicit=_native_environment(None,self.job,profile,{
                "sYsTeMrOoT":r"C:\FakeWindows",
                "localappdata":r"C:\WrongAccount",
                "PATH":r"C:\Untrusted",
                "TEMP":r"C:\WrongTemp",
                "BLENDER_USER_CONFIG":str(self.job/"config")})
        def entries(buffer):
            raw=buffer[:]
            self.assertTrue(raw.endswith("\0\0"))
            lines=raw.rstrip("\0").split("\0")
            self.assertEqual(lines,sorted(lines,key=str.upper))
            return dict(line.split("=",1) for line in lines)
        job=self.job.resolve()
        baseline={"SystemRoot":str(windows),"WINDIR":str(windows),
                  "SystemDrive":windows.drive,
                  "PATH":str(system)+";"+str(windows),
                  "LOCALAPPDATA":str(local),
                  "TEMP":str(job),"TMP":str(job),
                  "PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"}
        self.assertEqual(entries(block),baseline)
        self.assertEqual(entries(explicit),dict(baseline,
                         BLENDER_USER_CONFIG=str(job/"config")))

    def test_appcontainer_environment_refuses_unknown_duplicate_or_escaping_inputs(self):
        from backend.nvp_g03_windows_appcontainer import (
            _native_environment,AppContainerFailure)
        windows=self.root/"Windows"
        system=windows/"System32"
        local=self.root/"Local"
        profile=local/"Packages"/"NVP-Film-fixture"/"AC"
        system.mkdir(parents=True)
        profile.mkdir(parents=True)
        cases=[
            {"NVP_HOME":str(self.root)},
            {"PYTHONPATH":str(self.root)},
            {"BLENDER_USER_CONFIG":str(self.root)},
            {"Path":"x","PATH":"y"},
            {"PATH":"x\0y"},
            {"=C:":"C:\\"},
        ]
        with patch("backend.nvp_g03_windows_appcontainer._host_windows_paths",
                   return_value=(str(windows),str(system),str(local))):
            for env in cases:
                with self.subTest(env=env),self.assertRaises(AppContainerFailure):
                    _native_environment(None,self.job,profile,env)
            with self.assertRaisesRegex(AppContainerFailure,"paths unverified"):
                _native_environment(None,self.job,self.root,None)

    def test_native_environment_queries_actual_windows_locations(self):
        from backend.nvp_g03_windows_appcontainer import (
            _api,_host_windows_paths)
        kernel,_,_=_api()
        windows,system,local=map(Path,_host_windows_paths(kernel))
        for path in (windows,system,local):
            self.assertTrue(path.is_absolute())
            self.assertTrue(path.is_dir())
        self.assertTrue(system.resolve().is_relative_to(windows.resolve()))

    def test_launch_passes_explicit_native_unicode_environment(self):
        from backend.nvp_g03_windows_appcontainer import launch_appcontainer
        source=inspect.getsource(launch_appcontainer)
        self.assertIn("block=_native_environment(kernel,work,profile_folder,env)",source)
        self.assertIn("C.cast(block,W.LPVOID)",source)
        self.assertNotIn("dict(env or {})",source)
        self.assertIn("flags=0x4|0x08000000|0x400|0x80000",source)

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
