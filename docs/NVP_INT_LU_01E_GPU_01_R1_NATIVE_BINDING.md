# NVP-INT-LU-01E-GPU-01-R1 — Lu GPU lease v1 native binding

Status: SOURCE-QUALIFIED, installed Windows end-to-end **OPEN**. Only the
existing NVP PR #161 and Lu PR #244 are authoritative owners. No Docker,
unsandboxed LTX, direct Lu model-control API, or second IPC protocol.

## Exact new Lu source pin

- Lu Core draft PR #244 **`b7f6b51a1f0278dc411ff3c1311bf6172cb7dddb`**,
  `workspace.proto` Git blob **`c468669910fbc373cb9c19a9a2cf13c5ce0d8b51`**;
  this is newer than the currently pinned NVP old Lu blob `4e01d921...`.
- Existing `lu.workspace.v0.WorkspaceFrame` has `gpu_lease_request` (38),
  `gpu_lease_outcome` (39), `gpu_lease_release` (40); feature `gpu-lease-v1`.
  These are distinct from `ModelLease` for inference and legacy advisory
  `ResourceTransitionRequest`.
- New NVP `backend/nvp_lu_gpu_lease_v1.py` validates schema names/field
  numbers, original Lu `OriginRefs`, request/session/version and exact device,
  duration and Core lease ref, and rejects DENIED/DEFERRED/UNKNOWN, missing
  VRAM observation and other phases. It operates on generated Protobuf frames
  sent over an independently installed/authenticated existing pipe/UDS; it
  does **not** open a second listener or mint a Core grant.

## One GPU processing lifecycle

1. Host obtains user-authorized original NVP project, immutable Take and
   **preallocated exact NVP native worker job**. On the current LTX implementation
   `ProtectedLtxHandoff.run` generates `ltx_...` after entry; a trusted durable
   preallocation/reservation API is therefore a **real integration blocker**.
   `WindowsNvpGpuSupervisorBinding.run_protected_job` refuses until the
   installed owner independently attests exact job reservation BEFORE unload.
2. NVP's EFS + production supervisor owner persists GPU journal PREPARED and
   REQUEST_SENT before submitting `GpuLeaseRequest`; Core owns admission,
   model draining, GGUF unload, and independent driver VRAM probes.
3. A `gpu_lease_outcome` with ALLOWED/GRANTED and measured VRAM is only a
   claim on the native wire. NVP requires an *independent installed Core host*
   receipt specifying Core epoch, selected model generation, expiry and
   durable original source, then the original native owner separately admits
   launch. The current protobuf **does not carry these fields**, so physical
   positive proof cannot be generated from this source-only adapter.
4. NVP runs its original SCM/Job/AppContainer-supervised LTX worker. The
   returned job ID must equal the reserved job ID; mismatches refuse and
   preserve no-reload quarantine. Original NVP PCM/Takes are not changed.
5. After successful, failed or cancelled work, a worker return code and
   `GPUObserver` telemetry are **not enough**. Independent SCM-signed native
   termination, original Job group zero and installed GPU context quiescence
   must be attested. The owner records this under the protected GPU journal.
6. Only then NVP sends `GpuLeaseRelease` with Core-minted lease and
   independently resolved `nvp_worker_stop_ref`. Core verifies original
   bound worker group empty, new GPU samples and restores its selected GGUF
   model. A `RESTORED` reply is only a claim: NVP requires a separate trusted
   durable Core release receipt and checks the native stop digest before
   committing RELEASED. NVP NEVER reloads Lu's model.
7. On unknown outcome, disconnected session, Core/NVP restart, stale epoch,
   insufficient GPU capacity or worker orphan, NVP retains durable UNCERTAIN
   and MUST NOT claim automatic reload, auto-resend or start a new job.

## Native ownership and outstanding installed blockers

`backend/nvp_lu_windows_gpu_binding.py` opens one GPU journal using **the
original** `ProductionJournal` and `ProductionSupervisor` through
`WindowsProtectedIPCJournalOwner`, inheriting Win32 EFS, exclusive owner and
SQLite sidecar checks. This intentionally refuses Linux and has no secondary
privileged worker or signer. It additionally requires the installed original
NVP job reservation and native signer/OS GPU observer; this current source
**does not** supply those services. The existing read-only
`backend/nvp_gpu_observation.py` cannot prove zero GPU contexts.

Lu Core source currently supplies lease manager and extension traits but has
no fully installed Core host GPU observer, NVP worker-stop verifier or signed
Core result issuer. Full physical Windows R9700/SCM and authenticated Lu Core
positive exchange remain **BLOCKED**, not a test pass. A trusted receipt
must be tied to original OS signer, GPU, Core epoch, protected worker group,
selected model generation and durable receipt; the v1 wire alone is not such a
receipt. Lu issue #250 remains open. The native NVP LTX job-reservation
seam and original service binding must be finished before positive E2E.

## Qualification

Run from a complete NVP checkout:

```bash
python -m unittest discover -s tests -p 'test_nvp_int_lu_01e_gpu*.py' -q
python -m unittest discover -s tests -p 'test_nvp_int_lu_01f_r*.py' -q
python -m unittest discover -s tests -p 'test_nvp_diffusion*.py' -q
node frontend/tests/diffusionPrompt.node-check.mjs
python scripts/nvp_lu_01e_gpu_r1_source_qualification.py --lu-root /path/to/immutable/Lu-AI-GUI
```

The last command is fail-closed if the genuine Lu exact Git checkout or
`protoc` is absent, and its pass proves source pin and descriptor only, not
installed Windows signers or GPU correctness.
