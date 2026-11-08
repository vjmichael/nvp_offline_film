# WO5 — Real Production Acceptance and Original Up-to-30-Minute Film Proof

Status: **STARTED / implementation in progress / production acceptance OPEN** (2026-11-07).
Branch: `nvp/wo5-production-proof-20261107`, stacked on WO4 draft PR #90.
WO4 is **deferred, not closed**. The creator explicitly distinguishes passing a
synthetic pipeline benchmark from proving that NVP creates a film as intended.

## Creator production-scale milestones — revised 2026-11-07

**The <=30-minute original is the initial functional/workflow pilot**, not
the ultimate feature-film acceptance. The real production proof will be
an original **60–90-minute feature film** (86,400–129,600 frames at 24fps).
The extended endurance and creative-scale proof will be an **epic at least
3 hours long** (259,200+ frames at 24fps). Each must be NVP-authored with
varied authentic source scenes, real acting/camera/sound and editing,
creator inspection, correction iterations, genuine final AV playback and
delivery. The 2–3h *synthetic repeated-source native packaging CI* is NOT
the epic-film acceptance. Do not artificially extend Bv2.1 DCP coding rules
when producing higher-fidelity outputs outside the theatrical profile.

Current 30-minute FilmIndex original-feature checker is scoped intentionally
to the first pilot. The later 60–90-minute/3h tiers need explicit
end-to-end source scopes, playback and workflow evidence; multi-reel
resource planning alone does not certify them.
Full desktop handoff:
[NVP WO5 desktop director workflow](NVP_WO5_DESKTOP_DIRECTOR_WORKFLOW.md).

## Creator correction — original means up to 30 MINUTES, not 30 seconds

**Creator corrected the initial proof to a genuine NVP-produced original
film of no more than 30 MINUTES** (43,200 presentation frame slots at 24fps),
including varied original shot content, performance, camera, audio and
editing. The previous thirty-second threshold was a misunderstanding and is
superseded. The original 60-second throughput benchmark is not the creative
proof. Full separate two/three-hour diverse-feature and calibrated theatrical
evidence remain later gates. WO5 cannot close WO4 solely from synthetic
OpenJPEG/CineCert MXF/DCP CI.

**Implementation update — 30-minute source-admission checks exist; real
production proof still OPEN:** The historical one-reel sample API
`backend/nvp_wo5_original_short.py` remains limited to 720 frames/30 seconds.
WO5-01 now also includes `backend/nvp_wo5_original_feature.py` to audit
multi-reel features of up to 43,200 frames/30 minutes against real indexed
FilmIndex assembly and native journal evidence. This has passed *contract
regressions only*. It has **NOT** been proven with an NVP-authored 30-minute
original, nor is the physical/creative/theatrical acceptance complete.
Single-reel originals over 30 seconds still need a unified review route.

## Work packages and truthful status

| ID | Work | Status |
| --- | --- | --- |
| WO5-01 | Define an original-film evidence boundary: exact FilmIndex source Take, mastering decision, source XYZ12/J2K frame custody, PCM24/MXF, FilmIndex-indexed DCP. 30-minute multi-reel source-bound sequence (existing 1–30-second implementation is insufficient), reject three-frame repeated synthetic stand-ins, never elevate SHA uniqueness to artwork validation | **Multi-reel bounded source-audit IMPLEMENTED; 4/4 Windows/Linux Python 3.11/3.13 contract tests PASS in run 42401400107.** Genuine 30-minute NVP media/render/playback acceptance OPEN |
| WO5-02 | Define director's intent and human comparison receipt: approved script/shot intention, performed action/actor blocking, camera motion, scene continuity, audible dialogue/environment, final cut timing, explicit mismatch and correction notes; no independent SHA-based creative assertions | **Native desktop review code and user controls IMPLEMENTED** (`nvp_wo5_director_review.py`, `nvp_wo5_desktop_bridge.py`, `DirectorFilmReviewPanel.jsx`); genuine original Take 3D/PCM audition linked, new native/UI/WebView2 CI pending. **Installed real completed-feature playback, actual creator review and acceptance OPEN** |
| WO5-03 | Author, film, edit, render and inspect one genuine <=30-minute original using near-production scene+rigged actor+camera+native spatial audio, immutable Digital Takes and source-bound editing; compare full video/audio playback to director's intended outcome | **DEFERRED until NVP is near-production ready** |
| WO5-04 | Native installed Windows and Linux tests: trusted editor/project grant to independent supervisor, manual NVP lock, close/reopen, cancellation and crash recovery, actual 30-minute output, controlled disk/RAM/CPU/GPU/power evidence | **Windows source-code WebView2 smoke and native bridge regression submitted; installed NSIS/physical hardware and complete finished-film playback still DEFERRED/OPEN** |
| WO5-05 | External calibrated picture/sound specialist, independent SMPTE/DCP verifier, projector/cinema-server ingest and relevant distribution/encryption tests | **DEFERRED specialist acceptance, mandatory before theatrical claim** |
| WO5-06 | Representative genuine 30-minute original plus later 2h/3h sustained performance, including failure recovery, **not** repeated-frame synthetic throughput | **DEFERRED scale/performance gate** |
| WO5-07 | Release-time exact executable/runtime dependency SBOM and original complete third-party LICENSE/NOTICE, actual Windows/Linux distributables and installer/uninstaller | **DEFERRED to installer freeze, but mandatory for redistribution** |

