# NVP-INT-LU-01E-GPU-01 — Cooperative Lu GPU yield / NVP diffusion all-clear

**Status: NVP source implementation / local negative and fixture acceptance only. Lu installed GPU-yield contract #250 and physical Windows acceptance OPEN.**

## Ownership and user requirement

NVP may **request** cooperative unloading of Lu's GGUF/MMProj model before starting a GPU-intensive film-generation task. It must wait for Lu to independently verify the memory release and grant a bounded, original-turn-scoped GPU yield lease. NVP exclusively owns its LTX/Wan/Blender workers, production data, immutable Takes and PCM. When **all** NVP GPU contexts are released, NVP sends a durable all-clear. **Lu**, not NVP, may reload the prior AI model under its own current selection and model-generation policy. Neither an NVP process exit code nor a Core `ALLOWED` advice is release proof.

The existing `lu.workspace.v0` Protobuf `ResourceTransitionRequest` / `ResourceTransitionDecision` (Lu Core PR #244, blob `4e01d921197fb1c58c99958479b1cede36e13c9a`, wire major 1, draft minor 2) is the **advisory request**, not a GPU lease. `ResourceAction.COOPERATIVE_UNLOAD=1`; `ResourceTransitionDecision.ALLOWED=1` means only the request has been considered. The canonical wire retains OS-local named pipes / UDS, host-owned enrollment and exact origin references. There is **no** second NVP HTTP/model server, unilateral model kill, or use of `ModelLeaseRelease` as an LTX all-clear.

## NVP implementation

- `backend/nvp_lu_gpu_yield.py`: `YieldIntent` records the host-enrolled session, immutable original user/conversation/turn/task/operation refs, NVP project, a **host-reserved** GPU Job/session identity, independently observed GPU device, VRAM requested, duration and deadline. `LegacyResourceRequestCodec` can *build* a source-locked cooperative-unload request and a read-only capacity query. **The current `NativeLuAdvisoryGateway` deliberately sends only `QUERY_CAPACITY`; it REFUSES live cooperative unload** because the draft Core has no usable all-clear acknowledgment. Sending an unload without a corresponding safe release would strand the Lu model. An `ALLOWED` response is permanently **advisory only**. A future feature-negotiated Core roundtrip port will send actual unload requests. The coordinator itself checks `ready_for_safe_roundtrip` **before journaling or attempting an unload**, so an unavailable Lu handshake causes no model-memory action or stranded pending request.
- `GpuYieldJournal` uses protected SQLite WAL/FULL. One immutable operation has exactly one dispatch; the independently attested Core grant binds Lu Core epoch + host session + original source + NVP GPU job + device + Core model generation + observed free VRAM + expiry + genuine receipt. Duplicate lease refs, wrong original turn, a stale Core session/epoch and insufficient measured VRAM are refused.
- The coordinator's start gate independently checks **live Core lease** and NVP protected native-worker admission. `run_admitted_protected_diffusion` may call an existing installed NVP diffuser only behind that gate. On success, cancellation or failure, it demands independent native Job/AppContainer/SCM and GPU-context quiescence evidence before any all-clear. A pending or failed proof leaves the resource fence held. `cancel_before_launch` also requires native proof of **no launched GPU worker**; no blind cancel/reload.
- The all-clear carries a fresh, journaled one-use release identity plus original Lu lease and native receipt. Lu's authenticated durable ack is checked independently and reported with its **Lu-owned** model reload state; NVP cannot force reload. A duplicate ack is reauthenticated. On NVP restart every nonterminal operation is `UNCERTAIN`; it cannot launch, request a second lease, or retransmit/release optimistically. A matching independently authenticated Lu ack may reconcile a previously sent release.
- `backend/nvp_lu_windows_native_admission.py`: the new database and its SQLite sidecars share the **same existing Windows EFS/owner** as NVP's protected production journal, never a user-selected directory.

## State transitions

| State | Accepted progression | Denied/uncertain condition |
| --- | --- | --- |
| PREPARED | Original creator/turn verified; record exact request before sending | No original approval/session/identity |
| REQUEST_SENT / WAITING_CORE | Lu's legacy reply is informational; receive authenticated separately verified Core grant | `ALLOWED` alone **cannot launch**; DENIED -> REFUSED |
| GRANTED | Host verifies Core actually freed enough VRAM and holds a live bounded GPU lease | Wrong GPU, epoch, job, model generation, expiration, unseen measurement |
| PROCESSING | NVP protected owner supervises approved LTX/Wan/Blender work | No Core lease or installed worker custody |
| QUIESCENCE_PENDING | Native SCM/Job worker **and all GPU contexts** independently reaped/observed | Worker return code or Python `finally` alone |
| ALL_CLEAR_READY | Owner-authorized durable nonce prepared | Forged SCM witness or active workers |
| ALL_CLEAR_SENT | NVP sends exact lease + nonce + native receipt; waits for Lu durable ack | Lost ack -> UNCERTAIN on restart; no blind resend |
| RELEASED | Genuine Core ack bound to original lease & native receipt; Lu reports reload state | No NVP-side model reload command |
| UNCERTAIN | Explicit host/lease reconciliation or verified previously sent ack | No automated retry, assumed free VRAM, worker kill or timer-based reload |

## Required host integration before physical acceptance

1. **Lu-owned protocol**: Core issue [#250](https://github.com/vjmichael/Lu-AI-GUI/issues/250) must define accepted, feature-negotiated GPU-yield grant, renewal, all-clear and reconciliation messages with host-minted lease IDs, Core epoch, device, selected model generation and verified release receipts. This NVP candidate does **not** assign incompatible new Protobuf tag numbers or pretend a legacy ALLOWED equals `GRANTED_AND_RELEASED`. The `UninstalledCoreGpuYieldPort` fails closed by default.
2. **NVP protected worker binding**: reserve an original host GPU operation/job identity **before** requesting Lu memory. Current POST-01F `ProtectedLtxHandoff.run` mints its own `ltx_...` job ID *inside* `run`; the installed supervisor must link this child to the pre-authorized parent GPU session (or safely reserve the exact `ltx_...` job in advance) before it can be used for a real resource grant. No arbitrary UI-supplied native job ID. Verify *all* children/contexts are reaped, not only a positive picture receipt for one chunk.
3. **Installed physical evidence**: original Lu Core signed NVP enrollment, Windows Job/SCM/CNG P-256 + EFS/WFP/AppContainer custody, native GPU measurement (including AMD Radeon AI Pro R9700), cancellation and restart/timeout/lease-renewal proof. No source test asserts those installations or active-model eviction/reload.
4. **Creator UX**: report `Waiting for Lu to free GPU memory` → `Ready for diffusion` → `Processing` → `Checking GPU release` → `Lu may restore its model`. Display `UNCERTAIN` prominently; never claim a Lu model loaded until Core reports `READY`. NVP standalone mode is unchanged and must retain its own independent GPU admission policy.
5. **Long batches**: one Core resource lease across approved diffusion batches where supported. Core must preserve a GPU fence during active NVP work; expiration/connection loss never causes automatic Lu reload without independent GPU-worker quiescence. Lease renewal and multi-shot binding remain future Core protocol work.

## Local qualification

Run `PYTHONPATH=. python -m unittest discover -s tests -p 'test_nvp_int_lu_01e_gpu.py' -v` from the NVP source root. Fixture owners, projected Protobuf messages and fake Core acknowledgments test only local state-machine invariants. The existing R1–R2-R2 IPC, original NVP LTX audio-policy and JavaScript prompt suites are separately rerun. Independent physical Windows native installed acceptance is **not** implied.

**Publication policy:** use only existing NVP branch `nvp/mainline-convergence-20261113` and PR #161; do not stack a CI cohort or create new branches/PRs. Core's implementation remains wholly in the Lu repository.
