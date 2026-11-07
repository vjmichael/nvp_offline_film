# NVP DA-05/06 + DA-02/03/04/06B — sequential implementation receipt

**Creator instruction, 2026-11-06:** Batch FFmpeg-free final 2D output with
legacy codec/frames quarantine, then implement in order: live immutable
Digital Takes; native spatial audio; live 3D scene presentation;
non-destructive color decisions.

**Working branch:** `nvp/da05-06-native-sequential-closeout-20261106`
stacked on draft PR #75 (DA-05B), which stacks on active migration PR #74.
None of these changes modifies historical source data. CI and actual
installed-application acceptance are explicitly **OPEN** until results
from this branch's exact commit are inspected.

## Batch 1 — DA-05C + DA-06: Native final derivatives and FFmpeg quarantine

- `backend/nvp_native_avi_delivery.py` encodes SHA-verified
  derived PNG+48-kHz stereo PCM16 source into an AVI RIFF with uncompressed
  BGR24 picture samples and interleaved PCM. Native stream-copy/RIFF writing
  is entirely first party. At most 1 GiB and 7200 frames per one-file export;
  one bounded picture+PCM interval in memory at a time.
- A native OS folder selection, exact source SHA, derived manifest SHA and
  **two separate creator confirmations** are now wired to the pywebview
  bridge and editor panel. Neither JS nor an AI model supplies a worker path
  or external output filepath. Derived PNG+WAV stays separately available.
- The DA-05B full-PNG CRC/pixel validation and atomic no-replace publication
  foundation is inherited; AVI uses same-directory atomic hard-link
  publication and deletes the staged temporary path.
- `backend/nvp_legacy_quarantine.py` is installed as actual
  FastAPI ASGI middleware. Retired codec/EXR grade routes, frame-based
  mutators, old frame-based packages and Blender-script exports now return
  HTTP 410 before handlers execute. Read-only old sequence/history remains
  available as historical metadata, not new source capture.
- The no-FFmpeg native dependency guard now inspects each new runtime
  module, its active import graph, and installer requirements.
- **Limit:** this AVI is a large, bounded 640x360 first-party native raster
  derivative for existing USD cubes/spheres. Unsupported character meshes
  fail closed. No claim of ProRes, AV1, DCP, 4K HDR or finished cinema
  mastering. Historical FFmpeg modules still exist in source history;
  removal from every conceivable tool/plugin invocation is not proven.

## Stage 2 — DA-02: Live original Digital Take

- `backend/nvp_native_live_take.py` adds a real miniaudio
  mono 48-kHz signed PCM16 capture path and bounded queue to an on-disk
  original-source spool; no whole-film RAM buffer.
- The native bridge grants start consent, emits recording status and
  requires a second native confirmation to freeze the precise OpenUSD
  camera/effect timeline and immutable microphone source as a Digital Take.
  Cancel discards incomplete capture; closing the desktop cancels.
- Existing source producer (`NativeSceneSoundCapture`) remains the
  one shared freeze path. Browser cannot select microphone raw bytes,
  filesystem paths or make its own source-approval receipt.
- **Limit:** device start/stop and callback are code-supported; physical
  microphone permission, device-loss recovery, overrun safety and installed
  Windows/Linux lifecycle acceptance remain unverified.

## Stage 3 — DA-03B: Native scene spatial acoustics

- `backend/nvp_native_spatial_acoustics.py` supplies equal-power
  stereo gains in the real OpenUSD listener's local right axis, including
  rotation rather than assuming global +X.
- Only SHA-verified authored cube/sphere assets, tagged scene
  prop/environment, may produce coarse broadband obstruction; generic
  actor-position gizmos cannot pretend to be physical walls.
- The existing bounded `FrozenSceneAV.audio_window` consumes
  these gains/obstruction while continuing to read and verify original
  content-addressed PCM chunks.
- **Limit:** no HRTF, measured room-response, diffraction, reflection,
  frequency-selective absorption or continuous Doppler implementation.

## Stage 4 — DA-04: Live 3D source presentation

- OpenUSD source camera matrices and native focal-length metadata now
  drive an optional authored camera perspective in the WebGL scene.
- The editor still supports independent orbit view. Both are evaluated
  from exact Film Time with the audio device's presentation cursor,
  not by a prerendered movie-frame sequence.
- GPU context loss switches to textual source readouts. The PCM playback
  bridge now attempts to revoke native permission when end-of-source
  buffered audio drains, and on scheduling failure.
- **Limit:** primitive shapes only; no cinematic character/skin/Hydra
  geometry, full lighting/material parity, latency instrumentation,
  or uninterrupted feature-length verified playback.

## Stage 5 — DA-06B: Non-destructive color decisions applied

- Existing immutable `NativeColorDecisions` revisions remain
  bound to exact Digital Take SHA. The new
  `backend/nvp_native_color_eval.py` applies bounded
  display-referred exposure/contrast/saturation/temperature/tint controls
  **only** to derived PNG/AVI pixels after creator approval.
- Final output manifests and the second native AVI permission include the
  selected grade revision's exact SHA. The editor allows selecting a saved
  grade for derived output. No original performance, lighting, sound,
  scene, camera curve, or grade version changes.
- **Limit:** this is an explicitly labeled SDR/display-referred prototype,
  not ACES 2, OCIO-calibrated HDR mastering or a reference-grade transfer.

## Test/code evidence and open acceptance

Added new regression cases for AVI header and interleaved tracks, SHA
tampering/denial/no overwrite, HTTP legacy-ASGI pre-dispatch quarantine,
mock real microphone lifecycle/freeze/cancel, listener rotation and solid
obstruction, and grade-on-output with original SHA unchanged. The
DATA-AV native workflow now schedules these tests on Win/Linux with
OpenUSD, Pillow and miniaudio and includes the new modules in the
Windows PyInstaller build. These statements indicate **tests authored
and CI wired**, not tests confirmed passing.

Required next independent gates:
1. Exact-head Linux 3.11/3.13 and Windows 3.11/3.13 unit and native USD
   verification; repair compiler/test failures.
2. Installed NVP native file picker, AVI playback in an independent
   compatible player, source-preserving grade revision and no FFmpeg
   presence, and live microphone start/stop/denial/desktop close.
3. Real continuous synchronized 3D picture/audio, physical device-loss
   and restart containment, acoustic geometry accuracy and latency,
   bounded 20-minute/feature-length seek/playback.
4. Creator-approved film source with real character meshes, calibrated
   HDR/ACES/OCIO, independent non-FFmpeg professional encoding/muxing
   and real final delivery validation.

**No production, cinema, native installation, microphone or acoustic
acceptance is claimed by source implementation alone.**
