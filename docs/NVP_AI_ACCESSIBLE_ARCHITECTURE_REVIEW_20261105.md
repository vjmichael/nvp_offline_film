# NVP-AI-01 — AI-accessible internal architecture review

**Date:** 2026-11-05  
**Status:** Creator-requested architecture review and proposed implementation requirements. This is NOT a claim that the new AI-workspace contracts have been implemented or approved in all their technical details.  
**Reviewed source:** vjmichael/nvp_offline_film, PR #45, development branch nvp/stack02c3b14-picture-conform-20261104; source inspection at commit 349c35c66dde48c600a739496211b86bca4845d3.  
**Parent authority:** [NVP Master Design](NVP_MASTER_DESIGN.md), [Data-First Film ADR](NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md), [Film Lineage Index](NVP_DATA01_FILM_LINEAGE_INDEX.md), [Lu Workspace Contract](LU_DLC_WORKSPACE_CONTRACT.md).  
**Cross-project guidance:** Lu design requirement LU-AIW-01, in vjmichael/Lu-AI-GUI/docs/LU_V1_0_DESIGN_RECONCILIATION_20261103.md.  
**Creator intent [C]:** Make NVP's underlying internals easier for AI to use in service of the filmmaker, without compromising the creator's authority, replacing existing functional components, or forcing premature Lu integration.

## Executive decision

**Retain NVP's data-first film architecture. Add a cohesive, testable AI assistance layer above existing domain services, not a second production database or privileged agent framework.** The hard part is not merely storing production facts: an assistant must find *the right* facts and tools, resolve human references, identify real current readiness, propose a bounded operation, present its consequences, execute only when authorized, and demonstrate what happened.

An agent that says "I remember Blender was installed" but cannot verify the worker and dependency state is not operationally competent. An agent that can generate screenplay prose but cannot reliably identify the requested scene revision or downstream shot impact is not a production assistant. Conversely, indexing more data without task-aware retrieval does not solve either problem.

NVP currently has strong domain building blocks. The highest-value engineering work is **a unified read/reference/context contract and a small explicitly trusted capability catalog**. Native authorization, independent worker evidence, and durable rollback should remain with their established owners.

## Evidence-led assessment of the current implementation

| Concern | Verified source/design foundation | Missing or not yet accepted |
| --- | --- | --- |
| Film identity and exact lineage | backend/nvp_film_index.py: immutable source manifests, object IDs/revisions, typed dependency edges, impact queries, SHA-backed artifacts; tests/test_film_index.py | One cross-domain read/reference API across Story Bible, FilmIndex, shots, timelines, assets and media; complete time-range impact across unindexed outputs |
| Screenplay targeting | backend/nvp_studio.py parse_screenplay gives scene IDs and 1-based source positions. frontend/src/LineNumberedTextarea.jsx and backend/nvp_story_context.py provide line display/export/AI excerpts | Explicit source-revision binding for every AI line instruction and cross-revision span resolution; avoid using heading+occurrence alone as a durable identity under structural edits |
| Creative knowledge | Story Bible, timeline and SceneMind track canon, belief, chronology and creator decisions; backend/nvp_crew_roles.py produces bounded read-only role packets and validates context SHA | A common source-cited packet builder across all film subsystems; standardized missing/omitted/stale fields and selectable object scope |
| AI actions | Backend contains many typed Pydantic/FastAPI handlers; backend/nvp_lu_workspace.py models a trusted LuHostPort with proposal-only writing | Around 135 API route declarations do NOT constitute a curated host-validated AI operation catalog; usage guidance, effects, results, cancellation, resources, approval and evidence are not described in one interoperable format |
| Resource and tool readiness | backend/nvp_resource_ledger.py, native job supervision, RAM/VRAM admission and progress center support measured tasks | Verified reusable inventory for compilers, Blender, FFmpeg, codecs, licensed assets, model providers, existing artifact caches and worker health; history must not masquerade as current readiness |
| Safety and effects | Optimistic revision checks, creator review, signed/typed Lu DLC design, journal and OS worker supervision; captured takes immutable | One assistant-visible task lifecycle joining plan, staging, grant, worker, evidence, source impacts and post-restart status; preserve existing effect-specific authorities |
| Development continuity | Numerous narrow engineering docs and tests, plus alpha closeout handoff | Master document header/baseline is older than the active B14/E2E work; no mandatory generated authoritative single current-state ledger listing exact head, gate outcomes, environments, artifacts, blockers and next action |
| Installer | NSIS source and Windows alpha acceptance contract exist | Successful installed Windows desktop acceptance remains open; unsigned online bootstrapper and on-PC dependency repairs are not proof of an accepted single offline/standalone installer |

