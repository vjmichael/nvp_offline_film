"""R5-R2 source contracts: no desktop FFmpeg bypass or Windows path-alias false failures.

These tests are source checks, not a substitute for Windows kernel/SCM validation.
"""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class NativeMediaLaunchRepairTests(unittest.TestCase):
    def test_broker_nested_codec_sites_are_finite_and_guarded(self):
        tree=ast.parse((ROOT/'backend/nvp_post01f_ltx_broker.py').read_text())
        sites=[]
        for f in tree.body:
            if not isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef)):
                continue
            for call in ast.walk(f):
                if (isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute)
                    and isinstance(call.func.value,ast.Name)
                    and call.func.value.id=='subprocess' and call.func.attr=='run'):
                    guard=[g for g in ast.walk(f)
                          if isinstance(g,ast.Call) and isinstance(g.func,ast.Name)
                          and g.func.id=='require_current_scm_lowbox_job'
                          and g.lineno<call.lineno]
                    self.assertEqual(len(guard),1, f.name)
                    sites.append(f.name)
        self.assertEqual(sorted(sites),['_probe_media','conform_picture_only'])

    def test_host_independent_verifier_uses_release_owned_media_runner(self):
        tree=ast.parse((ROOT/'backend/nvp_post01f_picture_verify.py').read_text())
        owned=0
        for call in ast.walk(tree):
            if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute):
                self.assertFalse(isinstance(call.func.value,ast.Name) and
                   call.func.value.id=='subprocess' and call.func.attr in ('run','Popen'))
            if (isinstance(call,ast.Call) and isinstance(call.func,ast.Name)
                and call.func.id=='run_owned_subprocess'):
                owned+=1
        self.assertEqual(owned,2)

    def test_original_w1g_adapter_signature_never_receives_shell_override(self):
        # Original run_owned_subprocess has no shell parameter. Its internal
        # original Windows Job path is mandatory; an unsupported keyword
        # would fail before any authentic frame/PTS readback could occur.
        tree=ast.parse((ROOT/'backend/nvp_post01f_picture_verify.py').read_text())
        allowed={'cwd','timeout','check','capture_output','stdin','stdout',
                 'stderr','input','text','encoding','errors'}
        observed=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='run_owned_subprocess':
                names={kw.arg for kw in node.keywords}
                self.assertTrue(names <= allowed, 'Original W1-G argument contract changed')
                self.assertNotIn('shell',names)
                observed.append(names)
        self.assertEqual(len(observed),2)

    def test_windows_lowbox_guard_checks_kernel_job_and_token(self):
        source=(ROOT/'backend/nvp_post01f_scm_lowbox_guard.py').read_text()
        for token in ('IsProcessInJob','OpenProcessToken','GetTokenInformation',
                      'TokenIsAppContainer = 29'):
            self.assertIn(token,source)
        self.assertNotIn('NVP_PUBLIC_SYNTHETIC_CI',source)

    def test_portable_only_no_fabricated_scm_custody(self):
        import os
        from backend.nvp_post01f_scm_lowbox_guard import require_current_scm_lowbox_job
        if os.name!='nt':
            self.assertIsNone(require_current_scm_lowbox_job())
        else:
            with self.assertRaises(PermissionError):
                require_current_scm_lowbox_job()


if __name__=='__main__': unittest.main()
