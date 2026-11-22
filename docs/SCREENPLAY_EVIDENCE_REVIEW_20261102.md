# NVP-WRITE-07 — Evidence-backed Screenplay Continuity Review

**Date:** 2026-11-02  
**Source branch:** `nvp/screenplay-evidence-review-20261102`  
**Production architecture:** NVP remains an optional future Film Workspace DLC for Lu. **All Lu development and integration are deferred until Lu v1.0.** This milestone changes NVP film code and local development UI only.

## Purpose and trust boundary

NVP's Story Bible already separates objective, creator-approved canon from AI
suggestions, character beliefs, deceptive statements, and screenplay revisions.
The earlier Scene Minds reviewer flags inconsistencies among *structured*
records. This milestone adds **conservative extraction directly from actual
Fountain-style screenplay text**, including stage directions and character
utterances, with source evidence and explicitly reversible creative decisions.

The reviewer is **not** a general semantic NLP or LLM judge. A match is a
potential continuity issue, never proof. Its parser uses exact high-precision
phrase patterns and can miss virtually unlimited linguistic paraphrases,
context, metaphors, montage, flashbacks, unreliable narration, and subtext.

## Initial supported extraction grammar

Only **unambiguously named Story Bible characters** and their approved aliases
are matched. No matching person is invented from dialogue; no names from other
projects can leak in.

- Narration: `Mara drives a car`, `Mara cannot drive`, `Mara can't swim`,
  `Mara swims across ...`, `Mara is alive`, `Mara is dead`,
  `Mara has brown eyes`, `Mara's eyes are brown`.
- Character-cued first-person utterances: `I can drive`, `I can't drive`,
  `I can swim`, `I cannot swim`, `My eyes are blue`.
- Canon slot normalization is restricted to `can_drive`, `cannot_drive`,
  `can_swim`, `cannot_swim`, `alive`, and `eye_color`, and explicitly parseable
  values. Arbitrary prose slots (e.g., ownership, relationships, locations)
  are not guessed at.
- Only `story_scope=global` is compared with scene prose. Before/after event
  labels require an explicit semantic time mapping that this stage does not
  claim to have.
- Quoted/hypothetical narration is conservatively excluded. A matched
  character's dialogue is classified as possible belief/deception tension,
  **not** an objective contradiction.

No local model is required for the deterministic review; it performs no
network calls and makes no background inference.

## Evidence and suggestion types

Each candidate contains:

- Stable, content-derived suggestion ID tied to the **project**, scene hash,
  evidence passage and approved fact ID/value.
- Source type (`narration` or `dialogue`), literal quote, matched phrase,
  one-based scene-relative line, and one-based screenplay-absolute line.
- Exact referenced approved Story Bible fact, where available.
- Explanation, conservative confidence label (`pattern_match_only`) and a
  suggested *manual* review action.

Supported suggestion categories:

1. `narration_canon_mismatch`: a high-precision stage-direction claim is
   inconsistent with a recognized approved global fact.
2. `dialogue_canon_tension`: a character's first-person claim differs from
   approved global canon. If an accepted Scene Minds statement covers the
   same character/fact/scene, its declared intent is shown as *context*, not
   a verified match or proof of deception.
3. `narration_internal_tension`: two explicit statements about a property
   inside one scene disagree. This may be deliberate scene transformation,
   unreliable narration, a dream, or flashback; no chronology is assumed.

A clean report means **no matching issues within this limited grammar**, not
that the screenplay is free of errors. A fact whose value is too ambiguous to
normalize is skipped, not forced into yes/no.

## Creator review and audit trail

**GET** `/api/projects/{project_id}/screenplay-review/scenes/{scene_id}`

**POST** `/api/projects/{project_id}/screenplay-review/scenes/{scene_id}/suggestions/{suggestion_id}/decision`

Request: `decision`, `expected_review_revision`,
`expected_screenplay_revision`, optional `resolution`, optional `note`.

- `accept` requires `resolution=intentional` or `fix_later`. Accepting a
  *review suggestion* only records the creator's interpretation.
- `reject` rejects the suggestion without a resolution. Both decisions are
  immutable historical records. Neither one edits screenplay, canon, beliefs,
  scene links, effects, shots or model generations.
- SQLite `BEGIN IMMEDIATE`, strict project/scene lookup, expected revision
  checks and re-derived candidate identity prevent stale and conflicting
  decisions. Content changes invalidate old suggestion IDs; an accepted
  review for one passage cannot silently bless a revised passage.
- Unrelated screenplay edits do not erase reviews of unchanged scene evidence.
- Decisions survive a database restart and are retained even after the
  scene disappears.

**GET** `/api/projects/{project_id}/screenplay-review/history?scene_id=...&limit=100`

Read-only, project-scoped audit history, including the exact previously
reviewed evidence and whether each original suggestion still applies. Returns
up to 200 entries per request and reports when results might be truncated.

## User interface

`frontend/src/ScreenplayReviewPanel.jsx` adds the **Review screenplay** tab:

- User picks an active scene and manually refreshes the deterministic report.
- Each possible issue displays the exact quote and line, the approved fact,
  and a warning that dialogue may be intentionally deceptive.
- Creator chooses *intentional*, *fix later*, or *reject suggestion*, with
  an optional note. Existing reviews render read-only.
- Clear limitations and no-issues disclaimers are always visible.

Only the new standalone JSX component has been independently checked by a
TypeScript JSX syntax parser. Full React/Vite compilation and application UI
acceptance have **not** been completed; do not mark them passed.

## Acceptance evidence

Local NVP checkout `/mnt/data/nvp_write07`:

```bash
PYTHONPATH=. python -m unittest discover -s tests -q
python -m compileall -q backend tests
```

**170 distinct Python tests passed:** existing NVP tests plus 30 new reviewer
and audit tests. Coverage includes exact line references, narration/dialogue
separation, project isolation, alias matching, skipped relative scopes,
false-positive controls, intentional and rejected decisions, duplicate and
stale review refusal, source/fact invalidation, persistence, history on
removed scenes, API response validation, and unchanged-scene review retention.

Not verified: physical Qwen/Gemma runtime, natural-language creative quality,
full JSX/React production bundle, Windows application test, semantic accuracy
outside the documented patterns, film rendering, or Lu DLC integration.

## Suggested NVP-WRITE-08 expansion

Add an **optional evidence-proposal adapter** for richer model-generated
continuity hypotheses. Require quoted source spans and exact approved fact IDs
and validate those spans against current screenplay text before allowing a
suggestion into director review. Track precision and false-alarm rates on a
frozen set of actual scenes and compare against this conservative deterministic
baseline. No model-generated claim should ever silently modify canon.
