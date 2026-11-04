# NVP-STACK-02C3B13 — Imported edited OpenTimelineIO picture revisions

**Scope:** NVP standalone film editing. Lu ↔ DLC Workspace interface postponed until after Lu v1.0.

## B13 purpose and existing verified foundation

B12 independently produced and reopened a complete, non-destructive, 120-frame 24fps film package: original frozen Digital Take → 32-bit OpenEXR source → ACES 2 16-bit SDR viewing PNG → portable OpenTimelineIO 0.18.1 cut interchange and an independently decoded ProRes HQ technical MOV. B13 adds the **reverse import path** from an editor-adjusted `.otio` to a durable FilmIndex `edit` object without rewriting the original source, losing history, or silently accepting unsupported operations.

## Supported editorial actions

The official OpenTimelineIO 0.18.1 adapter parses the input JSON as a *real* `Timeline`, one `Video` track, and bounded `Clip`/`ImageSequenceReference` objects. NVP can **trim, split, reorder, and repeat** original shot ranges; each output frame maps to an exact original numbered B12 PNG frame, original 32-bit EXR source SHA and original shot ID. Every clip retains original media availability, six-digit `media/review_*.png` URI, the B12 original shot ID, source-image start frame, frame rate 24, bounded integral source start and duration. Timeline time is frame-accurate; no source out-of-range, empty clips, repeated frame caused by hidden speed effects or source media ID substitution. Maximum 128 clips, 480 edited frames, and 4 MiB OTIO input bytes.

**Explicitly unsupported and rejected:** audio tracks, effects, time warps, transitions, gaps, nested compositions, arbitrary external files/URLs, custom names as invented shots, scene source rebinds, changed source frame-rate, foreign or symlinked media, and an OTIO object that is not a genuine timeline. NVP does not claim import compatibility with every NLE flavor of OTIO yet; actual application-side interoperability is another acceptance gate.

## Durable edit revision without destroying source

An editor may keep one persistent FilmIndex `edit_id` and provide `expected_revision`. The first import commits revision 1. A second edited timeline under the same `edit_id` can commit revision 2 only when the client names the exact current revision and the same B12 source delivery. SQLite's `BEGIN IMMEDIATE` and `expected_revision` implement optimistic concurrency: stale editor saves fail rather than overwrite someone else's edit. The original `take` remains forever revision 1; all previous edit document bytes, their exact imported `.otio` SHA and metadata survive and are independently inspectable.

Each versioned edit document records the original frozen Digital Take identity/sha, B9 FLOAT32 source identity, B11 SDR review identity, B12 portable delivery ID/SHA, source-derived clip segments and **every output picture frame's exact original film frame and PNG/RGB48/EXR hash**. Its typed FilmIndex dependency edges point to original take, SDR review and original B12 presentation at revision 1; no model or NLE-supplied metadata is trusted as source authority.

`verify_imported_edit` reopens the official OTIO bytes from content-addressed FilmIndex storage; the original B12 complete portable package and source lineage must still verify. It reparses the true OTIO structure and recomputes all trim/reorder/repeat source frame and clip mappings, comparing the entire result to the committed immutable edit document. A newer revision does not rewrite the old. No new scene-linear image, SDR image, audio file, ProRes or final master is claimed for a metadata-only edit; **conforming and rendering the edited picture** will be a separate production gate.

## Native permission, containment and safety

`NativeB13ImportHost` requires trusted installed-host creator authorization of the exact original B12 delivery SHA, project, take, original 32-bit EXR identity, chosen edit ID, expected parent revision and **SHA of the actual edited OTIO input bytes**. A browser, model, HTTP endpoint or mere JSON document cannot mint a native import grant. CI fixture events are test-only and cannot stand for installed desktop UI presence.

The original untrusted `.otio` is staged into a private job directory under an exclusive name and fsynced, together with a canonical SHA-bound plan. NVP's existing `ApprovedTaskBindings` and `TaskLedger` journal the job without launching it; measured physical RAM admission runs before starting. A pinned Python executable/source hash and short-lived grant are checked again before the OS-contained `nvp_b13_reimport_worker` parses untrusted content. The child commits only an `edit` FilmIndex revision through the verified importer and writes a durable completion receipt. The host independently verifies it after process exit and can reopen old/new edits after restart. Native queued-only revocation requires a second creator action. Unknown OS worker termination holds ACTIVE RAM reservations until cleanup is proven.

## B13 automated evidence

`.github/workflows/nvp-stack02c3b13-otio-roundtrip.yml` covers Windows/Linux official OTIO manipulation, source mapping, foreign-media and time-warp rejection, mutable/expired/tampered staged source, RAM refusal, creator permission, cancellation, optimistic concurrency and exact edit history after restart. It reruns B12 source integration and React build/tests.

The Linux native end-to-end fixture starts from **real B12**: 120 original frozen take frames rendered in actual Blender to FLOAT32 OpenEXR, individually verified ACES2 SDR review PNGs, official OTIO and independently decoded ProRes HQ. It modifies that actual OTIO as if an external picture editor trimmed/reordered/reused the original shots, imports the edited timeline in an OS-contained RAM-admitted worker, makes a second revision of the **same edit object**, and independently reopens both revisions after restart alongside the untouched original B12 film.

**Open production gates:** This accepts picture edit decisions but does **not** yet reconform/edit the actual movie or recompute edited-grade frames, deliver audio, mark picture lock, support transitions, import NLE-specific interchange variants, create approved final ProRes/IMF/DCP or claim installed desktop creator presence. Separate edit-conform/render and audio synchronization tasks follow after this milestone.

**Status:** B13 draft PR stacked on B12; require exact current-HEAD CI green before marking accepted.
