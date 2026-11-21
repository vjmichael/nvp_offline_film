"""Authenticated host-side SCM envelope reader, using SYNTHETIC signing keys."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.nvp_post01f_scm_picture_result import (
    SCM_FORMAT, verify_signed_scm_picture_result,
)

class SignedNativeScmReceipt(unittest.TestCase):
    def setUp(self):
        self.secret=Ed25519PrivateKey.generate() # Synthetic source test ONLY.
        self.public=self.secret.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
        self.body={'job_id':'ltx_'+'a'*24,'project_id':'b'*32,
            'plan_sha256':'c'*64,'picture_sha256':'d'*64,
            'bootstrap_sha256':'e'*64,'model_stack_sha256':'f'*64,
            'worker_pid':19320,'appcontainer_sid_sha256':'a'*64,
            'appcontainer_zero_network_caps_verified':True,
            'wfp_no_egress_verified':True,'efs_verified':True,
            'scm_service_custody_verified':True,'receipt_nonce':'9'*32}
        self.consume=lambda *a:True
        self.envelope=self.sign()

    def sign(self):
        raw=json.dumps({"format":SCM_FORMAT,"body":self.body},sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
        return {'format':SCM_FORMAT,'body':dict(self.body),
                'signature':self.secret.sign(raw).hex()}

    def verify(self, **kw):
        opts={'pinned_public_key':self.public,'expected':dict(self.body),
              'consume_once':self.consume}
        opts.update(kw)
        return verify_signed_scm_picture_result(self.envelope,**opts)

    def test_signed_exact_scoped_result_is_quarantined_only(self):
        row=self.verify()
        self.assertTrue(row['scm_authenticated_receipt_verified'])
        self.assertNotIn('creator_approved',row)

    def test_mutated_picture_signature_refuses(self):
        self.envelope['body']['picture_sha256']='0'*64
        with self.assertRaises(PermissionError):self.verify()

    def test_valid_signature_foreign_pid_refuses(self):
        self.body['worker_pid']+=1
        self.envelope=self.sign()
        with self.assertRaises(PermissionError):self.verify(expected=dict(self.body,worker_pid=19320))

    def test_no_wfp_proof_refuses_even_with_signature(self):
        self.body['wfp_no_egress_verified']=False
        self.envelope=self.sign()
        with self.assertRaises(PermissionError):self.verify()

    def test_replayed_nonce_refuses(self):
        with self.assertRaises(PermissionError):self.verify(consume_once=lambda *a:False)

    def test_unreviewed_verifier_key_refuses(self):
        with self.assertRaises(PermissionError):self.verify(pinned_public_key=b'0'*32)

class SignedScmChannelGlue(unittest.TestCase):
    def test_signed_host_to_scm_response_bound_to_kernel_exit(self):
        from backend.nvp_post01f_scm_picture_result import SignedScmPictureWitness
        base=SignedNativeScmReceipt()
        base.setUp()
        scope={k:base.body[k] for k in ('job_id','project_id','plan_sha256',
            'bootstrap_sha256','model_stack_sha256','picture_sha256')}
        kernel={"format":"nvp.post01f.windows_appcontainer_kernel_exit.v1",
                "process_tree_custody_verified":True,"kernel_job_tree_reaped":True,
                "release_fence_closed":True,"worker_pid":base.body['worker_pid'],
                "appcontainer_sid_sha256":base.body['appcontainer_sid_sha256']}
        replay=set()
        def consume(job,nonce,signature_digest):
            marker=(job,nonce,signature_digest)
            if marker in replay:return False
            replay.add(marker)
            return True
        def receive(job,pid):
            self.assertEqual(job,base.body['job_id'])
            self.assertEqual(pid,base.body['worker_pid'])
            return json.dumps(base.sign()).encode()
        reader=SignedScmPictureWitness(
            pinned_public_key=base.public,receive_from_scm=receive,
            consume_once=consume)
        verified=reader(scope,kernel)
        self.assertEqual(verified['picture_sha256'],scope['picture_sha256'])
        with self.assertRaises(PermissionError):reader(scope,kernel)
        with self.assertRaises(PermissionError):reader(scope,dict(kernel,release_fence_closed=False))
