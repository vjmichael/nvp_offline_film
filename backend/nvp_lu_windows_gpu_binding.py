"""Installed Windows NVP production-supervisor boundary for Lu GPU yields.

Uses the ORIGINAL NVP ProductionJournal + ProductionSupervisor owner and EFS
rather than creating an unprotected second SQLite/signer or an NVP model
controller. The external NVP GPU/SCM observation service and Lu broker still
require separately installed OS custody; no source-only Python callback can
satisfy the physical Radeon/SCM acceptance gate.
"""
from __future__ import annotations

import os
import sys
import re

from backend.nvp_lu_gpu_yield import (
    GpuYieldRefusal, NvpGpuYieldCoordinator, YieldIntent,
)
from backend.nvp_lu_gpu_lease_v1 import NativeLuGpuLeaseV1Gateway


def require_original_native_gpu_job_result(intent: YieldIntent, result: dict) -> dict:
    """Postcondition of real NVP protected LTX/other native worker invocation.

    A worker may not swap another Take/job after Lu yields VRAM. Source-only
    checks are not native shutdown proof; failure retains the original fence.
    """
    if type(intent) is not YieldIntent or type(result) is not dict or \
            result.get('job_id') != intent.native_job_ref:
        raise GpuYieldRefusal('Native diffuser returned a foreign, unreserved job identity')
    return result


def validate_installed_windows_luid(device_ref: str) -> str:
    """Exact Lu Core GPU device format; never pass an NVP gpu-0 alias."""
    if type(device_ref) is not str or not re.fullmatch(
            r'dxgi:luid_0x[0-9a-fA-F]{8}_0x[0-9a-fA-F]{8}_phys_0',device_ref):
        raise GpuYieldRefusal('Installed Lu GPU lease requires exact Windows DXGI LUID')
    return device_ref


