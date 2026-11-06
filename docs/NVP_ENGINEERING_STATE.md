# NVP — Engineering state and resumption ledger

## Latest checkpoint — INDEX-TIME-10 progressive playback, November 6

- **Stacked development branch:** `nvp/index-time10-progressive-longform-20261106`,
  based on the exact INDEX-TIME-09 PR #72 head
  `974f2413b384e5970462fa6398924ada39c532d6`.
- Added native trusted progressive session begin/prepare-next/advance/stop,
  one explicit creator consent scoped to a specific frozen FilmIndex edit
  and no more than four hours of reviewed playback; at most two verified
  disposable A/V proxy tickets, one contained encoder worker, max 160 MiB
  disk derivative per section and bounded same-origin 206 media delivery.
- Next start derives only from the preceding sealed native plan; stale,
  altered or foreign session requests are refused. Old ticket is revoked
  after approved handoff, not while the next child worker is unverified.
  A late next section pauses both video and sound at its boundary.
- React indexed-footage editor has `Start progressive long-form review`
  and may pre-prepare the next disk-backed proxy, check its distinct
  stream receipt and transition on the media `ended` event. Section
  switches are **not yet certified gapless**; codec/audio timing and
  WebView2 RAM must be measured independently.
- Restart policy revokes previous session grants, cancels queued old
  tasks and retains unresolved ACTIVE worker reservations pending actual
  independent process-tree cleanup. Existing source recordings are never
  rewritten. Added native coordination/unit tests, frontend transition
  tests and separate Windows/Linux + React GitHub workflow.
- **Acceptance remains open** until the exact PR head's native CI,
  real 20+ minute multi-section playback, physical Windows installation,
  Linux app acceptance and hostile host-crash recovery are observed.
  Guide: `docs/NVP_INDEX_TIME10_PROGRESSIVE_LONGFORM.md`.

## Current continuation checkpoint — November 6, 2026

This section supersedes older November 5 navigation priorities **for the
imported-footage editor workstream only**. Do not infer that the entire native
film system, Windows installed release, or original 30–60 second AI film is
accepted. The creator continues to require immutable captured picture/audio,
non-destructive versioned Film Time assemblies and a straightforward GUI.

