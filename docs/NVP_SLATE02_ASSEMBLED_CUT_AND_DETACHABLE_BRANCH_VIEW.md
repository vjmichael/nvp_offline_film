# SLATE-02 — Committed Cut vs Inspection and Assembled Mixed-Take Editorial

**Creator decision (2026-11-06):** A director may record 50–60+ alternate Takes. The branching Take timeline must depict **straight dashed parent–child connectors** (not diagonal links), allow scrolling and a resizable separate window, and distinguish inspection from active editorial selection. Clicking a Take must NOT activate it. The editor explicitly chooses **Make Active**.

The active film may use a short portion of Wild Take 3 followed by Camera B from *Alternative Take 2*. That is not one source performance or a simple one-branch-per-group choice. It is a non-destructive **assembled cut of source references**.

## Data model and functionality

- The original SLATE-01 FilmIndex branch graph retains the complete source history (Scene, Take, camera setup, wild flag, parent fork, parallel group, frozen Take SHA and optional SHOT-01 OpenUSD SHA). The capacity is raised from 64 to 256 branch nodes per graph, with existing FilmIndex's separate 128-source-dependency budget. Large shoots may need paged/normally indexed metadata beyond those budgets in future.
- A new versioned **assembled editorial edit** uses format `nvp.slate.sequence_assembly.v1`. It stores an ordered list of source segments, each with unique instance ID, exact branch/Take/shot IDs and SHAs, source Film Time in/out, *destination* assembled time interval, and hard-cut join/continuity markers.
- `SlateSequenceAssembly.preview` validates a temporary sequence and may indicate a selected take for inspection. It never changes the active edit, publishes a FilmIndex revision, or grants a render authorization. The committed cut's green ranges are returned separately.
- `edit_draft` implements purely local Insert Before, Insert After, Replace, Trim, Move Before, Move After and Remove operations. Copy/paste is an additional source **reference with a new unique segment ID**, not a copy of USD actors or filmed bytes.
- `commit` requires a creator-authorized host action for the **exact** assembled source SHA, source graph SHA, duration and optimistic edit revision; FilmIndex then creates a new immutable edit. The previous revision survives and can be compared/reopened. An uncommitted focus remains grey with a separate inspection highlight.
- An assembled cut may use parts of **several branches in the same parallel group**, and the read model marks ONLY used source subsections green. The unused source ranges stay gray.
- Hard cuts of distinct performances are permissible, but **no implicit morphing, retiming, synchronization, audio replacement, crossfade, or final-master approval** occurs. Cross-Take joins are marked for continuity review, and the director may permit cinematic staging cheats using already-recorded SHOT-01 OpenUSD opinions.

## Director interface

`frontend/src/SlateBranchTimelinePane.jsx` and stylesheet provide a reusable React component with straight dashed vertical parent linkage, grey source lines plus committed green source-range overlays, separate amber inspection, a targetable assembled sequence strip, explicit Make Active/Before/After/Replace action callbacks, and bounded scrolling (up to 12 take rows in DOM view at a time).

The pane can detach into a resizable **same-origin browser pop-out** using React portal state shared with its parent editor. It does **not** yet implement a confirmed installed Windows native detached application window. Host API wiring and installed desktop acceptance remain open; the component deliberately provides no invented authority or automatic revision writes. React tests cover inspection/commit separation, multiple committed source ranges and a 60-take scrolling fixture.

## Acceptance and status

The backend native suite includes Take 1 camera coverage, Take 2 plus its Camera B shot, Wild Take 3, an assembled Wild3 -> Take2-Camera-B cut, a second assembled revision with inserted/trimmed/moved references, explicit refusal of unapproved commit, source SHA and restart verification, and 60 additional take nodes. A Windows/Linux Python 3.11/3.13 native CI gate and front-end Vitest gate are required.

**Status:** backend and UI component implemented in source, with tests authored. Actual native/desktop acceptance has NOT been proven merely by these commits. The prior FFMS2 imported-film index remains deferred.

**Core rule:** The film's source history is a branching collection of data; the edited film is an independently versioned sequence of selected source intervals. Merely looking at a branch cannot change the film.
