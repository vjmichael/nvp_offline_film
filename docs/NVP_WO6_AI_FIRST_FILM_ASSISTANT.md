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
| **WO6-03** | Grounded, bounded task-aware film context (shot/camera/sound/actor/scene) and installed tool/license/model readiness, without a new memory database; report stale/missing/unverified sources. | **OPEN.** |
| **WO6-04** | Preview effects to edits, Takes, stereo/5.1/7.1 sound, color, mastering and DCP; exact source SHA/revision, indexed/unindexed impacts, required grants, resources and recovery action. | **OPEN.** |
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
