"""NVP trusted LTX preallocation gate for Lu gpu-lease-v1.

This does not create a Windows Job or Lu model grant. The installed NVP SCM
supervisor must durably reserve the immutable original LTX job *before* Lu
unloads, then bind that reservation to its actual Job handle at launch.
The old standalone NVP workflow can still mint its own LTX job when it does
not borrow Lu VRAM; the connected path cannot.
"""
from __future__ import annotations

import re
import secrets
from typing import Callable

JOB = re.compile(r'ltx_[0-9a-f]{24}\Z')


def select_original_ltx_job(*, preallocated_job_id: str | None,
                            verify_installed_reservation: Callable | None,
                            project_id: str, take_sha256: str,
                            camera_id: str) -> str:
    """Require a previously sealed native SCM reservation in Lu-connected mode.

    The verifier must be supplied by a pinned installed NVP native owner,
    not from model/UI data. A caller cannot create a reservation merely by
    spelling an LTX ID. Standalone mode preserves the existing behavior.
    """
    if preallocated_job_id is None:
        if verify_installed_reservation is not None:
            raise PermissionError('Missing previously reserved native LTX job')
        return 'ltx_' + secrets.token_hex(12)
    if (type(preallocated_job_id) is not str or not JOB.fullmatch(preallocated_job_id) or
            not callable(verify_installed_reservation) or
            type(project_id) is not str or not re.fullmatch('[0-9a-f]{32}',project_id) or
            type(take_sha256) is not str or not re.fullmatch('[0-9a-f]{64}',take_sha256) or
            type(camera_id) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,80}',camera_id)):
        raise PermissionError('Invalid Lu-linked LTX source/job reservation')
    original = {'job_id':preallocated_job_id,'project_id':project_id,
                'take_sha256':take_sha256,'camera_id':camera_id}
    if verify_installed_reservation(dict(original)) is not True:
        raise PermissionError('Installed SCM has not reserved exact original NVP job')
    return preallocated_job_id


def verify_scm_original_gpu_scope(scope: dict, *, actual_ltx_job_id: str) -> None:
    """Validate exact Core lease source/SCM assignment before P-256 issuance.

    Actual HJOB ACTIVE_ZERO and signature are verified by the native issuer,
    never by this source-level check.
    """
    if (type(scope) is not dict or set(scope) != {
            'lease_ref','device_ref','module_id','workspace_ref','conversation_ref',
            'user_turn_ref','task_ref','core_epoch_ref','nvp_session_ref','original_nvp_job_ref'} or
            scope['module_id']!='nvp.film' or
            scope['original_nvp_job_ref']!=actual_ltx_job_id or
            not JOB.fullmatch(actual_ltx_job_id)):
        raise PermissionError('GPU receipt not bound to exact reserved LTX job')
    for name,value in scope.items():
        if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,128}',value):
            raise PermissionError('NVP SCM GPU receipt scope is invalid')
    if not re.fullmatch(r'[A-Za-z0-9-]{1,128}',scope['lease_ref']):
        raise PermissionError('Noncanonical Lu-installed GPU lease receipt filename')
