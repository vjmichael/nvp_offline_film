# NVP-INT-LU-01F-R2 — Lu→NVP Protobuf provider and durable supervisor handoff

2026-11-21. NVP-only **local implementation candidate**, NOT a deployed or signed IPC service. Base: existing draft PR #161 NVP commit `7ece5eb6efec8007fed867bfcf86a59770f081a5`. This candidate also includes unpublished R1 source. No new branch/PR, no changes to Lu Core, no CI run triggered by this local candidate.

## Decided connection architecture

```text
Lu UI / model / user turn
  → Lu Core: NativeToolRegistry, original-turn grant, effects, host journal
  → Lu Core's one authenticated bidirectional IPC session
       4-byte big-endian size + lu.workspace.v0.WorkspaceFrame (<=256 KiB)
       Windows: Lu-owned named pipe | Linux: AF_UNIX with SO_PEERCRED
  → NVP installer-admitted connector (OS owner, signed manifest/key/epoch)
  → NVP native supervisor: independ. film scope and creator/effect policy
  → NVP IPC operation journal [SQLite WAL/FULL] → claimed native work
  → NVP existing protected Windows SCM / Job / AppContainer worker
       → NVP immutable Takes / FilmIndex / source PCM, picture proposals only
  ← authenticated, bounded OperationEvent / CancelAcknowledged /
     ReconciledOperation; large assets are scoped ObjectRef locators.
```

**Use existing Lu `LuWorkspaceProvider`, not a second homegrown server.** After NVP independently authenticates Lu and Lu authenticates NVP over the native installed transport, NVP presents its exact `RegisterWorkspace`/`CapabilityDescriptor` information through the same full-duplex connection. Lu sends `CapabilityInvoke`, `CancelOperation` and `ReconcileOperation`; NVP returns `OperationEvent` (stream), `CancelAcknowledged` and `ReconciledOperation`. Existing Lu `Health` remains inert. The separate legacy NVP JSON status socket is *not* a fallback. Neither HTTP, TCP, gRPC server, Docker nor any network listener is added. The Protobuf service declarations designate roles; they do not create a transport or an authentication boundary.

**Exact upstream source pin:** `vjmichael/Lu-AI-GUI` commit `9f43d078aa5e979de0ff72ca4c19e8c5829572af`, `workspace.proto` Git blob `4e01d921197fb1c58c99958479b1cede36e13c9a`, version 1.0. NVP's eight original capabilities and effect classifications come from `contracts/nvp/film/v1/capabilities.json`. This bridge does not edit either source. The native installed owner MUST generate its runtime classes against the exact reviewed Protobuf schema; our local unit tests use a *partial* field-number projection and **cannot substitute** for generated/prost acceptance.

## Concrete R2 source

- `backend/nvp_lu_operation_journal.py`: R1 transactional store extended to bind **complete** declared effects, including `EXECUTE + WRITE_WORKSPACE` for render/export, and to read the *original* operation spec only with supervisor authorization. Original user turn, typed input digest, source-ordered object digest, deadline, session and Core epoch are durable. In-flight work never auto-restarts.
- `backend/nvp_lu_provider_bridge.py`: bounded, canonical Protobuf parsing and big-endian frame read/write (3-second deadlines), exact type URL/draft effect allowlist, 64 KiB typed values, 16 source-bound ObjectRefs, 256 KiB outer frame, user workspace/session check and testable `LuWorkspaceProvider` message dispatch.
- The bridge additionally returns a **fixed-category `ProtocolFailure`** only to an already admitted peer, never leaking local exceptions; ambiguous post-claim failure is explicitly `outcome_uncertain=true, retryable=false`. The provider calls an **external protected native supervisor** at every gate: verified installed Lu session, full Lu per-turn effects *and* NVP creator/Take/revision approval, single native worker dispatch, cancellation signal, native revocation, independent result receipts. No callback, no dispatch. Neither caller-supplied Protobuf IDs nor this Python object are authority.
- `tests/nvp_lu_provider_fixture.py`: deliberately incomplete Lu/NVP schema projection for isolated runtime tests only; **do not ship as official generated Protobuf bindings**.
- `tests/test_nvp_int_lu_01f_r2.py`: executable protobuf/framing, native-host seam and failure tests. Original 17 R1 tests retained unchanged.

## Operation lifecycle, exact wire behavior

