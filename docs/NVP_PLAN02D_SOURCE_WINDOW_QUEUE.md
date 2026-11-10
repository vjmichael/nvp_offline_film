# NVP PLAN-02-D1/D2 — Exact source window and non-executing durable render intentions

**Integration base:** canonical PR #74 at `a16e996839fc4c8b08e57189dd2d1f687e183bdf`.  
**Work branch:** `nvp/plan02d-exact-source-window-20261109`.  
**State:** source implementation and negative tests committed; **no exact-head native acceptance yet**. D3 process-tree custody and D4 actual renderer output remain OPEN.

## D1 — Canonical original-source selection

`ExactSourceWindowSelector` accepts only an immutable FilmIndex Digital Take SHA, an independently checked exact-time camera timeline SHA/revision, a single no-gap original camera shot and a bounded five-second `[first_tick,last_tick_exclusive)` interval using integer Film Time (7,056,000,000 ticks per second).

Optional director rail selection requires a separately published and independently reopened PLAN-02-C revision, including rail SHA, camera, original Take, source timeline and interval. Model candidates and unapproved editor drafts cannot be used.

The read-only sample endpoint recomputes the source-preview digest before every observation and evaluates actual source USD state at an arbitrary exact integer tick. Sample indexes and frame rate are not native source identities. This seam does **not** yet connect derived camera poses to the CPU raster, Hydra or Cycles renderer, and must not be presented as a finished shot.

## D2 — SQLite intent journal and real-window review seam

`DurableRenderIntentionQueue` uses existing FilmIndex SQLite revision CAS and immutable dependency links; it introduces no parallel JSON journal. Queue creation is non-executing. The native pywebview bridge checks the exact window origin, enqueues a source-bound intention, displays a *fresh* OS review dialog with Take, camera timeline, rail SHA and Film Time range, and persists a separate approved or refused decision.

A refused intention is terminal. An already-reviewed intention cannot reuse its revision. On restart, previously reviewed intentions require new OS approval even though they never authorized execution. No browser field can grant worker/process/camera publication approval, specify arbitrary native tool paths, or treat provider/model data as OS authority.

## Work remaining in PLAN-02-D

1. **D3 — Host-supervised renderer worker and process-tree custody.** Integrate an actual operating-system custody primitive: Windows Job Object and Linux cgroup/supervised process tree. Prove positive descendants terminated and independent restart attestation before any retry. **Do not** substitute a PID check, direct-child Popen exit, or `lambda *_:True`.
2. **D4 — Derivative native raster/Blender/Cycles output.** Verify source-selected original camera or separately approved rail through actual OpenUSD presentation evaluation, SHA-bound renderer receipt, independent reopen and no overwrite. No FFmpeg import, codec, preview, render, export or fallback.
3. **D5 — Native installed and hostile acceptance.** Run one consolidated Windows/Linux 3.11/3.13 gate after the D group is source-complete. Include OS approval, refusal, stale source, cancellation, crash, restart, process-tree escape, real USD render, exact final image and original PCM invariants. Physical Windows Radeon/creator acceptance remains separate.

## Source additions

- `backend/nvp_plan02d_source_selection.py`
- `backend/nvp_plan02d_render_queue.py`
- `backend/nvp_plan02c_desktop.py` — new host-only `plan02d_*` methods
- `tests/test_nvp_plan02d_source_selection.py`
- `tests/test_nvp_plan02d_render_queue.py`
- Existing DATA-AV grouped workflow extended to include tests and explicit PyInstaller imports **when D task-group acceptance is deliberately run**.

## Evidence distinctions

- PLAN-02-C actual GGUF Qwen 0.5B + llama-server smoke: push group `42762865361`, real camera advice PASS. This is **not** a representative 7B+ quality run, manual director approval, or D renderer acceptance.
- A separate pull-request workflow on that SHA skipped its marked GGUF job, as intended; do not confuse the skipped duplicate with the passed push run.
- The D branch has not run any native CI on its exact head. Its committed Python tests are only **authored**, not accepted.


## 2026-11-09 PLAN-02-D3/D4 implementation continuation (native acceptance still open)

**D3 source implemented:** `backend/nvp_plan02d_worker_custody.py`
builds on existing `nvp_worker_containment.launch_contained`, not a
new unproven subprocess wrapper: suspended creation and Job Object
kill-on-close on Windows; strict cgroup-v2+out-of-leaf guardian on
Linux, with no process-group fallback. Separate OS worker consent,
pinned executable SHA/resource bound, process-local one-use D2
review, durable STARTED before launch, cancellation, tree-close before
success, and fail-closed interrupted/no-replay inventory are implemented.
`tests/test_nvp_plan02d_worker_custody.py` covers negative contracts
and a genuine bounded child when supported.
`tools/nvp_plan02d_custody_native_witness.py` exercises a real
detached-descendant heartbeat under cancellation and abrupt host
termination, with platform backend attestation. **Linux without
delegated cgroup cannot pass this acceptance**; the runner must report
a real blocked gate, not a process-group simulation.

