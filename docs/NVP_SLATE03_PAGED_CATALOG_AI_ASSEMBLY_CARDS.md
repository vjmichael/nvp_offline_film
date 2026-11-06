# NVP SLATE-03 — Paged Branch Catalog and Assembly Cards

Status: Implementation committed for native and UI acceptance. GitHub CI and installed desktop integration remain unverified.

## Architecture

NVP's film timeline is an edit assembly of references to frozen 3D Takes, OpenUSD shot overrides, and exact source-time ranges. Frames are generated later during presentation and export. The source world and performance are not copied by inserting a segment.

SLATE-02 has a 256-node graph bound and FilmIndex also has a 128-dependency limit per revision. We should not fake creative parent-child relations to bypass these constraints.

SLATE-03 introduces pages of 64 branches, each as an immutable SHA-bound FilmIndex revision, and a catalog root referencing up to 64 pages. That supports 4,096 branches per catalog revision. True parent identities and fork ticks remain unchanged across pages. The API pages up to 100 items at once, with group, beat, character, emotion, shot type and technical status filters. A catalog adapter allows existing mixed-Take assembly to read these branches. The adapter currently materializes the bounded full graph when building an edit; the UI can use paged reads.

## Metadata

Digital slate identifiers remain source Take/shot IDs, revisions and hashes, scene, setup, camera, Take number, wild flag, parallel group, parent, fork and original time interval. Each source may also have story beats, characters, dialogue cue IDs, action and emotion tags, shot type, director rating/notes, technical quality and continuity flags. Optional editor/script-tagged moment cues pinpoint the exact source-time intervals carrying a story beat, dialogue, actor action or emotion; these are searchable without video frames or a particular rendering FPS. AI suggestions instead remain in their own source-timed unreviewed observation records. Machine observations always carry model identity, confidence, exact source interval and UNREVIEWED_AI_PROPOSAL status. The model cannot self-approve these suggestions or activate an edit.

## Cards and controls

The reusable React pane displays an assembled edit as boxes containing scene, shot, Take, camera, source and destination time ranges, story beat, emotion, director rating, notes, quality and continuity warnings. AI observations are visibly unreviewed. Only the committed portion of a source is green. Inspection does not make it active. Insert/replace/trim/move actions still operate on source references, and commit requires explicit authorized editor action. The pane offers a paged Load More callback and a detachable same-origin browser window; native desktop window integration is still open.

## Verification

Tests cover 305 branches over five pages, cross-page ancestry, source hashes, metadata search, rejection of unauthorized capture, unreviewed AI metadata, restart reopening, and mixed assembly through the catalog adapter. UI tests cover assembly cards and paged display. Exact-head CI and actual installed-editor wiring are not yet accepted.

Future growth beyond 4,096 branches can use a deeper manifest directory or indexed catalog. Storage hierarchy must never be mistaken for actual Take genealogy.
