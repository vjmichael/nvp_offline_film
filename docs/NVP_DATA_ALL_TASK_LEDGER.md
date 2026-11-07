# NVP-DATA-ALL — Per-task migration closeout ledger

**Creator directives (2026-11-06):** All NVP production, capture, authoring,
editing, playback, media import and final mastering must be DATA-FIRST;
**FFmpeg is not used anywhere in the resulting application.** Do not
reintroduce FFmpeg as an optional fallback, packaged dependency, PATH
discovery, executable, CLI, decoder, exporter or test prerequisite. Old
source code may remain in historical commits, but **must not be an active
product path**. Reusable third-party components are welcome provided they
are independently licensed and do not require/invoke FFmpeg.

**Source authority:** immutable Digital Film World + OpenUSD scene,
performance and exact signed-64-bit Film Time events (7,056,000,000
ticks/second), Digital Take hashes, source-signal references and
non-destructive assembly manifests. Hardware renders ephemeral samples
and visuals as requested. Only an explicit final 2D presentation freezes
output raster/video/audio; samples/frames never define a Digital Take.

## Ordered implementation and acceptance tasks

| ID | Task | Evidence required | Implementation | Native acceptance |
| --- | --- | --- | --- | --- |
| DA-00 | Supersede any FFmpeg anywhere; permanent dependency guard | Core/export/import paths cannot spawn FFmpeg; CI enforces no active dependency; no stale automatic CI | IN PROGRESS | OPEN |
| DA-01 | Replace FPS-based shot planning with tick-addressed camera/event editor | Creator can author/edit/revise shots/cuts/gaps in integer Film Time; no 24-fps authority | IMPLEMENTED (source editor) | OPEN |
| DA-02 | Migrate legacy capture and motion controls | New frozen take ties source OpenUSD pose/actor/mic/sound references and exact time; old fixed-frame proxy cannot be a native Take | PARTIAL (original-PCM live microphone capture; full motion pending) | OPEN |
| DA-03 | Connect filming sound producer and spatial evaluator | Immutable sample chunks and source events recorded at filming; two listeners from same Take yield different data-native audio | PARTIAL (live capture + orientation/coarse obstruction) | OPEN |
| DA-04 | Native 3D live picture/audio evaluation | Time-synchronized interactive OpenUSD picture and spatial sound without pre-rendered 2D movie, bounded RAM; renderer device failures contained | PARTIAL (authored USD camera, device-clock scene, GPU loss fallback) | OPEN |
| DA-05 | Non-FFmpeg import and non-FFmpeg final 2D export adapters | Trusted decode/import with source hash; approved 3D→2D image/audio render, independent encoder/mux, no FFmpeg | PARTIAL (native PNG/WAV + uncompressed AVI; cinema export open) | OPEN |
| DA-06 | Quarantine frame/proxy/media legacy entrypoints | No accessible editor, API, or native tool path routes to old frame-based authoring/decoding/execution; legacy data readable as explicitly labeled historical formats | PARTIAL (ASGI pre-dispatch quarantine; broader audit open) | OPEN |
| DA-07 | Native acceptance and installer | Win/Linux tests; installed Windows user interactions; long seek/playback/audio and picture sync; restart/crash/recovery; no FFmpeg present | OPEN | OPEN |

Definitions: **OPEN**=not coded/accepted; **PARTIAL**=substantial code
but missing required behavior; **IMPLEMENTED**=code landed without
independent acceptance; **ACCEPTED**=exact-head native tests including
relevant installed-app evidence passed. Do not collapse these statuses.

## Migration rules

- No claim of complete migration while an active UI/API path still
  produces an authoritative `frame_count`/`start_frame` or generates
  a legacy proxy for native filming or review.
- No deletion of immutable existing source data or silent rewriting of
  previously captured projects. Old formats can be inspected/imported
  only through a separately marked migration reader.
- Prefer one shared evaluator for the same Film Time/scene function.
  Preserve first-party authorization, opaque bounded windows, SHA
  provenance and recovery; tests cannot be waived merely because
  GitHub runs are delayed.
- All work and repair receipts go into
  `docs/NVP_ENGINEERING_STATE.md` and this checklist. The live branch
  is PR #74, `nvp/data-av01-native-scene-playback-20261106`.

## Work performed and outstanding defects

The existing USD/TemporalLedger and DATA-AV-01 source chunk reader,
dry spatial PCM mixer, native sound bridge and audio-clock-linked
world-state inspector establish the data-first foundation, **not**
complete acceptance. The most recent independently observed native
CI at commit `06546564941b319ccea436be59427d213db480ab`
failed: spatial USD time-code type, native consent test assumptions,
one existing React test; Windows installed acceptance was skipped.
These are tasks to repair, not releases to approve.

