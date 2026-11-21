"""POST-01F R5-R2-R2 Windows extended startup wire contract.

Static source guard only; genuine MSVC compilation and SCM/lowbox execution
MUST separately be observed on an unchanged GitHub checkout.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "tools/nvp_post01f_windows_scm_ltx_broker.cpp"

class NativeScmExtendedStartupContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CPP.read_text(encoding="utf8")

    def test_extended_startup_owns_attribute_list(self):
        self.assertIn("STARTUPINFOEXW start{};", self.source)
        self.assertIn("start.StartupInfo.cb=sizeof(start);", self.source)
        self.assertIn("start.lpAttributeList=attrs;", self.source)
        self.assertNotIn("start.StartupInfo.lpAttributeList", self.source)
        self.assertEqual(self.source.count("start.lpAttributeList=attrs;"), 1)

    def test_createprocess_receives_extended_startup_and_retains_native_lowbox_flag(self):
        code = self.source
        setup=code.index("start.lpAttributeList=attrs;")
        creation=code.index("BOOL started=CreateProcessW(",setup)
        cleanup=code.index("DeleteProcThreadAttributeList(attrs);",creation)
        self.assertLess(setup,creation)
        self.assertLess(creation,cleanup)
        chunk=code[creation:cleanup]
        self.assertIn("EXTENDED_STARTUPINFO_PRESENT|CREATE_SUSPENDED|CREATE_NO_WINDOW",chunk)
        self.assertIn("&start.StartupInfo,&pi",chunk)
        self.assertIn("AssignProcessToJobObject(h.job,h.process)",code)
        self.assertIn("assigned_token_appcontainer(h.process,h.sid)",code)

    def test_does_not_weaken_native_positive_receipt_requirements(self):
        code = self.source
        for token in (
            "nvp_post01f_creator::verify(approved,approval_file,creator_cert)",
            "add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_CONNECT_V4)",
            "add_wfp_block(h.wfp,h.sid,FWPM_LAYER_ALE_AUTH_CONNECT_V6)",
            "zero_active_processes(h.job)",
            "NCryptOpenKey(provider,&key,KEY_NAME,0,NCRYPT_MACHINE_KEY_FLAG)",
            "durable_new(receipt,envelope)",
            "encrypted(picture);encrypted(result)",
        ):
            with self.subTest(contract=token):
                self.assertIn(token,code)

if __name__ == "__main__":
    unittest.main()