## Original up-to-30-minute film success conditions

1. **Authored:** NVP's user-facing production workflow genuinely creates the
   story action, staging, scenery, camera and soundtrack intended by the
   filmmaker. It must not be a text-only workflow, stand-in still images or
   externally fabricated success log.
2. **Original source custody:** real FilmIndex project, frozen OpenUSD Digital
   Take and authored exact-time frame/sound sequence. Full source SHA and
   provenance reopened without modifying original takes. NVP may use AI for
   scene assistance, but the production result and user choice must be real.
3. **Varied frames:** genuine ordered image samples from the authored scene,
   not 3 repeated OpenJPEG frames or copy/hardlink aliases used in stress CI.
   The WO5-01 guard requires at least 50% distinct SHA receipts (minimum 12)
   for this **specific proof**. That is a low-level eligibility threshold, not
   a motion/quality criterion and **not** a rule that all fictional movies must
   contain changing pixels.
4. **Native delivery:** source-bound native picture+48 kHz PCM sound, original
   Film Time, completed DCP package, trusted FilmIndex publication, real
   playback/independent picture+audio decode. The actual picture and sound
   must be inspected, not merely their hashes.
5. **Director review:** watch and listen to the entire short. Record which
   intended shots and actions appear, camera/composition/lighting fidelity,
   actor performance, sync, cuts, sound placement and audible artifacts.
   Explicitly mark pass, correction-needed, untestable and not-observed
   categories. A SHA mismatch automatically invalidates the technical
   record; technical SHA success never becomes a director's pass.
6. **Failure/resume:** protected supervisor, process-tree cancellation and
   safe file/FilmIndex recovery after failures on an actual installed host;
   NVP manual Home/slide lock must never terminate or approve a job.
7. **Release boundary:** an original <=30-minute film is necessary for this first
   production validation, but is **not sufficient** to claim full feature
   rendering performance, theatrical/DCP certification, secure installation,
   color reference calibration, licensing clearance or production v1.0.

## Existing WO5-01 engineering sample entrypoint (not 30-minute proof)

`inspect_original_short_readiness(index, journal, project_id, job_id)` reads
**real trusted** `FilmIndex` and `CinemaDeliveryJournal` objects, checks the
specific immutable Take/decision/indexed DCP, actual re-verified source
XYZ12/J2K/PCM24/picture+sound MXF SHA receipts and full package structural
hashes; then currently checks exact contiguous 24fps duration <=720 frames and frame
variation. It does NOT yet authenticate a complete 30-minute multi-reel
creative presentation. This mismatch is an explicitly open implementation task. It does not open a web API, accept user/browser supplied approval
booleans, publish a film, mutate sources or mark production accepted.

Only returned status is
`ELIGIBLE_FOR_LATER_CREATIVE_REVIEW_NOT_ACCEPTED`. Even then, all actual
creative intent, installed-app, independent essence decode and theatrical
acceptance fields remain **false**. CI tests use synthetic hashes to validate
**rejection and contract enforcement only**, and are never evidence that NVP
made or delivered the original film.

