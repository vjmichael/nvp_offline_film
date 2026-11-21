# NVP-INT-LU-01F-R2-R2 — Windows native-admission and SCM receipt seam

**Status (2026-11-21): LOCAL SOURCE/NEGATIVE TESTS PASS; WINDOWS INSTALLED / RUST NATIVE OPEN.**

## Scope / exact reviewed inputs

NVP existing draft PR #161, branch `nvp/mainline-convergence-20261113` at SHA
`7ece5eb6efec8007fed867bfcf86a59770f081a5` remains the last published
source observed. The prior **46/46 CI success** applies to that **predecessor**,
not this unpushed R1+R2+R2-R1+R2-R2 candidate. No new NVP branch/PR/CI.

- Lu Core immutable reference: `9f43d078aa5e979de0ff72ca4c19e8c5829572af`
- Lu workspace.proto pinned Git blob: `4e01d921197fb1c58c99958479b1cede36e13c9a`
- NVP domain `nvp_film_v1.proto` Git blob: `5734d04bb08795240cde1508053cd9449847d3eb`
- Real domain `protoc` here: 16 messages, 1 enum, zero services.
- Lu native Rust/prost: **NOT RUN on this candidate.** Local container has no
  `cargo`, `rustc`, complete Lu checkout or installed Windows platform.

## New source changes

1. `backend/nvp_lu_windows_native_admission.py` is a strict **Windows-only**
   journal-owner/EFS admission factory. Requires real `ProductionJournal`,
   actual `ProductionSupervisor`, same protected root and `_require_owner`
   original OS-held supervisor lease. Uses NVP's existing `_protected_path`
   to validate EFS, reparse/identity and SQLite sidecars on every transaction.
   **Does not** authenticate Lu Core, issue HMAC keys or create a pipe listener.
2. `backend/nvp_lu_operation_journal.py::dispatch_binding` provides an
   authorized, read-only original dispatch ticket / request SHA for the
   installed receipt link, without re-execution or minted scope.
3. `backend/nvp_lu_scm_picture_receipt.py` is an **inert until installed**
   typed bridge. For `nvp.film.render.shot` only, it demands complete
   `EXECUTE + WRITE_WORKSPACE`, original operation and dispatch, NVP-owned
   project/plan/picture/bootstrap/model/worker identity, independent native
   SCM Job exit/release fence, and the already-existing fixed EFS/CNG P-256
   receipt reader `bind_installed_scm_receipt_channel` with the NVP's separate
   durable one-use nonce owner. Only after exact signed evidence, real creator
   domain approval and native owner recheck can it write an `APPLIED` terminal
   observation to the durable journal. That means **derived picture generation
   completed**; it is not an approved finished film and does not alter original
   Takes/PCM or bypass picture review.
4. `backend/nvp_lu_provider_bridge.py` has a typed **owner-only** method to
   reconcile a signed picture via the installed channel. It cannot be invoked
   from a `WorkspaceFrame` or work when its installed receipt link is absent.
   Unknown, forged, stale, revoked, cross-session or unregistered operations
   remain fail closed. An ambiguous crash after SCM nonce consumption but before
   IPC journal commit remains `UNCERTAIN`, with no automatic worker replay.
5. `backend/nvp_lu_native_production_link.py` additionally checks that the
   pre-existing read-only media integrity worker and IPC journal truly share
   the same EFS-protected state root. It stays a **read-only** worker, not an
   LTX or cinema export implementation.
6. `scripts/nvp_lu_01f_r2r2_qualification.py` supports explicit **source-only**
   tests and a strict `--native` mode. In native mode it requires a real exact
   Lu Git checkout/proto blob plus `cargo test --locked --offline --all-targets`
   on the existing NVP crate. Absence of any requirement is a BLOCKED/FAIL,
   never a silently skipped native PASS.

## Local test evidence

Python 3.13, protobuf 6.33.6, real local `protoc` 3.13.0: **63/63 focused
R1-R2R2 Python tests passing**, including independent R1/R2/R2-R1 tests,
additional signer/kernel/manifest/ref/effect/refusal and terminal journal
fixture tests. The *positive* receipt fixture deliberately bypasses Windows
construction for internal contract verification; it is **not** a real CNG
signature, native signer, Lu peer, or installed acceptance.

Use the exact local test command (from unpacked candidate root):

```bash
python scripts/nvp_lu_01f_r2r2_qualification.py \
  --protoc /path/to/real/protoc
```

Actual Windows/Linux Rust/prost requirement, only inside a complete NVP and
immutable Lu checkout:

```bash
python scripts/nvp_lu_01f_r2r2_qualification.py --native \
  --nvp-root /path/to/nvp --lu-root /path/to/Lu-AI-GUI \
  --protoc /path/to/protoc
```

The latter must run on *both* genuine Windows and Linux separately. An Ubuntu
pass does not satisfy the deferred Debian native acceptance. `--native`
without full source/toolchains **must exit nonzero**.

## Exact unfinished installed gates

- Create/provision a genuine signed, installed NVP Windows publisher and
  secure `nvp.film` Core credential enrollment; Lu issues #245/#247 remain
  independent and #249 covers actual Core-to-NVP provider routing. A Python
  `AdmittedLuPeer` or observed PID is never trusted enrollment.
- Lu Core #246 must provide exact native `ObjectRef` resolver and honest
  multi-effect `EXECUTE + WRITE_WORKSPACE` authorization. NVP still requires
  original creator/film/revision approvals and native SCM custody.
- Connect the POST-01F installed native owner to the new typed
  `original_spec`, `bind_picture_job`, `kernel_exit_witness`,
  `consume_native_nonce`, and `approve_terminal` callbacks (all from actual
  protected owner, never UI/IPC). Prove signed CNG P-256 receipts on installed
  Windows under native Job/AppContainer/WFP/EFS, cancellation and recovery.
- Complete the exact Rust/prost qualification on actual Windows and Debian,
  then full NVP regression and one reviewed guarded non-forced PR #161 update.
  Until those pass, the R2-R2 source is **prepared**, not accepted/installed.

No Docker, FFmpeg, developer-key fallback, network/HTTP/JSON IPC service,
new branch/PR, original PCM mutation, false Windows acceptance or CI stacking.