**Evidence scope:** A targeted local Python run passed 51 tests: tests.test_film_index, tests.test_crew_roles, tests.test_story_context, tests.test_lu_workspace and tests.test_resource_scheduler. This verifies existing units in a recovered development snapshot, not the complete latest-head matrix, a native Windows install or the new proposed contract.

## NVP-AI-01A — Unified source identity and reference resolver (first priority)

Create an **explicit read-only reference adapter** over existing authoritative stores. No new competing table for approved film objects.

A reference must include the relevant object family, project ID, object/scene/shot/asset ID, exact revision or content SHA, optional line/paragraph, frame/sample/timecode interval, and source/approval provenance. A human-readable reference such as "Scene 7, lines 142–148" is a locator; its durable counterpart resolves an exact screenplay revision and scene identity. A screenplay line cannot be silently redirected after source edits.

Target read operations (conceptual, not approved external API names):
- list_project_objects(kind, cursor, bounded_limit)
- resolve_reference(project, locator, expected_revision)
- read_source_excerpt(project, reference, max_lines_or_bytes)
- describe_object(project, object_id, revision)
- explain_change_impact(project, source_reference, proposed_delta)

The resolver must use existing FilmIndex lineage and domain ownership, distinguish **not indexed** from **no dependents**, reject cross-project references, preserve blank screenplay lines, and refuse ambiguous or stale selections. For video, the adapter must report frame rate and frame numbering convention rather than assuming that seconds or a bare frame index are interchangeable.

**Acceptance:** 1-based screenshot/AI line concordance, stable scene ID under benign edits where possible, explicit ambiguity under reordered/duplicate headings, exact prior-revision retrieval, CRLF and blank-line preservation, unauthorized project refusal, and no mutations.

## NVP-AI-01B — Bounded AI capability catalog

Expose trusted, **non-executable-on-discovery** capability descriptors for NVP's already implemented semantic functions. Do not automatically put every FastAPI route or Python method into the model tool list.

Proposed descriptor fields:
- stable namespaced ID, version, summary, use_when/avoid_when;
- exact typed request/response schema; source/object constraints;
- read/propose/mutate/compute/publish effect classification and host authority;
- expected input revision, preconditions, required assets/dependencies and resource estimates;
- result/evidence type, output location class, cancellation/checkpoint/retry semantics;
- runtime availability: available / unavailable / unknown, with measured source and verification age;
- creator-approval point and explicit failure/uncertain outcomes.

Start with a **small read-only slice**: project summary, screenplay excerpt, story canon/continuity, resource state, FilmIndex object lineage, and impact preview. Add a separate proposal-only slice only after required source provenance. Mutating tools stay behind the established host policy, idempotency and creator approval checks.

**Security invariant:** A metadata descriptor, remembered operation, model utterance, local HTTP route, or Lu DLC manifest **never issues permission**. Standalone NVP may use its existing local adapter, but no unapproved localhost write path becomes a generic AI action. Lu's authenticated per-turn authority and Protobuf host port are integrated only after Lu v1.0 and a separately tested contract.

## NVP-AI-01C — Task-aware, provenance-first context compiler

