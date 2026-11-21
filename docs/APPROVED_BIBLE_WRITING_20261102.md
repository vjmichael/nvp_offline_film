# NVP-WRITE-04 — Approved Story Bible → Screenplay Context

**Date:** November 2, 2026
**Branch:** nvp/story-bible-writing-context-20261102
**Product:** NVP remains a future Lu Film Workspace DLC.
**Scope:** NVP film logic only. All Lu work is deferred until Lu v1.0.

## Implemented

The writing assistant now receives a deterministic, bounded view of the
creator's **approved Story Bible** in addition to the approved logline,
synopsis, beat sheet and treatment.

A character, location, prop or event is represented by an immutable entity
ID, creator-selected display name and aliases. Entity names are included
even if no accepted facts exist yet.

Only status=accepted facts become authoritative writing context. Proposed,
rejected and superseded facts are excluded. AI suggestions cannot approve
themselves.

Each included fact carries its exact story_scope label and property key.

    [CHARACTER] Mara (ID ...)
      cannot_drive [scope=global]: Mara never learned to drive
      knows_secret [scope=before_reveal]: Mara does not know who stole the key
      knows_secret [scope=after_reveal]: Mara knows Bob stole the key

Scope labels are NOT interpreted as a temporal ordering algorithm. NVP
cannot infer that a screenplay scene is before or after a reveal without
explicit mapping. The prompt preserves this uncertainty.

## Scene context

- Whole-movie writing: all entities and accepted facts from that project
  subject to a visible context budget.
- Focused-scene writing: only entities explicitly linked to that scene.
  Prose/alias mentions never silently create trusted entity mappings.
- An unlinked scene reports missing context clearly.
- A linked scene whose text changed since the explicit reference
  refuses generation until the link is refreshed.

No cross-project or hidden context sharing.

## Durable dependency and race checks

New table: creative_draft_bible_contexts
  draft_id / canon_digest / scene_id / facts_total / facts_included

The SHA-256 digest covers all selected approved canon, names, aliases,
stable IDs and explicit scene links, including facts omitted from the
bounded prompt. The snapshot is checked within the SQLite write
transaction that persists a draft.

- Story Bible edits during inference refuse the write.
- Changes after draft creation mark bible_context_status=needs_review
  and prevent screenplay replacement until a new draft is reviewed.
- Entity creation and renaming, scene-link edits, and changes to
  omitted approved facts are tracked.
- Merely proposed or unapproved facts do not invalidate drafts.
- Stale approved earlier stages cannot silently influence later writing.
- The independent screenplay revision and earlier-stage lineage checks
  remain in place, and AI completion never approves or overwrites a script.
- Legacy drafts without Bible provenance remain available, marked
  legacy_untracked; with canon present they require re-creation and
  review before approval rather than invented provenance.

## API and UI

GET /api/projects/{project_id}/creative/bible-context?scene_id=...

Returns selected canon, counts, digest and scope limitations.
The writing UI previews the relevant approved facts and warns when
drafts refer to outdated canon. Backend checks remain authoritative.

## Verification

Local NVP developer checkout:

    PYTHONPATH=. python -m unittest discover -s tests -q
    python -m compileall -q backend tests

Result: **84 local Python tests passed** (63 prior + 21 local WR04 cases).
These cover approved/unapproved separation, character knowledge labels,
scene links, omitted-context invalidation, mid-generation revisions,
stale approval, upstream chain staleness, project isolation,
restart persistence, and API previews.

The GitHub branch also includes a compact WR04 regression suite.
The downloadable local package includes the full 21-case WR04 suite.
The frontend has NOT been production-built. No real Qwen/Gemma
inference or film rendering has been tested. Fake writing model tests
are not creative-quality benchmarks.

## Next NVP-only milestone

NVP-WRITE-05: creator-defined story events with partial ordering and
explicit links from scenes to events, to make chronological character
knowledge and prop/location changes testable rather than inferred.

Future work includes conservative contradiction review, selective retrieval,
a genuine token-budget planner, and physical GGUF bakeoff.

No Lu code, alpha, or DLC interface work is changed here.
