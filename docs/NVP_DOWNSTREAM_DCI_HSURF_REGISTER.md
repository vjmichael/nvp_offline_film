# NVP downstream register — theatrical DCI/SMPTE delivery and human AI skin

**Recorded:** 2026-11-09 America/Phoenix. **State:** planned; no new
standards acceptance or human-surface renderer claim is made by this register.

**Authoritative integration trunk:** NVP PLAN-02 PR #74, native
OpenUSD / FilmIndex / integer Film Time / frozen ActorID+PCM, zero FFmpeg.
Current PLAN-02-D source-selected renderer/OS worker acceptance precedes
the theatrical conformance task group. Do not reintroduce the FFmpeg 01T
conform donor or promote isolated historical DCP test results as an
accepted canonical source path.

## DCI / SMPTE theatrical output: WO3, WO4 and WO5

**Target:** interoperable theatrical SMPTE DCP **Bv2.1** application profile
(SMPTE RDD 52:2020), aligned with the then-current DCI Digital Cinema
System Specification **v1.5.1** and CTP **v1.6.0**. The DCI CTP
covers testing of digital cinema systems/equipment and does not mean
NVP's desktop editing app has received DCI equipment certification.
Our deliverable claim is conformance/interoperability of independently
validated DCP packages, not DCI certification of NVP as a projector/server.

- **WO3 — native cinema package.** Original source-locked director
  presentation → independently verified 2K/4K cinema sampling →
  12-bit X′Y′Z′ JPEG 2000 picture → SMPTE MXF picture and correctly
  timed 24-bit PCM sound → CPL, PKL, AssetMap, UUID and reel integrity.
  Audit all licenses, codec versions and native decoder/encoder provenance;
  absolutely no active FFmpeg/libav dependency.
- **WO4 — mastering.** Native scene-linear color/ACES and calibrated
  cinema transforms, audio mix/level and sync QA, framing and range,
  reel-break handling, subtitles/accessibility as applicable, validated
  SMPTE Bv2.1 profile, approved source/presentation color controls.
  Delivery formats are outputs; source Digital Takes remain unaltered.
- **WO5 — independent theater playback.** Verify DCP in at least two
  independent software implementations, independently decoded essence
  against original, package/cross-reel checksum checks, actual projector/
  cinema-server ingest, calibrated human sound/picture screening and
  genuine sustained-duration 2K/4K production tests. A mock,
  synthetic-frame repeat or isolated donor job is not enough.
- **DCI-TRACK — standards change watch.** For each release candidate,
  reverify active DCSS, relevant CTP status, SMPTE RDD/profile and
  codec/dependency licenses. Security/CTP equipment test results are
  a separate class from a film package quality report.

**Placement:** PLAN-02-D source renderer/worker custody → PLAN-02-E
30-second native source-to-derivative film → USD-FILM scene authoring
and WO3 package compatibility reconciliation → WO4 cinema mastering
→ WO5 independent screen/reel/ingest acceptance → production release.
The first 30-second film is not itself a DCI conformance certificate.

References:
- https://www.dcimovies.com/dci-specification/
- https://www.dcimovies.com/ (DCI CTP v1.6.0 announcement)
- https://pub.smpte.org/latest/rdd52/rdd52-2020.pdf

## HUMAN-SURFACE — AI Skin project: HSURF-00..10

**Explicit creator sequencing:** **DEFER HSURF-00 until the USD-FILM
family is complete.** Its groundwork remains recorded, never turned
into an accidental prerequisite for PLAN-02-D3/4/5 or the first native film.

- **HSURF-00** Audit reusable USD actor/UV/rig/material reference
  topology, baseline real renderer, licensing, photorealism benchmarks,
  failure modes, multi-view face/torso reference, content-addressed
  source/proposal and creator approval policies.
- **HSURF-01..03** Independent identity/UV-consistent, AI-*proposed*
  skin and face maps with typed PBR/MaterialX channels (albedo,
  normal/displacement, roughness, subsurface scatter). Reuse actual 3D
  head/body/eyelid/jaw/teeth/tongue/eyes geometry and physically
  valid skin lighting; never substitute flat AI-generated video frames.
- **HSURF-04..06** Reusable eyes, hair/eyebrows, pores, expression
  deformation, cinematic lighting and Blender/Cycles multi-view,
  multi-character test scenes. Compare conventional materials to AI
  variants with explicit provenance and no hidden actor drift.
- **HSURF-07..09** ActorID appearance continuity across movement,
  multiple cameras, Film Time, shot revisions and varying light;
  source-provenance, consent, memory/VRAM/latency and deterministic
  fallback benchmarks. Reject shimmer, uncanny geometry and identity
  inconsistency.
- **HSURF-10** Reviewed AI-assisted character surface production in
  one multi-shot, immutable-ActorID, original-PCM film, independently
  reopened/material-verified and creator screened.

**HYBRID-RENDER-00..05** builds the optional, reviewed,
scene-conditioned AI appearance authoring/presentation adapter.
Canonical OpenUSD world, actor identities, rig/performance, exact
source time, original textures/material assets and original spatial
sound remain authoritative; model suggestions never grant tools or
mutation authority. Defer production integration until USD-FILM and
core renderer/material parity gates have passed.

## Evidence / status rules

| Area | Source development | Native acceptance | Physical / production |
| --- | --- | --- | --- |
| PLAN-02-D3/D4/D5 | In progress on isolated D branch | OPEN until grouped exact-head Win/Linux and installed NSIS gate | OPEN |
| WO3 DCI/SMPTE package | Historical donor prototype only; reconcile for canonical DA-00 | OPEN | OPEN |
| WO4 mastering | Historical partial functionality | OPEN | OPEN |
| WO5 independent cinema | Planned | OPEN | OPEN |
| HYBRID-RENDER | Documented plan | OPEN | OPEN |
| HSURF-00..10 | Deferred by creator until USD-FILM completion | OPEN | OPEN |

Do not count a historical 01T/DCP donor compile as accepted data-first
delivery; do not confuse procedural raster PNG or a 0.5B camera-model
smoke with real human skin, cinematic quality, or theatrical conformance.