**D4 source implemented:** `backend/nvp_native_cpu_raster.py`
now accepts an independently verified director-rail camera pose as a
virtual look-at view over unchanged actual USD geometry; it does
not overwrite original source cameras. `backend/nvp_plan02d_derived_raster.py`
produces a real 640x360 PNG at selected integer Film Time, reopens it
through Pillow, checks source again after rendering, and permits
only OS-approved SHA-bound new presentation revision publication.
New first-party `plan02d_raster_preview/publish` WebView endpoints
and `NativeCameraRailPanel` controls provide actual native-pixel
preview rather than merely describing an intended shot.
`tests/test_nvp_plan02d_derived_raster.py` uses genuine OpenUSD
sphere/camera/asset and independently approved virtual rail.

**D5 integrated source:** a new `--smoke-plan02d` packaged NVP.exe
mode creates real OpenUSD source, tests live pywebview-native API scope,
verified PNG revision and independent SQLite restart. The grouped
D workflow runs matrix Windows/Linux native tests, real kernel custody
witness, React, and installed NSIS/WebView2/NVP.exe smoke at its exact
head. The smoke dialog is a test stand-in: it does NOT establish physical
human approval. A real 7B+ model, actual Cycles/Hydra film,
general 30-second picture+sound delivery, calibrated DCI
theatrical QC, and AI Skin HSURF remain outside this task group.

**Current status:** source authored and committed; native/installer test
execution **NOT YET OBSERVED** on this branch. Do not promote to canonical
PR #74 before any failing exact-head result is repaired. No CI job
should run for each small code edit; only the final grouped task gate.

**Downstream tasks preserved:** [DCI/SMPTE WO3–WO5 and
AI Skin HSURF-00..10 register](NVP_DOWNSTREAM_DCI_HSURF_REGISTER.md).


## Exact-head acceptance investigation — 2026-11-10 UTC

The first syntactically valid grouped run was
[PLAN-02-D run 42767744382](https://github.com/vjmichael/nvp_offline_film/actions/runs/42767744382)
at `389eee4e2bb8b610616f78f3a207577854aef5b9`.
Its DA-00 zero-FFmpeg audit, React build/source UI tests and genuine native
OpenUSD Python 3.11/3.13 matrices on **both Ubuntu and Windows** completed
successfully. This establishes D1/D2/D3 contract-regression/D4 procedural
image source tests on this exact source SHA; it is **not** whole task group
acceptance or a representative cinema renderer.

Two real OS positive tree-witness problems were identified independently:
- Linux GitHub-hosted Ubuntu 24.04 did NOT have a systemd `Delegate=yes`
  cgroup v2 scope. The positive detached descendant witness **FAILED
  CLOSED**. Do not use process groups, simulated cgroups or direct child
  exit as evidence of actual strict descendant custody. A genuine
  delegated self-hosted Linux scope and successful native witness remain
  a blocked acceptance gate.
- Windows positive witness progressed through an actual cancel path
  but the abrupt-host-crash subprocess script, located under a temporary
  directory, could not import the `backend` package. A bounded
  subprocess-only Python import path repair is staged on a separate
  repair branch; Windows actual host crash is **not accepted** until
  the repaired witness runs and confirms detached descendant exit.

The Windows installed NSIS/WebView2 job reached the actual
install/smoke/uninstall step; it had not produced an outcome when
the repair was staged. The repair groups bounded per-smoke process
waits, PID cleanup on timeouts and an always-uploaded stage diagnostic,
without faking a native application success.

**No extra per-edit CI jobs.** Finish the unblocked repairs, promote
the repair branch once as the next exact-head grouped run, and inspect
all real native results. Keep PLAN-02-D3 Linux custody and D5 physical
creator acceptance OPEN until witnessed independently.


## PLAN-02-D second exact-head evidence / genuine installed restart strengthening

The repaired task-group run is [42768650682](https://github.com/vjmichael/nvp_offline_film/actions/runs/42768650682)
at `094ea70070c670944478e21e8fbdd79a12f21b7f`. Its
**Windows actual detached-descendant cancel and abrupt-host-crash
witness passed**, with uploaded evidence
`nvp-plan02d-real-process-tree-windows-2025`. The known Windows
temporary-script `backend` import defect is therefore repaired. The
Ubuntu hosted runner continues to fail the separate positive strict
cgroup witness because it has no systemd-delegated scope: **not accepted**.

D5 strength-of-evidence repair staged separately: the installed
`--smoke-plan02d` smoke only reopened a new SQLite handle within one
process. Added two distinct installed binary invocation modes,
`--smoke-plan02d-restart-create` and
`--smoke-plan02d-restart-reopen`, with durable identical
NVP_HOME/FilmIndex source, real native USD PNG, and an independently
observed cold-process refusal to reuse an old in-memory OS review grant.
The grouped acceptance workflow must execute both and retain
bounded stage receipts. They are **not yet passed** until one final
integrated exact-head Windows NSIS test witnesses both processes.