class WindowsNvpGpuSupervisorBinding:
    """Opens GPU-yield journal under NVP's real exclusive Windows owner.

    The ``native_owner`` is an independently installer-provisioned service
    adapter, never an NVP UI callback. Construction does NOT authorize render
    launch; each coordinator operation still rechecks current user/peer
    authorization, NVP worker Job/SCM and driver quiescence receipts.
    """
    REQUIRED_NATIVE_OWNER_METHODS = frozenset((
        'verify_installed_session', 'authorize_original_turn',
        'verify_core_released_vram', 'verify_live_core_gpu_lease',
        'verify_native_diffuser_admission',
        'verify_native_scm_gpu_quiescence',
        'verify_no_protected_gpu_worker_launched',
        'reserve_original_ltx_job',
        'verify_original_ltx_job_reservation',
        'run_original_scm_ltx_job', 'cancel_original_scm_ltx_job',
        'observe_native_gpu_quiescence',
        'verify_core_durable_release_ack',
    ))

    def __init__(self, production_journal, production_supervisor, *, core_port,
                 native_owner):
        if os.name != 'nt' or sys.platform != 'win32':
            raise GpuYieldRefusal('Protected NVP GPU yield requires installed Windows')
        # Reuse existing identity/ownership/Win32 EFS verification. The
        # original constructor enforces concrete ProductionJournal and
        # ProductionSupervisor types, the owner lease, same journal identity,
        # and protected DB/file metadata; this class has no fallback path.
        from backend.nvp_lu_windows_native_admission import WindowsProtectedIPCJournalOwner
        if type(core_port) is not NativeLuGpuLeaseV1Gateway:
            raise GpuYieldRefusal('Only source-pinned Core GPU lease v1 port allowed')
        if native_owner is None or not all(callable(getattr(native_owner, n, None))
            for n in self.REQUIRED_NATIVE_OWNER_METHODS):
            raise GpuYieldRefusal('Installed native OS GPU/SCM receipt provider unavailable')
        self.storage=WindowsProtectedIPCJournalOwner(production_journal,production_supervisor)
        self.core=core_port
        self.owner=native_owner
        self.journal=self.storage.open_gpu_yield_journal()
        if self.storage.guard(self.storage.root) is not True:
            raise GpuYieldRefusal('Original NVP supervisor lost protected GPU journal custody')
        self.coordinator=NvpGpuYieldCoordinator(self.journal,
            native_owner=native_owner,core_port=core_port)

    def run_protected_job(self, intent: YieldIntent, *, approved_native_run,
                          verify_exact_preallocated_worker_job):
        """Runs a single reviewed native NVP diffuser under original Lu lease.

        An LTX worker currently generates its own random job ref in run();
        that ref MUST be preallocated or reserved under the trusted NVP native
        owner BEFORE asking Lu to unload. A later random ref does not satisfy
        the GPU lease. Until an installed NVP worker API exposes the *exact*
        reserved job and SCM process group, this gate refuses live diffusion.
        """
        if type(intent) is not YieldIntent or not callable(approved_native_run) or \
                not callable(verify_exact_preallocated_worker_job):
            raise GpuYieldRefusal('Original protected NVP job reservation required')
        if self.storage.guard(self.storage.root) is not True:
            raise GpuYieldRefusal('NVP supervisor/EFS custody changed')
        validate_installed_windows_luid(intent.device_ref)
        # SCM owns a durable *original* job reservation before the Core
        # unload request. It must be the same job and creator-bound Take as
        # the later protected LTX worker; never generate it on demand after
        # Lu has freed its model memory.
        if self.owner.reserve_original_ltx_job(intent) != intent.native_job_ref:
            raise GpuYieldRefusal('SCM original native LTX job was not preallocated')
        if verify_exact_preallocated_worker_job(intent) is not True:
            raise GpuYieldRefusal('No independently owner-reserved native job before Lu unload')
        def invoke_original_native_job():
            result = approved_native_run()
            # The original POST-01F ProtectedLtxHandoff returns its own job_id.
            # If the native worker did not actually use the exact job reserved
            # BEFORE Core unload, refuse and retain the GPU stop/quarantine
            # fence. Never reinterpret a different worker as the approved job.
            return require_original_native_gpu_job_result(intent, result)
        self.coordinator.request(intent)
        return self.coordinator.run_admitted_protected_diffusion(
            intent,run_worker=invoke_original_native_job)


    def run_preallocated_native_ltx(self, intent: YieldIntent, *, handoff,
                                    source_intent: dict, layout: bytes, look: bytes,
                                    conditioning: bytes,
                                    verify_exact_preallocated_worker_job):
        """Bind Lu's granted GPU lease to the ORIGINAL POST-01F LTX job ID.

        The original installed SCM service launches and drains the worker.
        The Python AppContainer launch_contained route is forbidden for Lu
        GPU leases, or it would create a second unrelated kernel Job.
        No native positive claim exists until independent Windows installation,
        SCM owner reservation, signed receipt and driver attestation.
        """
        from backend.nvp_post01f_ltx_native_handoff import ProtectedLtxHandoff
        if type(handoff) is not ProtectedLtxHandoff:
            raise GpuYieldRefusal('Only the genuine protected LTX handoff can consume Lu VRAM')
        def invoke():
            return handoff.run(intent=source_intent,layout=layout,look=look,
                conditioning=conditioning,
                preallocated_job_id=intent.native_job_ref,
                verify_installed_reservation=self.owner.verify_original_ltx_job_reservation,
                scm_owned_launch=lambda scope:self.owner.run_original_scm_ltx_job(intent,scope),
                scm_owned_cancel=lambda job:self.owner.cancel_original_scm_ltx_job(intent,job))
        return self.run_protected_job(intent,approved_native_run=invoke,
            verify_exact_preallocated_worker_job=verify_exact_preallocated_worker_job)


def open_installed_windows_gpu_yield_binding(
        production_journal, production_supervisor, *, core_port, native_owner):
    """No test-only OS impersonation or offline / headless positive path."""
    return WindowsNvpGpuSupervisorBinding(production_journal, production_supervisor,
        core_port=core_port,native_owner=native_owner)