Replace ad hoc all-purpose prompts with a reusable *context preparation service* (not a second permanent AI memory authority). It should:
1. Resolve the director's requested object, current project and revision.
2. Select the crew role and task; read only relevant screenplay spans, current Bible canon, actor knowledge vs objective truth, chronology, blocking, affected shots/takes and approved media hashes.
3. Carry typed provenance for each excerpt (source family/ID/revision, human-approved vs unapproved, digest and truncation marker).
4. Observe a deterministic token/byte budget and record exact omitted sources. Offer drill-down, never claim omitted context was inspected.
5. Produce a canonical context bundle digest and freshness/revision guard. AI output is a **proposal**, never a new approved fact.
6. Validate the output's reference to input context before any subsequent review, simulation or commit.

Reuse backend/nvp_story_context.py, backend/nvp_bible_context.py and backend/nvp_crew_roles.py rather than replacing their authoring/continuity rules. This is a data-assembly operation; an AI-selected role does not become a separate permission holder or independently resident model.

**Example:** "Make Alex sound less certain in Scene 7" should retrieve the exact approved screenplay revision, scene text/line span, Alex's canonical biography and knowledge at the scene time, affected dialogue and shots, and only the relevant earlier turns. It should not require all project assets or a re-index of unrelated scenes.

## NVP-AI-01D — Verified operational environment and artifact catalog

Extend the resource scheduling/worker infrastructure with an **inventory**, distinct from the scheduler's RAM/VRAM reservations. Track the actual availability and provenance of Blender, FFmpeg, DCP encoders/QC, Python/runtime packages, external approved libraries, voice/video models, assets and cached build tools.

Each record needs absolute verified location, platform, version, architecture, hash if meaningful, license/distribution status, dependency compatibility, last probe, observed success, producer/owner and capability constraints.

States must distinguish KNOWN_PREVIOUSLY, PRESENT_UNVERIFIED, VERIFIED, INCOMPATIBLE, MISSING, OUT_OF_SCOPE, DENIED and UNKNOWN. On a render/build/export request, an automatic host-side preflight queries this inventory, verifies stale entries and reuses compatible available tools. Never download an executable, silently switch model, or install globally solely because an AI asks.

**Acceptance:** After a fresh instance, NVP reuses a verified Blender/FFmpeg installation and previous source hashes; after simulated removal, NVP reports MISSING instead of claiming READY; no unapproved binary execution or license violation.

## NVP-AI-01E — Explainable production task and change-impact plan

Before executing a consequential operation, provide a **preview** of:
- requested change and exact source revision;
- affected and unaffected dependent take/presentation/shot/audio/edit/master revisions;
- required tool/model/assets, readiness, resources and permissions;
- estimated phases and expected outputs, with unknowns explicitly named;
- approval boundary, cancellation/recovery behavior and verifiable success criteria.

Plan → user review when needed → host authorization → stage → guarded execution → verify → promote/publish → receipt. Plans can be regenerated, but their revision/effect scope must be revalidated before action. The FilmIndex impact graph is authoritative only for indexed dependencies; do not pretend it proves frame-granular effects everywhere.

Keep existing Digital Takes immutable; creative suggestions may never rewrite approved footage or master timelines behind the director's back.

## NVP-AI-01F — Unified evidence and recovery summary

NVP already has durable subsystem-specific journals. Add a read-only *consolidated view* (not a replacement journal) exposing task ID, source revision, associated worker, stage, timestamps, reservations, outputs and hashes, pass/fail/uncertain verification, creator approval state and resumable next step.

Preserve distinctions:
- proposed vs creator-approved;
- queued vs running vs completed;
- output generated vs output saved/reopened;
- unit-tested vs actual native process-tested;
- NSIS executable produced vs installed Windows app proven;
- interrupted vs recovered vs uncertain.

The assistant must be able to say which exact sources and tools led to its conclusion and which steps have *not* run. Uncertain non-idempotent effects are reconciled before any retry.

