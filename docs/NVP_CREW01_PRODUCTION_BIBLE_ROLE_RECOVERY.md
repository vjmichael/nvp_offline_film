# NVP-CREW-01 — Recovering the original Film Studio's Production Bible and AI crew

**Status:** First implementation increment, on B14 development branch; Windows/Linux CI pending. This is a model-independent *role planning contract* and is not an AI crew orchestrator, actor animation model, Blender/UE5 plugin or creator-approved stage mutation.

## Original strengths retained

The early NVP design used a Production Bible, casting ledger, set/environment registry, optical rules, temporal story tracker, director, director of photography, acting coach, script supervisor, dailies and persistent 3D scenes. Its best idea remains essential: NVP is a director-controlled film studio rather than a collection of unrelated 3–10-second generated videos.

The original `nvp_dp_engine.py`, `nvp_acting_coach.py`, `nvp_version_control.py` and UE5 bridge included hardcoded or simulated outputs. Do **not** import or present those as validated production implementations. Keep their useful domain vocabulary, repair actual functionality using modern FilmIndex, StoryBible, immutable takes and native worker supervision.

## Authoritative creator-approved truth

The project screenplay, accepted writing decisions, Story Bible, spatial world state, approved take, performance and editorial revisions have separate domain ownership and version provenance. In particular:

- **Story Bible** owns canonical characters, locations, props, events, aliases, approved typed facts and explicit story scopes. Its existing approval and supersession workflow, not a crew agent, may accept new facts.
- **Scene/world state** owns persistent geometry, asset identity, positions, contact constraints, wardrobe and time. The script/Story Bible inform scene changes but cannot bypass deterministic placement and director approval.
- **FilmIndex** preserves exact revisions and data lineage; it cannot be rewritten because an AI role produces a new suggestion.
- **AI crew roles** are ephemeral functions of one model's task context, not independent memory stores or permission holders. All roles refer to one accepted bible, with bounded scene/text retrieval and exact context digests.
- **Human director** can override artistic rules intentionally, but the override is explicit and versioned. Neither a system role prompt nor an unreviewed AI claim is a creator approval token.

## Implemented CREW-01 code

`backend/nvp_crew_roles.py` exposes:

1. `prepare_crew_task(studio, project_id, role, instruction, scene_id=None)` — builds a role-specific, bounded read-only instruction packet from the actual SQLite project, screenplay revision and **accepted** Story Bible facts; hashes an immutable canonical snapshot.
2. `validate_crew_reply(task, reply)` — validates the expected JSON proposal shape and exact role/context SHA. It cannot authorize anything and always returns `unapproved_proposal` with no side-effects.
3. `check_crew_task_fresh(studio, task)` — recomputes the exact project/canon source digest and rejects stale AI output before a future director-review workflow.

Current film crew roles: director, script supervisor, cinematographer, acting coach, production designer, sound designer, editor, quality control. The same inference engine can be called with any one of these role packets; **no need to load a separate model for every crew member**.

Tests: `tests/test_crew_roles.py` verifies no unapproved facts injected as canon, role variation on shared approved facts, strict reply schema, source revisions, project isolation and no recorded side-effect claims. Workflow `nvp-stack02c3b14-conform.yml` now runs it on Windows and Linux.

## Deferred production-grade integrations

- Creator UI for switching/selecting crew role and reviewing proposed changes, with provenance of the actual model run.
- Dedicated deterministic contracts for camera recipes, blocking marks, performance cards (objectives, tactics, emotion/subtext, voice and full-body movement), lights, sound cues and editor cut suggestions; proposal → simulator/verifier → human approval.
- Scene-specific, scoped Bible retrieval and actor/prop continuity relations (avoid all-project context dumps).
- DAILIES-01 and virtual multicamera shooting, with retakes and explicit director overrides.
- Optional UE5 bridge alongside real Blender stages, with actual engine acknowledgments and test fixtures, not simulated "recording triggered".
- Native orchestrator/worker lifecycle and resource guard; the model runner cannot use a crew role to mint tool permissions.
- Harden packet provenance for *all* approved creative decisions, not just screenplay revision and typed accepted Bible facts. Current module only covers this first boundary.

## Current priority

Continue B14 and FILM-01 real edited high-bit-depth movie and audio pipeline. These recovered architecture concepts are incorporated into durable planning and tests without restarting NVP from its legacy prototype or delaying verified mastering.