## Developer handoff

When the real short is available, collect a source-bound goal/scene-to-receipt
ledger and capture actual viewable playback, original source revisions and
production/recovery logs; compare creator intent with output. Reopen WO4's
deferred full creative validation on that evidence. Keep the physical
theatrical, feature-length performance and distribution/NOTICE gates separately
open. **No FFmpeg.**

## Approved product end-state linkage

The theatrical release target is **SMPTE DCP Bv2.1 (SMPTE RDD 52:2020)**
with applicable normative SMPTE DCP operational constraints, not a custom
higher-bit-depth cinema package. NVP may deliver alternate higher-fidelity
OpenEXR/HDR/wide-gamut/non-DCP formats under separate validated contracts.
Production quality, novice-friendly native desktop usability and a
capability-aware **AI execution layer that understands and securely operates
NVP's actual tools** are first-class end goals, not optional polish.
Full decision: [NVP theatrical Bv2.1 and product end state](NVP_THEATRICAL_BV21_AND_PRODUCT_ENDSTATE.md).

## WO5-01 — 30-minute native multi-reel source-custody implementation (2026-11-07)

**IMPLEMENTED ON DRAFT PR #91; native 30-minute admission contract CI PASS (4/4, run 42401400107):**
`backend/nvp_wo5_original_feature.py` introduces
`inspect_original_feature_readiness(index, journal, project_id, feature_id)`.
It accepts only an actual `FeatureJournal` and `FilmIndex`, an **INDEXED**
feature (not an interrupted/orphan stage), the exact same native project DB,
a frozen FilmIndex multi-reel assembly and final indexed feature DCP receipt.
The existing feature journal independently verifies all source XYZ12/J2K/PCM24
and picture/sound MXF checkpoint bytes and the published multi-reel package.
WO5 then checks each ordered reel against the original source Take,
source-authorized mastering decision and per-frame ordered picture SHA,
re-opens the frozen OpenUSD Take, verifies source DCP FilmIndex receipts, and
streams per-position evidence through bounded SQLite cursors. Reels must have
continuous Film Time, 24 fps, and an aggregate of 24–43,200 frames. Exactly
six 7,200-frame reels represent 30 minutes. A separate bounded SHA-diversity
pilot rejects three repeated synthetic frames, but **SHA uniqueness never
proves movie quality, real camera/actor action or human creative intent**.

The host-side audit returns
`SOURCE_CUSTODY_READY_FOR_HUMAN_FILM_REVIEW_NOT_ACCEPTED` only, with all
creator review, installed hardware, independent decode, SMPTE DCP Bv2.1,
theatrical and WO4/WO5 production-acceptance flags **FALSE**. It does not
create the film, repair a production failure, approve scenes, overwrite
sources, grant model authority, spawn a duplicate supervisor or use FFmpeg.

