# NVP-INT-LU-01E-GPU-01-R2 — Original LTX Job, Lu worker-stop CNG receipt, exact Rust/prost

Date: 2026-11-21. Status: **LOCAL SOURCE PASS; INSTALLED WINDOWS POSITIVE BLOCKED; NATIVE CI NOT RUN.**

## Source lock and ownership

- NVP existing PR #161 staging head `d5754ed7e32294b9dd6b0b01a9ded0fed0fd2016`; unpublished prepared predecessor `45d68421414c79aa5d90fac9cba977b00aa6d32e`; no NVP PR branch update in R2.
- Lu Core's reviewed current PR #244 source pin `60afe6908a6abe3408bb952869d85b43781313ca`; canonical `workspace.proto` Git blob `747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1`; GPU Protobuf request/outcome/release/poll tags 38/39/40/41. This schema/host is still a **draft**, not installed acceptance.
- Lu alone owns GGUF/MMProj unload/reload and global GPU admission. NVP alone owns native LTX worker/SCM/Job, Take/PCM production artifacts and creator decisions. No NVP direct Lu model API.

## R2 source additions

1. `backend/nvp_lu_ltx_preallocation.py` validates the *same original job* before generation. Its trusted `select_original_ltx_job` is patched into `ProtectedLtxHandoff.run(preallocated_job_id=..., verify_installed_reservation=...)`. In Lu-connected mode the service must durably reserve a real original NVP SCM Job identity before Lu is asked to unload. Standalone mode retains independent random job IDs and **cannot** reclassify those as Lu GPU reservations.
2. `backend/nvp_lu_windows_gpu_binding.py` acquires an original SCM reservation and checks it before `coordinator.request`. It passes the very same job to the protected LTX invocation, and preserves the existing GPU yield journal/host Core grant verification and all-clear gating.
3. `tools/nvp_int_lu_gpu_stop_issuer.hpp` is a Windows-only **real CNG ECDSA-P256 machine-key signing** source; distinct fixed key name `NVP-INT-LU-GPU-JOB-EMPTY-P256-v1`. Requires LocalSystem Session 0, nonexportable CNG export policy, actual worker and SCM PID/creation FILETIME, original SCM-held Job kernel ACTIVE_ZERO, and a source-bound original job name. It outputs one immutable, write-through `LU_NVP_GPU_JOB_EMPTY_V1\0` raw P-256 signature receipt under installer-protected `%ProgramData%\Lu\IPC\nvp-gpu-stops-v1\<core-lease>.stop.v1`.
4. Lu's expected body uses ten one-byte-length-prefixed canonical ASCII fields, little-endian `service_pid:u32`, `service_birth:u64`, `worker_pid:u32`, `worker_birth:u64`, then 64-byte raw ECDSA-P256 signature over SHA-256 of the preceding body. Receipt file itself has an explicit *protected* SYSTEM/Administrators-only DACL and SYSTEM owner; a permissive inherited default would be rejected by Core.
5. `tools/nvp_post01f_windows_scm_ltx_broker.cpp` patch integrates the GPU receipt in the **existing** installed NVP LTX SCM service only when original installer-custodied approved machine registry fields specify the full same-job Lu lease. Absent GPU metadata, the original standalone NVP picture flow remains unchanged. Partial metadata, incorrect source/job/device or missing installed P256 key refuse. The SCM service now drains the original protected Job and can issue its **valid stop receipt even when LTX exits unsuccessfully or times out**; only then does it reject film success. No receipt is issued unless genuine kernel ACTIVE_ZERO and CNG signer acceptance are confirmed.
6. `native/nvp_lu_ipc_client/tests/gpu_lease_v1.rs` checks Lu's real prost-generated native request/release/outcome ABI. `scripts/nvp_lu_gpu_r2_repin_locked_source.py` atomically preflights all six existing NVP native pins and fixes them only in an exact original Git checkout (without publishing anything). Reviewed build/pin scripts and native workflows are prepared to use Lu commit `60afe6908a6abe3408bb952869d85b43781313ca` and `workspace.proto` Git blob `747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1`, with additive async `GpuLeasePoll` tag 41. The NVP Rust fixture uses the canonical numeric enum value and verifies the generated prost enum name rather than assuming an invalid short variant. `.github/workflows/nvp-int-lu-01e-gpu-r2-native.yml` tests actual **Ubuntu + Windows** Rust/prost against a full immutable Lu checkout, Python original-source IPC, plus Windows MSVC compile + negative direct-start denial for the signer and original SCM service.

