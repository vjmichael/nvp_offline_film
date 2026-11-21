"""Exact Lu Core LU_NVP_GPU_JOB_EMPTY_V1 receipt encoding (NVP side).

This produces ONLY unsigned canonical bytes for independent testing and C++
interoperability. A trusted installed Windows NVP SCM service, holding the
original Job handle, must sign with a separate installer-provisioned CNG key.
Python code can NEVER issue a positive worker-stop receipt.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
import struct

DOMAIN = b'LU_NVP_GPU_JOB_EMPTY_V1\0'
METHOD = 'WINDOWS_JOB_ACTIVE_ZERO_V1'
SIG_BYTES = 64
MAX_RECEIPT = 4096
_SCOPE = re.compile(r'[A-Za-z0-9_.:/-]{1,128}\Z')
_LEASE_FILE = re.compile(r'[A-Za-z0-9-]{1,128}\Z')


def _field(value: str) -> bytes:
    if type(value) is not str or not _SCOPE.fullmatch(value):
        raise ValueError('Unbounded or unsafe original Lu/NVP GPU scope')
    raw = value.encode('ascii')
    return bytes((len(raw),)) + raw


@dataclass(frozen=True)
class OriginalGpuStop:
    lease_ref: str
    device_ref: str
    module_id: str
    workspace_ref: str
    conversation_ref: str
    user_turn_ref: str
    task_ref: str
    core_epoch_ref: str
    nvp_session_ref: str
    service_pid: int
    service_birth: int
    worker_pid: int
    worker_birth: int

    def canonical_unsigned(self) -> bytes:
        if self.module_id != 'nvp.film' or not _LEASE_FILE.fullmatch(self.lease_ref):
            raise ValueError('Only the original NVP Core GPU lease may be released')
        values = (self.service_pid, self.service_birth, self.worker_pid, self.worker_birth)
        if any(type(v) is not int or v < 1 or v > limit for v, limit in zip(
                values, (2**32-1, 2**64-1, 2**32-1, 2**64-1))):
            raise ValueError('Actual SCM and worker PID/birth evidence required')
        names = (self.lease_ref, self.device_ref, self.module_id,
                 self.workspace_ref, self.conversation_ref, self.user_turn_ref,
                 self.task_ref, self.core_epoch_ref, self.nvp_session_ref, METHOD)
        result = (DOMAIN + b''.join(_field(n) for n in names) +
                  struct.pack('<IQIQ', *values))
        if len(result) + SIG_BYTES > MAX_RECEIPT:
            raise ValueError('Worker-stop receipt exceeds Lu protected reader limit')
        return result

    def receipt_name(self) -> str:
        self.canonical_unsigned()
        return self.lease_ref + '.stop.v1'


def validate_receipt_shape(record: bytes, original: OriginalGpuStop) -> bytes:
    """Test-only envelope structural check. NEVER a signature verifier."""
    expected = original.canonical_unsigned()
    if type(record) is not bytes or len(record) != len(expected) + SIG_BYTES or not record.startswith(expected):
        raise ValueError('Worker stop receipt changed original Lu/NVP GPU scope')
    return record[-SIG_BYTES:]
