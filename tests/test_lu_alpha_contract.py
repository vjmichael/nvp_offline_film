"""NVP B4: verify alpha source evidence and Lu passive status never grants control."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import nvp_lu_alpha_contract as lu
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


def sample():
    return ResourceSnapshot(1,32768,24000,0,())


def fake_lu_source(root):
    paths={
        "src-tauri/lu-core/proto/lu/v1/core.proto":
            b"message InferenceFrame {\n}\nmessage InferenceResourceUsage {\n}\n",
        "src-tauri/lu-core/src/persistent_llama_backend.rs":
            b'Command::new("pinned");\n.arg("--n-gpu-layers")\n',
        "src-tauri/lu-core/examples/persistent_llama_smoke.rs":
            b"LU_PERSISTENT_GGUF_TWO_TURNS_PASS\n",
        "lu-desktop/src-tauri/src/lib.rs":
            b"fn lu_status(\nasync fn lu_load_model(\nasync fn lu_unload_model(\nPersistentLlamaBackend\n",
    }
    for path,raw in paths.items():
        f=Path(root)/path
        f.parent.mkdir(parents=True,exist_ok=True)
        f.write_bytes(raw)
    return {path:lu.git_blob_sha1(raw) for path,raw in paths.items()}


class SourceContractTests(unittest.TestCase):
    def test_git_blob_digest_matches_git_algorithm(self):
        raw=b"hello\n"
        self.assertEqual(lu.git_blob_sha1(raw),
            hashlib.sha1(b"blob 6\x00hello\n").hexdigest())

    def test_checked_source_does_not_claim_installed_alpha_or_socket(self):
        with TemporaryDirectory() as root:
            sealed=fake_lu_source(root)
            with patch.dict(lu.LU_ALPHA_BLOBS,sealed,clear=True):
                report=lu.inspect_lu_alpha_source(root)
            self.assertTrue(report["source_contract_matched"])
            self.assertFalse(report["installed_binary_proven"])
            self.assertFalse(report["af_unix_external_inference_supported"])
            self.assertFalse(report["safe_to_control_lu_model"])
            self.assertFalse(report["lu_real_inference_proven_by_this_gate"])

    def test_changed_source_fails_closed(self):
        with TemporaryDirectory() as root:
            sealed=fake_lu_source(root)
            (Path(root)/"src-tauri/lu-core/proto/lu/v1/core.proto").write_text(
                "message InferenceFrame { changed }\n",encoding="utf8")
            with patch.dict(lu.LU_ALPHA_BLOBS,sealed,clear=True):
                with self.assertRaises(RuntimeError):
                    lu.inspect_lu_alpha_source(root)

    def test_missing_core_or_symlink_rejected(self):
        with TemporaryDirectory() as root:
            sealed=fake_lu_source(root)
            (Path(root)/"src-tauri/lu-core/src/persistent_llama_backend.rs").unlink()
            with patch.dict(lu.LU_ALPHA_BLOBS,sealed,clear=True):
                with self.assertRaises(RuntimeError):
                    lu.inspect_lu_alpha_source(root)
        with TemporaryDirectory() as root:
            sealed=fake_lu_source(root)
            target=Path(root)/"src-tauri/lu-core/src/persistent_llama_backend.rs"
            backup=Path(root)/"original.rs"
            backup.write_bytes(target.read_bytes())
            target.unlink()
            try:
                target.symlink_to(backup)
            except (OSError,NotImplementedError):
                self.skipTest("OS does not permit creating a test symlink")
            with patch.dict(lu.LU_ALPHA_BLOBS,sealed,clear=True):
                with self.assertRaises(RuntimeError):
                    lu.inspect_lu_alpha_source(root)

    def test_unrecognized_source_does_not_fallback_to_other_branch(self):
        with TemporaryDirectory() as root:
            sealed=fake_lu_source(root)
            # Experimental AF_UNIX crate should not grant authority to
            # execute inference from the separate accepted desktop.
            (Path(root)/"src-tauri/lu-ipc-common/src").mkdir(parents=True)
            with patch.dict(lu.LU_ALPHA_BLOBS,sealed,clear=True):
                report=lu.inspect_lu_alpha_source(root)
            self.assertFalse(report["af_unix_external_inference_supported"])


class PassiveStatusTests(unittest.TestCase):
    def test_lu_internal_status_is_observed_without_rss_reservation(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            statuses=iter([
                {"modelRef":None,"sessionId":None,"generationId":None,
                 "phase":"Idle","pid":None},
                {"modelRef":"m-0123456789abcdef0123456789abcdef",
                 "sessionId":"s-1234567890abcdef1234567890abcdef",
                 "generationId":None,"phase":"Ready","pid":501},
                {"modelRef":"m-0123456789abcdef0123456789abcdef",
                 "sessionId":"s-1234567890abcdef1234567890abcdef",
                 "generationId":"g-1234567890abcdef1234567890abcdef",
                 "phase":"Generating","pid":501}
            ])
            observer=lu.PassiveLuStatusObserver(ledger,read_status=lambda:next(statuses))
            results=[observer.observe(),observer.observe(),observer.observe()]
            self.assertEqual([x["native_phase"] for x in results],
                             ["Idle","Ready","Generating"])
            self.assertTrue(all(x["progress_fraction"] is None for x in results))
            self.assertTrue(all(not x["model_loading_authorized"] for x in results))
            self.assertTrue(all(not x["model_unloading_authorized"] for x in results))
            self.assertTrue(all(not x["nvp_owned"] for x in results))
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            recorded=ledger.get_task("lu_alpha_observation")
            self.assertEqual(recorded["state"],"OBSERVING")
            self.assertEqual(recorded["phase"],"generating")
            self.assertIsNone(recorded["completed_fraction"])

    def test_invalid_external_status_cannot_create_false_progress(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            fake=lambda:{"modelRef":"foreign/model.gguf","sessionId":"session",
                         "generationId":None,"phase":"Ready","pid":"not-a-pid"}
            observer=lu.PassiveLuStatusObserver(ledger,read_status=fake)
            with self.assertRaises(ValueError):
                observer.observe()
            self.assertIsNone(ledger.get_task("lu_alpha_observation"))

    def test_status_validation_rejects_missing_identity_or_arbitrary_phase(self):
        base={"modelRef":None,"sessionId":None,"generationId":None,
              "phase":"Idle","pid":None}
        bad=[
            dict(base,phase="Ready"),
            dict(base,phase="Generating",modelRef="m-123"),
            dict(base,phase="loading_model"),
            dict(base,phase="Idle",modelRef="m-123"),
            dict(base,phase="Idle",pid=-1),
            dict(base,phase="Idle",pid=True),
            dict(base,phase="Idle",extra="foreign"),
        ]
        for payload in bad:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    lu.LuRuntimeView.from_trusted_host(payload)


if __name__=="__main__":
    unittest.main()
