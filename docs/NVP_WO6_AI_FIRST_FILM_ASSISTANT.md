# WO6 — Creator-guided AI filmmaking operations

**Opened:** 2026-11-07. **Status:** New implementation work order, draft, independent of deferred WO4/WO5 film and cinema acceptance.  
**Parent:** `NVP_THEATRICAL_BV21_AND_PRODUCT_ENDSTATE.md`; `NVP_AI_ACCESSIBLE_ARCHITECTURE_REVIEW_20261105.md`.  
**Stack:** draft PR #92 (WO5 installed/sustained playback) → WO6 branch `nvp/wo6-ai-creator-guidance-20261107`.  
**Integration decision:** reuse NVP's existing Studio, FilmIndex, native trusted AI read host, scope guards, source provenance, job supervisor and creator approval systems. No second model runtime, no unbounded model-written filesystem actions, no direct privileged browser/HTTP operations, no Docker, no FFmpeg. The future Lu DLC/Protobuf ABI remains deferred, not invented here.

## Goal and actor-facing behavior

A creator should be able to ask NVP what film has been made, where a shot or Take came from, how to change it, which approved artifacts would be affected, and then ask NVP to help execute the allowed native operation **after separately confirming the creative choice and the native host permission**. NVP should distinguish plans, committed production source, rendered footage, finished delivery and human theatrical acceptance.

A director requesting a different Take from the final DCP must preserve: `published DCP → FilmIndex / FeatureJournal derived receipt → exact approved reel/editorial source → immutable Digital Take → exact OpenUSD scene + temporal events`. A standalone flattened DCP cannot recreate editable 3D scene data. The source project/archival provenance must be preserved separately. New edits and Takes get new identities; old source and DCP bytes stay immutable.

## Ordered engineering phases

| Task | Deliverable | Status |
| --- | --- | --- |
| **WO6-01** | Bounded SHA-bound FilmIndex source-to-retake lineage and host-authorized read-only plan, deterministic digest, negative/cross-project tests. Reuse `NativeAiReadHost` and `TrustedReadScope`; discovery is not authorization. | **IMPLEMENTED, CI verdict pending.** |
| **WO6-02** | Native FeatureJournal-backed origin resolver: reruns WO5's full indexed DCP/Take/PCM/J2K source audit, reports original per-reel Take/scene/temporal SHA and Film Time; host-injected only, read-only. Missing/retired/altered sources are refused. | **IMPLEMENTED, CI verdict pending; genuine 30m film still open.** |
| **WO6-03** | Trusted-host scene/actor/camera/sound/shot/script/accepted-canon context from reopened frozen Takes, exact Film Time, bounded SHA provenance and omissions; native installed binary/license pin preflight. Full model/runtime readiness and installed app integration are later gates. | **IMPLEMENTED, exact-head native CI verdict pending.** |
| **WO6-04** | Read-only SHA-pinned source-to-Take/edit/master/DCP impact graph, exact accepted Production Bible digest and typed fact continuity, separate director grants, optional 2K/4K 2/6/8ch capacity estimate, source-race/truncation refusal. | **IMPLEMENTED; exact-head CI verdict pending; installed creator UI remains WO6-07.** |
| **WO6-05** | Native creator-confirmed action bridge and model-independent proposals: concrete first-party tool execution through existing durable supervisor, no AI self-approval and no arbitrary filesystem/network authority. | **OPEN; human consent required.** |
| **WO6-06** | Unified read-only receipts for worker progress, cancellation, crash/restart reconciliation, source-vs-derivative status and filmmaker-facing errors; never fabricate finished-film evidence. | **OPEN.** |
| **WO6-07** | End-to-end novice-and-professional desktop/installed AI-assisted scene/Take/edit/sound/render/review workflow with actual local model tests, camera/actor direction and performance/film-quality review. | **OPEN; depends on previous gates and real film assets.** |

WO4 and WO5 remain independently **OPEN** for genuine full-resolution 30-minute original film, sustained installed picture and mastered audio, 60–90-minute actual feature, >=3-hour epic, native legally bundled release and independently validated SMPTE DCP Bv2.1/theater ingest.

## WO6-01 concrete implementation

