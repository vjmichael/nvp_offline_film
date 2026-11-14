# NVP-FLOW-01 — Filmmaker-facing workflow and product contract

**Decision:** November 10, 2026 (America/Phoenix)  
**Status:** Creator-approved design specification; **not** a claim of implementation or physical acceptance.  
**Canonical implementation target:** DATA-AV-01 [PR #74](https://github.com/vjmichael/nvp_offline_film/pull/74), following exact-head compatibility reconciliation.  
**Dependent host capability:** Lu Film Workspace [#152](https://github.com/vjmichael/nvp_offline_film/issues/152).  
**Related direction:** [NVP-FLOW-01 issue #150](https://github.com/vjmichael/nvp_offline_film/issues/150).  
**Execution plan:** [NVP_FILMMAKER_WORKFLOW_TASK_PLAN.md](NVP_FILMMAKER_WORKFLOW_TASK_PLAN.md).

## 1. Product purpose

NVP helps a human director **make a film**, not operate a collection of engineering subsystems. The user supplies ideas and creative decisions; Lu's AI collaborates with the user; NVP's internal tools construct, evaluate, protect, render, and deliver film data behind the scenes.

The user-facing top-level journey is exactly:

> **Script (optional) → Set Up Scenes → Film Scenes → Edit Film → Export Film**

**Set Up Scenes is a core NVP activity**, not a small submenu. Creating a visible, navigable low-poly film world precedes filming it.

The only filmmaker-facing data is creative production information: movies, scenes, locations, historical period, season, weather, time, characters/actors, dialogue, props, costumes, actions, director notes, camera preview/framing, performances, Takes, editing decisions, and film output. The Production Bible presents these in human language.

**No film-user access to the engineering subsystem UI.** FilmIndex tables, schemas, worker journals, process managers, IPC messages, memory allocators, GGUF/runtime internals, cgroup/Job Object controls, OpenUSD implementation parameters, debug logs, and codec commands are *not* creative navigation, including for advanced directors. Private support/developer diagnostics remain distinct from the filmmaker application. Advanced *filmmaking* options (lenses, lights, rigs, movement, color, sound, delivery profiles) are welcome.

## 2. Home, projects, and security

- Opening NVP presents a **chat-first home** with a left project sidebar. Project titles and optionally non-sensitive lock indicators are visible. The home can be hosted inside Lu when its Workspace integration is verified.
- Welcome prompt: **“Would you like to make a new movie or resume working on a movie?”** with **New Movie** and **Resume Working**. Resuming returns to the last meaningful filmmaking step, not an engineering screen.
- Projects have **Locked** and **Unlocked** states. Locked project data and thumbnails, scene previews, film assets, model context, native tool access and production files must be protected by real project-scope access enforcement. A lock icon alone is not security. Implement key management/encryption-at-rest or a proven OS-bound access policy, idle relock, multi-project isolation and recovery as independently tested safeguards. The director controls unlock; unlocking one project does not authorize another.
- New Movie shows an upload area and an idea text box with a **Next** button at bottom right. An optional, dismissible prompt asks **“Do you have a script or just an idea?”** with **I have a script** / **Just an idea**. Never require a lengthy wizard.
- Display only human-friendly AI status: **Connected/Ready**, **Model not loaded**, **Busy**, **Unavailable**, **Timed out**, **Retry**. NVP must not independently load a second large model when Lu owns an active GGUF. Never equate timeout with no model or GPU headroom with loaded-model identity.
- When AI is unavailable, preserve manual screenplay/scene authoring and unmodified project data. Explain simply what creative assistance is unavailable; do not expose an HTTP endpoint/config console.

## 3. Script is optional and does not define a performance

### Path A — Existing screenplay

1. The director uploads/pastes the actual script. Preserve the original input and revision provenance.
2. NVP extracts **scene boundaries and headers**; proposes location, interior/exterior, time of day and any setting supplied. Link lines to each SceneID.
3. NVP populates a **character roster** and assigns stable ActorIDs only to genuinely identified performers. Dialogue is associated with the script's character cues/ActorIDs when unambiguous; ambiguity triggers a small director question, not a fabricated identity.
4. NVP generates **actual low-poly/lo-fi OpenUSD scene drafts** for the extracted scenes. Place source-grounded characters, props and setting placeholders; missing details remain visibly proposed/unresolved, not asserted as facts. A scene *card* or static text inventory alone is not a generated 3D scene.
5. The director opens any scene, sees the live 3D stage and reviews/changes planning details, moving through Scene01 ... SceneN at their own pace.

A script **does not** tell NVP what performances, blocking, gesture timings, expressions, or complete physical actions should be frozen. Spoken dialogue is not a substitute for directing an actor.

### Path B — Only an idea

1. The director types a premise; create **one initial scene** with a visible draft stage. Do not invent a completed screenplay.
2. The AI asks short, relevant follow-up questions, such as **“What happens in this scene?”**; **“Where does this take place?”**; **“What time of year/day?”**; **“Does weather matter?”**; **“Are there any actors or animals?”**; **“What do they do?”**; **“Does anyone speak? What do they say?”**
3. NVP proposes a scene, objects and events, and updates a versioned screenplay/Production Bible only after the director has reviewed the proposal.
4. The director can explicitly **Add next scene**; proceed incrementally from Scene01 to SceneN. No screenplay is mandatory for filming a valid scene.

### Missing details and inclusivity of subject matter

- Ask only for details relevant to the scene: place, era, season, time of day, local geography, weather (rain, snow, fog, wind), props, animals/humans, actions, dialogue, and continuity.
- **No character or dialogue requirement.** Nature documentaries, scenic landscapes, still-life, experimental/abstract films, and actor-free sequences are valid. A scene may have moving clouds, light, water or environment events instead of performers.
- Maintain provenance categories: **script-derived fact**, **creator-specified fact**, **AI proposal (unapproved)**, **approved production fact**, and **unresolved question**. Do not silently fill story facts with AI guesses.
- Missing optional details may remain unknown. Do not ask redundant questions when the script or previous approved Production Bible already answers them.

## 4. Set Up Scenes — interactive 3D world planning

**Director-facing scene workspace**: a sizable live 3D viewport, scene name, editable human-readable scene information, simple **Ask AI**, and direct manipulation controls. Contextual popup conversations occupy only the space they need; there is no permanently docked full-width bottom chat consuming the viewport.

A scene contains (as applicable):
- SceneID, film/story beat and relevant script lines
- location, era/season/daylight/weather, set assets and environmental motion
- performers (ActorID), relative placement, wardrobe/appearance, props, dialogue associations
- planned actions, interactions, blocking, spatial sound sources and creative constraints
- draft/review/approved planning status, revision provenance and continuity with adjoining scenes

**Right-click interaction**: selecting a performer opens a menu with **Give Note**, **Change Wardrobe**, **Inspect Character** and other contextual creative options.

- **Give Note** opens an anchored AI conversation for a particular SceneID + ActorID + revision + source-time range (when known). It captures movement modes/path (walk, run, jog, crawl), emotion, expression, acting beat, physical interaction, pacing, or dialogue delivery. The AI proposes and previews a change. A note is not automatically a recorded action, a Take, or permission to operate native tools.
- **Change Wardrobe** creates a reviewed, versioned wardrobe/appearance binding for the same ActorID, linked consistently to OpenUSD and the Production Bible. Preserve earlier outfits and previously frozen Takes; changing a current planning scene must not rewrite old footage.
- For scenes without performers, equivalent context controls apply to **locations, props, lights, weather and environmental actions**, not a fake ActorID.

## 5. Film Scenes — direct a performance and freeze data

The filmmaker enters **Production** only after choosing a filmable scene (a complete screenplay is optional).

- The AI suggests **three camera viewpoints and three familiar shot sizes**—wide, medium, close-up—as a nonbinding starting point. These do **not** require nine redundant roll renders or separate performances. The director can preview combinations, set custom cameras, lighting, lens and movement, or choose to defer framing.
- The filmmaker directs actors and non-actor environmental events, moves objects, adjusts interactions, refines timing/performance, reviews original sound and chooses retakes. AI accelerates tedious work while source updates require explicit human authority.
- The authoritative capture is **original OpenUSD world state + spatial/performance events + source PCM/audio and exact Film Time**, sealed as an immutable Digital Take with source identities and verified hashes. After freeze, alterations produce new approved versions/retakes; never overwrite source.
- **A frozen Take is not a locked 2D camera angle.** The same recorded performance/world can be viewed from new cameras at post-production time. Default framing during filming is only a preview, aesthetic choice and optional presentation decision. A director can film first and choose exact angles later.

**Production ends with one or more approved, frozen Takes**, not an automatically edited or exported film.

## 6. Edit Film — separate Post-Production window

**All editorial editing belongs here.** This workspace has a purpose-built film timeline, selected Takes, shot/camera coverage, non-destructive cutting, transitions, sound editing/mixing, color grading, and look evaluation.

- The director may reframe the same original Take from a previously unused viewpoint without refilming the original performance, provided the camera/view is physically valid for the recorded 3D world.
- Edits, grades, sound treatments, camera decisions and render settings are **versioned derivative decisions**. They refer back to original frozen Takes rather than mutating their scene, ActorID, PCM or performance records.
- Advanced film options remain discoverable here, not in a wall of technical subsystem controls.

## 7. Export Film — a verified derivative presentation

- Export creates a creator-approved **Presentation Package** with selected picture views, sound and editorial decisions, a specified presentation cadence/profile, and verified source lineage.
- Output may include an independently reopenable movie/master or, later, SMPTE DCP Bv2.1, but **a final delivery format is not the original Film World**.
- All active NVP capture, editing, rendering, playback and export workflows obey the creator's **zero-FFmpeg rule**, including no FFmpeg library/executable/optional fallback.
- Do not represent a 30-second pilot, 2K/4K feature, spatial mix or DCP as accepted until real output and independent viewing/decoding evidence exist.

## 8. Lu/NVP division of responsibility

**Lu owns:** local GGUF discovery/loading/runtime/session, verifiable readiness, model inference and cancellation, resource arbitration, workspace identity, host-side policy, trusted tool authorization and worker supervision/recovery.

**NVP owns:** filmmaker scene/story/roster semantics, Production Bible, stable ActorID, OpenUSD/FilmIndex source identity, exact Film Time, original performance/PCM, native filming, editing/presentation decisions and film-specific output verification.

The AI model **proposes, asks questions, and operates only explicitly authorized typed tools**; it cannot declare approval, overwrite a Take, run arbitrary workers or unlock projects. NVP's model-assisted experience must work with the already-loaded Lu model and avoid loading a duplicate GGUF.

## 9. User-facing state transitions

```text
Launch NVP / Film Workspace
  └─> Project list (locked/unlocked) + New Movie / Resume Working
          ├─> New Movie ──> (Script upload OR idea text; optional prompt)
          │                   └─> Set Up Scenes ──> Film Scenes
          │                                            └─> Edit Film (separate window)
          │                                                   └─> Export Film
          └─> Resume ──> last approved creative step (after unlock)
```

At every step, the user sees **what has been created, what is only proposed, and what action is available next**. An AI error does not discard the current scene or masquerade as a successful operation.

## 10. Product acceptance examples

1. **With script:** `INT. KITCHEN — NIGHT` + ALEX/SAM dialogue produces a correct scene list, speaker-linked dialogue, actor roster and visible low-poly kitchen; missing physical acting remains explicitly undirected.
2. **No script:** “A mountain valley covered in morning fog” produces an actor-free visible scene. AI may ask about season, wind, weather and action, but never requires a human or dialogue.
3. **Note:** right-click ALEX → Give Note (“walk to the window, pause, look worried”) creates a previewable proposal tied to the *correct* ActorID. Refusal leaves approved source unchanged.
4. **Wardrobe:** an approved wardrobe revision affects only its applicable scene/time and does not change the frozen Take SHA.
5. **Camera:** film one action once; choose a different valid angle in Edit Film and see distinct derived presentation views without altering the original Take SHA.
6. **Model unavailable:** human-friendly readiness/error/retry shown; manual scene editing remains usable; no claimed generation without model evidence.
7. **Security:** a locked project's content and tools deny access even when the UI is bypassed, including after restart.
8. **Export:** independently reopen a real, zero-FFmpeg presentation with source lineage, continuous picture/audio where specified, and no hidden original-data replacement.

## 11. Provenance and implementation status

This is a **workflow contract only**. Existing NVP has scoped source-authoring, scene inventory and Blender/Cycles native evidence, but it does **not** yet have an accepted complete director path, physical Lu-hosted Qwen3.8-27B inference, verified actor/context AI notes, real general-purpose scene generation, or a finished 30-second production. Those gaps are tracked in the [implementation plan](NVP_FILMMAKER_WORKFLOW_TASK_PLAN.md).

Do not merge this documentation branch into the moving canonical PR #74 until any reference drift is reviewed. No prior CI result is inherited by a new integrated source head.