**Zero-FFmpeg clarification:** prior statements that FFmpeg could
remain for external media or final export are explicitly withdrawn.
A decoder/encoder must come from another suitable library or a native
format adapter; where none exists, the operation remains unavailable
until implemented instead of silently invoking FFmpeg.

## DA-05B — Protected final 2D derived-package integrity (2026-11-06)

**Implementation: committed on isolated draft branch** `nvp/da05b-2d-package-integrity-20261106`, stacked on PR #74 at `d2e81ea2`. **Native acceptance: OPEN.** This hardening is intentionally independent of the continuing DA-00–DA-07 migration job.

The trusted renderer's PNG response must now pass complete Pillow chunk/CRC validation and bounded pixel decoding, not only IHDR signature checks. Reject missing IEND, extra bytes after IEND, malformed IDAT/CRC, unsupported pixel modes and over-limit dimensions; export failure cleans the staged presentation without changing its frozen Take SHA. A complete package is published with OS-native no-replace directory rename: Windows `os.rename`; Linux `renameat2(RENAME_NOREPLACE)`. A concurrent empty output directory must never be silently overwritten. If atomic no-replace cannot be provided, fail closed.

Regression cases are added to `tests/test_nvp_final_2d_native.py` for corrupted PNGs and a destination-creation race. A separate local Pillow/Linux syscall contract exercise passed, **not** a repository regression or Windows-installed acceptance. Exact-head CI, real original-scene 2D raster acceptance, crash orphan reconciliation, and real approved presentation remain open. No FFmpeg dependency was introduced.

## 2026-11-06 — Creator-ordered DA-05/06 batch, then DA-02/03/04/06B

Development branch `nvp/da05-06-native-sequential-closeout-20261106` stacks on PR #75 and the migrating native PR #74. Committed, subject to native verification: creator-approved FFmpeg-free one-file uncompressed AVI from derived PNG+PCM; FastAPI ASGI legacy frame/EXR/proxy quarantine; native miniaudio microphone source recording and freeze/cancel lifecycle; listener-rotated spatial stereo and coarse SHA-bound USD obstruction; real authored camera mode and WebGL-loss recovery; preview-only source-bound saved color decisions applied to derivative picture bytes. Regression tests and Win/Linux CI paths added. **These are implementation receipts, NOT real hardware/installed-app or cinema acceptance.** Full ordered write-up: [NVP_DATA_AV_SEQUENTIAL_CLOSEOUT_20261106.md](NVP_DATA_AV_SEQUENTIAL_CLOSEOUT_20261106.md).

## DA-BATCH-1 — Native 2D delivery, retired executor quarantine, exact source edit cursor (2026-11-06)

On `nvp/datafirst-batch1-2d-quarantine-editorial-20261107` stacked on PR #76, the independent AVI writer now binds the actual PNG bytes read during mux to the manifest's SHA-256, and rechecks the unchanged WAV/manifest after streaming, before publication. Retired SLATE-08B Blender still/proxy CI workflows have been moved to manual-only historical evidence; the live DATA-AV matrix now verifies that the still IPC fails closed rather than expecting prohibited legacy processing. ASGI quarantine permits safe read-only historical sequence/motion records but refuses mutations, codec/color routes and legacy render artifacts. The original `SlateSequenceAssembly` is reused (no parallel rewrite), with a new SHA-pinned `source_at` exact-tick projection from committed assembly output to its frozen Take/shot; no transient review selection changes a committed cut, and no frame materializes. Regression tests were added. **CI and installed output acceptance remain OPEN.** Full professional encoding/mux formats and complete old executable path audit remain outstanding.

## DA-BATCH-2 — Live capture containment, spatial geometry and original USD mesh presentation (2026-11-06)

Branch `nvp/datafirst-batch2-live-spatial-world-20261107` stacks on DA-BATCH-1 PR #77. No FFmpeg; no source video frames. The native microphone recorder now refuses to publish a Take after sample overrun or disk writer failures and protects any spool whose worker cannot be proven terminated; new tests cover failure/cancellation. The spatial PCM mixer now interpolates geometry-based occlusion as source/listener/wall transforms change within each bounded sample window, rather than keeping one abrupt constant attenuation. `OpenUSDAssetRegistry` now accepts strictly bounded original source triangle meshes (max 2,048 vertices / 4,096 triangles), persists the exact topology in SHA-bound FilmIndex and OpenUSD, independently revalidates the original USD layer, and passes the bounded mesh to both the live Three.js renderer and restricted native 2D picture projector. It does **not** claim animated/skinned character parity, physical acoustics, HDR material fidelity, or installed app acceptance. Native Win/Linux OpenUSD tests were added, but **native test results are pending**. Professional actor rigs, HRTF/room simulation, continuous full-length synchronized playback and physical microphone acceptance remain OPEN.
