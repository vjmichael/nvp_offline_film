# WO5 — Real Production Acceptance and Original Up-to-30-Minute Film Proof

Status: **STARTED / implementation in progress / production acceptance OPEN** (2026-11-07).
Branch: `nvp/wo5-production-proof-20261107`, stacked on WO4 draft PR #90.
WO4 is **deferred, not closed**. The creator explicitly distinguishes passing a
synthetic pipeline benchmark from proving that NVP creates a film as intended.

## Creator correction — original means up to 30 MINUTES, not 30 seconds

**Creator corrected the initial proof to a genuine NVP-produced original
film of no more than 30 MINUTES** (43,200 presentation frame slots at 24fps),
including varied original shot content, performance, camera, audio and
editing. The previous thirty-second threshold was a misunderstanding and is
superseded. The original 60-second throughput benchmark is not the creative
proof. Full separate two/three-hour diverse-feature and calibrated theatrical
evidence remain later gates. WO5 cannot close WO4 solely from synthetic
OpenJPEG/CineCert MXF/DCP CI.

**Implementation mismatch, explicitly OPEN:** WO5-01's current
`backend/nvp_wo5_original_short.py` hard-stops at 720 frames/30 seconds and
only verifies one indexed reel. This is an *existing narrow engineering sample
gate*, not the requested 30-minute production proof. Extending the host
validation to an authentic multi-reel FilmIndex assembly with streaming
verification is required before attempting or accepting the new full proof.
The correction is a documentation decision; no code changes were made here.

## Work packages and truthful status

| ID | Work | Status |
| --- | --- | --- |
| WO5-01 | Define an original-film evidence boundary: exact FilmIndex source Take, mastering decision, source XYZ12/J2K frame custody, PCM24/MXF, FilmIndex-indexed DCP. 30-minute multi-reel source-bound sequence (existing 1–30-second implementation is insufficient), reject three-frame repeated synthetic stand-ins, never elevate SHA uniqueness to artwork validation | **Existing read-only 30-second sample gate only; real 30-minute multi-reel audit OPEN**; four-platform sample tests do not prove the corrected target |
| WO5-02 | Define director's intent and human comparison receipt: approved script/shot intention, performed action/actor blocking, camera motion, scene continuity, audible dialogue/environment, final cut timing, explicit mismatch and correction notes; no independent SHA-based creative assertions | **Acceptance protocol documented; real NVP UI and authored film pending** |
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