1. **Invoke:** Require a fresh OS-attested session before parsing any effect. Validate `WorkspaceFrame` canonical bytes, version, safe session/request refs, original `OriginRefs`, capability ID/version, generated NVP `TypedValue`, ObjectRef hash/size/expiry and full declared effect set. Host/NVP supervisor independently approves real user-turn grants and creator controls. Atomically `PREPARED → IN_FLIGHT` in SQLite before calling `dispatch_once`. A crash or exception after claim is **ambiguous** and cannot cause automatic re-dispatch. Duplicate `operation_ref` is denied and routed to Reconcile.
2. **Stream credit:** No event is sent until Lu supplies a bounded `StreamCredit`. Stream event sequence starts at 1, credit requests must be unique, max 64 event budget. `DISPATCH_ADMITTED` means *only* the native owner accepted the handoff; it is **not** an effect success. No artificial repeated progress. The native owner must witness actual worker output.
3. **Native terminal:** The supervisor supplies an externally verified `ReceiptObservation`. It is durably reconciled before optional `OperationEvent.terminal` emission. If the pipe dies, or credit is missing, the terminal remains in SQLite for `Reconcile`, with no auto re-execution or media publication. Terminal SHA is evidence *locator*, not proof without native key/source checking.
4. **Cancel:** `CancelOperation` identifies existing original operation and reason; the supervisor binds it to the admitted session/epoch and checks authorization again. SQLite records `cancel_requested` first. `CancelAcknowledged.signal_recorded` means **the signal was recorded, not that worker exit, effect rollback or terminal CANCELLED occurred**. A prepared/undispatched operation can be cancelled durably without fake native worker acknowledgment.
5. **Revocation:** Lu v0 does **not** define `RevokeOperation`. NVP native supervisor, not model/caller-provided Protobuf, delivers revocation from protected enrollment/host policy. Journal records revoked state and supervisor forwards an independent stop signal if work was dispatched. Revocation does not rewrite already applied effects.
6. **Reconcile:** `ReconcileOperation.expected_origin` must exactly match the durable original workspace, conversation, user turn, task, operation; host independently reauthorizes across epochs. Valid native receipts may resolve `UNCERTAIN → TERMINAL` even after Lu disconnects. No evidence yields `TERMINAL_STATE_UNCERTAIN`/`evidence_available=false`; **never** treat uncertain as failed/cancelled/retryable.

## Local acceptance

`PYTHONPATH=. python -m unittest discover -s tests -p 'test_nvp_int_lu_01f_r*.py' -q`

Observed on Linux/Python 3.13 with `protobuf 6.33.6`: **41 tests run; all passed**. Includes real AF_UNIX separate-process socket framing and kernel SO_PEERCRED observation, partial sends, oversized/truncated frame denial, forged session, altered user turn, corrupt ObjectRef, compound effect binding, no creator grant, duplicate/crash safety, explicit cancel ACK semantics, supervisor revocation, verified native terminal, and reconciling after Lu disconnect. Test owner/session/receipt approvals are **synthetic callbacks**. No native Rust/prost compilation for R2, genuine Debian qualification, installed Windows SCM/Job/AppContainer tests, signer's peer authentication or positive Lu→NVP installed exchange. This Linux UDS fixture is NOT a production OS peer-admission test.

## Required follow-on acceptance / blockers

- Implement the **actual installed NVP native supervisor adapter** that securely issues callbacks using Windows SCM/Job/AppContainer process custody, source-bound Project/FilmIndex/Take and creator signoff; it must not trust arbitrary Python lambdas, caller-minted `AdmittedLuPeer` or fixture classes.
- Re-pin current Lu source on integration; generate full Lu + NVP Protobuf in Rust/prost with the NVP provider direction and compile exact source on Windows and Debian. The R2 Python fixture projection is never used as production binding.
- Lu Core (Lu-owned issues #245 real Health; #246 NVP ObjectRef/effect bridge; #247 signed NVP enrollment) must authorize/register 8 exact capability descriptors; installed broker must provide bidirectional channel, per-turn original scope and effect grants. If a missing Core contract is discovered, create **a Lu Core issue**, never edit Core here.
- Add bounded native transport receive loop, multiple concurrent sessions/backpressure and exact provider admission with an OS identity witness; real read/proposal and explicit creator-approved render/decision, session revoke, restart, power-loss and denial tests on installed Windows.
- Run whole-NVP regressions before stabilization/security/installer acceptance. Keep standalone NVP functional without Lu; keep original Take and PCM unmodified; LTX produces picture only. No new NVP branch/PR, no force push or CI stacking.

**R2 disposition:** NVP-side Protobuf and journal-to-native-owner *interface* implemented and locally tested; **actual protected installed native supervisor/worker connection and genuine Lu-to-NVP acceptance remain OPEN**. Do not label tests as a trusted installed positive exchange.
