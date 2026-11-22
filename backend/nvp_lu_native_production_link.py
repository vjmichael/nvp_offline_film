"""NVP-INT-LU-01F-R2-R1: protected NVP production-supervisor IPC job link.

Binds an ALREADY created, source-verified native NVP production job to the
at-most-once Lu IPC dispatch journal. It does not submit a job, mint a Lu grant,
create a Protobuf listener, accept a receipt as terminal, or bypass NVP creator
approval. The existing protected Windows ProductionJournal/ProductionSupervisor
own actual execution, cancellation and restart custody. The provider may only
report a final applied effect after a *different* installed, independently
verified receipt is bound through IPCOperationJournal.reconcile_receipt.

This is a narrow integration seam, not a signed installer/installed Lu session.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import sys
import re
from uuid import UUID

from backend.nvp_lu_operation_journal import (
    IPCOperationJournal, JournalRefusal, OperationSpec, _digest, _ref,
)

# This native worker implements READ-ONLY integrity verification of already
# approved, immutable media. It is NOT NVP's LTX picture generator, nor its
# export/creator-approval service. No nvp.film.* action maps automatically to it.
NATIVE_KIND = 'production-integrity'
_NATIVE_STATES = frozenset({
    'QUEUED', 'RUNNING', 'VERIFY_COMPLETE', 'REVIEW_REQUIRED', 'CANCELLED',
})


@dataclass(frozen=True)
class NativeProductionIdentity:
    """Host-derived source identity; constructing it grants no permission."""
    job_id: str
    project_id: str
    manifest_sha256: str

    def __post_init__(self):
        _ref(self.job_id)
        _ref(self.project_id)
        _digest(self.manifest_sha256)
        # ProductionJournal.submit mints canonical UUIDv4 job IDs, and
        # FilmIndex project identity is a 32-hex opaque ID. Do not accept
        # arbitrary Lu-provided strings as a native job locator.
        try:
            job_uuid = UUID(self.job_id)
        except (ValueError, AttributeError) as exc:
            raise JournalRefusal('Unrecognized native production job ID') from exc
        if (job_uuid.version != 4 or str(job_uuid) != self.job_id or
                re.fullmatch(r'[0-9a-f]{32}', self.project_id) is None):
            raise JournalRefusal('Unrecognized native production/project identity')


def _exact_native_job_status(status: dict, expected: NativeProductionIdentity):
    """NVP original verified manifest status, not a signed receipt."""
    if (type(status) is not dict or status.get('job_id') != expected.job_id or
            status.get('project_id') != expected.project_id or
            status.get('manifest_sha256') != expected.manifest_sha256 or
            status.get('task_kind') != 'VERIFY_APPROVED_MEDIA_V1' or
            status.get('state') not in _NATIVE_STATES or
            status.get('production_dcp_accepted') is not False or
            type(status.get('cancel_requested')) is not bool):
        raise JournalRefusal('NVP native job does not match original manifest/worker')
    return {'job_id': expected.job_id, 'project_id': expected.project_id,
            'manifest_sha256': expected.manifest_sha256,
            'state': status['state'], 'cancel_requested': status['cancel_requested']}


class WindowsProtectedProductionLink:
    """Only the installed Windows NVP supervisor may construct this link.

    Arguments are trusted *existing NVP objects*, never supplied over Lu IPC.
    Creator cancellation and scope authorization are provided by the installed
    film domain; this class never accepts claimed creator approval from Lu.
    """
    def __init__(self, ipc_journal: IPCOperationJournal, production_journal,
                 production_supervisor, *, resolve_native_scope, creator_cancel_approval):
        if os.name != 'nt' or sys.platform != 'win32':
            raise JournalRefusal('Genuine installed Windows production custody required')
        # Lazy import avoids pulling Windows-only EFS/native codecs into the
        # portable Lu schema and R1/R2 recovery tests.
        from backend.nvp_production_journal import ProductionJournal, _require_owner
        from backend.nvp_production_supervisor import ProductionSupervisor
        if (type(ipc_journal) is not IPCOperationJournal or
                not isinstance(production_journal, ProductionJournal) or
                not isinstance(production_supervisor, ProductionSupervisor) or
                production_supervisor.journal is not production_journal or
                not callable(resolve_native_scope) or not callable(creator_cancel_approval)):
            raise JournalRefusal('Unrecognized real NVP supervisor/journal/creator owner')
        _require_owner(production_journal.root)
        # The Lu IPC journal must inherit the *same* real EFS native producer
        # custody, never arbitrary state_root or a merely permissive callback.
        from backend.nvp_wo4_pcm_stream import _protected_path
        if ipc_journal.root != production_journal.root:
            raise JournalRefusal('IPC and NVP native worker must share protected owner root')
        _protected_path(ipc_journal.path)
        if ipc_journal._storage_guard(ipc_journal.root) is not True:
            raise JournalRefusal('Protected IPC state owner was not verified')
        # No Python certificate, caller-supplied pid or callback substitutes
        # for installer verification of Lu peer and NVP protected storage.
        self._ipc = ipc_journal
        self._production = production_journal
        self._supervisor = production_supervisor
        self._require_owner = _require_owner
        self._resolve_scope = resolve_native_scope
        self._creator_cancel = creator_cancel_approval

    def _owned(self):
        self._require_owner(self._production.root)

    def _verified(self, spec: OperationSpec, native: NativeProductionIdentity):
        self._owned()
        if type(spec) is not OperationSpec or type(native) is not NativeProductionIdentity:
            raise JournalRefusal('Original Lu and native identities required')
        # Native owner resolves user-turn, project, immutable revision and
        # film permissions from protected state; never parse a path from Lu.
        if self._resolve_scope(spec, native) is not True:
            raise JournalRefusal('Native film job not bound to original Lu user-turn')
        status = self._production.status(native.job_id)  # existing real API
        return _exact_native_job_status(status, native)

    def bind_after_native_admission(self, spec: OperationSpec, dispatch_ref: str,
                                    native: NativeProductionIdentity):
        """Write one durable cross-journal binding, not a worker-start grant.

        If the native supervisor died before this record, the original IPC
        operation stays UNCERTAIN. This API NEVER submits/retries a job.
        """
        status = self._verified(spec, native)
        return self._ipc.bind_native_job(spec,dispatch_ref=dispatch_ref,
            native_job_ref=native.job_id,project_id=native.project_id,
            manifest_sha256=native.manifest_sha256,native_kind=NATIVE_KIND,
            authorize=lambda action, data: self._verified(spec,native) == status and
                data['dispatch_ref'] == dispatch_ref)

    def _linked_status(self, spec: OperationSpec):
        self._owned()
        saved = self._ipc.native_job_binding(spec.origin.operation_ref,
            authorize=lambda action, row: row['request_sha256'] == spec.request_sha256 and
                row['native_kind'] == NATIVE_KIND)
        native = NativeProductionIdentity(saved['native_job_ref'],
            saved['project_id'],saved['manifest_sha256'])
        return native,self._verified(spec,native)

    def signal_cancel_to_real_journal(self, spec: OperationSpec, reason_code: str):
        """Uses the real ProductionJournal.request_cancel creator gate.

        A true result means a cancellation REQUEST was recorded. Only the real
        ProductionSupervisor.finalize_cancel after owner exit can prove stop.
        """
        _ref(reason_code)
        native,before = self._linked_status(spec)
        if before['state'] in ('CANCELLED','VERIFY_COMPLETE'):
            raise JournalRefusal('Native job already terminal; no retroactive cancellation')
        result = self._production.request_cancel(native.job_id,
            authorize=lambda exact_scope: self._creator_cancel(spec, native,
                reason_code, exact_scope) is True)
        if result.get('status') != 'CANCEL_REQUESTED' or result.get('job_id') != native.job_id:
            raise JournalRefusal('Native owner did not record exact cancellation')
        _,after = self._linked_status(spec)
        if not after['cancel_requested']:
            raise JournalRefusal('Native cancellation signal was not durably recorded')
        return True

    def observe_native_without_terminal_claim(self, spec: OperationSpec):
        """Bounded state view; no APPLIED/FAILED decision without signed proof."""
        _,status = self._linked_status(spec)
        return dict(status)

    def reconcile_real_supervisor_restart(self):
        """Native supervisor alone owns original restart reconciliation."""
        self._owned()
        return self._production.reconcile_after_restart()
