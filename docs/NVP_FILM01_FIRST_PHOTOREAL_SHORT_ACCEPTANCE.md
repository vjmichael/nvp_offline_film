# NVP-FILM-01 — First complete photorealistic 30–60-second short-film acceptance

**Type:** Future end-to-end film-production acceptance gate (NOT yet passed).
**Dependency:** Complete and verify the B13/B14 edit reimport and conform foundations, native creator-approved render/export, source-linear color-managed edited video, synchronized audio, and independently audited playable master.
**Scope:** NVP only. Lu–DLC interface remains deferred until after Lu v1.0.

## Outcome

Produce an original narrative or visual short film of **30–60 seconds** from NVP's world/scene/performance/camera/lighting/material data and frozen Digital Takes. Deliver a coherent, **photorealistic-looking** presentation (not merely high bit depth), with **actual persistent, non-destructive picture edits**, **sample-accurate synchronized sound**, and **a playable, technically auditable high-quality master**. The human reviewer, not an automated file-format check, determines whether the images look genuinely convincing.

This milestone does not demand full feature-film scale, advanced VFX, DCP, or complete Lu integration. It does demand one real start-to-finish film rather than a stitched test-only synthetic video or renamed low-quality proxies.

## Mandatory film content

- 24 fps, 30–60 seconds: **720–1,440 actual final output frames**. Existing B12/B13/B14 small-fixture limits (120 original and 480 edited frames) MUST be extended through a separately engineered bounded, streaming production path; never silently bypass resource protections.
- At least three visually distinct shots and two visible, motivated editorial cuts; persistent editable cut list and two non-destructive revisions. Exact source ranges/camera identity preserved.
- Physically plausible materials, lighting and shadows, stable scene geometry, temporal continuity and camera motion; any humans/creatures/props must remain consistent across cuts. Visual evidence must come from generated render content, not reference stills substituted into a video container.
- At least one time-critical visible action with an associated synchronized sound effect, with optional dialogue or musical score licensed/original as appropriate. Silence alone does not count.
- A creator-review playback format and a professional high-quality **video+audio** master (e.g. proper ProRes 422 HQ MOV with PCM audio, appropriately tagged; additional mezzanine or H.264 preview optional). Frame rate, dimensions, bit depth/chroma, sound sample rate/channels and correct color transfer/primaries recorded and independently checked.

## Source-of-truth production workflow

1. Author and freeze world, shots, performances and production instructions into indexed Digital Take(s).
2. Render real scene-linear high-bit-depth image frames from the authored world. Record source frame SHA, timing and camera shot.
3. Make color-managed editorial review pictures, retaining immutable source and look policy.
4. Edit the actual shots through supported OpenTimelineIO cut revisions. Import and persist at least two versions; old versions remain reopenable.
5. Conform **the approved edit version only** into the actual final sequence, preserving full frame lineage. The technical master path works from scene-linear original source and explicit color transform; do not relabel sRGB PNG codes as Rec.709 mastering.
6. Compose/synchronize audio to editorial frame/sample timeline. Specify the frame↔sample mapping rationally (24 fps and 48 kHz => 2,000 samples per frame), avoid cumulative clock drift, and enforce clip boundaries and trim behavior.
7. Render professional picture+audio deliverable under native creator consent and OS-contained, resource-admitted workers. Persist FilmIndex master record with exact take/edit/audio/grade dependencies and media hashes.
8. Reopen after NVP restart and independently decode/verify the *actual* output master: expected frame count, duration, audio presence and duration, A/V sync event timings, color tags, picture/frame lineage, full content SHA, no missing assets, no leaked resource reservations.

## Two independent acceptance tracks

**Technical (automated, required):**
- Real on-disk source/render/edit/sound/conform/delivery; not mocked image or soundtrack tests.
- Full 720–1,440 frames at actual chosen resolution and source bit depth, with CI/local resource budgets stated; bounded work chunks and no full-film RAM residency.
- No source rewrite across edits; SHA-based FilmIndex provenance; restart persistence and approved revision exactly matches delivered master.
- Video decode checks, stream probing, A/V timebase and sample-frame sync checks, deliberate failure/recovery/cancellation/retry paths, worker containment and disk/RAM accounting.
- Honest codec/color/audio claims verified by probe and decode; master is truly playable.

**Creative/visual (human review, required):**
- Photoreal quality plausible to a viewer: coherent lighting, shading, texture, temporal stability and motion, with no distracting render artifacts.
- Editing enhances the miniature film rather than merely demonstrating cuts.
- Audio causally matches onscreen events and levels are listenable; no conspicuous synchronization drift.
- Story or action conveys a clear intended beat within 30–60 seconds.
- Human creator approves the actual viewed output. Automated metrics assist but cannot certify photorealism.

## Gate policy

- A 120-frame fixture or picture-only conform proves **component functionality**, NOT FILM-01.
- Real 30–60 s photoreal cinematic quality is an **aspirational, measurable acceptance target**, not an already-proven capability.
- Do not mark FILM-01 PASSED without independent technical evidence and explicit human creator viewing/approval. Keep technical pass and visual approval separate.
- No fake audio, no 8-bit proxies called scene-linear 32-bit assets, no silent omission of unsupported film operations, no unverified exported master.
- Production costs/latency and hardware limits must be reported with actual measured runs, not estimates presented as results.

## Implementation sequence after B14

1. Finish native-approved B14 conform and exact-source real edited output acceptance.
2. B14 professional edited picture mastering from source-linear frames, with independently verified video decode.
3. Film-audio authoring/edit-conform, 48 kHz sample-accurate sync, audio lineage and inspection.
4. High-quality picture+audio mux/master with immutable FilmIndex delivery and restart audit.
5. Extend short test frame/raster budgets to bounded streaming **720–1,440-frame** workload; photoreal visual-production pipeline and creator review.
6. Execute FILM-01 and record technical proofs plus separate human creative verdict.

**Status:** Specification only; not an implementation or acceptance claim.
