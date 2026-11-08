# WO6-07D — AI-reviewed original PCM sound and digital-slate editorial operations

**Date:** 2026-11-07. **Branch:** `nvp/wo6-reviewed-ai-sound-editorial-20261107`.
**Stack:** WO6-07C native shot PR #101.
**Acceptance:** source implementation submitted; exact-head Windows/Linux and React CI **OPEN**.
No previous CI, original 30-minute film, or physical installed-Windows gate is implicitly closed.

## First-party architecture

This extends NVP's **existing** WO6 native decision host and data-worker
entrypoint; it does not introduce a second dispatcher, tool authorization
channel, model-driven executor, job store, database, FFmpeg path, shell or
MCP requirement. The two added typed decision kinds are:

### Sound cue: `sound_cue`

- The director chooses an immutable original frozen Take, a newly created
  timeline identity, a new sound event ID, exact source subject, original
  PCM source ID/revision/SHA, source sample offset, authoritative Film Time
  start/end and a finite 0–2 gain.
- Reopens the Take's exact original temporal timeline and requires its
  current head. Reopens `RecordedSoundSources` native 48 kHz mono PCM16LE
  source and verifies original indexed SHA and that chosen sample span is
  available. Film Time cue length must equal an exact whole number of
  48 kHz samples.
- Reopens **ALL** original temporal source events, with a bounded maximum
  of 128. If source exceeds this cap, fails closed rather than producing
  a silently incomplete re-edited timeline. Original actions, camera,
  dialogue and sound source events are copied as source references, with
  one extra new sound cue. Never overwrites the original timeline/recording
  or changes waveform PCM bytes.
- Trusted `TemporalLedger.publish` creates a **new immutable event
  timeline**, not a mixed stereo/multichannel master or rendered soundtrack.
  The native host reopens and independently compares all inherited and new
  event fields, sample count, original source SHA and no-render flags.

### Editorial: `editorial_cut`

- The director chooses an existing true DigitalSlateBranches graph,
  a new immutable edit ID, and one to 64 manually ordered source segments,
  each with original branch identity and exact source in/out Film Time ticks.
  The source graph must reference the AI-reviewed original Take if model
  advice is linked; the creator may also author an independent cut.
- Reuses **`SlateSequenceAssembly.preview`** to check every actual
  original Take/shot reference, trim limits, source dependency and duration.
  A read-only preview describes the exact segment count, order, source
  graph SHA and duration, not an active edit or cinematic render.
- The original contained WO6 data worker invokes
  **`SlateSequenceAssembly.commit`** with an explicit first-party
  sealed editor-event proof; a model is never this callback. A new
  FilmIndex `edit` revision is committed and reopened against its
  normalized clip digest. Original source performances remain intact;
  neither a picture frame nor finished audio is generated.

## Native UI and approval lifecycle

The original installed WebView2/React creator panel exposes native recorded
PCM sources and actual digital-slate graphs from bounded project FilmIndex
catalog reads. An AI proposal remains untrusted text. The human may select
`sound_cue` or `editorial_cut` as a separate reviewed consultation, but
the model does not populate any audio sample offset, gain, clip, source ID,
edit order, new output ID or editorial reason.

For either operation, the creator types **all** parameters and their own
creative reason (12–512 characters), views an explicit **read-only typed
decision preview** with a SHA over the exact original source ID/revision,
new decision ID, payload, duration and human reason, and then obtains a
separate **source impact preview** identifying downstream sound, mixing,
edit, picture, master and DCP dependencies.

Only after the director requests the operation do TWO existing host-owned
OS dialogs authorize (1) the exact creator decision and human reason,
and (2) the contained first-party worker binary+sealed spec. No authorizer
is supplied by a model, browser JSON or generic shell. The original WO6
TaskLedger admits the **exact** notified task under SQLite resource limits,
the existing OS containment guards the child process, and durable cancellation
and no-auto-replay apply normally.

When AI advice was reviewed, the original actor/project-owned in-memory
proposal must be complete and its SHA current. The original frozen Take,
scene and temporal heads are independently reopened. A sound edit must use
the Take's original timeline; a slate cut must include the exact Take as a
source branch. Only the reviewed proposal ID, model text SHA, context SHA,
Take SHA, Film Time and the human-selected operation are sealed in the
creative dialog, original native task and child-worker receipt. Model text
is never an executable argument, and an accepted review cannot submit
twice. Stale/source mismatches or a refused native dialog fail closed.

## Durable restart and receipts

The worker writes `receipt.json` with the exact immutable output ID/SHA,
original source impact SHA, reviewed AI provenance (if any),
`model_instruction_executed:false`, `model_approval_accepted:false`,
`film_delivered:false`, `rendered_frames:false`. The parent verifies
the receipt against the independently reopened source and sealed task before
ever marking it SUCCEEDED.

The existing `WO6DurableRecovery` recognizes these as original WO6 data
worker tasks: queued/active cancellations remain durable, crash-after-commit
does not become an automatic retry, and an authenticated status read exposes
the SHA-only consultation proof without replaying approvals after restart.
An interrupted source publication may require explicit reconciliation;
never infer an undo of an immutable FilmIndex commit.

## Dedicated native evidence and limitations

Workflow: `.github/workflows/nvp-wo6-07d-native-sound-editorial.yml`.
The matrix executes Windows 2025 and Ubuntu 24.04, Python3.11 and 3.13,
real OpenUSD 26.11, real recorded PCM original bytes, actual first-party
contained sound/editorial worker subprocesses, exact source SHA and receipts,
negative typed-preview/model-authority/source-mismatch tests, prior WO6
data/shot/recovery regressions, and a separate real React build/Vitest run.

The AI consultation in native permission regressions is intentionally a
**fake model response** to isolate approval correctness. Genuine GGUF/visible
installed WebView2 acceptance belongs to WO6-07B PR #100. CI test OS
callbacks simulate a human pressing approval solely for testing; the
real installed creator must still independently approve in a visible
Windows app. These tests are **not** final mastered soundtrack playback,
codec/ADM/BWF mix compliance, frame-rendered edit quality, original
30-minute screening, physical calibrated GPU/display, second-renderer
color accuracy, SMPTE Bv2.1 or independent theatrical projection.

**Current status:** implementation and negative regressions committed; no
native CI outcomes or install-run artifacts have been inspected for this
final head. All installed and theatrical gates remain OPEN. Unrelated next
development should continue rather than wait on GitHub verification.
