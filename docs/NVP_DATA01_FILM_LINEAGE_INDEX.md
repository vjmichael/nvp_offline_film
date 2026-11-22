# NVP-DATA-01 — Durable Film Source and Provenance Index

**Date:** 2026-11-03  
**Status:** Implemented source/index foundation; Python/native cross-platform regression evidence recorded below when available. **Does not yet implement the complete Digital Take/Presentation/Editor pipeline.**  
**Architecture authority:** [Data-First Film ADR](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md) and [Film Package Specification](NVP_DIGITAL_FILM_PACKAGES_AND_REGENERATION.md).

## Product purpose

The NVP Film World is *editable structured production information*. A rendered movie is a derived presentation. To preserve this relationship, every production object needs a stable identity, exact immutable revision, project-scoped source references and a dependency graph that answers which downstream artifacts are affected when a creator changes a particular source version.

This is the first implementable piece of the architecture adopted on November 3.

## Delivered modules

- \`backend/nvp_film_index.py\`: \`FilmIndex(studio)\` uses the same existing Studio SQLite project database and WAL/foreign-key settings. No second competing account database, no Lu integration needed for these metadata operations.
- \`tests/test_film_index.py\`: real Studio project, approved ProductionScene proxy layout import, restart, binary integrity/tamper/symlink checks, exact revisions, frozen take registration, typed downstream presentation/edit/master lineage, stale optimistic writes, cross-project isolation, malformed input and selective impact queries.
- \`.github/workflows/nvp-production-acceptance.yml\`: full existing Linux/Windows Python and real Blender regression workflow also runs on the DATA-01 branch.

## The implemented storage contract

\`FilmIndex.put_blob(project_id, bytes, media_type)\` writes up to **32 MiB per blob/chunk** into a per-film SHA-256 content-addressed disk directory next to the Studio database. It uses a private temporary file, flush/fsync and atomic **no-clobber hard linking**; it refuses replaced/symlinked/corrupted content, then registers metadata in a project-scoped SQLite row. \`get_blob\` verifies both registration and actual disk bytes again. If power fails after filesystem publication but before SQL registration, an orphaned disk blob may remain, but there is **no indexed, false-approved film artifact**. Orphan cleanup is deferred.

\`put_json\` stores canonical, deterministic JSON (same \`compact\`/SHA semantics as existing production modules) with a strict **1 MiB manifest limit**. It never places large videos or high-poly meshes directly into film metadata. This is foundational chunk storage, **not a streaming large-media ingest/export API yet**.

SQLite tables:
- \`film_blob_refs\`: film-scoped verified content digest, byte count and media type.
- \`film_objects\`: one canonical project-scoped object ID and kind, current latest revision.
- \`film_object_revisions\`: immutable revision number, canonical manifest digest, parent revision and commit time.
- \`film_dependencies\`: exact typed links between two **specific revisions** in the same film. Foreign-key enforced; reverse index supports dependents queries.

Supported kinds include world, scene, actor, asset, style, performance, camera, dialogue, audio, lighting and prop, plus derived take/presentation/edit/master records. A record's \`kind\` cannot silently change; \`take\` identities are **immutable single-commit** by design. A changed capture must use another take identity. Approval semantics and complete capture validation are **not provided by this index alone**.

\`register_revision(project_id, object_id, kind, data, expected_revision=..., dependencies=[...])\` enforces optimistic revision expectations and resolves every dependency to an **already committed** record in the same project. Dependencies contain \`object_id\`, \`revision\` and typed \`role\`. Each saved revision includes the exact source dependencies in its hashed JSON; revision metadata and recorded SQL edges are verified against that blob on reopen. A source revision may be superseded but never mutated or silently replaced.

\`read_revision\`, \`history\`, \`list_objects\`, \`direct_dependents\` and \`impact\` expose the source lineage. The impact query traverses version-bound edges and reports actual currently indexed downstream records. It does **not** claim knowledge of unindexed legacy outputs or that a video generator can repair individual frames.

## Example relationships

    film: project_abc
      asset_wardrobe@1 (brown jacket)
        -> scene_diner@1
          -> take_004@1 (frozen)
            -> presentation_noir@1
               -> edit_001@1
                  -> master_001@1
            -> presentation_anime@1

    asset_wardrobe@2 (black jacket)
       [new revision; NO retroactive overwrite of source @1]

If \`asset_wardrobe@1\` is superseded, \`impact\` reports \`scene_diner@1\` through the linked presentations and master. This does **not** delete or rewrite the old master; it is still valid for the old approved source. The new wardrobe and scene would need explicit reviewed revisions, new capture as necessary, and new presentation jobs.

An unrelated dialogue or sound record that was not linked to the changed wardrobe should not appear in the impact list.

## Actual integration and limits

One regression builds a **real approved** \`ProductionScene\` layout through the existing \`Studio\`/solver/approval path, imports its exported proxy world manifest into \`FilmIndex\`, reopens the index and verifies exact source identity/asset edges. This is intentionally more meaningful than testing only fabricated JSON examples.

The DATA-01 index **does not yet**:
- Capture a full timed \`ShotSequence.export\` into a complete, source-validated, frame-accurate frozen Digital Take Package. That is \`NVP-CAPTURE-01\`.
- Actually produce frames/voice from two model-specific workers or verify hi-fi output. That is \`NVP-PIPE-01\`.
- Implement approved director GUI actions, model authorization, trusted user identity and package export/import.
- Maintain semantic timecode-range impact scopes for generated video, lip-sync and audio; current impact is exact indexed revision-level **conservative graph traversal**.
- Stream multi-gigabyte video blobs, garbage-collect unreferenced source, or guarantee protection from arbitrary malicious local disk access.
- Claim a complete film can yet be produced via the new package pipeline.

## Acceptance classification

\`NVP-DATA-01A\` is the **storage and lineage foundation**. The gate may be marked verified only after Linux and Windows Python regressions, persistence/tamper/refusal tests, real approved proxy world import and correct change-impact behavior complete.

\`NVP-DATA-01B / NVP-CAPTURE-01\` follows: **capture a real current approved timed shot sequence** into an immutable take with complete source/time/actor/camera/audio references. It must independently reopen, reject stale world dependencies, and prove that hi-fi assets or a video model need not be loaded during source capture. Then the presentation adapter and edit/reproduction modules can consume exact versioned take references.

The current source code and this document should never be used as evidence that an integrated media production pipeline has already shipped.
