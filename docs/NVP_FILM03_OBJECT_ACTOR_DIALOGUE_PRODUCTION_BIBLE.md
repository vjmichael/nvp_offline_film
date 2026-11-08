# NVP FILM03-01 — Script-Linked Object-Actor Dialogue, Takes and Production Bible

**Status:** First-party source implementation and native Windows/Linux acceptance
submitted 2026-11-08. Full installed editor workflow, recorded dialogue voice,
spatial playback, human creative approval and film release remain OPEN.

## Creator's non-destructive rule

> A screenplay revision never erases an earlier script, original voice file,
> object-actor performance, OpenUSD scene or frozen Digital Take. The scene
> uses only the creator-approved dialogue version. Bible canon/identity is
> pinned to each performance.

NVP's existing Studio screenplay, revision history and restore are
authoritative (backend/nvp_studio.py). The existing StoryBible manages
character, prop, location and event canon, scene linkage and changes
(backend/nvp_story_bible.py). FILM03 builds on those; it does NOT introduce
a second competing screenplay database. The FilmIndex index preserves
immutable revision dependencies and the originally frozen Digital Take.

### Three separate version histories

1. **Script.** ObjectActorDialogue.publish_script_snapshot reads the exact
   existing Studio screenplay revision and SHA with a transactional source
   guard. FilmIndex stores an immutable dialogue-source manifest. Every
   scene retains its Studio scene ID, exact scene source SHA, cue, text,
   content SHA and line identity. Older source snapshots remain available.
2. **Performance.** Each object-actor line delivery is a NEW single-commit
   FilmIndex performance, bound to exact script revision/line identity/text
   SHA, approved StoryBible character/scene revision, real OpenUSD actor
   prim and original frozen Digital Take. Performance has exact start/end
   Film Time, delivery direction and optional already-recorded mono PCM16
   voice source ID/revision/SHA. No audio is synthesized or approved by this
   metadata operation. StoryBible identity, approved canon fact SHA and
   scene-link version are captured as provenance of the performance.
3. **Selection.** publish_scene_dialogue appends a new derived TemporalLedger
   revision and a new FilmIndex presentation selection of actor performances
   with original source Take SHA and exact script selection. ALL original
   Take sound/actions are preserved. An old source Take, original OpenUSD
   layers, existing audio and earlier selection/timeline revisions remain
   immutable. A dialogue metadata event is not automatically a playable
   recorded voice; a separately verified recorded voice source is required
   before adding a sound event.

### After the screenplay changes

- Studio saves the revision, preserving prior text in its existing history.
- A read-only source-impact preview finds changed/removed/new lines, earlier
  performances now differing from the current line, indexed FilmIndex
  downstream consumers, plus the StoryBible's stale scene links and pending
  canon decisions. It does not render, delete, re-record or auto-approve.
- Unchanged lines retain ID across surrounding edits; a one-to-one same
  speaker rewrite retains ID but updates the content SHA, making the old
  performance historical and visibly in need of director review.
- Ambiguous multi-line edits never guess ancestry. A creator can authorize
  exact same-scene and same-speaker old/new line mappings; the reconciliation
  is a NEW immutable dialogue-source revision with the old snapshots intact.
- Selecting an older delivery with changed script words is blocked by
  default. The director may explicitly document a reason to retain it, or
  record a new source-bound delivery, refresh the StoryBible scene link and
  publish a NEW scene dialogue version. Original visual Take remains intact.
- The existing WO6-03 film crew scene reader can now accept an optional
  exact dialogue-selection ID+revision and sees the actual selected speaker,
  line, object prim, Bible character ID, recorded-voice presence, and
  screenplay drift. It never silently picks the newest script, and read
  paths do not create StoryBible tables.

### Original nonhuman cast

The native regression fixture uses the existing genuinely source-authored
RelayRekindleTake and original OpenUSD objects, without re-rendering it:

| Writer's character | Source OpenUSD actor | Test screenplay dialogue |
| --- | --- | --- |
| DONUT | /World/Engineer | The relay has been silent for twenty years. |
| BOX | /World/CrossingBox | I think I found the problem. |
| SPHERE | /World/PassingSphere | Stand aside. I've got this. |

The test revises the donut's line to: The relay is coming back online.
It proves creator-explicit retention of the earlier delivery and separately
publishing a new delivery, with the old Take and first script still readable.

**These are test-authored screenplay words and typed dialogue source records,
NOT captured speaking voices.** They have not been silently added to the
original 30-second movie, which remains controlled under FILM02.

### Native acceptance and next groups

- Code: backend/nvp_film03_object_dialogue.py; read-only WO6-03
  integration: backend/nvp_wo6_scene_context.py.
- Native regression: tests/test_nvp_film03_object_dialogue.py, covering real
  Studio screenplay edits and revision history, StoryBible identity and scene
  linkage, actual frozen OpenUSD actor verification, original TemporalLedger
  events, revised or retained performance, versioned scene selections,
  ambiguous-line director reconciliation, authorization refusal and AI
  scene-context drift detection.
- Real OS workflow: .github/workflows/nvp-film03-object-actor-dialogue.yml
  (Windows 2025/Ubuntu 24.04, Python 3.11, actual native OpenUSD source
  plus regression tests). Status must come from real exact-head CI,
  not from merely writing the workflow.

**Not yet closed:** final exact-head native results, actual UI/script editor
impact preview and old/new comparison, voice recording/retake operations,
speaker-specific spatial audio and timing, installed application end-to-end,
director viewing/listening/approval, legal package and DCP release.

**FILM03-02** should connect the source-impact preview and explicit script
reconciliation controls to the installed NVP screenplay/Take editor.
**FILM03-03** should record real creator-selected voice performances with
durable original PCM provenance and multiple Takes.
**FILM03-04** should use existing native spatial-audio/listener machinery
for position-aware dialogue and test true original sound/picture continuity.
**FILM03-05** should require installed-app Windows/Linux acceptance.

The full NVP production bible must ultimately connect script, canon,
actors, sets, props, camera/lens, director intentions, sound, dialogue,
visual Takes, edits, approvals, and source-forward DCP relationships.
FILM03-01 closes the SCRIPT → BIBLE CHARACTER → PERFORMANCE → SCENE
DIALOGUE chain, without claiming the entire production bible is finished.
