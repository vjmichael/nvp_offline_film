# NVP WO5 — Desktop director intent, source audition and human review

Status: **SOURCE-CODE INTEGRATION IMPLEMENTED; real installed desktop and
theatrical playback acceptance OPEN** (2026-11-07).
Draft PR: [WO5 #91](https://github.com/vjmichael/nvp_offline_film/pull/91).

## Accepted end-to-end production scale objectives (creator decision)

The creator distinguishes three real-film milestones. Each must use an
**original NVP-authored, creatively reviewed film with representative unique
source pictures, acting/action, camera/lighting, edited cuts and synchronized
sound**, not a synthetic timing/structural stand-in.

| Tier | Desired original film | What it proves | Current status |
| --- | --- | --- | --- |
| **Pilot: working NVP** | Up to 30 minutes (24fps, up to 43,200 frames) | Authoring-to-editorial-to-real-playback-to-mastering workflow and director-intent comparison; verified source custody | Multi-reel source-audit and human-report **code implemented**; real original/installed review **OPEN** |
| **Feature-film production** | **60–90 minutes** (86,400–129,600 frames @24fps) | Actual narrative movie produced, edited, sound-mixed, delivered, revised and viewed end to end using installed NVP | **OPEN; deferred until near-production-ready original pilot** |
| **Epic-scale endurance** | **At least 3 hours** (259,200+ frames @24fps) | Distinct-source genuine long-form sustained rendering/encoding, editorial responsiveness, storage/memory/VRAM, human review, cancellation, crash/restart and realistic final delivery | **OPEN; long-form native repeated-source DCP packaging is NOT this test** |

The pilot is not the final production ambition. **A 60–90-minute genuine
feature film is the meaningful primary production acceptance**, and the
3-hour-plus epic is the extended endurance/creative-production benchmark.
Current WO5 inspector's 30-minute limit protects the pilot; higher tiers
require explicit approved longer duration scopes and independent real
media/hardware evidence, not just changing a maximum integer. Existing
WO4 multi-reel resource planner can represent much longer films but has
not proved full genuine scene-rendered feature filmmaking.

## Actual desktop integration (not an arbitrary new HTTP API)

- `tools/nvp_desktop_alpha.py` still boots the existing native
  Windows WebView2 app, local FastAPI server, and the same
  `TrustedDesktopCameraBridge` interface through **a subclass**
  `TrustedDesktopWO5Bridge` as `js_api`. All original
  `data_av_catalog/begin/audio_window/scene_at/stop` methods remain.
  No privileged WO5 write routes were added to FastAPI.
- `backend/nvp_wo5_desktop_bridge.py` checks the actual native window's
  exact local origin **and native project** for every WO5 read/write. It
  inventories source-bound FilmIndex `edit` assemblies, native
  `FeatureJournal` feature states, frozen director intent and human
  review records without exposing native file paths or worker tokens.
  It reuses the same `FeatureJournal` durable store; it never creates a
  second production supervisor or launches a feature encoder.
- **Write approval is a real native OS confirmation** over the exact
  source identity and intent/observations SHA, via pywebview's
  `create_confirmation_dialog`. JavaScript never supplies a
  self-signed `creator_approved` flag. If the window origin changes or
  consent is declined, the write fails closed.
- `frontend/src/App.jsx` adds **19 · Watch & review film** inside the
  existing project workflow. `DirectorFilmReviewPanel.jsx` lets the
  filmmaker select a real approved assembly and plan up to 512
  contiguous exact-Film-Time shots, each with intended action/camera/
  sound; freeze the human decision; inspect the indexed feature's
  complete immutable-original/DCP structural evidence; and record
  later per-shot observed action/camera/sound and revision judgment.
  Statuses remain independent: technical source custody and human
  self-report do not mean creative, theatrical or DCI acceptance.
- `backend/nvp_wo5_original_feature.py` now returns an **approved
  per-reel source Take and exact source Film Time** in its
  hash-verified review response. Selecting a reel opens the existing
  `DataFirstAVPanel` at the real Take and approved 48-kHz source
  sample, with actual native 3D OpenUSD scene evaluation and real PCM
  via the original session grant. The browser does not synthesize a
  fake frame, soundtrack or movie file.
- The native A/V source player now **fails closed if the exact requested
  source Take is not in the verified project catalog**; it never silently
  substitutes an unrelated source. Closing the panel revokes its
  native source-audio session through existing cleanup.

### Playback limitation that must not be concealed

**Native original-TAKE playback is connected** for source review: real
OpenUSD actors/camera/scene state and live spatial sound at approved source
Film Time. However, the current WO5 screen does **not** independently decode
and play the complete flattened multi-reel SMPTE DCP, including final
grade, final edit/cuts, PCM channel order and mastered sound. The creator
must **not** check the "I watched the complete finished film" or
"I listened to the complete finished soundtrack" statements based solely
on original Take audition. They are explicit human attestations, not a
substitute for a missing finished-picture+sound player.

**Outstanding requirement:** a trusted, source-bound, continuous
finished-feature review player, using independently re-opened approved
native picture/sound essence (or a validated native review presentation),
with exact Film Time, seek and continuous sound/picture synchronization
across reel and Take boundaries, and explicit actual installed
application/physical audiovisual inspection. No FFmpeg.
Until proven, the complete-delivered-film playback and human acceptance
gate stay **OPEN**. The work here does not misrepresent a 30-minute actual
film as already created.

## Native and frontend regression plan

- Windows 2025 / Linux 24.04 × Python 3.11/3.13:
  real local Studio/FilmIndex project, native bridge exact-origin window,
  creator's denied/accepted OS confirmation, immutable director intent,
  cross-project denial, no untrusted browser `creator_approved` flag,
  read-only feature and missing published feature refusal.
- Windows/Linux React + actual installed-app frontend build:
  film tab, real native catalog/intent request, clear source-vs-final
  playback distinction, selected source Take/time forwarded into
  `DataFirstAVPanel` and its original data-first source session,
  missing approved Take fail-closed, no synthetic successful acceptance.
- **Actual installed WebView2 acceptance** must be carried out separately
  from React/jsdom unit tests and native simulated-window tests. They
  establish code paths, not GUI installation, OS audio device,
  cinema-grade visual fidelity or completed film production.

## Follow-on needed

1. Obtain exact-head native/React test receipts and repair any failures.
2. Implement genuine finished-assembly picture+audio review playback in
   the installed native desktop, without FFmpeg, with bounded memory and
   source-to-final identity and sound-timing audit.
3. Prove real physical creator authorization, manual lock-unlock,
   stop/recover on GUI exit/relaunch while one durable production
   supervisor continues safe work.
4. Create and personally review original <=30-minute pilot, then
   60–90-minute full feature and >=3-hour epic; record actual director
   comparisons and correction cycles.
5. Independently validate target **SMPTE DCP Bv2.1** and theater
   ingest, calibrated cinema picture and sound, and complete
   release-time licensed third-party notices/SBOM.

WO4 remains open/deferred. WO5 does not claim production or cinema acceptance.

## WO5-04 actual published finished picture + mastered sound (2026-11-07)

**SOURCE IMPLEMENTED; uninterrupted installed-app playback remains OPEN.**

The director review now distinguishes original OpenUSD Take audition from final
published SMPTE DCP viewing. The new native finished-film player decodes the
published picture MXF's real JPEG2000 XYZ12 picture and the published sound
MXF's actual 48kHz PCM24 audio using verified native CineCert asdcplib and
OpenJPEG. It reopens indexed FilmIndex and FeatureJournal identities; checks
the finalized multi-reel CPL/PKL/AssetMap, MXF SHA at admission and exact
per-frame J2K SHA, source time, and original Take approval. The delivered
picture generates a bounded uncalibrated sRGB *screen review* image. The actual
mastered stereo/5.1/7.1 PCM24 is downmixed temporarily to 48kHz stereo for
Web Audio monitoring; the original sound track is preserved. One WebAudio
device clock synchronizes sound samples and display frames across reel
boundaries. The viewer supports exact output frame seek, native OS consent,
stop/revoke, 16-frame bounded buffering, and fail-closed on slow decode,
late audio cues, missing/skipped displayed frames or incomplete presentation.

The first genuine native OpenJPEG/CineCert two-reel test PASSED in
[GitHub run 42408366415](https://github.com/vjmichael/nvp_offline_film/actions/runs/42408366415):
six distinct 2K picture samples with real mastered PCM24, SMPTE multi-reel
packaging, independently decoded published frame 2 and frame 3 on opposite
sides of the reel boundary, exact 48k sample offsets and nonmutation.
Both Windows and Linux React player checks in that run also passed.
Native Python unit checks failed due to an undersized synthetic placeholder
codestream in the test fixture, corrected on a newer commit (new CI pending).
This proof is real native essence **but NOT 24fps real-time performance**,
a fully rendered original 30-minute film, or a theater ingest.

**IMPORTANT installed release limitation:** The normal packaged desktop
does not yet include an approved legally noticed OpenJPEG/asdcplib decode
bundle. The native player is deliberately disabled without a trusted
build-time pinned binary/notice manifest. A developer test can pass exact
host-side codec paths and SHA pins through an explicitly opted-in native
environment, never browser UI or AI self-authorization. Native decode
currently runs external supervised picture unwrap + OpenJPEG decompress +
sound unwrap for each 24fps frame; sustained 24fps throughput is not
yet demonstrated and may require an optimized persistent codec worker.

**Remaining before closing WO5:** verified real installed Windows NSIS
playback, decoder installer/license packaging, optimized uninterrupted 24fps
picture plus actual mastered 48k sound and device drift, real cuts/seek
and cancellation/reopen under sustained load, a 30-minute original workflow
pilot, a real 60-90 minute original feature and 3h+ epic, independently
calibrated cinema picture/real surround sound and SMPTE DCP Bv2.1 validation.
The previous Windows visible WebView2 smoke failed in a source-material
MaterialX scalar verification path. A narrow source-verified PBR connection
fix was committed; its exact-head native results are still pending.

Backend: backend/nvp_wo5_finished_playback.py, codec admission in
backend/nvp_wo5_codec_binding.py, frontend controls in
frontend/src/FinishedFilmPlaybackPanel.jsx and actual native WebView2
bridge in backend/nvp_wo5_desktop_bridge.py. No FFmpeg or original Take writes.
WO4 deferred/open; WO5 production acceptance remains FALSE.
