# NVP-SLATE-01 — Digital Slate, Parallel Takes, and Branch-Selectable Film Time

**Creator direction (2026-11-06):** NVP is a data-first film world, not one flattened video timeline. One scene may contain an original continuous Digital Take, any number of camera coverage presentations sharing that performance, and alternate/wild performances that branch at particular story moments. The editor must see which shots and takes are parallel and choose the active branch without discarding or overwriting the others.

**State:** The initial data contract and creator-directed architecture are recorded here. Full native editor, GPU/rendering, retiming/audio and multi-shot cut playback remain separately open.

## Mental model

Imagine a main horizontal line (original Take 1) running left-to-right in **green**. At a meaningful authored tick, an angled connector leads to alternate gray lines below it (Take 2, Take 3, wild take, or a coverage view). When the director selects a different branch for that editorial slot, the chosen branch turns green and the formerly selected path becomes gray. The choice is an **editorial read model**, not a physical fork operation or destruction of any data.

NVP can display this with a branching directed acyclic graph (DAG); **quantum entanglement/multiverse are useful creative analogies, not literal physics requirements**. A new performance is a new frozen Digital Take; a different camera angle may simply observe the *same* Digital Take through an alternate OpenUSD shot layer. These must have different identity semantics:

- **Scene**: script/location/story unit, with one stable scene identity and its underlying world/asset references.
- **Performance take**: one immutable, time-addressed performance (actor motion, dialogue, gesture, timing, events), frozen with FilmIndex source SHAs. A wild take is explicitly flagged and may be radically different.
- **Shot/coverage**: a camera/setup/presentation of a performance at a particular interval, optionally with director-authored shot-specific OpenUSD overrides. Multiple shots can see the same Take; they do not create a new performance.
- **Parallel group**: all candidates offered for the *same editorial decision or story beat* (e.g. the reaction close-up), even if they have different source durations. The group does not imply identical actor positions or timing.
- **Branch parent**: the original or alternative performance/view from which this candidate conceptually diverges. Store a parent identity and fork point in the **parent's Film Time**, not just a display connector.
- **Active edit**: versioned selections for the parallel groups, not a mutation of source Takes or shot layers. One selection per group; other parallel candidates remain browseable.
- **Sync/alignment**: distinct time coordinate domains. A 12-second wild take and an 8-second original are parallel creative alternatives, not automatically time-warped to match. Selection reports the duration difference and requires an explicit cut/ripple/retime decision later.

## Digital slate fields

Every captured view or performance candidate has:
1. Stable film project, scene label + scene ID, capture session and source Take ID/revision/SHA;
2. Shot/setup label and camera label (use an explicit e.g. A/B, not camera number baked into performance identity);
3. Take number and whether it is a **wild take**; script/scene revision reference and notes;
4. Intended Film Time source range and a stable **parallel_group** identifier;
5. Optional shot-specific OpenUSD opinion ID/revision/SHA for camera/actor/lighting cheats;
6. Parent branch ID, **parent-relative fork tick**, reason/intent and a continuity classification;
7. Date/time, operator/creator and sound-sync marker can be captured in a later full acquisition slate; missing metadata must be labeled unknown, never fabricated.

FilmIndex provides immutable revision custody and source SHA identities. OpenUSD stores scene representation and per-shot composition opinions. The Temporal Ledger stores authored performance actions in exact integer ticks. A separate digital-slate graph indexes their identities and relationships. **Do not store a fake slate by hiding it in arbitrary frame filenames.** No external FFMS2/video-frame indexing is needed.

## Selection constraints and continuity

NVP should support both a shot whose *composition* changes while the underlying actor performance stays exactly the same, and a wild performance whose events diverge. The main line is not always the winner: the selected editorial path alone turns green. An alternative must not accidentally overwrite the canonical world.

A branch may be local to only one scene/shot/story beat. The continuation after the branch remains the original unless separately selected. Conceptually this is a **cut composition graph**: the final editorial sequence may consist of sections taken from several frozen Take branches. It is not one newly forged continuous performance. A renderer needs an explicit join/cut transition record between takes and must not blend incompatible world states without permission.

A continuity inspector later compares joins, character identity, scene geography, performance timing, eyelines and props. It should flag questionable jumps but respect explicit director tags for intentional nonphysical shot staging and intentional narrative alternatives. The editor—not a continuity algorithm—chooses which branch appears in the final film.

## Initial non-rendering implementation

The first native metadata contract uses **two FilmIndex revisioned documents**, independent of OpenUSD-heavy computation:

- A slate **branch graph** (`nvp.slate.branch_graph.v1`) stores topologically ordered nodes, each pinned to one immutable frozen Take SHA, optional shot-override revision and exact scene identity, plus slate fields, parallel group and lineage. It cannot create/destroy a Take.
- A slate **selection edit** (`nvp.slate.branch_selection.v1`) stores one chosen branch per parallel group, with references to the exact branch graph revision/SHA, a creator policy receipt and a time-alignment warning for variable-length alternatives. Switching selection creates a new immutable edit revision. An editor can reopen old cuts and compare them side-by-side.

Dependencies are FilmIndex-bound rather than implicit "latest" references. An alternate scene/take from another project must fail. Source lengths and the parent-relative fork must be validated without pretending source clocks are interchangeable.

The first graph is purely structured metadata and may be manipulated using native film tables before any desktop graph display exists. Actual interactive green/gray branch visualization, side-by-side previews, camera/audio sync, beat-level timing, cut joining, continuity automation, and final render are follow-ons.

## Acceptance criteria

- Register Original Take 1, Camera A/B coverage of Take 1, and an alternate Take 2 / wild Take 3 with distinct frozen source SHA.
- Same-identity scene rules: coverage of Take 1 cannot quietly become Take 2; fork ancestry is explicit and acyclic.
- Query a parallel group with all candidate choices and one selected green candidate. Change the selected branch and old one turns gray *in the read model*, while the older edit is still restorable by revision.
- Reopen after Studio restart and retrieve the identical source Take/Shot SHAs; reject cross-project, absent, unknown and malformed branch links.
- Different duration alternatives report a timing mismatch; they are not silently stretched or forced to match.
- Source scene and Take remain unchanged when selections change; approval for choice is distinct from any final presentation/master approval.
- CI on Python 3.11/3.13 Windows/Linux for ledger/metadata tests; separate native pxr tests later for actual alternate 3D presentations.

**Core principle:** One persistent film world with parallel recorded performances and multiple shot presentations. The director's selected composition changes the film we see, not the reality or history of the unselected data.
