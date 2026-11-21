# NVP-WRITE-05 — Story chronology and character knowledge

**Date:** November 2, 2026
**Architecture:** NVP Film Workspace DLC, developed independently.
**Lu freeze:** All Lu work deferred until Lu v1.0. No Lu changes here.

## Explicit story time, not screenplay page order

The Story Bible's existing event entities participate in an acyclic
partial-order graph. The creator declares event A BEFORE event B, removes
relationships, and leaves unrelated events unordered. Transitive
precedence can be proven, but screenplay scene number is never treated
as the fictional chronology.

A scene is anchored at an explicit BEFORE or AFTER named event point.
The scene fingerprint and screenplay revision are persisted. Changing
the script without refreshing its anchor invalidates the time reference.

## Approved character knowledge

Knowledge proposals record a film-scoped character, an already accepted
Story Bible fact, optional learning event, and source note. A null event
means explicitly known before the story began. Only accepted claims are
authoritative; the creator must review each proposal.

For an anchored scene the engine reports known, not_yet, indeterminate
(unordered events), unanchored (no time anchor), and source_fact_changed.
Claims for the same acquisition event are BEFORE/AFTER phase-sensitive.
An absent knowledge record never establishes ignorance.

For now knowledge is monotonically acquired. Forgetting, lies, false
beliefs, within-scene transitions, and inferred event timestamps are
left for a later milestone.

## Durable records and continuity safety

SQLite tables: timeline_state, timeline_edges, timeline_scene_marks,
timeline_knowledge. Project-specific revisions protect competing edits.
Cyclic/duplicate event relations, cross-project IDs, unapproved fact
references, and duplicate accepted knowledge are refused.

The screenplay writer receives separate approved objective facts and
character-knowledge state, including explicit event-order facts. Its
canonical SHA-256 snapshot includes authored timeline data even if a
prompt is truncated. Canon changes during generation refuse the draft;
changes afterward prevent stale approval. Unapproved proposals do not
invalidate approved canon. Superseded facts are flagged without
re-introducing their old values as current character knowledge.

Focused scenes still require explicit Story Bible entity links; names
mentioned in dialogue are not automatically authoritative associations.

## NVP-only API and development UI

GET /api/projects/{id}/timeline?scene_id=...
POST /api/projects/{id}/timeline/precedence
POST /api/projects/{id}/timeline/precedence/remove
PUT /api/projects/{id}/timeline/scenes/{scene_id}
DELETE /api/projects/{id}/timeline/scenes/{scene_id}
POST /api/projects/{id}/timeline/knowledge
POST /api/projects/{id}/timeline/knowledge/{claim_id}/decision

The NVP React developer interface has a Story Timeline tab for event
ordering, scene anchoring, knowledge proposals, creator approvals, and
scene-specific knowledge preview. It is not a consumer installer.

## Verification

Local NVP working copy: 111 distinct Python tests passed (84 prior,
21 chronology, 6 additional invariants). Python compileall also passed.
Checks include flashbacks, event transitivity/incomparability, cycles,
BEFORE/AFTER boundaries, stale scene hashes, project isolation, database
restart, optimistic concurrency, source-fact supersession, writing
proposals, and API round trip.

Not verified: complete remote-branch test run, production React build,
physical Qwen/Gemma inference, film rendering, full semantic contradiction
detection, or Lu integration. The downloadable development archive contains
the exact locally tested Python source and tests.

## Next milestone: NVP-WRITE-06

Explicit event occurrences and within-scene points; mistaken/forgotten
character knowledge; an auditable continuity reviewer that suggests
changes but never edits creator-approved canon automatically.