Added `tests/test_nvp_wo5_original_feature.py` with 43,200-frame metadata
and per-position identity coverage, intentional three-frame-repeat rejection,
missing/altered/out-of-order source receipt denial, immutable original
FilmIndex vs journal ownership checks, and 30-minute bound. The
`nvp-wo5-original-short.yml` workflow runs both the old narrow 30-second
sample tests and the new 30-minute bounded admission tests on Windows/Linux
Python 3.11/3.13, all four passed in [run 42401400107](https://github.com/vjmichael/nvp_offline_film/actions/runs/42401400107). **These tests are contract checks using synthetic SHA
receipts, NOT a 30-minute original film or a full real feature integration.**

**Still OPEN:** actual fully approved 30-minute six-reel native source film and
complete independent picture+sound decode; deeper installed GUI/creator-intent
review flow; real native feature restart/cancel/error tests; Bv2.1-specific
interoperability validation; calibrated external theater playback; actual
licensed packaging. The original single-reel sample API is unchanged and
remains explicitly limited to 720 frames; future source-unified single-
reel >30-second review is still a separate integration gap.

## WO5-02 — Immutable director-intent versus viewed-result records (2026-11-07)

**NATIVE IMPLEMENTATION COMMITTED; exact-head CI for this addition pending.**
`backend/nvp_wo5_director_review.py` provides two distinct FilmIndex
`presentation` records and strict native-approval scopes:

1. `register_director_intent` freezes the filmmaker's intended camera,
   subject/action and sound for each ordered 24fps shot over the approved
   immutable FilmIndex edit/assembly. Bounded full-coverage 1–512 shot
   identities and exact nonoverlapping Film Time are required. Records are
   read-only/new-object revisions; they do not create a film and cannot
   replace the original Take or revised cut.
2. `record_director_review` first reopens the trusted WO5-01 source-custody
   auditor for the **same** published film, then captures exactly ordered
   host-authorized human observations and `MATCHED`,
   `NEEDS_REVISION`, or `NOT_OBSERVED` judgments. It binds the
   review via immutable FilmIndex dependencies to both the earlier intent
   and exact published feature presentation. Review completeness and
   whether the director requests revisions are attributed to the human
   report, not inferred by the model or from files. The return remains
   **production_acceptance=False** and **independent creative/technical/
   SMPTE Bv2.1/theatrical acceptance FALSE**.

`tests/test_nvp_wo5_director_review.py` includes actual local FilmIndex
intent/observation persistence, refused consent, shot scope and timing
validation, original-assembly nonmutation, malformed report refusal,
and distinct self-report vs certification. One review test stubs the
WO5-01 audit result *solely to test document transaction semantics*;
it is NOT evidence of rendered media. Windows/Linux 3.11/3.13 CI queued
against the new exact head.

**Still OPEN:** installed native graphical shot-review UI and actual
authentication implementation; independent observed real 30-minute
picture/audio and non-synthetic scene performance; full creative/artistic
comparison with corrections, Bv2.1 independent DCP validation and real
theater ingest. A developer callback used by tests is not a verified
desktop creator grant.

## WO5 actual native desktop integration — implementation 2026-11-07

**Code committed; current six-job Windows/Linux native/React CI pending.**
The existing Windows `tools/nvp_desktop_alpha.py` window now instantiates
`TrustedDesktopWO5Bridge` (which subclasses the original
`TrustedDesktopCameraBridge`) via the same pywebview `js_api`;
original native camera and FFmpeg-free OpenUSD A/V functions are retained.
No creator authorization was exposed through FastAPI and no second
supervisor was introduced. All WO5 project reads are tied to exact
first-party native window origin plus real Studio project identity.

The NVP project's React navigation includes `19 · Watch & review film`
wired to `DirectorFilmReviewPanel.jsx`. The filmmaker can select a
real frozen FilmIndex cut, author the original action/camera/sound of
each exact-time shot, request real native OS confirmation and freeze
immutable director intent, select the authentic production feature
and run its complete source/package SHA audit, audition the exact
source OpenUSD Take plus native spatial audio at approved source Film
Time through the pre-existing DataFirst A/V viewer, and record specific
director observations per shot through another OS-confirmed native
FilmIndex presentation revision. No model-generated response counts as
execution or creative approval.

**Explicit playback qualification:** The linked A/V viewer is a real
source-Take 3D scene/spatial-sound audition, **not a full continuous
finished-film/DCP decoded playback**. Human checks claiming the creator
saw and heard the entire finished film must NOT be derived from source
preview alone. Complete delivered movie playback, exact multi-reel AV
sync/seek, OS hardware verification, actual 30-minute real original,
60–90-minute real feature, 3h epic and external SMPTE Bv2.1/theatrical
acceptance remain OPEN. The native Take chooser fails closed if the
approved source is missing; it never switches to another Take.

Tests:
`test_nvp_wo5_desktop_bridge.py` and
`DirectorFilmReviewPanel.test.jsx`/
`WO5NativeSourcePlayback.test.jsx`; 6-job
`nvp-wo5-desktop-review.yml` on Windows/Linux.
Exact installed WebView2 tests are separately required, as unit
tests/mock WebView windows do not prove that the shipped installed
NVP executable works end to end. See
[NVP WO5 desktop workflow](NVP_WO5_DESKTOP_DIRECTOR_WORKFLOW.md).

## WO5-04 real published picture+mastered sound desktop player (2026-11-07)

**Implemented in draft PR #91, but NOT independently installed/realtime
accepted.** New native FinishedFilmPlayer checks source-bound FilmIndex
and fully SHA-audited multi-reel DCP structure, reopens final 2K/4K
picture MXF, unwraps true approved JPEG2000 and 24-bit/48kHz mastered
sound MXF, verifies J2K exact original SHA, and maps globally continuous
24fps output Film Time to the correct source reel. An OS-scoped session
in the same pywebview native bridge grants read-only viewing. A bounded
16-frame screen buffer plays audio via WebAudio as the single hardware
clock and displays corresponding decoded picture. The exact-frame seek
and stop controls never change the source or mastered DCP. It fails closed
on missed audio deadlines, missing picture or skipped frames. The screen
preview is approximate sRGB from actual XYZ12; stereo local monitoring
is downmixed from actual mastered PCM24 and is not cinema surround.

The new real native codec CI proved **two-reel final-DCP output/unwrap
picture and sound across the frame 2->3 reel transition** in
[run 42408366415](https://github.com/vjmichael/nvp_offline_film/actions/runs/42408366415).
Two React platform jobs passed there. Python mock-codec fixture with a
too-short placeholder codestream failed and was corrected; newer tests
remain pending. Real sustained 24fps performance, native installed
application playback and audio-device timing remain OPEN. The current
backend launches three supervised native codec processes for every
frame, which is not a demonstrated efficient feature-film decoder.

**Native decoder release gate OPEN:** the ordinary NVP installer has
not packaged a build-time SHA-pinned and legally noticed OpenJPEG/
CineCert viewer bundle, so the finished-DCP play button remains disabled
by default. Explicit host-side developer binary+digest config can run
the native player; JavaScript cannot approve or supply binaries.
Do not mark WO5/WO4, creator viewing, SMPTE DCP Bv2.1, 60-90min feature
or >=3h epic accepted on the basis of this short real 6-frame test.
See NVP_WO5_DESKTOP_DIRECTOR_WORKFLOW.md for exact code and open gates.

### WO5 final DCP bounded-batch decoder acceptance — 2026-11-07

**PROVEN: 7/7 [native final-film CI run 42409121482](https://github.com/vjmichael/nvp_offline_film/actions/runs/42409121482).**
Windows/Linux Python 3.11+3.13 real XYZ12-to-preview and PCM24
sample/channel tests; Windows/Linux React WebAudio time/denied grant/
reel-continuity/late-sound and skipped-picture tests; one real
Linux native OpenJPEG/CineCert two-reel SMPTE DCP master/unwrap/decode
test all PASSED. The native test reopened actual published picture
and actual mastered sound MXF at global frame 2 -> 3, then also
decoded bounded 1/2-frame windows clipped at the same reel boundary.
New native window API unwraps at most 4 final pictures and paired
sound together in two native unwrap calls + per-picture pinned
OpenJPEG decode, reducing native process launches compared with
one frame at a time. All revisions remain derived/read-only.

**Technical decoder and UI integration code gate COMPLETE.** The
*film reviewing production acceptance gate is NOT complete*: no
verified 30-minute real authored movie, no uninterrupted benchmarked
24fps actual device playback, no fully legally bundled installed
decoder, no real creator judgment of final story sound/motion, no
60–90-minute original feature, no 3h+ original epic, no independent
SMPTE DCP Bv2.1/theater validation. These are outstanding, not
synthetic test substitutes.

## WO5-05 — installed native finished-film playback and original thirty-minute source pilot (2026-11-07)

**Engineering implementation in draft PR #92, stacked on #91. Both acceptance gates OPEN pending exact-head native results.**

### Actual installed Windows application / sustained playback

- Trusted Windows GitHub Actions builds **source-pinned OpenJPEG 2.5.4** from commit
  `6c4a29b00211eb0430fa0e5e890f1ce5c80f409f` and **CineCert asdcplib**
  from commit `905d6047f67c8211c2d22f29fb0e2e44c142b59b` as genuine native
  binaries. A fresh release staging manifest records exact installed
  executable SHA-256 and the full upstream BSD license-notice SHA-256 for
  all five codec tools, with the manifest SHA compiled into the frozen NVP
  executable at build time. Browser/AI/runtime project bytes cannot choose
  codec executables, re-pin their own manifests or bypass notices.
- A native PyInstaller WebView2 bundle includes the reviewed codec payload.
  The Windows NSIS installer must actually install this bundle, prove
  installed NVP.exe SHA identity, decode genuine published **two-reel
  SMPTE DCP picture JPEG2000 + mastered PCM24** and record 24fps
  throughput from the installed executable, then open the visible
  WebView2 and call its native decoder capability method before uninstall.
  Source codec fixture uses six distinct authored 2K patterns and
  genuine native wrapping; its playback speed is a codec load test,
  **NOT an original movie**. No source DCP assets ship with installer.
- The installed native smoke emits a structured timing+memory report and
  **fails the release performance gate** if native processing is below
  24 picture fps. A separate real WebView2/device clock full-film
  presentation gate remains open even if codec throughput passes:
  codec decoding alone does not prove uninterrupted audio-device playback,
  accurate physical picture/sound sync or user-viewed film.
- The earlier finished-film decoder passed seven native/React CI jobs in
  GitHub run 42409121482; those did NOT test a standalone NSIS install,
  licenses or sustained real-time output. Do not transplant that result
  into the new installed gate.

### Original 30-minute pilot, not a pretend completed film

The original demonstration **Last Light at Relay Nine** is a six-act
data-first native OpenUSD scenario, not someone else's video or a three-
frame JPEG2000 loop. Real source authoring creates one 1,800-second
immutable Digital Take linked to a native 3D relay/crew scene, actual USD
motion curves, a 60-cut exact Film Time camera timeline, a combined
authoritative action/sound event ledger, six freshly authored recorded
48kHz mono PCM source motifs, genuine SQLite/FilmIndex dependency
records, and a six-by-5-minute reel production plan. Every act also
attempts a real **source-derived OpenUSD scene-linear review frame**
at its authored film time; this is a 640x360 uncalibrated *source*
preview, deliberately NOT a 2K cinema master. A new edited scene
revision and distinct new frozen Take must be proven possible while
the earlier scene/Take SHA remain unchanged.

The 30m *source/shot/sound workspace* is distinct from a
production-ready 30m *finished film*. A real movie requires all
43,200 distinct authored-time picture frame derivations at 24fps
using an authentic full-resolution 2K/4K scene renderer, approved
graded XYZ12 output, actual 30m mastered PCM24 and multi-reel DCP,
continuous end-to-end replay of the published essence in the
installed NVP application, and a human filmmaker's evaluation
of performance, camera decisions, grading, cut timing and soundtrack.
The current NVP 640x360 uncalibrated native raster cannot be silently
upscaled and presented as calibrated DCI. Those gates **remain OPEN**.

### Return from theatrical package to original scene / new Take

A DCP is **flattened** picture/sound delivery, not a reversible USD
archive. FilmIndex's original feature presentation record stores the
ordered native source reel job IDs and approved assembly SHA;
`FeatureJournal` binds each reel to the approved source Take and
mastering decision SHA. The Take manifest binds exact scene,
animation and temporal revisions and their original SHA-checked
blobs. Thus an NVP project with its original source data still present
may follow **DCP presentation → feature/assembly receipt → reel
mastering decision → frozen Take → original USD scene + temporal data**.
The director authors a **new scene revision and new Digital Take ID**;
the old Take and published DCP remain immutable. Standalone DCP
picture/sound data without FilmIndex and scene blobs CANNOT recreate
editable 3D actors, cameras or performances. Avoid embedding
project-secret source data into a cinema DCP; preserve an accompanying
native production archive instead.

**Bigger original deliverables:** 60–90-minute feature and >=3-hour epic
remain deferred major acceptance targets, never satisfied by synthetic
throughput results. Open WO4 and WO5 production/DCI gates remain OPEN.


## WO5 native installed-film repair round — 2026-11-07

**Observed previous native run**: The earlier Windows NSIS installed acceptance
experienced a 180-second real MXF/OpenJPEG throughput timeout, a 600-second
visible WebView2 30s picture/PCM24 final presentation timeout, and a
180-second multi-stage installed source review timeout. The DATA-AV suite
also had a real failure in `test_nvp_wo2_presentation_look.py`, where
a literal escaped-NUL model rationale was not rejected. These are release
blockers, **not passed acceptance**.

**Code repairs submitted to PR #92**:

- Fixed assistant rationale validation to reject actual control characters
  plus escaped NUL/control instructions; no AI approval or arbitrary native
  shader/command execution is introduced. Existing legitimate newline/tab
  text remains permitted.
- Changed the installed visible test-only actual final SMPTE DCP predecode
  to 24-frames-at-a-time native MXF sound/picture unwrap instead of launching
  two subprocesses per four original frames. It still independently checks
  every original published JPEG2000 frame, real PCM24 exact-sample window,
  published SHA and real reel boundary. The test fixture cannot substitute
  its cache for production real-time native decode throughput.
- The *independent throughput gate* now overlaps four separate native
  OpenJPEG decodes of four distinct genuinely unwrapped J2K frames using
  the existing SHA-pinned OS-contained codec worker. No cached picture,
  synthetic frame count, DCP change, FFmpeg or shortened film gets
  counted as genuine measured 24fps.
- Added an inner 60–120s bounded probe time budget, per-codec limits,
  honest incomplete/under-target vs passed reports, and fsynced stage
  checkpoints naming the native MXF reel/window, OpenUSD installed source
  stage and WebView2/Canvas/audio receipt stage. The runner always prints
  the collected diagnostic tail and uploads surviving reports even when
  a step times out. Source-window budget now covers the actual multi-panel
  OpenUSD, GPU, PCM, film catalog and camera work; a higher timeout is not
  itself acceptance.
- **All underlying cinematic release gates remain strict**: actual
  `NVP.exe` installation, measured picture 24fps, full 720 actual
  published DCP picture/PCM blocks drawn/queued by real visible
  WebView2/WebAudio, real audio clock continuity, no skipped footage,
  meaningful performance audit, and no substituted pixels or sounds.

**Current exact-head acceptance status:** Windows installed CI has been
submitted and is queued; no newer green or measured throughput result is
available. Real creative production of 43,200 distinct 2K/4K mastered
frames and original 30m sound is still open, as are human director
screening, 60–90min feature, >=3h epic and independent theater Bv2.1
qualification. These performance fixes cannot be conflated with film
delivery or calibrated speaker/display proof.


### Native PCM24 reel-window optimization (additional WO5 performance repair)

The 30s published-MXF visible acceptance now reopens the ORIGINAL signed
SMPTE sound MXF once per reel with the SHA-pinned native CineCert decoder,
verifies the real complete 48 kHz stereo 24-bit sample count for that reel,
and reads each exact 2,000-sample-per-film-frame window from the real
unwrapped temporary PCM file. The picture path still independently
unpacks all original J2K MXF frames in bounded 24-picture chunks and checks
real J2K SHAs; the six repeated test patterns are transparently identified
and their predecode cache is **not** counted as real-time codec throughput.
This avoids about 58 redundant native sound-unwrapping subprocesses in a
two-reel, 720-frame test without dropping/muting/replacing any PCM samples.
The genuine separate 24fps decoder-speed and real visible WebAudio/Canvas
release gates remain required and OPEN pending exact-head installed runs.

### WO5 production playback follow-up — one verified PCM second (2026-11-07)

The **actual product** `FinishedFilmPlayer` (not just the installed test
fixture) now retains at most 24 frames of decoded **original published-MXF**
PCM24 per active reel/segment and session. Consecutive four-frame
presentation windows reuse the exact 2,000-sample-per-frame slices instead
of repeatedly launching CineCert sound unwrap. Changing reel/segment
evicts the cached sample block; stop, close and new session clear it.
Each delivered JPEG2000 frame still undergoes its own source-hash check
and original OpenJPEG decode; no picture skip, fabricated throughput
or new audio master was introduced.

`tests/test_nvp_wo5_finished_playback.py` now checks the real
native-wrapper invocation count, PCM reuse across neighboring windows,
original per-picture decoding, reel transition and cache disposal.
`tools/nvp_wo5_installed_sustain.py` now emits newline-delimited,
fsynced stage records, making a stuck installed codec easier to locate.

These are **submitted changes, not accepted native results**.
WO5 PR #92 updated from its earlier `e89ec7b5` head; all installed
24fps, genuine visible synchronized WebView2 picture/audio, 30-minute
original and theatrical certification gates remain OPEN pending real
exact-head GitHub Actions/physical acceptance.
