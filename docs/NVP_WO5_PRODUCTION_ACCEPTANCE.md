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
| WO5-02 | Define director's intent and human comparison receipt: approved script/shot intention, performed action/actor blocking, camera motion, scene continuity, audible dialogue/environment, final cut timing, explicit mismatch and correction notes; no independent SHA-based creative assertions | **Immutable FilmIndex director-intent/observation code IMPLEMENTED** (`nvp_wo5_director_review.py`) with host-confirmed scope and new native tests; real creator UI and creative review of original film OPEN; new CI pending |
| WO5-03 | Author, film, edit, render and inspect one genuine <=30-minute original using near-production scene+rigged actor+camera+native spatial audio, immutable Digital Takes and source-bound editing; compare full video/audio playback to director's intended outcome | **DEFERRED until NVP is near-production ready** |
| WO5-04 | Native installed Windows and Linux tests: trusted editor/project grant to independent supervisor, manual NVP lock, close/reopen, cancellation and crash recovery, actual 30-minute output, controlled disk/RAM/CPU/GPU/power evidence | **DEFERRED physical installed acceptance** |
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