## NVP-AI-01G — Single development-state ledger and documentation discipline

The 2026-11-03 master baseline remains an architectural source, but it cannot alone convey the active November 4–5 delivery state. Maintain one central, machine-friendly development-state document **plus a revisioned event log** recording current exact repository/branch/SHA, accepted design decisions, feature implementation state, verified test matrix with environments, immutable artifact hashes and locations, outstanding blockers, and the next precise engineering task.

Recommended destination: docs/NVP_ENGINEERING_STATE.md with a structured companion JSON schema/manifest. Git history stays authoritative for code changes; the state ledger is **an index of evidence**, not a substitute for Git and not a free-form AI summary. CI/test code should update or validate machine-derived fields where possible, and human approvals stay explicitly human-attested. Do not fabricate successful gates or state from stale notes.

**Acceptance:** a new AI conversation can identify the current head, previous successful bench inputs, applicable installer toolchain, available packages and pending tests without requiring the human to reconstruct the environment. Stale file paths are probed rather than blindly trusted.

## Ordered delivery gates

| Gate | Delivery | Depends on | Objective acceptance |
| --- | --- | --- | --- |
| AI-00 | Documentation and evidence/state inventory | Existing design/source | Review with current module-level status, source refs and no false integration claims |
| AI-01 | Read-only source/reference resolver | Studio + Bible + FilmIndex | Exact revision refs; bounded reads; negative isolation/ambiguity/stale tests |
| AI-02 | Read-only trusted capability catalog | AI-01 | Small relevant catalog; pure discovery has zero effects and does not grant authority |
| AI-03 | Crew task-specific context bundle | AI-01, current crew/Bible | Deterministic digest, bounded context, provenance, omissions, stale refusal |
| AI-04 | Resource and artifact preflight | Resource ledger/native worker adapters | Reuse present resources; detect moved/deleted/incompatible ones; accurate statuses |
| AI-05 | Consequence preview + proposal contracts | AI-01/03, FilmIndex | A proposed screenplay/scene/shot change reports indexed impacts and unchanged artifacts |
| AI-06 | Consolidated evidence/recovery status | Current journals and verification | Fresh-process reopen, no double execution, explicit uncertainty and provenance |
| AI-07 | Model-in-the-loop end-to-end acceptance | AI-01 through AI-06 | Human asks for an edit by reference; model locates it, proposes, previews, awaits approval, runs permitted tools, verifies exact result and preserves other source hashes |

**Independent film-delivery milestones remain active:** E2E-01E installed desktop alpha, authentic film production, audio/DCP, Win10/11 GUI and crash recovery. Do not claim those gates are satisfied because an AI descriptor or read-only context service passes a unit test. Implement AI-01/02/03 in small additive steps while preserving those gates.

## AI usability evaluation

Test a small local transformer as well as larger models; the objective is **less unnecessary reasoning and rediscovery**, not a claim that a particular model becomes smarter. Compare identical tasks with vs without host preflight/context adapter. Measure: target/reference accuracy, source-provenance correctness, unsupported tool calls, stale-resource claims, needless dependency downloads, task completion, human clarification burden, verified outcome rate, CPU/tokens/latency and crash recovery. Test long projects, missing tools, conflicting revisions and attempts to turn untrusted screenplay text into tool instructions.

## Immediate engineering recommendation

Implement **AI-01**, the read-only, revision-aware film reference resolver, next. Use existing Studio, Bible, and FilmIndex stores; do not create another object database. Follow with **AI-02/03** and tests proving context is source-bound. Keep installation/packaging fixes on their own release track.

**Important boundary:** NVP remains a standalone film-production application for now. Do not introduce a required Lu socket, second model manager, mandatory MCP server, or privileged generic local tool executor. Future Lu integration should adapt these read-only and typed domain contracts to the host's eventual stable Workspace API, with explicit authorization and native acceptance.
