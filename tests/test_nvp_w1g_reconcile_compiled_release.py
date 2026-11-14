"""Signed native worker candidate reconciliation contracts; entirely synthetic bytes.

The signed reviews in this test use throwaway ephemeral Ed25519 keys. They
verify cryptographic binding, NOT actual creator redistribution permissions or
a production Windows install. Real compiled execution runs in the separate
native Windows/Linux workflow and is not asserted by these synthetic PEs.
"""
import base64
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from test_nvp_e2e01e_package_guard import make_pe
from tools.nvp_w1g_native_package import _inventory,FORMAT as RELEASE_FORMAT
from tools.nvp_w1g_reconcile_compiled_release import (
    reconcile_original_native_bytes,reconcile_independently_signed_release,
)
from tools.nvp_w1g_worker_package import (
    ROLES,FORMAT as ROSTER_FORMAT,provision_native_workers,
)
from tools.nvp_w1g_native_dependencies import FORMAT as WHEEL_FORMAT
from tools.nvp_w1g_reviewed_release import (
    FORMAT as REVIEW_FORMAT,_canonical,license_review_digest,
)
from tools.nvp_w1g_signed_wheelhouse import unsigned_wheelhouse_review_candidate


class SignedFirstPartyByteReconciliationContracts(unittest.TestCase):
    def prepare(self,root):
        compiled=root/"compiled";compiled.mkdir()
        staged=root/"staged";staged.mkdir()
        workers=[]
        for role in sorted(ROLES):
            path=compiled/(role+".exe")
            make_pe(path,subsystem=3)
            workers.append({"role":role,"filename":path.name,
                            "sha256":sha256(path.read_bytes()).hexdigest()})
        roster={"format":ROSTER_FORMAT,"platform":"windows-amd64","workers":workers}
        source=Path(__file__).resolve().parents[1]/"native"/"w1g_first_party_worker.cpp"
        (compiled/"build-candidate.json").write_text(json.dumps({
            "status":"FIVE_REAL_NATIVE_EXECUTABLES_COMPILED_CANDIDATE",
            "native_executables_compiled":True,"production_native_roles_complete":False,
            "source_sha256":sha256(source.read_bytes()).hexdigest(),
            "role_count":5,"roster":roster,
        }),encoding="utf8")
        provision_native_workers(compiled,staged,roster)
        make_pe(staged/"NVP.exe")
        receipt={
            "format":RELEASE_FORMAT,"platform":"windows-amd64",
            "app_sha256":sha256((staged/"NVP.exe").read_bytes()).hexdigest(),
            "files":_inventory(staged),"native_worker_manifest_verified":True,
        }
        return compiled,staged,receipt

    def sign_ephemeral(self,receipt,key):
        payload={
            "format":REVIEW_FORMAT,
            "platform":"windows-amd64",
            "payload_sha256":license_review_digest(receipt),
            "reviewer_reference":"Ephemeral compiler fixture reviewer",
            "reviewed_artifacts":[
                {"file":name,"sha256":row["sha256"],"spdx_license":"MIT",
                 "redistribution_reference":"Only a fixture, not a legal grant"}
                for name,row in sorted(receipt["files"].items())],
        }
        return {"payload":payload,"signature_base64":base64.b64encode(
            key.sign(_canonical(payload))).decode("ascii")}

    def wheel(self,root):
        wheelhouse=root/"wheelhouse";wheelhouse.mkdir()
        file=wheelhouse/"demo_pkg-1.0-py3-none-any.whl"
        with zipfile.ZipFile(file,"w") as z:
            z.writestr("demo_pkg-1.0.dist-info/METADATA",
                       "Metadata-Version: 2.1\nName: demo-pkg\nVersion: 1.0\n")
        lock={"format":WHEEL_FORMAT,"platform":"windows-amd64","wheels":[{
            "name":"demo-pkg","version":"1.0","filename":file.name,
            "sha256":sha256(file.read_bytes()).hexdigest(),
            "license_review":"Only a fixture, not a legal grant",
        }]}
        return wheelhouse,lock

    def test_compiled_sha_exactness_and_external_signature_join(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
        with TemporaryDirectory() as td:
            root=Path(td)
            compiled,staged,receipt=self.prepare(root)
            verified=reconcile_original_native_bytes(compiled,staged)
            self.assertEqual(len(verified["worker_sha256_by_role"]),5)
            self.assertFalse(verified["trusted_external_compiler_provenance_signature_verified"])
            private=Ed25519PrivateKey.generate()
            public=private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
            signed_package=self.sign_ephemeral(receipt,private)
            wheelhouse,lock=self.wheel(root)
            signed_wheels=unsigned_wheelhouse_review_candidate(
                lock,wheelhouse,platform="windows-amd64")["signed_review"]
            wheel_payload=signed_wheels["payload"]
            wheel_payload["reviewer_reference"]="Ephemeral offline reviewer fixture"
            for item in wheel_payload["reviewed_artifacts"]:
                item["spdx_license"]="MIT"
                item["redistribution_reference"]="Only a fixture, not a legal grant"
            signed_wheels["signature_base64"]=base64.b64encode(
                private.sign(_canonical(wheel_payload))).decode("ascii")
            result=reconcile_independently_signed_release(
                compiled=compiled,staged=staged,installed_receipt=receipt,
                signed_release_review=signed_package,offline_lock=lock,
                wheelhouse=wheelhouse,signed_wheel_review=signed_wheels,
                pinned_external_reviewer_public_key=public)
            self.assertEqual(result["status"],
                             "NVP_W1G_SIGNED_RELEASE_AND_OFFLINE_BYTES_RECONCILED")
            self.assertTrue(result["external_release_and_offline_signatures_verified"])
            self.assertFalse(result["full_native_film_role_completeness_proven"])
            self.assertFalse(result["creator_authorization_obtained"])
            self.assertFalse(result["physical_efs_recovery_verified"])
            # Same review cannot be reused for a modified original worker.
            target=staged/"_internal"/"nvp_workers"/"audio.exe"
            target.write_bytes(target.read_bytes()+b"x")
            with self.assertRaises((PermissionError,RuntimeError)):
                reconcile_independently_signed_release(
                    compiled=compiled,staged=staged,installed_receipt=receipt,
                    signed_release_review=signed_package,offline_lock=lock,
                    wheelhouse=wheelhouse,signed_wheel_review=signed_wheels,
                    pinned_external_reviewer_public_key=public)

    def test_missing_or_wrong_native_source_is_refused_before_any_review(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            compiled,staged,_=self.prepare(root)
            candidate=compiled/"build-candidate.json"
            doc=json.loads(candidate.read_text("utf8"))
            doc["source_sha256"]="0"*64
            candidate.write_text(json.dumps(doc),encoding="utf8")
            with self.assertRaisesRegex(PermissionError,"source identity"):
                reconcile_original_native_bytes(compiled,staged)


if __name__=="__main__":
    unittest.main()
