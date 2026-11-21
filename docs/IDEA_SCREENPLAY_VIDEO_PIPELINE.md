> **Host boundary:** Production NVP is Lu's optional Film/NVP DLC Workspace.
> NVP owns film-specific project and scene data; Lu owns inference and
> authorized tool/worker execution. The existing local AI server is a
> temporary test harness, not a separate production runtime.

# NVP idea → screenplay ↔ video contract (2026-11-02)

## Product identity
NVP is a **personal movie-making pipeline** for anyone with an idea. Beginners get
plain-language guidance; experienced writers and studio artists can import an
existing script and take over individual decisions. No user is required to
learn studio jargon before expressing what they want.

**The idea is the entry point, not an input to discard.** Story, screenplay,
characters, locations, physical 3D scene, performance, shots, audio, edit,
and rendered video are related representations of the same creative project.

## Two equal starts
1. **Start with an idea.** Write, speak (later), or import rough notes. The
   writing partner can suggest a logline, synopsis, beat sheet, treatment,
   and proper scene-formatted screenplay. Every step may be skipped.
2. **I already have a script.** Import/paste Fountain or text in the current
   prototype. Preserve the existing words, scene order, and authorship.
   FDX/PDF extraction and format validation require later dedicated adapters.

An existing script can be *developed* by AI (pacing, character objectives,
dialogue, continuity) only as separate reviewable proposals. Do not
automatically rewrite the author's work.

## Writing is part of filmmaking, not a disconnected tool
- Each scene will have a stable identity and links between narrative events,
  scripted beats, lines, character/object states, shot plans and media takes.
- **Script → visuals:** changed lines/blocking mark affected performances, shots
  and clips as potentially stale. They are not silently deleted.
- **Visuals → script:** on-screen improvisations, changed blocking or editor notes
  can generate *suggested* script amendments or continuity notes.
- The user's approved choices are pinned. AI may propose alternatives but must
  not overwrite approved work without explicit review.
- An existing video cannot be assumed perfectly reconstructible as a script.
  Video-to-script proposals need appropriate recognition models and review.

## AI development loop
Creator idea → optional clarifying conversation → alternate loglines →
synopsis → beats → treatment → screenplay scenes → producer's scene bible →
physical scene plan → acting and camera plan → preview → edited movie.

This is not a rigid wizard. The user can write or edit at any point, and can
enter at the screenplay or scene level. The AI should ask only clarifications
that materially affect a decision.

A proper screenplay uses scene headings, action descriptions, speaker cues,
dialogue and parentheticals. AI drafts must be critic-reviewed for character
voice, narrative causality, continuity, clarity, and filmability.

## First concrete backend slice
A local, model-optional development ledger stores draft stages, provenance,
review status and optimistic revision checks. With a local compatible LLM
server configured it can request creative drafts without cloud services.
There is **no built-in local model in this branch**. No film generation exists yet.

Draft output never updates the screenplay on its own. The explicit
"Use as screenplay" decision is required. It replaces the screenplay
at the *current* revision, and must warn users if it already contains work.
The previous screenplay revision should eventually have snapshot-based recovery;
current shot records are not destroyed when scenes change.

## Acceptance tests for later film workflow
- Start from a one-sentence idea, approve a generated scene, revise a line,
  and see only dependent performance/audio/shot items flagged for review.
- Import a real screenplay, change no words, and produce camera coverage.
- Edit a clip's blocking, propose a script revision, and reject it without
  changing the original screenplay.
- Move to a different machine with no cloud login; open the project and replay
  exactly which creative decisions were approved.
