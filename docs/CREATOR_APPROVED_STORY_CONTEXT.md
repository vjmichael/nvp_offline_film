# Creator-approved story context — NVP-WRITE-02

**Development date:** November 2, 2026
**Scope:** NVP film-specific writing/persistence only; no Lu changes.
**Runtime status:** Python local-prototype tests passed; actual Qwen/Gemma generation
and React production build still require physical-machine acceptance.

## Decision: Pause all Lu work until Lu v1.0

NVP's final product form remains an optional Film Workspace DLC in Lu.
**No Lu coding, interface integration, SDK work, signed-worker work, or Lu
release gating is part of the active NVP backlog until Lu v1.0.**
Film-specific development proceeds in this repository using temporary
local test adapters. It must not introduce a second required model app in
the final product or silently expand Lu Core.

## The actual writing chain

    idea → logline → synopsis → beat sheet → treatment → screenplay

Each stage is optional: users can skip ahead, bring an existing screenplay,
or type their own drafts. Nothing is automatically approved. The original
idea and creator-approved **earlier-stage** drafts supply context for the
next writing task.

New pure film module: backend/nvp_story_context.py

- Per-stage task instructions emphasize causality, character motivation,
  filmability and concrete screenplay dialogue.
- Only a draft with status=accepted can supply authoritative upstream story
  material. Proposed, discarded or merely generated AI text cannot.
- Individual approved-stage excerpts are bounded; truncation is visibly
  labelled. Never advertise omitted text as reviewed by the model.
- The screenplay context is also bounded, so large projects require later
  summary/retrieval work rather than false full-context claims.
- The model response is always a separate **proposed** creative draft.

## Durable dependency snapshots

The creative_draft_contexts table stores a JSON list of upstream
(stage, approved draft ID) pairs for each new creative draft. No existing
draft or approved screenplay is rewritten during migration.

When a new logline or earlier stage is approved after later work exists:
- All affected downstream drafts retain their text and decision history.
- The API marks each stale draft context_status=needs_review and reports
  changed_upstream_stages.
- Generation of a later stage will refuse if one of its currently selected
  earlier accepted stages is stale; the creator must review/re-establish that
  earlier approved stage.
- Accepting an already-written stale proposal is refused; discarding it
  remains possible.
- A change to upstream approvals during model inference is caught before
  saving the model proposal. A separate screenplay revision check still
  catches manual script edits and restores while generating.
- New draft creation and approval use immediate SQLite write transactions
  so approval snapshots and project revision checks cannot interleave with
  competing writes on that database.

The newest accepted draft in any stage becomes the active stage source.
Older accepted versions are retained in history, rather than deleted.
Creators who want to reaffirm an old accepted draft against a new earlier
stage should create a new proposal using the old text and approve it; do not
silently relabel the old decision as current.

Existing pre-migration drafts lacking a context snapshot are returned as
legacy_untracked, not falsely labelled current. They remain stored and
available for review. New approval tracking does not retroactively invent
their generation provenance.

## API and GUI

- GET /api/projects/{project_id}/approved-story?stage=beat_sheet
  returns the most recently approved earlier-stage entries, including their
  context status and relevant provenance.
- GET /api/projects/{project_id}/creative-drafts includes context_status,
  changed_upstream_stages, and upstream_sources.
- The existing writing interface shows approved earlier stages and a
  visible Needs review warning where lineage is outdated. Generation is
  disabled from the interface while earlier approvals require review.
- The backend remains authoritative: a forged or stale UI state cannot
  bypass its approval checks.
- Development-only local model selection stays available for isolated
  Gemma 4 31B, Qwen3.8 27B, and Qwen3.6 35B-A3B testing. It is NOT
  NVP's final Lu model manager.

## Test evidence

In the local developer copy of NVP:
    PYTHONPATH=. python -m unittest discover -s tests -q

45 Python tests passed (32 existing + 13 new), including:
- approved logline and synopsis appear in beat-sheet prompts
- unapproved AI suggestions excluded from canon
- later-stage staleness after changing an approved logline
- stale manual and model approvals blocked
- changes to approved facts DURING inference rejected
- project isolation and persistence after reopening SQLite
- bounded context with honest truncation marker
- stage-order isolation (later stage never bleeds into earlier stage)
- API approved-story endpoint and film-specific prompt rules

This is a local Python acceptance test, not a GGUF screenplay-quality result,
React production build, Blender video render, or end-to-end Lu DLC test.

## Next NVP-only milestone (NVP-WRITE-03)

Persistent character/setting/prop/story facts with stable IDs, human approval,
provenance and scene references. Create an independently queryable story bible
and continuity report so screenplay changes produce explicit scene/shot
impact warnings rather than silently corrupting older approved work.