`backend/nvp_wo6_creator_plan.py` builds an immutable, bounded source-chain preview from an **exact FilmIndex object/revision**. It reads canonical SHA-verified revision records and their typed dependency edges, then validates matching scene and temporal revision SHA values for original OpenUSD frozen Takes. The output includes retained source references and downstream **one-hop indexed** scene consumers, along with explicit missing coverage. It does not assert that all FeatureJournal source jobs have been read; it does not open the actual OpenUSD stage, render new content or validate projector compatibility.

`backend/nvp_ai_read_host.py` now adds `nvp.film.plan_retake.v1` to the existing **read-only** semantic catalog and dispatches via the **same trusted per-turn authorization callback and project-scoped digest receipt** as screenplay/context reads. No model can call this just by discovering it. Inputs are exactly project ID, object ID, revision and bounded node limit; unknown fields, cross-project requests and unauthorized turns fail before project reads. Nothing in the returned plan grants approval or writes a new Take.

WO6-01 may report `PINNED_USD_RETAKE_SOURCES_FOUND_NOT_AUTHORIZED` only if the bounded indexed path really includes a frozen OpenUSD Digital Take whose exact scene+temporal identities and SHA edges match. It must report `INCOMPLETE_OR_UNLINKED_RETAKE_SOURCE_EVIDENCE` for flattened DCP-only or truncated/unlinked evidence, while acknowledging other source receipts could exist in FeatureJournal.

The read proof itself is narrower than **actual source file reopen/independent scene validation**. Approval and execution belong in later phases, not the read host.

## CI gates and truthfulness

`tests/test_nvp_wo6_creator_plan.py` covers source-to-final dependency graph, SHA-bound original Takes, immutable revised scene versus original Take, forged take manifest refusal, incomplete bounded graph, DCP-only nonreversibility, cross-project and stale/missing revision denial, unknown/write operation rejection, per-turn authorization digest and mid-task revocation. Add Windows/Linux Python 3.11/3.13 tests plus existing AI-01/02/03 regressions; **only mark tests accepted after their actual exact-head GitHub receipts arrive**.

Current WO6-01 is a **planning contract**, not a live AI filmmaker or a claim that finished film/creative approval exists. The subsequent phases must add actual source navigation, purpose-built native execution, genuine working installed UI and model-in-the-loop evidence without bypassing creator authority.

## WO6-02 implementation update — 2026-11-07

`backend/nvp_wo6_feature_origins.py` adds a **separately bounded and
potentially expensive** source-custody resolver. It requires an existing
trusted `FilmIndex` and a real host-owned `FeatureJournal`; it first
checks the exact project, indexed state, cancellation and FilmIndex
feature SHA. It invokes WO5's `inspect_original_feature_readiness`
which independently rechecks real native project/reel/Take originals,
picture XYZ12/J2K, mastered PCM24, published MXF and DCP SHA provenance,
and original OpenUSD Take reopening. It then re-reads each approved
Take's exact FilmIndex SHA and verifies matched source scene+temporal
SHA, maps Film Time by reel and checks publication state once more.
The result never changes the film or implies calibrated cinema,
human screening, an AI-executed task or a replacement Take.

The original trusted `NativeAiReadHost` accepts an **optional,
host-injected** FeatureJournal. Only that configuration advertises
`nvp.film.resolve_published_sources.v1`; no model-supplied path
or web request can inject a journal, and the per-call actor/project/
turn digest authorization is unchanged. The no-journal catalog does not
advertise the capability.

`tests/test_nvp_wo6_feature_origins.py` tests the adapter boundary
against an explicitly **mocked WO5 native auditor** to isolate consent,
revocation, changed source hashes, changed feature state and returned
FilmIndex edges. These tests do NOT constitute a new genuine native
DCP/2K/PCM24/FilmIndex source-chain E2E proof. Existing WO5 genuine
native tests and later installed movie/creator acceptance remain
independent. WO6-02 current native matrix verdict is pending.


## WO6-03 — Real source-aware scene/crew context and native-tool readiness (2026-11-07)

