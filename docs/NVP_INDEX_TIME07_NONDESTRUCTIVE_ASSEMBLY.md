# INDEX-TIME-07 — Non-destructive Original-Footage Assembly

**2026-11-06. Implemented as a draft stacked on INDEX-TIME-06; exact-head native/installed acceptance remains open.**

## What the user does

In the installed NVP editor, open **17 · Indexed footage**, select a real
FilmIndex imported-video edit and use **Arrange source footage**. The
editor works with existing original clip references and original indexed
presentation timestamps (PTS). No source movies are cut, copied, decoded,
overwritten, retimed, transcoded or deleted.

A creator can:

- Move a selected placement earlier/later.
- Duplicate a source reference (not a movie file).
- Remove a placement from this assembly (not its original source).
- Trim in/out at exact original source-frame ordinals. The out is exclusive;
  no artificial constant-FPS frame duration is inferred.
- Change the exact gap before a clip, which preserves intentional empty
  source-video ranges. Film Time remains 64-bit exact decimal ticks.
- Insert a referenced original clip from another project-local, SHA-bound
  imported-video edit, or from the current edit. This is versioned copy by
  reference, not an archive/copy operation.
- Restore any earlier immutable revision using a *new* revision. The
  initial UI offers the immediately previous revision.

The native controller calculates the proposed placements by asking the
**existing** `FilmTimeEditorialPublisher._source_bound` to verify every
source boundary/PTS and duration. It produces a bounded metadata-only
before/after plan with exact source IDs, source revisions, original frame
ordinals, Film Time starts, duration and SHA. It does **not** run a decoder,
allocate a render worker, or publish anything on preview.

Only clicking **Save new edit revision…** invokes another native OS
confirmation showing the proposed operation, the old/new exact revision,
count, film duration and plan SHA. The native host checks current project,
head revision and document SHA, repeats the plan after consent to exclude
time-of-check/time-of-use changes, and then commits through the existing
FilmIndex compare-and-swap publisher. The SQLite source clip rows and new
FilmIndex manifest are one atomic transaction. Original film clips and
all previous edit revisions remain recoverable after restart; source
movie bytes never change.

## Architecture and boundaries

- **Original video / FilmIndex:** authoritative source hash/size/probe and
  immutable source revision. The local NVPFrameIndex retains actual VFR
  ordinal/PTS/keyframe records and fast source-change stamp checks.
- **Timeline:** versioned arrangement of *references* using source ranges,
  exact placement Film Time and gaps. The timeline is disposable/editable
  metadata. It is not the source recording and does not need video frames
  loaded into RAM.
- **Slate:** separate production metadata describing the source/take;
  neither owns nor executes imported footage or film rendering.
- **Preview:** a proposed assembly manifest, not a film preview or approved
  still. Existing INDEX-TIME-06 **Preview actual source frame** remains
  separately OS-approved and runs a sealed original-PTS FFmpeg job.
- **Authorization:** no generic POST HTTP mutation, new file writer or
  browser-generated approval tokens. Native `TrustedFootageDesktop`
  verifies its own window origin and runs a physical OS confirmation.
  Changes have a strict typed operation schema; extra keys such as
  `source_path` or executable locations are refused. Browser-visible
  source-frame ordinals/ticks are decimal strings to avoid JavaScript
  2^53 precision loss.
- **Bounds:** one single-lane imported-video edit, 1–256 placements per
  operation, no overlap, no retiming, no transitions, no changes to authored
  OpenUSD/Temporal Ledger or soundtrack. Existing indexed original last
  frame remains outside the first source placement until a measured
  next-PTS boundary is available. Empty editorial assemblies are deferred
  until an explicit empty-assembly record format exists.

## Regression and acceptance

`tests/test_nvp_index_time07_assembly.py` uses a real FFmpeg VFR/B-frame
original and FFprobe-owned frame index to exercise move, duplicate,
trim, gap, cross-edit insert, restoration, refusal of no-op/out-of-range or
browser path keys, consent rejection, stale revision SHA/plan, foreign
project, source mutation and restart reopen while checking that original
SHA is unchanged.

`frontend/src/FilmTimeAssemblyPanel.test.jsx` exercises native preview
vs commit, exact decimal trim bounds, cross-source insertion, denied
approval, stale plan and restoration. The existing installed desktop
`--smoke-source` now additionally proposes and approves an actual trim,
then reopens old and new immutable FilmIndex revisions after its native
original-video import and contained one-frame PNG.

`.github/workflows/nvp-index-time07-assembly.yml` requires Windows 2025
and Ubuntu 24.04 on Python 3.11/3.13 with actual FFmpeg/FFprobe, plus React
build/Vitest. The E2E-01E NSIS job must independently run the updated
installed executable smoke. Draft until exact-head runs pass, real
Windows human mouse/file picker/edit interaction is witnessed, and
the FFmpeg/FFprobe public redistribution/license audit closes.
