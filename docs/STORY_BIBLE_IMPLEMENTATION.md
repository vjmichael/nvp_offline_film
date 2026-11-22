# NVP-WRITE-03 — Persistent Story Bible and Continuity Engine

**Date:** 2026-11-02  
**Scope:** NVP film-specific code only. All Lu work is deferred until Lu v1.0.

## Implemented

* New `StoryBible` SQLite service with schema-migrating setup and project-scoped character, location, prop, and story-event entities.
* Stable UUID-style entity identities, display names, aliases, rename history (retaining previous name as alias), and optimistic entity revisions.
* Human-controlled fact proposals and decisions. Fact slots are keyed by `(entity, fact_key, story_scope)`; a proposed replacement cannot silently replace an accepted fact. Explicit supersession preserves historical accepted facts and an audit change record.
* Story-time/context-scoped facts; `global`, `before_crash`, `after_crash` etc. A changed fact in a *different* scope is not automatically treated as a contradiction.
* Manual links to real screenplay scenes with the scene ID, heading, SHA-256 text fingerprint, and screenplay revision at linking time. Changes and removals are reported; changing a screenplay never destroys references.
* Impact reports identify changed/removed linked scenes, current or archived shot IDs, proposed factual disagreements, and accepted canon-change audits with linked scenes and shots. An explicit acknowledgment records the screenplay revision reviewed; it does not alter screenplay or shots.
* REST API endpoints to list/create/rename entities, add aliases, propose/approve/reject facts, link scenes, inspect continuity, and mark canon changes reviewed. The local UI work is in the NVP integration development branch.
* Existing parser-derived `project['bible']` remains heuristic, not human-approved. The new StoryBible is authoritative only for explicitly approved entries.

## Limitations

* This is deterministic reference tracking, **not natural-language contradiction detection**. It cannot infer whether two paraphrased screenplay passages conflict, nor automatically resolve character identity from dialogue.
* The local FastAPI prototype has no Lu auth or signed DLC delivery. Do not expose the development server remotely. Production NVP remains a future optional Lu DLC.
* Entity and fact decisions are made through the local creator UI. Identity/authentication/permissions in Lu are deliberately deferred.
* Automatic *model* incorporation of Bible facts into prompts, dynamic event ordering, scene remapping after changed headings, role/relationship graphs, and richer character knowledge are next steps.

## Verification

Tested in the existing NVP Python developer working copy (Python 3.13):

    PYTHONPATH=. python -m unittest discover -s tests -q

**63 passing tests** = 45 foundation/story-context tests + 18 new Story Bible tests (including local API and revision/scope/proposal/shot recovery tests). Tests run against an isolated SQLite database, not a real AI model or media renderer.

## Apply to NVP development checkout

The bundle includes **complete** `backend/nvp_story_bible.py`, the updated `backend/nvp_api.py` and `tests/test_story_bible.py`. Place them at those relative paths in a checkout of the NVP `nvp/story-approved-context-20261102` branch, overwriting `backend/nvp_api.py` only after inspecting local modifications. Then run the tests shown above.

The in-repository Story Bible UI is under review in `nvp/story-bible-continuity-20261102`; it requires the API changes from this bundle. This bundle does not contain a rebuilt Windows installer or a finished film renderer.