**Code implemented, CI verdict PENDING.** The native internal readers are:
\`backend/nvp_wo6_scene_context.py\` and \`backend/nvp_wo6_tool_readiness.py\`.
They extend \`backend/nvp_ai_read_host.py\` with two *read-only* capabilities:
\`nvp.film.read_scene_crew_context.v1\` and, only when the native host
has explicitly pinned local tools,
\`nvp.tools.inspect_host_pinned.v1\`. The first is not enabled for
model self-authorization: each call must pass the existing
\`TrustedReadScope\` current actor/project/turn authorization callback.
Unknown keys/paths and other projects are rejected before access.

The scene context **reopens the actual frozen OpenUSD Digital Take** and
verifies its immutable scene+temporal source hashes and sample/checkpoint
digest using \`OpenUSDTakeCapture.verify_take\`; it does not trust a
model-supplied or self-described scene. At a caller-selected exact integer
Film Time tick, it reads NVP actor/camera/prop/light semantic roles,
actual composed OpenUSD world translations, lens/light values when
real UsdGeom.Camera/UsdLux schemas exist, active typed sparse events
and their exact source IDs/SHA/revision. Linked immutable audio source
events are classified separately; actual bounded recorded PCM samples
are reopened from source chunk SHA before reporting them as verified.
Original sound here is **not** finished multichannel mastered sound.
The original Take and current head scene revision are distinguished,
so an earlier original performance cannot be mistaken for the current
working revision.

If the creator selects an existing exact \`ExactTimeShotSequence\` ID
and revision, the packet validates its original scene SHA and identifies
the active camera shot at that time; gaps remain gaps, not invented
shots. If an exact current screenplay revision+scene ID is selected,
existing AI-02 context supplies screenplay excerpts. The Story Bible is
queried **without creating tables or altering canon**; only explicit
scene-linked and creator-accepted facts with matching exact scene-text
SHA/revision are included, up to a bounded limit. AI proposals, rejected
facts and stale scene links are excluded. A screenplay character and a
3D actor are *not* automatically treated as the same person merely
because their names look similar. Unseen prims/events/facts carry
explicit omission counts/flags; a packet SHA seals the result.

Native tool readiness is an *actual local file preflight*, not
model assertion or remembered file path. An already trusted host
injects \`TrustedToolInventory\` with exact absolute installation root,
expected SHA-256 native binary/license notice hashes, and tool IDs.
The read checks current files and detects MISSING, binary SHA mismatch,
missing/altered license or verified matching on-disk files, without
executing a program, probing PATH, creating worker authority or
installing packages. Model/browser requests cannot supply new
tool paths, pin hashes, or create a tool inventory. Even
\`SHA_AND_LICENSE_VERIFIED_NOT_EXECUTED\` is **not** evidence of
actual runtime execution, GPU compatibility or release acceptance.
If no native inventory is injected, NVP returns
\`HOST_HAS_NOT_PINNED_NATIVE_TOOL_INSTALLATIONS\` rather than guessing.

**Native tests submitted:** \`tests/test_nvp_wo6_scene_tool_context.py\`
uses real OpenUSD actors/cameras/lights, moving camera/actor,
actual indexed temporal event and original PCM chunk, immutable Take
reopen, creator-authored shot timeline, Story Bible accepted versus
proposed facts, stale scene/camera source, cross-project/turn revocation,
binary/license tampering, missing files, symlink refusal and no model
tool-path injection. CI matrix is Windows/Linux x Python 3.11/3.13 and
runs existing AI-01/02/03 regression tests. It requires actual
\`usd-core==26.11\`; earlier GitHub YAML install scalar parse failure
was repaired. **This is not a model-in-the-loop or installed GUI
film production acceptance**. WO6-04+ and the earlier WO5 original
film/theater gates remain independent; installed model readiness,
actual runtime tool execution and full creative source/canon linking
will require later first-party native acceptance.

## WO6-04 implemented — 2026-11-07

**WO6-04 Production Bible impact design:** `docs/NVP_WO6_PRODUCTION_BIBLE_IMPACT.md` defines how the existing approved Story Bible, StoryTimeline, SceneMind, screenplay, OpenUSD, FilmIndex and FeatureJournal are composed into one **read-time authority** without introducing an AI-maintained Bible store. The original `backend/nvp_bible/` casting/optical/environment JSONs remain historical references, not automatically approved live state. Native `nvp.film.preview_source_impact.v1` includes bounded known FilmIndex effects, approved-canon SHA and scene/fact links, distinct unknown/unindexed outputs, strict per-turn authorization, separate director approval requirements and optional WO4 resource estimates. It never writes a scene or Take, starts a worker, or approves a film. Implementation/tests committed; exact-head Windows/Linux CI awaiting results. Full installed model UI integration remains later.
