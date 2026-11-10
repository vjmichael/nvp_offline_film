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
