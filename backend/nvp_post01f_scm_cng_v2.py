"""Windows SCM-owned LTX result witness, wire v2 / CNG P-256.

This is a *reader*, not a signer and not an SCM process. It accepts a signed
result only from an independently installed SCM transport, with a separate
host-side durable one-use nonce database. No trusted signer/key is bundled.

V1 Ed25519 envelopes remain for historical *source tests*; production v2
explicitly refuses them, and never borrows desktop AppContainer custody.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

FORMAT = 'nvp.post01f.scm_cng_p256_picture_result.v2'
KERNEL_FORMAT = 'nvp.post01f.scm_owned_kernel_result.v2'
SHA = re.compile(r'[a-f0-9]{64}\Z')
JOB = re.compile(r'ltx_[0-9a-f]{24}\Z')
PROJECT = re.compile(r'[a-f0-9]{32}\Z')
FIELDS = frozenset((
    'appcontainer_sid_sha256', 'appcontainer_zero_network_caps_verified',
    'bootstrap_sha256', 'efs_verified', 'job_id', 'model_stack_sha256',
    'picture_sha256', 'plan_sha256', 'project_id', 'receipt_nonce',
    'scm_service_custody_verified', 'wfp_no_egress_verified', 'worker_pid',
))
IDENTITIES = frozenset(('job_id','project_id','plan_sha256','picture_sha256',
                        'bootstrap_sha256','model_stack_sha256',
                        'appcontainer_sid_sha256','worker_pid'))
BOOLEANS = frozenset(('appcontainer_zero_network_caps_verified',
                      'efs_verified','scm_service_custody_verified',
                      'wfp_no_egress_verified'))


def _canonical(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def verify_scm_cng_v2(payload: bytes, *, pinned_p256_public: bytes,
                      expected: dict, consume_once) -> dict:
    """Authenticate one exact service-issued witness and consume its nonce.

    The 65-byte uncompressed SEC1 P-256 key must be pinned by the **installed
    host** independently of the worker and result. The signature is CNG's raw
    IEEE-P1363 r||s representation (64 bytes), *not* ASN.1 DER.
    """
    if type(payload) is not bytes or not 2 <= len(payload) <= 8192 or not callable(consume_once):
        raise PermissionError('Expected a bounded independent SCM v2 response')
    if (type(pinned_p256_public) is not bytes or len(pinned_p256_public)!=65 or
            pinned_p256_public[0]!=4 or type(expected) is not dict or
            set(expected)!=IDENTITIES):
        raise PermissionError('Missing installed host trust or exact expected scope')
    try:
        document=json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise PermissionError('Invalid SCM v2 result JSON') from exc
    if (type(document) is not dict or set(document)!= {'format','body','signature'} or
            document['format'] != FORMAT or type(document['body']) is not dict or
            set(document['body'])!=FIELDS or type(document['signature']) is not str or
            not re.fullmatch(r'[a-f0-9]{128}',document['signature'])):
        raise PermissionError('SCM signed-result schema/algorithm mismatch')
    body=document['body']
    if (type(body['job_id']) is not str or not JOB.fullmatch(body['job_id']) or
            type(body['project_id']) is not str or not PROJECT.fullmatch(body['project_id']) or
            type(body['worker_pid']) is not int or body['worker_pid'] <= 0 or
            type(body['receipt_nonce']) is not str or not PROJECT.fullmatch(body['receipt_nonce']) or
            any(type(body[k]) is not str or not SHA.fullmatch(body[k]) for k in (
                'plan_sha256','picture_sha256','bootstrap_sha256',
                'model_stack_sha256','appcontainer_sid_sha256')) or
            any(body[k] is not True for k in BOOLEANS)):
        raise PermissionError('SCM native custody/identity proof missing')
    if any(type(expected[k]) is not type(body[k]) or expected[k] != body[k]
           for k in IDENTITIES):
        raise PermissionError('SCM result does not match protected installed job/worker')
    signed=_canonical({'format':FORMAT,'body':body})
    if _canonical(document)!=payload:
        raise PermissionError('SCM response must be exact canonical JSON')
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        key=ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),
                                                         pinned_p256_public)
        raw=bytes.fromhex(document['signature'])
        r,s=int.from_bytes(raw[:32],'big'),int.from_bytes(raw[32:],'big')
        signature=utils.encode_dss_signature(r,s)
        digest=sha256(signed).digest()
        key.verify(signature,digest,ec.ECDSA(utils.Prehashed(hashes.SHA256())))
    except Exception as exc:
        raise PermissionError('Invalid Windows CNG SCM P-256 signature') from exc
    signed_sha=sha256(signed).hexdigest()
    if consume_once(body['job_id'],body['receipt_nonce'],signed_sha) is not True:
        raise PermissionError('SCM one-use receipt replay or persistent journal unavailable')
    return {
        'format':KERNEL_FORMAT,
        'scm_authenticated_receipt_verified':True,
        'scm_service_custody_verified':True,
        'process_tree_custody_verified':True,
        'appcontainer_zero_network_caps_verified':True,
        'wfp_no_egress_verified':True,
        'efs_verified':True,
        'job_id':body['job_id'],
        'project_id':body['project_id'],
        'plan_sha256':body['plan_sha256'],
        'model_stack_sha256':body['model_stack_sha256'],
        'bootstrap_sha256':body['bootstrap_sha256'],
        'picture_sha256':body['picture_sha256'],
        'worker_pid':body['worker_pid'],
        'scm_receipt_sha256':signed_sha,
    }


class InstalledScmCngV2Channel:
    """Read-only adapter. Service start/OS attestations are NOT implemented here.

    A production binding must supply a *native SCM connection* and machine-key
    trust anchor installed outside the NVP UI/model/worker. No mock, network
    adapter, file selected by the worker or raw user key is a production issuer.
    """
    def __init__(self, *, pinned_p256_public: bytes, receive_from_scm, consume_once):
        if (not callable(receive_from_scm) or not callable(consume_once) or
                type(pinned_p256_public) is not bytes or len(pinned_p256_public)!=65):
            raise TypeError('Native SCM transport, key and durable nonce ledger required')
        self.key=pinned_p256_public
        self.receive=receive_from_scm
        self.consume=consume_once

    def __call__(self, scope: dict, scm_kernel: dict) -> dict:
        if (type(scope) is not dict or type(scm_kernel) is not dict or
                scm_kernel.get('format')!=KERNEL_FORMAT or
                scm_kernel.get('scm_service_custody_verified') is not True or
                scm_kernel.get('kernel_job_tree_reaped') is not True or
                scm_kernel.get('release_fence_closed') is not True or
                scm_kernel.get('scm_owned_job') is not True):
            raise PermissionError('Only independently installed SCM-owned kernel receipts are accepted')
        expected={k:scope[k] for k in IDENTITIES if k in scope}
        expected.update({k:scm_kernel[k] for k in ('worker_pid','appcontainer_sid_sha256')
                         if k in scm_kernel})
        if set(expected)!=IDENTITIES:
            raise PermissionError('Incomplete exact SCM result identity')
        response=self.receive(scope['job_id'],scm_kernel['worker_pid'])
        return verify_scm_cng_v2(response,pinned_p256_public=self.key,
                                 expected=expected,consume_once=self.consume)


def load_installed_scm_verifier_key() -> bytes:
    """Load only the installer-pinned HKLM machine signer key (read-only).

    Windows-only. No development key, project metadata, env var, UI, model,
    worker result or user-selected path may override this trust anchor.
    """
    import sys
    if sys.platform != 'win32':
        raise PermissionError('Only the installed Windows registry can authorize SCM trust')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
            r'SOFTWARE\NVP\POST01F\SignerTrust',0,
            winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
            fmt,_=winreg.QueryValueEx(key,'Format')
            source,_=winreg.QueryValueEx(key,'PublicP256X962Hex')
        if fmt!=FORMAT or type(source) is not str or not re.fullmatch(r'04[a-f0-9]{128}',source):
            raise PermissionError('Installer-pinned SCM signature algorithm/key malformed')
        return bytes.fromhex(source)
    except (OSError,ValueError) as exc:
        raise PermissionError('Trusted installed Windows SCM signing key unavailable') from exc
