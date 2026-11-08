# FILM03-02 — Canonical ActorID and source-linked Production Bible

**Source implementation submitted 2026-11-08; native CI and installed desktop
acceptance must be obtained before calling this complete.**

## One stable ActorID for every castable character

Every castable NVP character has ONE ActorID: the existing project-scoped
StoryBible bible_entities.id. This applies equally to a donut, box, sphere,
person, robot, car, animated prop or other object when cast as a character.
ActorID survives names/aliases, changed screenplay, recasting, different
costume, voice, new meshes, different textures, additional source Takes
and editor revisions. An ordinary prop is not silently assigned an ActorID:
the director explicitly casts that object as a StoryBible character.

No duplicate ActorID database or arbitrary label-matching is allowed.

## Production-bible source relationships

backend/nvp_production_bible_actors.py implements a versioned source-backed
actor relationship registry. Every entry has: ActorID, durable link ID,
link revision, StoryBible revision, typed role, target source family and
exact ID/revision, source SHA, frozen source snapshot, OpenUSD actor path
where applicable, production scope, director note, status and timestamp.

| Relationship | Real verified source |
| --- | --- |
| scene | Existing Studio screenplay scene at exact revision/SHA or FilmIndex OpenUSD scene |
| dialogue | FilmIndex typed dialogue/script source |
| performance | FilmIndex immutable actor performance |
| voice | FilmIndex recorded PCM audio source and exact revision |
| wardrobe | StoryBible prop, FilmIndex asset or verified original GLB/rigged GLB |
| prop | StoryBible prop, FilmIndex source prop/asset, verified static GLB |
| model and mesh | FilmIndex OpenUSD asset, registered static/rigged GLB source byte SHA |
| texture | FilmIndex asset source, or verified original PNG texture blob by SHA |
| rig | FilmIndex asset or registered rigged GLB |
| take | Frozen FilmIndex Digital Take |
| actor_prim | Exactly verified real OpenUSD actor prim within frozen Take |

Asset source verification must check the project identity. GLB paths
are derived from project-owned content-addressed original blobs and SHA
checked, not from unreviewed filenames or external URLs. Original PNG
texture SHA references require existing stored bytes and actual PNG decode.
A FilmIndex generic asset role does not by itself prove the intended
subtype; exact texture and GLB families verify the original bytes.
Associating an asset is NOT a redistribution license or finished render.

The director can add an association, revise the same link to another exact
source version, or retire it with an explicit reason. **Every mutation
APPENDS a row; previous links and source material remain unchanged.**
Optimistic expected actor and relationship revision checks prohibit
silent concurrent editing. A source is revalidated under the same durable
SQLite write lease used for committing the source relation.

## Source-cast completeness

A scene is not actor-complete unless EVERY OpenUSD prim authored as role
actor within the frozen Take is tied to exactly one canonical StoryBible
ActorID. The read-only casting_coverage function reports uncast,
ambiguously cast and valid actor paths. require_complete_cast fails closed
if any actor identity is missing or ambiguous.

The already-rendering FILM02 Cycles fixture is not retroactively rewritten
or claimed fully cast. This new proof must be connected to later final
source acceptance before production-grade ActorID completeness is granted.

## Installed editor integration

frontend/src/Film03ActorBiblePanel.jsx is embedded in NVP's existing Story
Bible screen and exposes stable ActorID, source-verified resource links,
active history and append-only revision/retirement controls, plus a
missing-actor casting audit. Wardrobe, prop, model, mesh, texture,
dialogue, voice, Take and scene are shown as selectable link categories.

frontend/src/Film03ScriptChangeImpactPanel.jsx appears in Screenplay and
Story Bible screens. It reads existing Studio screenplay history against
FILM03 source snapshots and reports changed lines, prior performance
references, StoryBible continuity warnings and indexed downstream source
consumers, without an automatic mutation or rerecording.

For a director to CREATE a new immutable script source snapshot, the UI
requires installed NVP's first-party pywebview host. The native method
film03_publish_script_snapshot in backend/nvp_wo6_desktop_bridge.py
checks exact Studio script revision/SHA, exact FilmIndex manifest head
and the creator's OS confirmation dialog. It then invokes FILM03-01's
trusted creator-action verifier, which checks the exact approval scope
again inside the FilmIndex/Studio transaction. Denial creates no source,
and stale revisions are refused before prompting. This does not authorize
any Blender process, AI model, voice generator, or recorded audio mutation.
No untrusted HTTP endpoint can publish a script source with an invented
approval flag. Read-only preview remains available without native consent.

backend/nvp_api.py serves local actor catalog, read-only source and
casting reports, explicit-creator-metadata link and retire endpoints,
and a separate read-only script-impact endpoint. It never grants a
native worker execution token or starts a model on behalf of this UI.

## Native acceptance and open gates

tests/test_nvp_film03_actor_bible.py uses the real original 30-second
OpenUSD FILM02 source plus actual Studio and StoryBible data. It
checks stable ActorIDs for Donut/Box/Sphere/ServiceCraft, authentic
OpenUSD scene actor prim, script changes, non-destructive wardrobe/mesh/
texture/voice links, source SHA, revision conflicts, asset cross-project
rejection, SQLite restart and full-cast proof.

Frontend Vitest component tests require actual director click for
POSTing an existing verified source; script impact must stay GET only.
CI workflow nvp-film03-02-actorid-bible-ui.yml checks native Windows and
Linux source tests plus Node/React desktop bundle and regression tests.

**OPEN:** full exact-head native CI; real installed NVP Windows/Linux
acceptance; native host authorization for high-trust operations; integration
of complete-cast into every later Take/film approval; richer garments,
rig and texture role schemas, legal source review, true voice capture and
spatial performance synchronization, visual director review and final DCP.
