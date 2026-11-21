# NVP-SHOT-01 — Director-Controlled Shot-Specific OpenUSD Overrides

**Decision:** APPROVED ARCHITECTURAL DIRECTION — 2026-11-06.
**Implementation scope:** first shot-specific USD data layer and revisioned source/approval contract. Actual native acceptance, advanced look-at IK, cross-cut continuity analysis, full shot renderer and Windows UI remain OPEN.

## Filmmaking rule

**Continuity is primarily about characters, performance, story and audience perception—not enforcing one physically identical arrangement in every camera angle.** Directors and cinematographers may deliberately 'cheat' an actor's mark, eyeline, chair distance, prop angle, camera focal length, source light or visibility in *one shot* to make that shot visually and emotionally effective.

NVP must support this craft, not fight it. It needs a consistent canonical world and continuous performance **and** a non-destructive, explicitly versioned, per-shot **presentation reality**. The canonical world is never silently rewritten to fit a shot; the shot override never becomes a new independent actor or performance. A deliberate mismatch must remain documented, attributable, reversible, approval-gated and reviewable across cuts.

## Data authority and layer stack

1. **FilmIndex:** immutable actor/object/scene/performance/take revisions and approval evidence.
2. **Canonical OpenUSD world:** asset instances, geometry, topology, base staging, space conventions. One shared object identity.
3. **Temporal Ledger / performance:** events, acting, motion curves and exact film time. One continuous performance source.
4. **Frozen Digital Take:** exact references to scene/timeline sources, approved source freeze and sampled checkpoint evidence. Never edited to fix a single camera angle.
5. **SHOT-01 override:** per-shot time scope, source take SHA, target prim identity, director-authored offset, visibility, optional lens or light adjustments and a continuity decision. **A stronger USD opinions layer** lives outside the frozen Digital Take.
6. **Presentation/evaluation:** compose canonical take + one selected shot override when its time window and cut context match; evaluate with the same film tick; picture/audio are derived. No universal 'latest shot override' applies to other shots.

The first source may be a simple director-approved blocking edit, with static parent-space XYZ offsets layered on top of time-varying **original** translate values. USD standard xform-op composition must keep the underlying animated translation intact, rather than replacing its entire animated value with a frozen one. Object and performance identity are **references, not copies**.

The initial interface only supports existing trusted NVP-defined prim paths. It cannot create a new USD prim, swap an actor identity, inject arbitrary USD syntax, import file paths, mutate the original scene/take, or issue a worker authorization. More sophisticated constraints remain separate milestones.

## Supported first opinions

- **translation_offset** — additive three-component offset in the prim's parent coordinate space; keeps baseline time samples. An actor retains the original walking performance while the entire shot's blocking moves relative to it. This is intentionally not a replacement of the canonical actor position.
- **visibility** — shot-only hide/show decision for scenery, props, actor, light or other compatible imageable object, without removing the actual object.
- **camera_focal_length_mm** — shot-local native UsdGeom.Camera lens property where the scene uses native camera schemas; convert real millimeters according to scene meters-per-unit.
- **light_intensity** — shot-local native UsdLux lighting input where the scene supports native lighting schemas.
- **eyeline_target** — bounded explicit director eyeline intention as shot metadata, not a claim that an actual character's eye/neck mesh deformation or IK solver has run. A later rigging/acting pass must convert it into actual motion with separate acceptance.

Each opinion stores an intentional director rationale and the exact prim path. At most one opinion of each type per prim within the shot revision. All input values are finite, typed, role-checked, range-checked and size-bounded. Only exact NVP Film Time ticks within the shot are evaluated. Shot stages cannot bleed across another shot's cut.

## Continuity policy

Every shot records:

- a **shot ID**, its exact source Digital Take and immutable source SHA;
- a bounded **[start_tick, end_tick)** interval in authoritative Film Time;
- a director **purpose** (framing, eyeline, lighting, occlusion, emotion, continuity or other explicitly supported creative intent);
- a **continuity classification**: PRESERVE or INTENTIONAL_CHEAT;
- a short written reason for the staging choice, the adjusted paths and an exact opinion-layer digest;
- whether a trusted director approval verifier accepted this specific revision. The approval is **for the shot data change**, not for final picture/render/master release.

PRESERVE means the director expects existing cross-shot continuity to remain. INTENTIONAL_CHEAT means a visible staging mismatch may be a legitimate choice; the system may report it but **must not auto-correct it**. A future continuity inspector should compare the canonical and effective states at a cut, quantify discrepancies, consider camera-space visibility and call for review only when a policy requires it.

Intentional cheats must not affect physical scene ownership, NPC/actor identity, temporal event chronology, source performance or scene asset graph. No globally changed 'chair X' just because one coverage angle preferred it moved.

## Initial contract, limitations and follow-on

This milestone builds a bounded stored native OpenUSD shot layer plus data evaluation at exact film time. It is not an installed production shot editor, live camera display, mesh deformation, full AI acting, physical lighting approval, Houdini/Blender viewport integration, full rig IK, a conform/media index nor a new renderer.

Future work after real native acceptance:
1. Director UX: shot list, camera preview, gizmos for moving actors/props, A/B canonical/effective toggle, eyeline target handles, history, explicit continuity exception markers and undo via new revision.
2. Real character blocking/IK: translate/rotate poses, hips, feet planted on ground, gaze/neck/jaw, camera-aware posing with performance continuity and retargeting.
3. Smart continuity supervision: detect violations across **unapproved** cuts, explain uncertainty, respect director-marked exceptions, show original versus shot-local offsets, do not rewrite art.
4. Presenter integration: choose a frozen shot revision for every shot; composite override layer **only** in its approved interval, preserve source time and actor identity, and render actual low-fi proof then hi-fi presentation.
5. Acceptance: native OpenUSD pxr both Windows/Linux, exact SHA/reopen checks, changing Shot B must not change Shot A, scene/take must reproduce identically after override publication, explicit approval refusal, revisions, shot out-of-range refusal, and renderer frame evidence.

## Key principle

> **One underlying film world. One continuous performance. Many director-controlled cinematic views of that world. A shot may artfully depart from physical staging without becoming a different story or corrupting the original scene.**
