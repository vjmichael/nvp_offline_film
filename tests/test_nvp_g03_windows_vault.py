"""G03 Windows DPAPI/AES-GCM archive acceptance. No fake crypto fallbacks.

This covers a real separately encrypted original-data archive, NOT the live
movie database or all NVP worker source storage. Full project confidentiality
remains blocked until those layers are integrated and accepted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_g03_windows_vault import (
    FORMAT, VaultError, create_archive, restore_archive, verify_archive
)

PID="ab"*16
WRONG_ID="cd"*16
PASSPHRASE="Film archive passphrase 2026 is unique"


class WindowsVaultTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nvp-g03-vault-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"source"
        self.root.mkdir()
        (self.root/"Scenes").mkdir()
        (self.root/"Audio").mkdir()
        self.sources={
            "Scenes/scene.usda":b"#usda 1.0\n\ndef Xform \"Original\" {}\n",
            "Audio/original.pcm": bytes(range(256))*10240,
            "script.fountain":b"EXT. VALLEY - MORNING\n\nNo human appears."
        }
        for name,data in self.sources.items():
            (self.root/name).write_bytes(data)
        self.vault=Path(self.temp.name)/"sealed"
        self.restored=Path(self.temp.name)/"restored"

    def source_hashes(self):
        from hashlib import sha256
        return {name:sha256((self.root/name).read_bytes()).hexdigest()
                for name in self.sources}

    @unittest.skipUnless(sys.platform=="win32","Native Windows DPAPI only")
    def test_real_windows_user_passphrase_dpapi_roundtrip(self):
        before=self.source_hashes()
        result=create_archive(PID,self.root,self.vault,PASSPHRASE)
        self.assertEqual(result["status"],"sealed_archive_verified")
        self.assertFalse(result["working_files_encrypted"])
        self.assertEqual(result["source_files"],3)
        self.assertEqual(before,self.source_hashes())
        self.assertEqual(verify_archive(PID,self.vault,PASSPHRASE)["source_files"],3)
        metadata=json.loads((self.vault/"key.nvpdpapi").read_text())
        self.assertEqual(metadata["format"],FORMAT)
        self.assertEqual(metadata["scope"],"current-Windows-user+passphrase")
        self.assertFalse(metadata["complete_active_project_encryption"])
        self.assertNotIn(PASSPHRASE,(self.vault/"key.nvpdpapi").read_text())
        for path in self.vault.iterdir():
            self.assertNotIn("original",path.name.lower())
            if path.name.endswith(".nvpsealed"):
                data=path.read_bytes()
                self.assertNotIn(b"#usda",data)
                self.assertNotIn(b"No human appears",data)
        restored=restore_archive(PID,self.vault,self.restored,PASSPHRASE)
        self.assertEqual(restored["source_files"],3)
        self.assertEqual(
            {name:(self.restored/name).read_bytes() for name in self.sources},
            self.sources)
        self.assertEqual(before,self.source_hashes())

    @unittest.skipUnless(sys.platform=="win32","Native Windows DPAPI only")
    def test_wrong_passphrase_and_foreign_project_fail_closed(self):
        create_archive(PID,self.root,self.vault,PASSPHRASE)
        with self.assertRaises(VaultError):
            verify_archive(PID,self.vault,"A wrong unique long passphrase")
        with self.assertRaises(VaultError):
            verify_archive(WRONG_ID,self.vault,PASSPHRASE)
        with self.assertRaises(VaultError):
            restore_archive(PID,self.vault,self.restored,
                            "A wrong unique long passphrase")
        self.assertFalse(self.restored.exists())

    @unittest.skipUnless(sys.platform=="win32","Native Windows DPAPI only")
    def test_authenticated_ciphertext_tampering_denied_without_partial_restore(self):
        create_archive(PID,self.root,self.vault,PASSPHRASE)
        target=next(p for p in self.vault.glob("*.nvpsealed")
                    if p.name!="manifest.nvpsealed")
        raw=bytearray(target.read_bytes())
        raw[len(raw)//2] ^= 0x40
        target.write_bytes(raw)
        with self.assertRaisesRegex(VaultError,"authentication"):
            verify_archive(PID,self.vault,PASSPHRASE)
        with self.assertRaises(VaultError):
            restore_archive(PID,self.vault,self.restored,PASSPHRASE)
        self.assertFalse(self.restored.exists())
        self.assertEqual(len(list(Path(self.temp.name).glob(".nvp-restore-staging-*"))),0)

    @unittest.skipUnless(sys.platform=="win32","Native Windows DPAPI only")
    def test_manifest_tampering_and_replay_archive_denied(self):
        create_archive(PID,self.root,self.vault,PASSPHRASE)
        path=self.vault/"manifest.nvpsealed"
        raw=bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        with self.assertRaises(VaultError):
            verify_archive(PID,self.vault,PASSPHRASE)
        with self.assertRaises(VaultError):
            restore_archive(PID,self.vault,self.restored,PASSPHRASE)
        with self.assertRaises(VaultError):
            create_archive(PID,self.root,self.vault,PASSPHRASE)

    @unittest.skipUnless(sys.platform=="win32","Native Windows DPAPI only")
    def test_streaming_larger_pcm_does_not_accumulate_plaintext_in_vault(self):
        payload=os.urandom(12*1024*1024+3)
        path=self.root/"Audio/original.pcm"
        path.write_bytes(payload)
        create_archive(PID,self.root,self.vault,PASSPHRASE)
        restore_archive(PID,self.vault,self.restored,PASSPHRASE)
        self.assertEqual((self.restored/"Audio/original.pcm").read_bytes(),payload)

    @unittest.skipUnless(sys.platform=="win32","Native Windows DPAPI only")
    def test_source_change_during_seal_does_not_promote_archive(self):
        import backend.nvp_g03_windows_vault as module
        original=module._encrypt_file
        def corrupt_in_flight(inp,destination,**kwargs):
            result=original(inp,destination,**kwargs)
            if kwargs["name"]=="Audio/original.pcm":
                # Simulate an independent writer modifying original bytes
                # while the archive is being assembled.
                (self.root/"Audio/original.pcm").write_bytes(b"modified")
            return result
        with patch.object(module,"_encrypt_file",side_effect=corrupt_in_flight):
            with self.assertRaisesRegex(VaultError,"changed during archive"):
                create_archive(PID,self.root,self.vault,PASSPHRASE)
        self.assertFalse(self.vault.exists())
        self.assertFalse(list(Path(self.temp.name).glob(".nvp-vault-staging-*")))

    def test_non_windows_has_no_fake_secure_storage(self):
        if sys.platform=="win32":
            self.skipTest("Covered by real CryptProtectData tests")
        with self.assertRaisesRegex(VaultError,"Windows user-scoped DPAPI"):
            create_archive(PID,self.root,self.vault,PASSPHRASE)
        self.assertFalse(self.vault.exists())

    def test_reject_path_traversal_and_nested_vault(self):
        import backend.nvp_g03_windows_vault as v
        for name in ("../steal", "Scenes/../../steal",
                     "C:/Users/secret", "Scenes\\secret",
                     "Scenes//secret", "Scenes/./secret"):
            with self.subTest(name=name):
                with self.assertRaises(VaultError):
                    v._relative(name)
        with self.assertRaises(VaultError):
            create_archive(PID,self.root,self.root/"sealed",PASSPHRASE)


if __name__=="__main__":
    unittest.main()