## Latest native Core CI blocker (owned by Lu Core)

Lu's immutable source snapshot `bfbffc3` is **not native CI accepted**: [Core run #44940810207](https://github.com/vjmichael/Lu-AI-GUI/actions/runs/44940810207) fails both Windows and Ubuntu with actual Rust **E0599** in its newly-added async GPU poll enum. Core references `GpuLeaseTransitionKind::Acquire` / `::Release`, which the generated prost implementation does not define with those names. This is Core source and must be repaired in Lu's existing branch before cross-repo installed acceptance. NVP's Rust fixture avoids the same mistaken naming assumption and tests the numeric enum's canonical Protobuf label. Reported to [Lu issue #250](https://github.com/vjmichael/Lu-AI-GUI/issues/250#issuecomment-7068069050). Newer Core commits are not silently treated as accepted schema pins; any later re-pin requires exact native requalification.

## Limits and remaining physical gates

- This R2 package includes **reviewable patches** against original full NVP files because the task environment has a sparse test-only checkout, not a full verified NVP mainline checkout. The original LTX/SCM integration patches were compared with actual original Git file content; **not claimed as full native compile passed**.
- NVP's existing Python `ProtectedLtxHandoff` launches via `launch_contained`, while the separate native Windows SCM LTX service holds the real Job used by the issuer. A genuine installed positive path MUST unify these under the same preallocated NVP SCM job; signing an unrelated or later-created process would be unsafe and is rejected. A real installed issuer/private machine key/public pin is **not provisioned here**.
- Lu Core's protected record public pin `%ProgramData%\Lu\IPC\enrollments\nvp-gpu-stop-p256.pub` must be the distinct 72-byte public ECC blob corresponding to NVP's nonexportable SCM key. NVP must not create Lu's protected folders/key pins unilaterally; signed installer coordination required.
- Lu's GPU protocol provides `GRANTED/RESTORED` claims but NVP still needs independently authenticated Core resource-release and durable acknowledgment evidence. Until Core enrollment, installed observer and writer are accepted, `NativeLuGpuLeaseV1Gateway` **refuses positive** without verified installed receipts.
- Windows R9700 native VRAM, real installed CNG signing, genuine original Job-zero after success/failure/cancellation, restart/UNCERTAIN recovery, owner revocation, Lu Core GGUF unload/reload and real picture/PCM end-to-end are **NOT RUN**. No physical positive release/restore claimed; on unknown outcome Lu keeps the GPU fence and NVP retains the unresolved journal.
- The reviewed new Lu Core state machine serializes whole-host leases, fences new inference, checks two independent WDDM/DXGI GPU samples and independently rechecks NVP stop before restore. Linux Lu installed GPU observer presently refuses positive.

## Focused local source receipts

- Prior GPU suite **49/49 PASS**, including bounded original-lease asynchronous GRANTED/RESTORED polling.
- New R2 stop-wire/preallocation/SCM failure-drain suite **10/10 PASS** (including ephemeral in-memory P-256 raw signature parity, which is *not* an installed machine key signature).
- Prior durable IPC regression suite **66/66 PASS**.
- Existing background-music LTX suite **11/11 PASS**; frontend prompt check PASS.
- Strict source-only protobuf/schema pin fixture is prepared, but actual exact-source Windows + Linux locked Cargo/prost run **NOT RUN** until the reviewed complete NVP branch source can be published once without stacking CI.

## Next gate

Complete full-checkout patch replay and original SCM service native Windows compilation, then one non-forced source publication to existing NVP PR #161 only after consolidating the current unpublished predecessor/R1/R2 candidates; independently inspect the new exact SHA Windows and Ubuntu Rust/prost and SCM native negative jobs. Physical installer keys and verified positive Lu↔NVP handoff are separately gated.
