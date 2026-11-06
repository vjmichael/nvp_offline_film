# INDEX-TIME-08 — Safe Visual Playback of Original-Footage Assemblies

**November 6, 2026 · Draft implementation; exact-head Windows/Linux and installed Windows NSIS acceptance pending.**

## Filmmaker's workflow

Open a movie, go to **17 · Indexed footage**, and select an imported
source assembly. The new **Review your film assembly** panel sits next to
the existing non-destructive editing controls.

- A simple film playhead permits scrubbing, jumping forward/back five
  seconds, jumping to previous/next cut, and inspecting a precise original
  source frame without decoding video during ordinary metadata navigation.
- **Review & play original footage…** requests one native OS approval for a
  short, exact, SHA-bound review of *up to 96 original frames*. NVP may
  cross multiple original source clips and intentional gaps in that
  section; the scope includes project ID, saved edit ID/revision/SHA,
  starting Film Time and bounded original-frame/worker count.
- NVP's existing O(log N) original Film Time resolver chooses the initial
  source frame; the FilmTimeWindowPreflight maps each actual source PTS
  into exact integer Film Time. It assembles no fake CFR frame numbers or
  invented durations. The end of a held source frame is its next original
  source-PTS boundary. In an editorial gap, the viewer is deliberately
  black rather than holding a previous camera frame.
- The existing creator-authorized `NativeFilmTimeWindowHost` launches
  each bounded 12-frame sub-window as a separate contained FFmpeg process
  with durable TaskLedger, native resource admission, cancellation and
  independent source-PTS and PNG receipt verification. The browser never
  selects worker binary/source path/destination. The playback review queue
  is separate from the single-still review queue to avoid stealing jobs.
- The UI starts showing already verified batches while later batches
  decode. It retains **one actual PNG image data URL at a time** in React,
  not the whole video. Play/pause and frame stepping act on the verified
  output list; stopped or stale reviews are discarded. An ordinary pause
  pauses playback and doesn't pretend an authorized decoding job was
  terminated; **Stop review** cancels its native work.
- A finished bounded section can be continued by moving the playhead
  to its exact next Film Time and approving another bounded review.
  This is deliberately a *short assembly review*, not yet a full-length
  uninterrupted player or a final audio/video conform.

## Frozen-state invariants

1. **Original recordings and film source revisions are not written.**
   The decoder accesses externally referenced, SHA-ingested original
   footage only through existing immutable project-scoped FilmIndex and
   NVPFrameIndex maps. Fast preview uses source-stamp/PTS integrity;
   it does *not* claim a new whole-file SHA proof at every interactive
   frame. Conform preparation remains an independent stronger custody
   gate.
2. **Assembly history cannot change during review.** A review identifies
   one exact head edit revision and document SHA. Every job has a
   precommitted sealed plan, time/ordinal bounds and exact scope consumed
   by the existing creator authorization check. If the head changes,
   the old review cannot supply further picture data to the desktop.
3. **Review is not publishing.** No new HTTP source write or arbitrary
   executable launch endpoint, no Slate/actor/temporal-event mutation, no
   final film approval and no new assembly revision. Returned pictures
   carry `master_approved: false` and source-stamp-unverified preview
   provenance, never a fake final mastering receipt.
4. **Cancellation and recovery fail closed.** A cancelled or altered PNG
   never leaves the native window as a verified frame. A contained worker
   that fails native recovery reports `RECOVERY_REQUIRED`, not a
   fabricated picture. The UI excludes stale source/revision frames and
   drops images when selection or project changes.

## Implementation and verification

- `backend/nvp_index_time08_playback.py`: native window-owned review
  session, exact cross-cut/gap PTS planner, up to 96 original frames /
  12 actual decoding windows, trusted native consent, isolated durable
  TaskLedger, independent per-chunk and per-PNG SHA audit.
- `backend/nvp_index_time06_native_desktop.py`: bounded trusted
  pywebview JS API for starting/polling/reading/stopping a session, and
  session shutdown from the installed window lifecycle. All exceptions
  are translated into closed-status responses without original paths.
- `frontend/src/FilmTimePlaybackPanel.jsx` and
  `frontend/src/FilmTimeIndexPanel.jsx`: filmmaker-friendly transport,
  exact BigInt scrub, cut navigation, frame stepping, buffering, black
  gaps, one-image IPC and stale-result controls.
- `tests/test_nvp_index_time08_playback.py`: real VFR/B-frame original,
  two saved source clips with a gap, actual contained native FFmpeg
  jobs, receipt-verified PNGs, denial, cancellation, changed source
  edit, altered review picture and original-file SHA preservation.
- `frontend/src/FilmTimePlaybackPanel.test.jsx`: Play/Pause/step, exact
  BigInt playhead, next-cut jump, native refusal and stale PNG exclusion.
- `.github/workflows/nvp-index-time08-playback.yml`: real native
  Windows/Linux 3.11/3.13 plus React/Vitest gates.
- Windows installed `--smoke-source` now verifies 2+ actual PNG frames
  from the *installed* frozen worker **after** the source import and
  immutable editorial trim; Windows `--smoke-window` must confirm
  playback controls mount in real native WebView2.

**Open before accepted:** exact-head native Windows/Linux/React CI,
installed NSIS acceptance, independent real mouse/keyboard experience,
native worker crash/termination cleanup evidence, long-form streaming
without repeatedly approving short sections, audible soundtrack and
multilane picture/audio transitions. FFmpeg redistribution license
obligations must also be cleared before public installer release.

**Future UX direction:** The technical frozen-data protection is built
into the engine rather than imposed on the user. The player should
eventually look like a familiar video editor, with fluid cut/copy/paste,
drag-rearrange, non-destructive undo/redo, optional thumbnails, native
review playback, multitrack sound, and prompt-free navigation among
already authorized original references. The source footage is
effectively write-protected while the mutable assembly is forgiving.