- **Active draft:** [INDEX-TIME-09 PR #72](https://github.com/vjmichael/nvp_offline_film/pull/72),
  branch `nvp/index-time09-continuous-av-proxy-20261106`, stacked on
  INDEX-TIME-08 PR #71. This is the latest authored work in the
  original-footage editor. The earlier PR #45 is a separate DCP/picture
  conform stack, not the head of this editor workstream.
- **Implementation in PR #72:** bounded up-to-20-minute, 24fps review-only,
  H.264/AAC 48kHz stereo, film-edit-and-source-SHA-grounded temporary A/V
  preview with black/silent editorial gaps, native OS approval, contained
  FFmpeg worker, independent FFprobe/SHA receipt and <=1MiB HTTP 206 private
  disk ranges. Sources stay original and are never rewritten. Native
  cache/run-window memory caps remain *design goals*, not hard measured
  Windows memory acceptance.
- **SYSTEM-READY-01:** installed app's System readiness screen performs
  read-only library/codec/runtime/disk checks; optional missing components
  use exact allowlisted OS-package repairs with native consent plus OS
  privilege approval. The November 6 follow-up closes gaps around
  ready-component refusal, post-consent recheck and genuine Debian/Ubuntu
  identification. This does **not** authorize blanket package downloads.
- **November 6 repair:** frontend native READY-receipt digit-validation bug
  corrected; small seek/scrub/cut movements within a verified A/V section
  reuse the native media clock and current ticket, whereas crossing a section
  boundary stops/revokes the old one. React/native tests added.
- **Verification reality:** earlier independent native FFmpeg *filtergraph*
  fixture passed, but that is not a full installed-app test. The current
  exact-head Windows/Linux/React GitHub jobs had been queued at last
  inspection; no pass, installation, human audio perception, crash-kill
  reconciliation, multi-section seamless playback, or 256MiB RAM compliance
  may be inferred from implementation alone.
- **Next:** repair actual updated exact-head CI failures first; run the
  existing `tools/nvp_index_time09_independent_acceptance.py` on real
  Linux and already-installed physical Windows (without building NSIS on
  the creator's machine); validate hostile worker cancellation/host crash;
  then work on progressive overlap/prebuffering beyond 20 minutes and
  dialogue/music mixing while keeping every capture frozen. Full public
  packaging remains a separate creator-controlled release gate.

**Purpose:** One concise, machine-readable-by-convention entrypoint for a newly started AI development conversation.

**LATEST CREATOR PRIORITY (2026-11-05): WINDOWS NSIS INSTALLER WORK IS PAUSED.** Do not attempt setup scripts, packaging or on-PC dependencies unless the creator explicitly resumes that task. Active objective: a real continuous 30–60-second NVP-produced short film, with AI-generation and production continuity verified; technical reel assembly is a stepping stone. Git commits, exact build/test logs, creator approvals and artifact hashes remain the sources of truth. This document is a **navigation index**, not proof that an effect ran.

**Status:** Initial ledger, manually reconciled 2026-11-05. A future automation/CI gate must populate SHA, test and artifact evidence reliably; do not treat this file as self-updating.

## Source identity (recheck before working)

- Repository: vjmichael/nvp_offline_film
- Active development: PR #45 (draft), branch nvp/stack02c3b14-picture-conform-20261104
- Last inspected substantive source commit: 393c068988217319b978e9815b7d3753da73b95b (NVP-AI-01 tests). **The actual HEAD will change after this documentation commit; re-read it from GitHub each time.**
- Main architectural authority: docs/NVP_MASTER_DESIGN.md.
- AI-readiness review: docs/NVP_AI_ACCESSIBLE_ARCHITECTURE_REVIEW_20261105.md.
- Lu integration: deferred until Lu v1.0 host/DLC contracts are accepted. Standalone Windows desktop alpha is a separate active milestone.

## Current workstreams / what is proven

| Workstream | State at this entry | Evidence / required next gate |
| --- | --- | --- |
| FilmIndex and provenance | Implemented source/index foundation; not complete whole-film acceptance | backend/nvp_film_index.py; tests/test_film_index.py; confirm exact-head cross-platform tests |
| Screenplay editing | Editable 1-based gutter, AI excerpt numbering and line navigation are committed | frontend/src/LineNumberedTextarea.jsx; backend/nvp_story_context.py; source line tests. Native Windows WebView interaction still needs physical acceptance |
| AI-01 read-only source resolver | Initial implementation committed | backend/nvp_ai_refs.py; tests/test_nvp_ai_refs.py. Read-only Python service only, **not an authorized model tool or exposed API**. Requires host integration, more cross-revision tests |
| MASTER-01C host-owned unapproved film publication | **Implemented and locally verified; actual film/Windows remains open** | Opt-in native host-staged worker, SHA-bound real ProRes/PCM24 30s/60s, hard-exit before/after host FilmIndex commit, no replay, staging tamper refusal, cancellation before publication; 57 targeted tests across 5 groups; see docs/NVP_MASTER01C_HOST_PUBLICATION.md |
| MASTER-01B contained AV review | **Implemented and locally verified; Windows/strict Linux acceptance open** | Native creator-scoped host, queue/admission, containment, controlled cancellation, genuine hard-exit/recovery, saved source hashes. 46 Linux tests across 3 groups; see docs/NVP_MASTER01B_NATIVE_SUPERVISED_REVIEW.md |
| MASTER-01A real 30–60s technical review | Native technical assembly implemented, not a finished AI film | backend/nvp_longform_review.py, tests/test_nvp_longform_review.py; real FFmpeg/FFprobe 36s and 60s checks; 30 related tests passed, CI/native Windows still pending |
| AI-02 through AI-07 | Proposed architecture, not implemented/accepted | AI review document; staged context, capability, inventory, impact and evidence acceptance gates |
| Worker/resources | Existing supervision/journal/admission mechanisms with partial native evidence | Follow existing STACK-02, audio, Blender and E2E tests; do not generalize one test to every worker or platform |
| Windows desktop installer (paused) | **NOT ACCEPTED; PAUSED per creator 2026-11-05** | An experimental signed-unknown online NSIS bootstrapper has failed on physical Windows due to Python package problems; v3 is an attempted repair without reported successful install. The desired verified self-contained Windows installer is still open |
| Audio/DCP/full-film | Numerous source modules, tests and native-fixture results; end-to-end commercial/installed acceptance remains separate | AUDIO-01K3, E2E-01D, E2E-01E and FILM-01 gates; do not equate local tests or queued CI with exact-head native acceptance |

## Local evidence, last verified

2026-11-05 targeted Debian tests in recovered source snapshot:
- Command: python -m unittest tests.test_nvp_ai_refs tests.test_film_index tests.test_crew_roles tests.test_story_context tests.test_lu_workspace tests.test_resource_scheduler -q
- Result: **57 tests passed** (6 new AI reference tests, 51 existing related tests). Does not certify Windows installed GUI or latest exact-head regression.
- Editor React/Vite and earlier NVP smoke tests were run in earlier task checkpoints. Their exact revisions/environments are in the corresponding logs/artifacts, not to be silently promoted here.
- All paths/resources from an earlier ephemeral container are **historical** until reverified in the current runtime.

## Mandatory new-turn discovery order

1. Read PR #45 and current GitHub exact HEAD SHA, its changed files and current acceptance results.
2. Read this ledger and the master design's most recent amendments; read a subsystem doc only when its task is relevant.
3. Determine whether the task is about Windows distribution, media workers, film-authoring UX, or AI-accessibility, and inspect the matching live source and durable previous outcome.
4. Verify existing accessible source tree, required binaries, caches, fixtures and model/runtime **before downloading or reconstructing** packages.
5. Execute/tests with authentic artifacts and record the exact environment, SHA, commands, pass/fail/skip and limits; keep unavailable evidence marked unavailable.
6. Update this ledger and affected design/acceptance docs on substantive changes. Do not make a stale previous success current merely by restating it.

## Next actionable engineering sequence

**Priority A (current): MASTER-01D** — adapt authentic frozen Digital Take/Pipeline/B14 and synchronized dialogue/audio outputs into exact indexed AV reels for the new two-phase host-owned native assembler. Build a 30–60-second coherent, creator-reviewed cinematic short, not procedural color/sine fixtures. Verify selective revision, persistent character/shot identity, sound sync and editable FilmIndex source lineage.

**Windows packaging: PAUSED by creator 2026-11-05.** Earlier v3 diagnostics remain historical but NSIS and installer follow-up are not active tasks. Resume only when explicitly requested.

**Priority B (AI-readability):** extend AI-01 to other film objects and add a small read-only AI-02 capability catalog and AI-03 context bundle, with exact-provenance and stale-ref tests. No generic write executor and no premature Lu socket.

**Priority C (film deliverable):** maintain native AUDIO-01K.3 and E2E-01D crash/verification gates and real approved 30–60 s film acceptance. Exact-head native workflow evidence is mandatory before merge or release acceptance.

## Change log (append-only entries)

- **2026-11-05 later:** MASTER-01C two-phase staging passed 57 Linux native/related tests across 5 bounded groups (6 new host tests, 5 new staged-media tests, 9 MASTER-01B, 7 MASTER-01A, 30 existing index/scheduler/worker tests). Genuine 30s/60s ProRes/PCM24 technical reels, host publication, real OS-process crash before and after index commit, cancellation before publication and tamper refusal. Native Windows/strict Linux whole-tree results remain pending. Next MASTER-01D authentic film source integration. No new installer work.

- **2026-11-05 later:** MASTER-01B native reviewer passed 46 Linux Python tests in three targeted groups (9 new, 7 MASTER-01A, 30 existing). Actual contained 30s AV output, creator scope, strict executable selection, controlled cancellation, post-worker-stop host hard exit and no-replay restart reconciliation verified. Windows and delegated Linux cgroup whole-tree acceptance still unverified; next MASTER-01C two-phase host-owned publication.

- **2026-11-05 later:** Creator paused NSIS work and prioritized real film output. Added MASTER-01A source-indexed multi-reel technical preview. Real 36s/60s ProRes/PCM24 stream-copy assembly tested with FFmpeg, exact SHA/revision/AV clock, packet-order and decoded-PCM equality, reopen and corruption refusal, 29 related tests passed on Debian. Windows CI requested, not confirmed; next MASTER-01B worker supervision and real production-reel integration. No claim of generated acting, native installed application or approved finished short.
- **2026-11-05:** Reviewed NVP AI usability against LU-AIW-01 and existing data-first master. Added proposed NVP-AI-01 architecture review to master design. Initial read-only revision-bound screenplay reference adapter and six tests committed. Created this ledger so subsequent AI work can resume from source state instead of context guesses. 57 related local Python tests passed; Windows installer acceptance still open.

## Required evidence for any future ledger update

Record: date; actor/source (human decision, tool observation, AI hypothesis); branch; source SHA; exact command and tested input; OS/runtime/tool versions; outcome + skips; artifact SHA/path if produced; relationship to prior accepted versions; outstanding blocker; next action. Never invent a successful install, benchmark, model inference or DCP screening. A remembered resource is not a verified current resource.


## 2026-11-06 — INDEX-TIME-05 source-index editor integration

- Return from SLATE feature development to preexisting indexing. Source truth remains original indexed footage PTS and immutable FilmIndex, not a rendered frame sequence or a replanned constant-fps approximation.
- Implemented: FilmTimeDesktopRead 64-bit exact source/time browser; bounded manifest-audited source pagination; project/revision/SHA-locked binary seeks and honest gaps; API GET-only routes; main NVP "Indexed footage" tab; React BigInt decimal ticks; real FFmpeg VFR tests and CI.
- Submitted on distinct indexing branch stacked on INDEX-TIME-04 PR #57; do not conflate with SLATE-08B PR #67 (still draft native acceptance).
- Open: native exact-head Windows/Linux/React CI, real Windows installed source browser acceptance, native creator-authorized media review UI, external media import picker, FFMS2 A/B, native installer video tool availability. No full-indexing completion claim or final movie approval.


## 2026-11-06 — INDEX-TIME-06 installed native footage picker and approved source still

- Continues INDEX-TIME-05 PR #68; SLATE-08B remains separate and verification pending. No arbitrary media-write HTTP endpoints, no new worker engine, no external multi-install requirement for the planned NSIS payload.
- Created `TrustedFootageDesktop` per installed WebView2 window. Native OS file dialog selects one MP4/MOV/MKV/WebM; separate human confirmation binds full-SHA original registration, normalized FFprobe, logical volume and immutable FilmIndex asset. Existing NVP SQLite frame index scans original PTS/keyframes, and one initial precise Film Time edit is published. Original source remains in place, untouched. Last original source frame remains indexed but intentionally unplaced under existing out-exclusive PTS invariant.
- Explicit source-frame preview binds exact edit/FilmIndex SHA/source ordinal/PTS/tick to a second physical OS consent; the existing `NativeFilmTimeWindowHost`, ApprovedTaskBindings, TaskLedger, contained FFmpeg child, PTS receipt and independently verified PNG are reused. React receives only bounded approved-to-view but **unapproved-to-master** image bytes on a native JS API ticket; no source paths or worker IDs. Queued cancellation and active stop use existing durable worker lifecycle, with fail-closed recovery.
- Fixed installed-only Python interpreter mismatch: `NVP.exe --trusted-film-time-worker` verifies the packaged raw source worker SHA and runs it inside the supervised child. NSIS pipeline packages actual x64 FFmpeg/FFprobe and worker file; payload audit rejects missing binary/shim. Real installed VFR original + PNG child smoke and native WebView2 Indexed footage tab smoke added.
- Actual Windows/Linux 3.11/3.13 native/React tests and E2E Windows installer CI submitted. **Not yet accepted** until exact-head green and independent installed interaction; FFmpeg redistribution/license obligations require legal audit before public release. Detailed design: `docs/NVP_INDEX_TIME06_TRUSTED_IMPORT_AND_PREVIEW.md`.


## 2026-11-06 — INDEX-TIME-07 non-destructive original-footage assembly

- Stacked directly on INDEX-TIME-06 PR #69, independent of SLATE expansion. Original indexed VFR media/FilmIndex remain the source of truth; the editorial assembly is a versioned, non-destructive map of original source references/PTS onto authored Film Time.
- Implemented typed native `IndexedFootageAssembler`: move, copy reference, remove placement, exact source-ordinal trim, gap, cross-edit insert and previous-revision restore. Every proposed plan verifies the full immutable source edit and measures every original frame-range duration from the existing NVPFrameIndex/FilmTimeEditorialPublisher, not from assumed CFR. Up to 256 placements per initial desktop editing operation.
- Main editor offers `Arrange source footage`: preview typed metadata change, see original IDs/frames, film-clock starts, duration and plan SHA, then click save to physically approve via exact-origin `TrustedFootageDesktop`. Native host rechecks plan SHA/head after consent, publishes new FilmIndex edit revision through CAS/one SQLite transaction; existing imported source, previous edit revisions, Slate and temporal events unchanged. Generic web HTTP remains read-only for imported-video editing.
- Dedicated real FFmpeg VFR/B-frame Windows/Linux Python 3.11/3.13 CI and React UI tests committed. Installed NVP NSIS `--smoke-source` now also requires an approved trim and old/new revision/source SHA survival after source PNG worker. **Exact-head CI and independent installed Windows human acceptance pending**; do not mark as a verified final movie/decoded assembly playback. See `docs/NVP_INDEX_TIME07_NONDESTRUCTIVE_ASSEMBLY.md`.


### INDEX-TIME-07 actual editor hardening continuation (2026-11-06)

- Closed implementation gaps: real source-frame split with adjacent original PTS intervals; full 256-clip revision-safe metadata pagination before edits (the prior 40-clip browser view was insufficient); horizontal source strip with explicit gaps and click selection; existing PTS playhead-based split; human HH:MM:SS.mmm gap editor with BigInt and preserved advanced exact ticks; stale form draft invalidation.
- Expanded Windows/Linux original VFR tests, >40-clip React pagination/forged page tests, source-strip/playhead split tests, exact human clock tests, and an installed real WebView2 project/assembly/split mount smoke. Still **DRAFT** until exact-head native jobs and Windows installed acceptance actually pass; original video bytes remain external and unchanged by all edit operations.


## 2026-11-06 — INDEX-TIME-08 safe original-footage assembly playback

- Stacked on INDEX-TIME-07 PR #70, not Slate. Added simple `Review your film assembly` transport: short, native-approved source playback with play/pause, previous/next original frame, film-clock scrub, ±5 seconds, jump to preceding/following cut, and seeking to an exact existing original source frame. A blank review gap never holds or fabricates a prior camera picture. One verified original PNG held by browser at a time.
- New native `NativeAssemblyReview` owns a window-local, SHA/revision-scoped review session (up to 96 real source PTS frames across max 12 x 12-frame chunks, not a full movie). One physical OS confirmation covers an explicit bounded original-PTS manifest; each chunk receives a one-use exact native approval, existing `NativeFilmTimeWindowHost`/TaskLedger/ApprovedTaskBindings admits and contains its FFmpeg process, and the host independently verifies decoded receipts and each requested PNG. Playback has its own owner/queue so it cannot claim an unrelated single-frame review. No arbitrary filesystem paths or native runner requests over HTTP.
- Actual original-VFR two-clip/gap tests with native contained workers, real PNGs and stale-edit/tampered picture/cancel refusal are committed alongside React transport tests. NSIS `--smoke-source` now checks real installed frozen multi-frame review after non-destructive edit publication; real `--smoke-window` requires the player to mount on the existing indexed original.
- **Draft, not yet accepted:** exact-head Windows/Linux native and React jobs, installed Windows NSIS verification, multi-minute streaming, full audio playback/conform and public FFmpeg licensing remain open. See `docs/NVP_INDEX_TIME08_SAFE_ASSEMBLY_PLAYBACK.md`.


### INDEX-TIME-08 playback lifecycle / human UX hardening (2026-11-06)

- The playback transport now tracks its actual selected original PTS frame on the visible Film Time scrubber. An intentional gap owns its own black-screen timer so moving into the gap cannot cancel the only resume timer; Play/Pause/step are distinguished from Stop (which revokes native decode work). Next-section action refers only to the terminal reviewed source frame.
- Scrubbing or jumping to another cut immediately drops old pictures and cancels the obsolete bounded native review. A late OS approval after the user has navigated away is explicitly cancelled rather than left decoding in the background.
- The native reviewer isolates its TaskLedger queue from single-frame approvals, rechecks saved FilmIndex head between decoding batches, and deletes only temporary review PNG derivatives on Stop/close/next session, leaving external originals, saved versions, index and durable worker evidence untouched.
- Expanded actual original-video tests cover reviewed gap/cross-cut PTS, cancellation, stale revision, tampered PNG, native window origin, bounded derivative disposal. React tests now cover playhead advance/black gap timer, scrub cancellation, exact 64-bit large scrub and late native approval revocation. **Not accepted until native CI and physical Windows installed smoke pass.**


## 2026-11-06 — INDEX-TIME-09 continuous picture-and-sound assembly review

- Continues INDEX-TIME-08 PR #71 in independent footage indexing stack. Slate stays metadata, original camera/video/audio is SHA-ingested and externally referenced, and the editorial assembly remains only reversible versioned references.
- Implemented source-bound **up to 20-minute synchronized H.264/AAC temporary review proxy** for a selected exact FilmIndex edit/revision/SHA and original Film Time. One physical desktop approval precedes a typed, sealed native task under ApprovedTaskBindings, durable TaskLedger and existing Windows Job Object/Linux worker containment. FFmpeg chooses original VFR PTS source cut points, 24fps review-only picture, 48kHz stereo AAC audio, and black/silent intentional gaps; audio track is the first embedded camera stream or silence (separate multistem sound integration still future). 48 source/gap pieces, 32 originals, 160 MiB compressed media cap.
- Added native verified A/V receipt: H.264+AAC actual streams, expected picture frame count, 48kHz stereo, stream duration drift ≤50ms, media SHA, source unchanged stamp checks, exact current FilmIndex head. Browser reads the derivative through one private pywebview ticket in ≤1 MiB SHA-checked chunks and verifies complete Blob SHA before HTML5 video playback; decoder's single media clock drives synchronized picture/audio. Original paths, worker IDs and generic media-write HTTP routes are never exposed.
- Frozen Windows `NVP.exe --trusted-av-proxy-worker` verifies packaged worker script SHA; NSIS bundles that worker and payload audit requires it. Installed `--smoke-source` now requires actual synchronized VFR/embedded camera sound H.264/AAC MP4 with measured ≤50ms drift and intact source SHA. Real WebView2 smoke requires the synchronized film review UI to mount.
- Real native Windows/Linux 3.11/3.13 CI and React tests authored. Separate independent **Linux FFmpeg media-layer experiment** succeeded with video/audio/gap H.264/AAC: 72 decoded video frames, ~3s soundtrack, 41.7ms difference in reported video/audio stream duration, audible 440Hz original-source signal. This was not full NVP or installed-app verification. **Exact-head native CI and independent physical Windows/Linux app acceptance remain open.** See `docs/NVP_INDEX_TIME09_SYNCHRONIZED_AV_REVIEW.md`.


### INDEX-TIME-09 off-GitHub acceptance evidence (2026-11-06)

- Added `tools/nvp_index_time09_independent_acceptance.py`: reproducible *outside-CI* actual-source Windows/Linux Python native worker test runner with JSON SHA/evidence output and optional already-installed Windows NVP.exe `--smoke-source` + real WebView2 `--smoke-window` path. This is a QA artifact, not the GUI workflow, and **was not executed on a physical Windows installed candidate in this conversation**. The independent Linux FFmpeg audio/video filtergraph test has passed; complete app/native CI and independent acceptance remain open.


### 2026-11-06 — INDEX-TIME-09 bounded RAM media and SYSTEM-READY-01 native package discovery

- Fixed the former **whole 160 MiB MP4 downloaded into JavaScript Blob memory** approach. INDEX-TIME-09 now preserves the independently SHA-audited H.264/AAC 20-minute review derivative on private disk and serves only **read-only HTTP 206 media ranges of at most 1 MiB per request** through an unpredictable, window-bound native review ticket. The FastAPI route is inactive outside the installed trusted window, rejects foreign origins, honors byte seek/suffix requests and rechecks edit revision, source stamps and private proxy file identity. The browser native video decoder owns the muxed picture/sound clock; film original clips and sound source bytes are never exposed or rewritten by HTTP. Tests cover media seek, bounded reads, cross-origin and ticket refusal. The old full-file Blob helpers are removed.
- Memory policy recommendation: nominal 3–5 seconds compressed lookahead, ~1–2 seconds decoded picture, ~1 second history and ~0.25–0.5 seconds audio, with a **256 MiB preview target / 512 MiB adaptive ceiling**, not yet enforced by a native budget monitor. The native HTMLMediaElement chooses actual decoded buffer residency; this wave enforces **1 MiB per range** and avoids entire 20-minute browser-RAM copies, not an independently proven 256 MiB hard limit.
- Introduced `backend/nvp_system_packages.py`: Windows runtime WebView2 detection via HKCU/HKLM native+WOW64 registry, bundled FFmpeg/FFprobe presence, Linux GTK/WebKit and FFmpeg availability, and private preview disk free-space. GUI accessible **System readiness & packages** before a film is opened; discovery never launches installers. Fixed allowlisted repairs use a separate native consent plus official OS package-manager authorization, currently Microsoft WebView2 via Windows winget and Debian/Ubuntu FFmpeg/GTK/WebKit via pkexec apt, never arbitrary shell/pip/packages. Unsupported environments fail closed.
- Windows NSIS single-click installer now checks for missing WebView2 and only when absent offers installation of an official **Microsoft Authenticode-signed Evergreen bootstrapper** embedded at Windows build time. NVP still bundles Python, native source workers and FFmpeg/FFprobe; no end-user Docker or command-line setup required. The CI build must fetch and verify the bootstrapper before embedding; missing or invalid signature blocks a release build. OS recheck blocks false installation success.
- Native/React package/HTTP Range regression tests, installed A/V disk range comparison, exact-head Windows/Linux CI and independent non-GitHub Python acceptance harness updated. **None of these CI acceptance results is assumed green until run-specific evidence is obtained.** Linux GUI packaging, signed offline-only WebView2 redistributable, full 256 MiB governor, seamless arbitrary-length progressive render and independent physical Windows/Linux installed testing remain open.
