"""R2 original Lu P-256 receipt wire and LTX job reservation source gates."""
from __future__ import annotations
from dataclasses import replace
import struct
import unittest
from backend.nvp_lu_gpu_stop_wire import (
    OriginalGpuStop, DOMAIN, METHOD, validate_receipt_shape)
from backend.nvp_lu_ltx_preallocation import (
    select_original_ltx_job, verify_scm_original_gpu_scope)

class GpuStopWireR2(unittest.TestCase):
    def setUp(self):
        self.record=OriginalGpuStop('gpu-abc123',
            'dxgi:luid_0x12345678_0xabcdef12_phys_0','nvp.film',
            'film-1','conversation-1','turn-1','task-1','epoch-1','session-1',
            42,123,57,890)
        self.job='ltx_'+'1'*24
        self.scope=dict(lease_ref=self.record.lease_ref,
            device_ref=self.record.device_ref,module_id='nvp.film',
            workspace_ref=self.record.workspace_ref,
            conversation_ref=self.record.conversation_ref,
            user_turn_ref=self.record.user_turn_ref,task_ref=self.record.task_ref,
            core_epoch_ref=self.record.core_epoch_ref,
            nvp_session_ref=self.record.nvp_session_ref,original_nvp_job_ref=self.job)

    def test_exact_lu_binary_layout_and_method(self):
        b=self.record.canonical_unsigned()
        self.assertTrue(b.startswith(DOMAIN));offset=len(DOMAIN)
        fields=[self.record.lease_ref,self.record.device_ref,'nvp.film',
            'film-1','conversation-1','turn-1','task-1','epoch-1','session-1',METHOD]
        for field in fields:
            n=b[offset];offset+=1
            self.assertEqual(b[offset:offset+n],field.encode());offset+=n
        self.assertEqual(b[offset:],struct.pack('<IQIQ',42,123,57,890))
        self.assertEqual(self.record.receipt_name(),'gpu-abc123.stop.v1')

    def test_wire_rejects_foreign_scope_and_noncanonical_names(self):
        for item in [replace(self.record, module_id='lu.ide'),
            replace(self.record, lease_ref='../escape'),
            replace(self.record, device_ref='\n'),
            replace(self.record, task_ref='x'*129),
            replace(self.record, worker_birth=0),
            replace(self.record, service_pid=2**32)]:
            with self.subTest(item=item),self.assertRaises(ValueError):item.canonical_unsigned()

    def test_signed_length_only_is_not_crypto_proof(self):
        payload=self.record.canonical_unsigned()+b'\x00'*64
        self.assertEqual(validate_receipt_shape(payload,self.record),b'\x00'*64)
        # A shape match never implies an installed CNG signature is valid.
        with self.assertRaises(ValueError):validate_receipt_shape(payload,replace(self.record,task_ref='other'))
        with self.assertRaises(ValueError):validate_receipt_shape(payload+b'e',self.record)

    def test_preallocate_accepts_only_native_scm_verified_original(self):
        observed=[]
        def owner(scope):observed.append(scope);return True
        actual=select_original_ltx_job(preallocated_job_id=self.job,
            verify_installed_reservation=owner,project_id='a'*32,
            take_sha256='b'*64,camera_id='cam1')
        self.assertEqual(actual,self.job);self.assertEqual(observed[0]['job_id'],self.job)
        self.assertEqual(observed[0]['take_sha256'],'b'*64)

    def test_preallocation_refuses_unverified_and_foreign_job(self):
        fields=dict(project_id='a'*32,take_sha256='b'*64,camera_id='cam1')
        for value,fn in [(self.job,None),(None,lambda _:True),
                         (self.job,lambda _:False),('ltx_'+'x'*24,lambda _:True)]:
            with self.subTest(value=value),self.assertRaises(PermissionError):
                select_original_ltx_job(preallocated_job_id=value,
                    verify_installed_reservation=fn,**fields)

    def test_original_worker_scope_exact(self):
        verify_scm_original_gpu_scope(self.scope,actual_ltx_job_id=self.job)
        with self.assertRaises(PermissionError):verify_scm_original_gpu_scope(self.scope,actual_ltx_job_id='ltx_'+'2'*24)
        for name,value in [('lease_ref','../../escape'),('module_id','lu.ide'),('core_epoch_ref','')]:
            other={**self.scope,name:value}
            with self.subTest(name=name),self.assertRaises(PermissionError):
                verify_scm_original_gpu_scope(other,actual_ltx_job_id=self.job)

    def test_nvp_installed_gpu_id_is_lu_compatible_dxgi_luid(self):
        from backend.nvp_lu_windows_gpu_binding import validate_installed_windows_luid
        self.assertEqual(validate_installed_windows_luid(self.record.device_ref),
                         self.record.device_ref)
        from backend.nvp_lu_gpu_yield import GpuYieldRefusal
        for name in ('gpu-0','dxgi:luid_0x12345678_0xabcdef12_phys_1',
                     'dxgi:luid_0x1234_0x5678_phys_0','../../gpu',None):
            with self.subTest(name=name),self.assertRaises(GpuYieldRefusal):
                validate_installed_windows_luid(name)

    def test_ephemeral_p256_raw_signature_matches_lu_worker_stop_envelope(self):
        """Source-only crypto fixture; no Windows installed key/SCM is claimed."""
        from hashlib import sha256
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from cryptography.hazmat.primitives import hashes
        import struct
        private=ec.generate_private_key(ec.SECP256R1())
        expected=self.record.canonical_unsigned()
        der=private.sign(expected,ec.ECDSA(hashes.SHA256()))
        r,s=utils.decode_dss_signature(der)
        raw=r.to_bytes(32,'big')+s.to_bytes(32,'big')
        self.assertEqual(len(raw),64)
        envelope=expected+raw
        self.assertEqual(validate_receipt_shape(envelope,self.record),raw)
        signature_der=utils.encode_dss_signature(
            int.from_bytes(raw[:32],'big'),int.from_bytes(raw[32:],'big'))
        private.public_key().verify(signature_der,expected,ec.ECDSA(hashes.SHA256()))
        with self.assertRaises(Exception):
            private.public_key().verify(signature_der,
                expected+b'forged',ec.ECDSA(hashes.SHA256()))

    def test_original_scm_drains_failure_before_gpu_all_clear(self):
        """Film failure must still permit safe verified GPU cleanup, not film approval."""
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        service=root/'tools/nvp_post01f_windows_scm_ltx_broker.cpp'
        source=(service if service.is_file() else root/'docs/NVP_INT_LU_01E_GPU_01_R2_SCM_SOURCE_DIFF.patch').read_text()
        self.assertIn('const bool worker_succeeded=', source)
        self.assertIn('worker_succeeded?0:13',source)
        self.assertIn('must(drained,"SCM Job still has child processes after 10s drain")',source)
        self.assertLess(source.index('issue_after_original_job_empty('),
                        source.index('must(worker_succeeded,'))

    def test_native_issuer_source_no_user_authorization_substitute(self):
        from pathlib import Path
        source=(Path(__file__).resolve().parents[1]/'tools/nvp_int_lu_gpu_stop_issuer.hpp').read_text()
        for required in ('LU_NVP_GPU_JOB_EMPTY_V1','WINDOWS_JOB_ACTIVE_ZERO_V1',
                         'JobObjectBasicAccountingInformation','account.ActiveProcesses==0',
                         'NCRYPT_MACHINE_KEY_FLAG','GetProcessTimes',
                         'CREATE_NEW','FILE_FLAG_WRITE_THROUGH',
                         'SDDL_REVISION_1','NCRYPT_EXPORT_POLICY_PROPERTY'):
            self.assertIn(required,source)

if __name__=='__main__':unittest.main()
