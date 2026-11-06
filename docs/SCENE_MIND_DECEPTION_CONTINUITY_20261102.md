# NVP-WRITE-06 — Within-scene knowledge, mistaken beliefs, deception and review

**Date:** 2026-11-02  
**Status:** Locally tested NVP backend developer milestone; UI JSX parsed but the full React production build has not been run.  
**Product direction:** NVP remains the future Film Workspace DLC. **All Lu work is deferred until Lu v1.0.**

## The semantic separation

1. **Objective canon** is a creator-approved Story Bible fact, with a stable fact ID. A fact's truth is not changed by a character misunderstanding it.
2. **Subjective epistemic state** is a creator-approved, explicitly beat-anchored transition for a particular character and fact. States: `learn_truth`, `believe` a supplied value (possibly false), `doubt`, and `forget`/does-not-recall. A missing record means **unverified**, not ignorant.
3. **Spoken assertions** are a separate creator-approved record with speaker, recipient, referenced fact, asserted value and declared intent: `deliberate_deception`, `mistake`, `bluff`, or `truthful_claim`. A listener's belief is **never** changed merely because someone said something. A deliberately deceptive intent can be creator-authored without the model having evidence of what the speaker already knows; that gap triggers a *suggestion*, not a hard rejection.
4. **Continuity suggestions** identify structured issues, not arbitrary prose contradictions. Examples: explicitly false character belief, a truth-labelled statement conflicting with canon, a lie matching objective truth, deliberate deception with no earlier recorded speaker awareness, stale scene beats and superseded fact sources. Suggestions are deterministic, project-scoped, revision-checked and backed by evidence fingerprints.

## Scene beats and before/after queries

`scene_mind_beats` anchors a named moment to a **1-based line number relative to the parsed screenplay scene** and records its screenplay-scene content SHA and screenplay revision. A changed scene requires an explicit creator re-anchor. The selected beat's before and after snapshots are distinct: a transition at a beat is not effective in a **before** snapshot of that beat. Line numbers are used only **within** that scene, never to infer the temporal order between two screenplay scenes. Prior NVP-WRITE-05 event edges retain partial-order semantics for flashbacks and parallel scenes.

## Durable tables

The new service (`backend/nvp_scene_mind.py`) creates:

- `scene_mind_state`: a per-project optimistic revision, bumped on approved actions and suggestion review.
- `scene_mind_beats`: explicit per-scene positions, named and fingerprinted.
- `scene_mind_changes`: proposed / accepted / rejected changes in character knowledge and beliefs, referencing approved Story Bible facts.
- `scene_mind_statements`: proposed / accepted / rejected spoken assertions and their intent.
- `scene_mind_suggestion_reviews`: idempotent (exactly once) accept/reject review outcomes with optional director's note and an explicit acceptance resolution (`intentional` / `fix_later`).

Creator approvals use SQLite `BEGIN IMMEDIATE` transactions, project-scoped record lookups and expected revisions. Only creator-approved changes enter the writing model's context. Proposed and rejected changes remain available in the editing interface but do not become authoritative canon.

## What accepting a suggestion does

- **Accept + intentional:** the creator acknowledges a potential discrepancy as purposeful (for example, a dramatic misunderstanding) and may add a rationale. A current acceptance is included as an *explicit creator continuity note* in writing context.
- **Accept + fix_later:** the creator records that a correction is needed, without silently altering the scene or asserting the correction already happened.
- **Reject:** the creator dismisses the suggestion. Rejected review notes are not injected into model prompts as if they were positive instructions.
- **None** of those actions modifies the screenplay text, accepted facts, approved knowledge transitions, shot plans, character dialogue or rendered media.

A review is keyed by a deterministic fingerprint of its evidence. If the accepted fact or scene changes, the old review cannot silently apply to the new situation. Duplicate reviews and stale optimistic revisions are refused. The underlying issue remains auditable, with a review status.

## Integration with NVP writing

`nvp_bible_context.canon_snapshot()` now includes approved within-scene changes and spoken assertions, with explicit labels (`[BELIEF: BELIEVES_FALSE]`, `[STATEMENT: DELIBERATE_DECEPTION]`, etc.). The approved canon's objective value remains separate, and a quoted false belief cannot be mistaken for world truth. Both whole-film and scene-specific writing contexts carry this provenance.

The durable context SHA-256 covers **all accepted** beat changes, statements and current review records, even if the bounded model prompt omits some for length. An approval made during model generation invalidates the draft and refuses storage. Approval after generation flags the draft `bible_context_status=needs_review` and prevents using it as a screenplay without re-review.

## Developer API and UI

All endpoints remain under `/api/projects/{project_id}/scene-mind` (developer-only local NVP API):

- `GET /` with optional `scene_id`, `at_beat_id`, `phase=before|after`.
- `POST /beats`, `PUT /beats/{beat_id}` (creator-selected anchor / re-anchor).
- `POST /changes`, `POST /changes/{id}/decision`.
- `POST /statements`, `POST /statements/{id}/decision`.
- `GET /scenes/{scene_id}/suggestions`, `POST /scenes/{scene_id}/suggestions/{id}/decision`.

`frontend/src/SceneMindPanel.jsx` supplies line-marking, before/after previews, knowledge/statement proposals, approval controls and review decisions. The main development frontend mounts it as an optional **Scene Minds** tab. No Lu runtime, HTTP model loader, GPU library, browser storage or external API is introduced by the new panel.

## Verification and limitations

Run locally:

```
cd /mnt/data/nvp_write06
PYTHONPATH=. python -m unittest discover -s tests -q
python -m compileall -q backend tests
```

**140 Python tests passed locally**, including 29 new NVP-WRITE-06 tests, with a fake writing model. The scene panel independently passed a TypeScript JSX syntax parse; that is **not** a production React build or proof that a real user can edit a film end-to-end.

The continuity suggestion engine does not understand natural-language subtext or arbitrary scene dialogue. It compares *creator-authored structured evidence*. Scene line anchors are fragile under screenplay edits and require explicit re-anchoring. Character state outside the current scene remains subject to WR05's partial event order, not screenplay display position. End-to-end Qwen/Gemma screenwriting and frontend production build remain separate acceptance gates.

## Next NVP-only work

WR07: independently review script prose against explicitly approved canon and mind states with evidence-backed **proposed** annotations; do not grant an AI authority to rewrite the screenplay. Expand scene beat anchoring from line offsets to stable shot/beat IDs and improve batched revision/merge UX. Lu remains frozen until v1.0.
