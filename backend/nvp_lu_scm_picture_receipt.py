"""NVP-INT-LU-01F-R2-R2: signed picture-receipt to durable Lu operation.

The only positive evidence is the *existing installed* NVP SCM/CNG P-256
channel, fixed ProgramData/EFS source, OS-owned kernel witness and durable
one-use nonce ledger. No test key, unsigned worker result, claimed PID or
IPC-provided job ID can become an APPLIED receipt. An ambiguous result remains
UNCERTAIN, not retried.

This is an integration boundary and is INERT until the installed NVP native
owner supplies the missing protected job/kernel/nonce methods. It does NOT
implement Lu Core enrollment or install Windows SCM itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import sys

from backend.nvp_lu_operation_journal import (
    IPCOperationJournal, JournalRefusal, OperationSpec, ReceiptObservation,
    _digest, _ref,
)

_LTX_JOB = re.compile(r'ltx_[a-f0-9]{24}\Z')
_PROJECT = re.compile(r'[a-f0-9]{32}\Z')
_REASON = 'SCM_PICTURE_VERIFIED'
# Exactly the complete native compound effect; READ/WRITE-only downgrades deny.
_PICTURE_EFFECTS = frozenset({3, 4})


@dataclass(frozen=True)
class ScmPictureNativeBinding:
    """Native owner-produced context, not a user/Protobuf-created grant."""
    operation_ref: str
    dispatch_ref: str
    request_sha256: str
    job_id: str
    project_id: str
    plan_sha256: str
    picture_sha256: str
    bootstrap_sha256: str
    model_stack_sha256: str
    appcontainer_sid_sha256: str
    worker_pid: int

    def __post_init__(self):
        _ref(self.operation_ref)
        _ref(self.dispatch_ref)
        _digest(self.request_sha256)
        if (type(self.job_id) is not str or not _LTX_JOB.fullmatch(self.job_id)
                or type(self.project_id) is not str or
                not _PROJECT.fullmatch(self.project_id) or
                type(self.worker_pid) is not int or self.worker_pid <= 0):
            raise JournalRefusal('Invalid protected SCM picture job identity')
        for key in ('plan_sha256','picture_sha256','bootstrap_sha256',
                    'model_stack_sha256','appcontainer_sid_sha256'):
            _digest(getattr(self, key))

    def scope(self) -> dict:
        return {key: getattr(self,key) for key in (
            'job_id','project_id','plan_sha256','picture_sha256',
            'bootstrap_sha256','model_stack_sha256')}


def require_picture_binding(spec: OperationSpec, durable: dict,
                            native: ScmPictureNativeBinding) -> None:
    """Check pinned IPC operation, exact dispatch and full effect class set."""
    if (type(spec) is not OperationSpec or
            type(native) is not ScmPictureNativeBinding or
            type(durable) is not dict or
            spec.capability_id != 'nvp.film.render.shot' or
            spec.capability_version != 1 or
            frozenset(spec.declared_effects) != _PICTURE_EFFECTS or
            spec.effect_class not in _PICTURE_EFFECTS or
            spec.origin.operation_ref != native.operation_ref or
            spec.request_sha256 != native.request_sha256 or
            durable.get('operation_ref') != native.operation_ref or
            durable.get('dispatch_ref') != native.dispatch_ref or
            durable.get('request_sha256') != native.request_sha256):
        raise JournalRefusal('SCM picture result is not the original granted dispatch')


class InstalledWindowsScmPictureReceipt:
    """Native-owner-only verified terminal handoff, no user-selected trust key.

    The installed NVP owner must implement:
      require_native_owner() -> bool: independently OS-held supervisor custody
      original_spec(operation_ref) -> OperationSpec (durable, user-turn-bound)
      bind_picture_job(spec,durable) -> ScmPictureNativeBinding: original job
      kernel_exit_witness(binding) -> dict: independently verified SCM/Job exit
      consume_native_nonce(binding,job_id,nonce,sha) -> bool: durable one-use
      approve_terminal(spec,binding,kernel,witness) -> bool: original NVP creator
          (idempotent read-only verification; invoked only inside SQLite commit)

    Constructor intentionally does not take any raw key or arbitrary receipt
    stream. It obtains the *existing* installed fixed Windows receipt channel.
    """
    def __init__(self, journal: IPCOperationJournal, native_owner):
        if os.name != 'nt' or sys.platform != 'win32':
            raise JournalRefusal('Installed Windows CNG/EFS SCM receipt required')
        if type(journal) is not IPCOperationJournal:
            raise JournalRefusal('Only the original protected Lu operation journal is usable')
        if native_owner is None or native_owner.require_native_owner() is not True:
            raise JournalRefusal('Original NVP native owner lease missing')
        from backend.nvp_post01f_installed_receipt_transport import (
            bind_installed_scm_receipt_channel,
        )
        self._journal = journal
        self._owner = native_owner
        self._bind_channel = bind_installed_scm_receipt_channel

    def reconcile_signed_picture(self, operation_ref: str) -> dict:
        """Validate original job and real signed result BEFORE terminal commit.

        A crash after SCM nonce consumption but before journal commit yields an
        UNCERTAIN operation. The owner must independently reconcile existing
        native evidence later; this function never auto-relaunches the worker.
        """
        ref = _ref(operation_ref)
        if self._owner.require_native_owner() is not True:
            raise JournalRefusal('Native owner unavailable during result handoff')
        spec = self._owner.original_spec(ref)
        if type(spec) is not OperationSpec:
            raise JournalRefusal('Missing original host-authorized Lu user scope')
        durable = self._journal.dispatch_binding(ref,
            authorize=lambda action, state: self._owner.require_native_owner() is True and
                state['operation_ref'] == ref)
        native = self._owner.bind_picture_job(spec, dict(durable))
        require_picture_binding(spec, durable, native)
        kernel = self._owner.kernel_exit_witness(native)
        if (type(kernel) is not dict or
                kernel.get('worker_pid') != native.worker_pid or
                kernel.get('appcontainer_sid_sha256') != native.appcontainer_sid_sha256 or
                kernel.get('kernel_job_tree_reaped') is not True or
                kernel.get('release_fence_closed') is not True or
                kernel.get('scm_owned_job') is not True):
            raise JournalRefusal('Missing independent SCM-owned kernel exit and release fence')
        channel = self._bind_channel(consume_once=lambda job,nonce,digest:
            self._owner.consume_native_nonce(native,job,nonce,digest) is True)
        witness = channel(native.scope(), dict(kernel))  # Actual P-256/EFS verification.
        if (type(witness) is not dict or
                witness.get('scm_authenticated_receipt_verified') is not True or
                witness.get('scm_service_custody_verified') is not True or
                witness.get('process_tree_custody_verified') is not True or
                witness.get('wfp_no_egress_verified') is not True or
                witness.get('efs_verified') is not True or
                witness.get('job_id') != native.job_id or
                witness.get('project_id') != native.project_id or
                witness.get('worker_pid') != native.worker_pid or
                witness.get('picture_sha256') != native.picture_sha256 or
                witness.get('plan_sha256') != native.plan_sha256):
            raise JournalRefusal('Signed SCM picture result not bound to original native job')
        receipt_sha = _digest(witness.get('scm_receipt_sha256'))
        if self._owner.require_native_owner() is not True:
            raise JournalRefusal('NVP native owner lost custody before terminal commit')
        observed = ReceiptObservation(ref, 'APPLIED', receipt_sha, _REASON, True)
        return self._journal.reconcile_receipt(spec,observed,
            verify_receipt=lambda receipt, original, stored:
                receipt == observed and original == spec and
                stored == durable and self._owner.require_native_owner() is True and
                self._owner.approve_terminal(spec,native,kernel,witness) is True)
