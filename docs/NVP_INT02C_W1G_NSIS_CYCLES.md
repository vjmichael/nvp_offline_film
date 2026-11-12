# INT-02C / W1-G — Native Cycles, shot composition, protected workers, NSIS upgrades

Implementation branch: nvp/int02-w1g-native-film-package-20261112
Date: 2026-11-12. Source-only checkpoint; NOT release acceptance.

## INT-02C — production picture path (SOURCE INTEGRATED, OPEN)

- The committed native SlateSequenceAssembly edit is still authoritative.
  Per-segment approved SHOT-01 USD layers are now validated by exact
  original Take SHA, director-shot SHA, revision and source-time window.
- An ephemeral composed stage at exact original Film Time applies approved
  transforms, visibility, camera optics and native lighting. Unsupported
  eyeline intention, acoustic listener/emitter movement and uncomposed
  director actions refuse delivery rather than change source silently.
- First-party Cycles worker reads a flattened static OpenUSD scene, not a
  browser file or FFmpeg frame. The trusted host SHA-pins its worker script,
  plan and scene. Existing NVP BlenderWorkerSupervisor provides native
  process containment, memory admission, bounded jobs and output auditing;
  Windows uses the suspended-process Job Object path and Linux requests
  strict delegated cgroup-v2 tree custody.
- Each frame is requested at the committed edit's actual source tick,
  through approved camera context. The worker imports USD natively into
  Blender and renders 1920x1080/96-sample Cycles PNG. It refuses missing
  imported camera, source actor geometry/rig, authored scene lights, native
  USD importer, and incomplete picture evidence. There is no automatic
  fallback to the simplistic 640x360 CPU rasterizer.
- The existing 720-picture/1,440,000-sample-PCM edited derivative path
  verifies every original-time source/camera/picture SHA and exact PCM
  windows independently on reopening. Source FilmIndex Takes stay frozen.
- The installed WebView2 handoff requests a separate native approval
  before staging plaintext USD for Blender, explaining temporary source
  exposure. Existing encrypted-film/project key-custody requirements
  are not considered satisfied by this consent.
- A source-only native test covers real shot visibility composition and
  refusal of unimplemented director intent and acoustic source movements.

**Still open:** actual Blender Cycles USD import/render acceptance of real
meshes, rigged actors, performance, materials, light shadow/occlusion,
correctly preserved original audio and shot edits; composited acoustic
listener movement; HDR/ACES/MaterialX/Hydra fidelity and calibrated color;
stronger encrypted-film staging protection; sustained 30-second real run,
film playback/delivery master without FFmpeg, long-form performance.
A worker script and CI fixtures do not prove production-quality output.

## W1-G — protected execution and Windows NSIS upgrades (SOURCE INTEGRATED, OPEN)

- A first-party protected executable host reads the reviewed W1-G worker
  roster from an installed NVP bundle. It pins roles, binary SHA, typed
  project plan, job ID and finite memory/deadline budget. Its only
  subprocess path is NVP's existing OS-contained launcher, with Linux
  cgroup-v2 required. One-use trusted human approval is mandatory.
- Result success requires the original plan and binary hashes, an exact
  native worker receipt, independent domain verification, and a separately
  provided kernel-backed process-tree custody receipt. Child exit/PID,
  journal state or handle close ALONE is never acceptance evidence.
  Uncertain restart or cancellation cannot auto-relaunch a worker.
- NSIS now stages a complete candidate under a dedicated sibling program
  directory, refuses unknown preexisting program directories, parks the
  previous version before promotion and preserves it for reconciliation.
  A failed second rename attempts restoration and preserves interrupted
  evidence rather than overwriting the active executable in place.
- An explicit creator-approved NSIS rollback/recovery utility verifies PE64
  marker, old/new content hash, original-film hashes and repeated
  independent OS-stop checks before restoring the previous program. The
  failed candidate remains available for investigation.
- The native Windows packaging workflow explicitly includes the pinned
  first-party Cycles worker script and static payload audit requires it.
  The native Linux deb candidate guard also refuses bundles lacking it.
  Full-source W1-G regression contracts cover protected-worker false
  successes, native shot refusal and original-film preservation.

**Still open:** real reviewed wheelhouse and signed/approved native worker
binaries, dependency redistribution review, installed NSIS upgrades with
power-cut and locked-executable tests, actual Blender GUI/render and
negative process containment under Windows Job Objects and Linux cgroup-v2.
The NSIS batch still requires live compile/installation acceptance; source
does not establish that the rollback instructions run successfully.
Protected original-film staging and key custody must also be independently
accepted. The previous-version directory is NOT auto-deleted.

## Development/acceptance separation

These code changes are on the separate INT-02/W1-G branch and do not merge
the active DATA-AV PR #74 or restart old FFmpeg workflows. No FFmpeg code,
proxy fallback or legacy B11-B14 frame-authority path is introduced.

No workflow was launched in this source checkpoint. Tests were authored,
but the Windows/Linux native/installed matrix and owner-operated Windows
physical film still require genuine execution and independent results.

Status: INT-02C PARTIAL/OPEN; W1-G PARTIAL/OPEN. W1-F physical/sustained
acceptance and original DA-03 filming/custody gates remain outstanding.

## Follow-on safety corrections (same development branch, SOURCE ONLY)

- INT-02 now independently reopens all staged picture and original PCM
  samples BEFORE any target-directory publication, then reopens the final
  published derivative again. Failed stage verification leaves no final film.
- SHOT-01 composition refuses source emitter/non-camera translation until
  the original PCM acoustic observer is composited. The Cycles worker uses
  explicit valid Blender USD importer controls and rejects remaining
  animated time samples after exact-tick static USD baking. Blender API
  compatibility was checked against published docs; real native execution
  remains unverified.
- NSIS requires marker CONTENT verification (not merely presence), a
  newer declared X.Y.Z release rather than a same-version rewrite/downgrade,
  and staged program tree promotion. Recovery includes a stranded
  pre-promotion previous program and a separate human/OS-approved historical
  archive or quarantine of failed program-only artifacts. No film files are
  recursively removed.
- The release helper allows a version specified by NVP_RELEASE_VERSION and
  rejects malformed values. The prior installed release is not discarded
  until independently accepted by a real installed launch/restart witness.
- New test cases are SOURCE ONLY: staged-film denial, stranded NSIS
  restoration, refusal of unaccepted previous-version closeout, and
  quarantine preserving original film bytes. No real NSIS or OS kernel
  tests were executed by these edits.


- A Cycles restart that finds prior interrupted Blender jobs now REFUSES
  to admit more render work until original OS custody is independently
  reconciled. No journal-only or PID-only clearance is assumed.
- The NSIS installer additionally offers interactive, owner-confirmed
  recovery of a stranded previous program at startup. Silent mode refuses
  uncertain recovery. These transitions still require a genuine compiler
  and OS installation run before acceptance.
