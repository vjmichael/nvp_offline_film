# NVP SLATE-04 — Source-Truth Custody, Reference-Only Editing, On-Demand Preview

**Creator direction — November 6, 2026.** Frozen 3D film data are immutable while they exist, but creators may deliberately delete data. The edited film timeline is only a versioned assembly of source-data interval references, not the source of truth. It must support cut, copy, paste, split, trim, replace and rearrange without editing the original performance. No need to load every Take, world layer or rendered image into RAM when the editor only needs source metadata or a single preview.

**Implementation state:** Native backend and React component source authored with tests and CI. Exact-head Windows/Linux native acceptance and installed desktop integrations remain OPEN.

## 1. Reference-only film assembly

The FilmIndex Digital Take, source 3D scene, actor identity, Temporal Ledger and shot-specific OpenUSD override retain their separate SHA-pinned immutable revisions. A committed SLATE-02 edit contains only ordered segment references with unique instance IDs, original branch/Take/SHOT revision SHAs, source in/out ticks, destination in/out ticks and hard-cut continuity markers. The same source interval may be reused any number of times subject to the existing bounded edit length.

SLATE-04 extends the pure in-memory draft editor with:
- **split:** divide one source interval at an original source tick, retaining a left segment and giving the right segment a NEW unique segment ID;
- **paste_before/paste_after:** insert an existing source reference with another unique segment ID, not a deep copy of any original data;
- existing insert/replace/trim/move/remove; these do not publish FilmIndex revisions.

Copying a source reference to the UI clipboard cannot mutate a Take. Cutting a clip is removal from an **uncommitted draft only**. A filmmaker must approve the complete edit SHA with Make Active/Commit Cut before the new version is published. Earlier cut revisions remain openable. Selecting or previewing a branch does not activate it.

The React timeline pane has draft-specific Copy Reference, Cut Draft Reference, Paste Before/After and Make Draft Active controls. The UI issues host callbacks only; it does not directly write FilmIndex. Green source intervals still reflect the last committed edit while a draft is being arranged. Native host API callbacks and installed Windows acceptance are OPEN.

## 2. RAM-efficient editorial and preview access

New `SlateLazyPreview` resolves a playhead tick by opening only the committed cut manifest (bounded to at most 500 light segments) and its small source-catalog root, locating the occupied interval with binary search, and verifying **only the selected** frozen Take/optional SHOT SHA. It maps requested edit-time to exact source-time ticks by integer translation. It does **not** load the rest of the 3D world, all parallel Takes, the entire catalog's source blobs, a video frame or FFmpeg.

A batched preview request may select up to **16** timeline ticks. Each ticket contains project, exact committed edit SHA, source Take SHA, optional shot SHA, selected film-time tick, source-data tick and deterministic cache key from source SHA/tick/preview quality. It explicitly reports that no picture, worker launch or final render was produced. A ticket is a **source selection**, not a screenshot.

`structural_sample(ticket, prim_paths)` is the explicit heavier option: re-resolve and re-validate the ticket, open **one** selected OpenUSD scene and optional shot layer, and evaluate at most **16 named prim transforms** at that source tick. This is actual structured 3D state, still not a rendered preview image, skeletal performance/IK, sound or picture conform. The eventual native low-fi preview renderer can consume the same SHA-bound ticket through the established authorized worker system and maintain a bounded disk thumbnail/cache policy. The renderer hookup is not claimed implemented here.

Data-only seeking supports very large authored cuts without needing film-length RAM or GPU state, although the selected Take's OpenUSD layer may require ordinary memory when structural sampling/rendering is deliberately requested.

## 3. Immutable yet deliberately deletable source-of-truth

Do **not** reinterpret immutable as undeletable. Data that remain in NVP must not be silently rewritten; an authorized creator may remove them. Source deletions need referential integrity:

- **Retire / move to trash:** record an explicit creator-authorized retirement in SQLite, preserve original SHA-pinned source bytes and all historical cuts. The source is unavailable for *new* FilmIndex dependencies or new assembled edit commits, even when the editor refers indirectly through an old slate catalog. Existing historical revisions can still be opened for custody/reconciliation. Retired Takes are hidden from ordinary active-source listing, but may be shown explicitly in a trash/history view.
- **Restore:** separate creator authorization changes its availability status without editing its content or SHAs.
- **Purge unreferenced registration:** after retirement and another explicit authorization, remove the FilmIndex object/versions **only if no recorded typed or legacy normalized consumers remain**. This may require deleting dependent edits and slate catalogs first. No implicit recursive cascade of a director's historical film is permitted. The permanently retired ID cannot be reused.
- **Media bytes:** deleting the FilmIndex registration is *not* secure media erasure. Source blobs remain orphaned for a future supervised, authorized, crash-recoverable physical garbage collector with a global shared-hash/retention check. The API explicitly says `physical_blobs_deleted=False`.

The lifecycle state is accompanied by an append-only SQLite event journal (retired, restored, purged), and the creator can request a bounded transitive source-impact report before attempting irreversible purge. That report is advisory; the purge repeats the authoritative dependency test under the SQLite writer lock. Trusted approval callbacks used inside a transaction must be fast, noninteractive checks of permissions already obtained by the desktop host, not a blocking user-consent dialog.

FilmIndex's normal revision publication now checks for retirement and identity reuse within the **same SQLite writer transaction** as new source dependencies. The SLATE-02 edit commit additionally checks every selected Take and shot in its own precommit guard, closing the indirection loophole through an older catalog. These checks prevent a retirement/new-cut publication race.

Existing SQL dependent evidence is used to refuse unsafe purges, including typed FilmIndex dependencies and legacy normalized media/event links. File-level deletion, global orphan garbage collection, legal retention rules, mounted external originals and multi-user authorization require separate gates; they are NOT implied by retirement.

## 4. Tests and acceptance

Native tests cover split and paste by reference (source Take digest stays identical), a committed mixed cut with on-demand playhead selection from different Take/shot branches, exact source-time mapping, 3-source ticket windows without OpenUSD load, a separately requested structural sample that opens the selected scene, inspection-only no-picture behavior, retirement with existing cut consumers, refused purge, refused newly activated cut after retirement, restore, and an unreferenced registration purge that forbids reused IDs.

React tests cover an uncommitted draft clipboard, explicit Make Draft Active callback, unchanged green committed source while draft changes, and preview requests only from selected committed intervals.

CI: actual native OpenUSD on Windows/Linux Python 3.11/3.13; frontend build/Vitest. **Only actual green exact-head runs count as acceptance.**

## 5. Further engineering work

- Durable GUI edit/clipboard adapter to the native host, installed multi-window UI acceptance, and preserving volatile drafts on app crash if desired.
- Renderer-owned bounded thumbnail image cache (disk-first), asynchronous cancellation, low-fi proxies, priority scheduling, source-shot lighting/actor preview and high-fi confirmation.
- Native timeline virtualization for thousands of assembled segments, sub-frame-time transitions, audio synchronization and deliberate cinematic continuity overrides.
- Explicit directory-safe physical blob garbage collector, custody/retention checks, forced-worker-death recovery and a creator-reviewed purge impact report.

**Core invariant:** Source truth is immutable while present, deletable only through explicit custody-aware actions. A Film Time edit is just a reversible organization of selected source-data intervals. No original Take is altered by editing, and no unused performance needs to be loaded merely because another Take was selected on the timeline.
