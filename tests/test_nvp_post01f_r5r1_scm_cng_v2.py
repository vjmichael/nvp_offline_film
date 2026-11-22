"""Portable crypto interoperability tests; no native Windows acceptance claims."""
import copy
import hashlib
import json
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec,utils
from backend.nvp_post01f_scm_cng_v2 import (FORMAT,KERNEL_FORMAT,
                                            verify_scm_cng_v2,InstalledScmCngV2Channel)

H='a'*64;P='b'*32;J='ltx_'+'c'*24

def canonical(o):return json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')

class ScmCngP256SourceContract(unittest.TestCase):
    def setUp(self):
        self.key=ec.generate_private_key(ec.SECP256R1())
        self.pub=self.key.public_key().public_bytes(serialization.Encoding.X962,
                 serialization.PublicFormat.UncompressedPoint)
        self.body={'appcontainer_sid_sha256':H,
            'appcontainer_zero_network_caps_verified':True,'bootstrap_sha256':H,
            'efs_verified':True,'job_id':J,'model_stack_sha256':H,
            'picture_sha256':H,'plan_sha256':H,'project_id':P,
            'receipt_nonce':'d'*32,'scm_service_custody_verified':True,
            'wfp_no_egress_verified':True,'worker_pid':1450}
        self.expected={k:self.body[k] for k in ('job_id','project_id','plan_sha256',
               'picture_sha256','bootstrap_sha256','model_stack_sha256',
               'appcontainer_sid_sha256','worker_pid')}
        self.used=set()
    def sign(self,body=None,wire=FORMAT):
        data={'format':wire,'body':body or self.body}
        signed=canonical(data)
        der=self.key.sign(hashlib.sha256(signed).digest(),
                 ec.ECDSA(utils.Prehashed(hashes.SHA256())))
        r,s=utils.decode_dss_signature(der)
        data['signature']=(r.to_bytes(32,'big')+s.to_bytes(32,'big')).hex()
        return canonical(data)
    def consume(self,job,nonce,digest):
        key=(job,nonce)
        if key in self.used:return False
        self.used.add(key);return True
    def verify(self,payload,**kw):
        return verify_scm_cng_v2(payload,pinned_p256_public=kw.get('pub',self.pub),
                expected=kw.get('expected',self.expected),consume_once=kw.get('consume',self.consume))
    def test_valid_synthetic_cng_p1363_signature_and_exact_identity(self):
        receipt=self.verify(self.sign())
        self.assertEqual(receipt['format'],KERNEL_FORMAT)
        self.assertTrue(receipt['scm_authenticated_receipt_verified'])
        self.assertEqual(receipt['picture_sha256'],H)
    def test_replay_rejected(self):
        doc=self.sign();self.verify(doc)
        with self.assertRaises(PermissionError):self.verify(doc)
    def test_malicious_worker_flags_cannot_replace_signature(self):
        raw=json.loads(self.sign())
        raw['body']['worker_pid']=555
        with self.assertRaises(PermissionError):self.verify(canonical(raw))
    def test_missing_native_security_flag_rejected_even_if_signed(self):
        for k in ('appcontainer_zero_network_caps_verified','efs_verified',
                  'scm_service_custody_verified','wfp_no_egress_verified'):
            bad=dict(self.body);bad[k]=False
            with self.subTest(k=k),self.assertRaises(PermissionError):self.verify(self.sign(bad))
    def test_wrong_model_project_worker_rejected_even_if_signed(self):
        for k,val in (('project_id','f'*32),('picture_sha256','f'*64),
                      ('worker_pid',99),('model_stack_sha256','f'*64)):
            bad=dict(self.body);bad[k]=val
            with self.subTest(k=k),self.assertRaises(PermissionError):self.verify(self.sign(bad))
    def test_wrong_public_key_or_corrupt_signature(self):
        doc=self.sign();other=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
          serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        with self.assertRaises(PermissionError):self.verify(doc,pub=other)
        value=json.loads(doc);value['signature']='0'*128
        with self.assertRaises(PermissionError):self.verify(canonical(value))
    def test_old_ed25519_wire_cannot_downgrade_v2(self):
        with self.assertRaises(PermissionError):self.verify(self.sign(wire='nvp.post01f.scm_authenticated_picture_receipt.v1'))
    def test_noncanonical_bounded_and_extra_fields_rejected(self):
        doc=self.sign()
        with self.assertRaises(PermissionError):self.verify(json.dumps(json.loads(doc)).encode())
        with self.assertRaises(PermissionError):self.verify(doc+b' '*9000)
        bad=dict(self.body);bad['extra']='data'
        with self.assertRaises(PermissionError):self.verify(self.sign(bad))
    def test_reject_invalid_raw_signature_shape(self):
        v=json.loads(self.sign());v['signature']='zz'*64
        with self.assertRaises(PermissionError):self.verify(canonical(v))
    def test_host_channel_refuses_desktop_owned_kernel(self):
        channel=InstalledScmCngV2Channel(pinned_p256_public=self.pub,
            receive_from_scm=lambda job,pid:self.sign(),consume_once=self.consume)
        with self.assertRaises(PermissionError):
            channel(dict(self.expected),{'format':'nvp.post01f.windows_appcontainer_kernel_exit.v1',
                       'kernel_job_tree_reaped':True,'release_fence_closed':True})
    def test_host_channel_positive_requires_scm_owner_proof(self):
        channel=InstalledScmCngV2Channel(pinned_p256_public=self.pub,
            receive_from_scm=lambda job,pid:self.sign(),consume_once=self.consume)
        kernel={'format':KERNEL_FORMAT,'scm_service_custody_verified':True,
                'kernel_job_tree_reaped':True,'release_fence_closed':True,
                'scm_owned_job':True,'worker_pid':1450,'appcontainer_sid_sha256':H}
        scope={k:v for k,v in self.expected.items() if k not in ('worker_pid','appcontainer_sid_sha256')}
        self.assertEqual(channel(scope,kernel)['job_id'],J)
    def test_absent_nonce_store_not_accepted(self):
        with self.assertRaises(PermissionError):self.verify(self.sign(),consume=lambda a,b,c:False)

if __name__=='__main__':unittest.main()
