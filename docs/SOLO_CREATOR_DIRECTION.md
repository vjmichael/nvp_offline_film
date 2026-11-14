# NVP — The Personal Movie-Making Pipeline

## Who NVP is for
NVP serves **one person with an idea** who might not know screenwriting, 3D modeling,
cinematography, animation, sound production, or editing. It is not a studio management
platform and not a collection of complex tools that the creator must master.
The creator directs with plain language; NVP offers small, explainable choices,
performs technical production work, and retains the creator's authority.

## Product contract
1. **Idea first, expertise optional:** the user can begin with a few sentences.
2. **Offline first:** core creation does not require cloud APIs or subscriptions.
3. **GPU vendor neutral:** AMD, NVIDIA and CPU fallbacks; no mandatory CUDA startup.
4. **Film, not random clips:** persistent characters, sets, wardrobe, props, timeline,
   world continuity and scene geography across the whole film.
5. **Director owns decisions:** proposed AI changes cannot overwrite accepted edits.
6. **No fake completion:** show exactly which stages are operational, which are simulated,
   which require external dependencies, and which are future work.
7. **Safe iterative production:** changes have scopes, checkpoints, rollback and receipts.
8. **Simple UI by default:** a guided flow; expert controls only when requested.
9. **One Lu DLC installation eventually:** the user installs Lu and enables the optional NVP Workspace through Lu's add-on lifecycle. NVP must not require a separate model server, desktop installer, Python, Node, CUDA or Docker setup for normal use.

## Intended experience
Idea -> guided story/storyboard -> screenplay -> characters and locations -> blocking and
performance -> 3D production -> camera coverage -> editorial timeline -> audio / light
/ effects -> review -> playable exported movie.

This is a destination, **not** the current implementation state.

## Architecture
- **Local project ledger:** stable IDs for movie, scene, character, set, prop, shot,
  performance, take and editorial decision. Versioned world and production state.
- **Creative interpretation:** local LLM proposes typed scene, action, performance and
  shot records; never emits arbitrary executable code as if it were a camera action.
- **Deterministic production:** scene graph, anchors, collision, animation constraints,
  camera geometry, validated render and edit operations.
- **Review:** previewable proposals; human accepted changes are pinned and must survive
  regeneration and reload.
- **Backends:** Blender-first candidate for open rendering, optional Unreal, optional
  generative video. Runtime capability probing avoids vendor lock-in.
- **Lu integration — product requirement:** NVP is the Film/NVP DLC Workspace hosted by Lu, not an independent consumer application. Lu owns the loaded models, inference runtime, registration, scoped permissions, native Protobuf IPC, worker admission and effect journal. The existing Python/React app is a temporary development harness, not the production launch path.
- **GitHub:** repository and milestone record, not the production runner or development hub.

## Foundation build (this branch)
Real, tested: local SQLite project persistence, simple Fountain-style heading/cue parsing,
character and location summaries, editable deterministic camera-coverage suggestions,
approval preservation, conflict detection, and a beginner-friendly web UI.
Not implemented: AI scriptwriting, semantic story reasoning, 3D generation,
actor animation, TTS, audio alignment, rendering, editing, packaging.
The parser does not correctly interpret all screenplay styles or PDF/FDX.
Scene IDs are derived from headings and occurrence; renaming headings preserves old
shot rows as archived, but automatic reconciliation is future work.

## Next acceptance milestone
Produce and edit a 60–90 second two-person scene in one interior with durable 3D
actors, 6–8 shots, spoken dialogue, basic performance and exportable 1080p/24-fps video.
Do not claim success without independently replaying the actual generated media.


## Idea/script entry and AI writing status (Nov 2)
The creator can enter with a free-form idea **or** an existing screenplay.
The new story-development UI offers logline, synopsis, beat sheet, treatment
and editable screenplay drafts. A loopback-only LLM adapter can draft those
stages when a separate local model server is configured, but NVP does not
yet install or load the model itself.

The screenplay and approved camera plans now retain revision history/approval
records. Restoration is accessible in the screenplay UI. Script-to-video and
video-to-script dependency tracking remain **design goals**, not functioning
production capabilities. The new backend has been exercised with local
fake-model/API fixtures; a real local LLM and the frontend installer still
require integration testing.
