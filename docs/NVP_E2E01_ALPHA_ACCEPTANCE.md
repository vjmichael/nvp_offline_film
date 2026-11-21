# NVP-E2E-01 — Full Filmmaking Workflow Integration

**Status: IN PROGRESS. E2E-01A test committed; native CI and full alpha
workflow acceptance pending.**

## Objective

Demonstrate a user-visible standalone NVP alpha:

install/launch -> create project -> save/edit screenplay -> import footage ->
construct and revise editorial timeline -> preview/render picture and audio ->
perform approved mix and color grade -> approve picture lock and final audio ->
publish synchronized ProRes/PCM24 final film -> restart and independently
reverify FilmIndex/source custody -> export a real SMPTE DCP -> validate
independently -> reject altered assets.

NVP must **not** require Lu, an MCP server, Docker, a network service, or a
running AI model for this first acceptance. The native editing engine and
app GUI can function independently.

## E2E-01A: Real native editorial technical gate (implemented, CI pending)

`tests/test_nvp_e2e01_native_editorial.py` invokes **real FFmpeg and
FFprobe**; there are no prerecorded surrogate files. It:

1. Opens a real SQLite `Studio` and creates a film project.
2. Saves a screenplay using actual optimistic revision guards.
3. Generates two unique 24fps ProRes/PCM24 camera-like MOV source clips.
4. Imports/rehashes both using real FilmIndex immutable media blob storage;
   commits two FilmIndex asset revisions and removes original source files.
5. Commits an actual `edit` FilmIndex revision selecting 12 frames from
   source A and 12 frames from source B, with exact source revision edges.
6. Invokes FFmpeg's real video/audio trim and concat filters *only on the
   stored immutable FilmIndex source blobs*. Outputs ProRes/PCM24 MOV.
7. Uses FFprobe to independently require 24 video frames at 24fps and an
   approximately 1 second synchronized PCM24 stereo audio track.
8. Registers the output media as immutable FilmIndex bytes and publishes
   a dependent `presentation` preview revision (neither approved final
   master nor approved theatrical delivery).
9. Deletes the preview working file, discards the Studio/FilmIndex objects,
   instantiates new Studio/FilmIndex objects, reloads the screenplay and
   film revision graph, and re-verifies all source/export SHA-256 hashes.
10. Proves stale screenplay updates and replayed edit publication fail.
11. Flips a real byte in the FilmIndex-stored export and proves
   `verify_media_file` refuses altered media.

This is a production-meaningful **integration smoke test**, but its FFmpeg
driver runs directly from the test rather than using NVP's trusted native
worker authorization/containment framework. It is not yet GUI acceptance or
an approved film mastering chain. Never describe E2E-01A alone as a
complete user-facing alpha.

### CI

`.github/workflows/nvp-e2e01-native.yml` requires installed real FFmpeg,
ProRes and PCM24 encoders, and runs on:

- Windows Server 2025 + Python 3.11 and 3.13
- Ubuntu 24.04 + Python 3.11 and 3.13

All four combinations must actually run. No missing-binary skip is accepted.

## Remaining E2E gates

- [ ] **E2E-01A native CI:** Exact-head Windows/Linux four-cell native
  media/edit/SQLite restart/tamper job successful; investigate failures.
- [ ] **E2E-01B native worker:** Reroute the source-to-render flow
  through the existing NVP B14 source-bound conform, resource watchdog,
  OS-contained workers, creator authorization, cancellation, and recovery
  rather than FFmpeg directly from the test.
- [ ] **E2E-01C creative finishing:** Durable native finishing handoff implemented
  in `backend/nvp_e2e01c_finishing.py` with actual AUDIO-01I/J/K native host
  interfaces, FilmIndex approval IDs and restart custody. Four-cell contract
  workflow added; full real color/audio/AV mastering and crash acceptance
  remain pending. See `docs/NVP_E2E01C_CREATIVE_FINISHING.md`.
- [ ] **E2E-01D complete crash/restart:** Durable staging-intent repair
  and abrupt-process-death tests committed for B13, B14, J, K and actual
  TaskLedger ACTIVE RAM reservation. Test reopens new host/Studio objects
  and rejects inferred completion. Native worker kill/crash-injection
  and full filmmaker approval/export recovery remain unverified.
  See `docs/NVP_E2E01D_CRASH_RECOVERY.md`.
- [ ] **E2E-01E installed Windows alpha:** Native React/FastAPI WebView2
  launcher, per-user NSIS installer and Windows workflow committed. The
  workflow must build the bundled application, install, reopen a genuine
  persisted film project in a second app process, load a real visible
  WebView2 window, uninstall and preserve film SQLite data. **Not yet
  accepted.** Import/cut/preview/approved export remain unimplemented or
  unintegrated in the standalone GUI; a shell smoke is not final alpha.
  See `docs/NVP_E2E01E_WINDOWS_DESKTOP_ALPHA.md`.
- [ ] **E2E-01F cinema finishing:** Run actual creator-approved film
  through DCP-o-matic, independently validate SMPTE J2K/MXF/CPL/PKL
  with DcpDoctor, reopen FilmIndex and reject altered DCP MXF.
  Synthetic source DCP tests alone are not sufficient.
- [ ] **E2E-01G regression:** Cross-project isolation; permissions;
  zero RAM leaks and zombie workers; replay protection; exact source
  and renderer/validator binary provenance; bounded disk/scratch and
  power-loss recovery under Windows/Linux.

## Release gating

The final NVP alpha must **run independently** of the Lu AI GUI.

NVP-E2E-01A success allows only the claim that actual footage can be
imported, trimmed, combined, saved, reloaded and tamper-detected by
Studio/FilmIndex. Do not mark E2E-01, AUDIO-01K.3, or NVP's desktop
alpha complete based on E2E-01A.

Draft verification PR: https://github.com/vjmichael/nvp_offline_film/pull/45
