# USD-FILM-02M-F → loaded-model authoring → actor/camera film — task-group acceptance

Status: **NOT YET ACCEPTED**. This document defines the execution sequence; it is not evidence of an installed Windows run, loaded model, or final filmed shot.

## CI policy (2026-11-09 creator decision)

Do **not** run a separate GitHub Actions matrix after each incremental file change. Work on one task group, collect changes into its head commit, then run one deliberate exact-head Windows/Linux acceptance batch for that group. While jobs queue, implement unrelated work without repeatedly pushing the same CI-triggering branch. Do not interpret queued, skipped, cancelled or superseded jobs as passing. Inspect logs and downloadable receipts; consolidate genuine repairs and rerun only the failed or final group gate. Do not cancel useful in-flight exact-head jobs merely to make a new queue.

## Group 1: Installed Windows director + interruption recovery

**Entry:** PR #148 director draft, WebView2 origin protection, native pywebview confirm, SQLite WAL/FULL recovery and immutable FilmIndex revision support.

**Executable end-to-end scenario on a real installed Windows NVP binary** (not a React mock or Python service alone):

1. Build a signed/hashed installer, record installer SHA, built commit SHA and version; install as an ordinary user. Launch the installed binary from its installation folder, not from a development server.
2. Load an original 02M approved building and an existing or new district. Record source and root USD SHA. Create a draft, preview, add/hide a building, undo, close the entire installed app; reopen and verify exact draft, version, undo history, immutable approved world and actor Take state.
3. Deny the native OS approval; prove no new FilmIndex revision. Approve a *new* exact preview in the genuine Windows OS confirmation dialog; prove a single immutable district revision, actual source-layer reopen and no actor Take mutation. Negative foreign-origin and injected `creator_approved` calls must fail.
4. Inject controlled host termination **before** approval, **after approval persistence but before FilmIndex publication**, and **after immutable publication but before proposal journal finalize**. Relaunch the installed app and inspect durable state. Missing publication must require new approval; exact completed publication may reconcile without replay; different source must conflict. Ensure no descendant Blender worker remains and no stale one-use grant survives.
5. Restart, uninstall and reinstall. Test both durable user data retention and the intended clean-uninstall behavior separately. Capture installed executable identity, OS/app logs, draft ledger state, source SHA, FilmIndex revision and video/screenshot of genuine dialog interaction. Check that restart recovery is navigable in the actual GUI.

**Gate:** physical Windows OS + installed app evidence for all steps; exact-head Windows native compilation and tests, no failures hidden by mocks. Keep OPEN until those artifacts exist.

## Group 2: Loaded AI → bounded actual model-authored source proposals

1. Identify and run NVP's actual loaded local or configured model through its real worker/provider API; record model file digest or provider/model/version, request/response IDs and execution session. A UI `proposed_by=ai` selector is never model-execution evidence.
2. Supply a strict **read-only** source catalog, project/district/base revision/SHA, geometry/budget limits and creator intent. Separate the raw model output from the host's validated typed candidate.
3. Admit only the exact existing original-world `params` shape and whitelisted edit operations. Reject arbitrary tools, script bodies, path/URL substitution, unknown fields, excessive building IDs/instances, nonfinite coordinates, missing source references or stale source SHA. Validate with 02M-E1 native source planner and USD stage; never treat an LLM self-report as geometry proof.
4. Record source-locked request, response, validation/error, model provenance and host-created draft ID as durable evidence. A model may suggest/iterate/preview/diff/undo/discard; **never approve or publish**. OS creator approval remains a separately scoped human action.
5. Kill/restart the real worker during generation and between proposal/edit operations; prove a partial or invalid response cannot leave an approved world, a resurrected capability or an unaccounted worker. Reopen only a complete valid host-owned draft.

**Gate:** real loaded-model generated response trace, independently revalidated native USD proposal, rejection/interrupt cases and genuine Windows installed UI inspection. Keep OPEN if the model was mocked or a human pasted JSON.

## Group 3: Approved original building worlds → original actor + camera film

1. Resolve the approved immutable 02M district FilmIndex revision through the existing 01E frozen performance/source working-set and 01D shot data-source path. ActorID and approved voice/animation performance Takes remain independent primary sources, as do approved shot/camera/light authored data.
2. Introduce a single time-aligned shot scene working set that binds exact district/source layer SHAs, bounded visible instance selection, ActorID/Take/animation revision and original camera transforms/focal settings. Generated/manual district layers can affect staging, occlusion, window/door visibility and lighting, but may not silently rewrite performances/cameras.
3. Preview in the installed original film timeline. Verify world→actor→camera transforms and scale with a 3D source scene, front/rear/inside view, occlusion, near LOD for doors/windows/interiors, source-consistent material and original lighting. Reuse E2 Blender/Cycles supervised workers for derived rendering, never replace source truth with a generated image.
4. Change only an approved district revision and re-render the same locked performance and shot: demonstrate changed environment but identical actor/Take and camera source SHAs; then move the camera with a separately authorized shot edit and show world/performance unchanged.
5. Interrupt/recover shot preparation/render and independently validate source and derived image/EXR/PCM receipts. Original 01T 720 frame/48k PCM thirty-second film remains its own full creative acceptance gate.

**Gate:** real original actor/camera source integration, exact-head Windows/Linux build/run, installed timeline review, verified rendering and interruption recovery. Keep OPEN until evidence is inspected.

## Work boundaries and next implementation checkpoint

PR #148 currently provides a host-controlled editor with durable world proposals. It **does not** supply actual loaded-model provenance, installed physical Windows user acceptance, complete original actor/camera shot binding, or full 3D triangle preview. These must be developed and proved; no CI run should be triggered for this documentation checkpoint alone. Group work should be committed on a staging branch and batched into the appropriate single group validation head.
