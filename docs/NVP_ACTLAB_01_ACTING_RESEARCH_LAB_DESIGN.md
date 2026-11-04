# NVP-ACTLAB-01 — Acting Research Lab and Film Intelligence Research Design

**Status:** Design proposal; no trained acting model, dataset ingestion, or working performance-synthesis backend is claimed by this document.  
**Created:** 2026-11-04  
**Branch:** `nvp/acting-research-lab-20261104`  
**Parent development line:** `nvp/stack02c3b14-picture-conform-20261104`  
**Scope:** Separate research and benchmarking program. NVP remains the filmmaker-controlled workspace; a filmmaking-specialized model remains optional, replaceable, and independently versioned.

## 1. Purpose and non-goals

Build a rigorous acting-research environment to answer which methods *actually* translate human direction into convincing, coherent, reproducible virtual performances. Study acting craft, dramatic interpretation, interpersonal behavior, anatomy, physiology, voice, facial motion, gaze, body movement, and film-length continuity. Measure conventional baselines first, then decide whether a specialized transformer, adapter, vision model, or learned performance model adds demonstrable value.

NVP itself is not the AI. It is the persistent virtual production workspace: screenplay, Production Bible, 3D sets, approved character/world state, FilmIndex, immutable performances/takes, cameras, lighting, audio, editorial, dailies, and delivery. A single general or specialized transformer may adopt bounded crew roles (director, acting coach, cinematographer, script supervisor, etc.) without becoming the authoritative source of facts or execution permission.

**Not goals:** training a foundation video/LLM model from scratch now; assuming labels such as `sad` or `angry` equal acting craft; requiring NVP to bundle this research system; claiming research-only data provides a loophole for commercial deployment; replacing deterministic geometry, signal processing, audio sync, continuity checks, or rig constraints with LLM guesses.

## 2. Governing principles

1. Human director owns artistic decisions, approved canon, and approval of performance changes.
2. AI proposes *why and how* to realize intent; deterministic/learned production tools perform bounded operations. Tool discovery and role selection do **not** grant execution authorization.
3. Authoritative facts, character beliefs, audience knowledge, actor performance evidence, AI observations and dramatic instructions are distinct, provenance-bearing record types.
4. Preserve actual baked artifacts, not merely seeds or prompts: an existing performance must remain camera-independent and unchanged across new render coverage.
5. Benchmark against the strongest practical conventional pipeline (prompting + retrieval + specialized deterministic tools), not a deliberately weak baseline.
6. Research results must not be treated as commercially cleared training data, inferred rights, or deployment approval.
7. Every status assertion is one of **proposed**, **implemented**, **tested**, **independently verified**, or **blocked**. No placeholder or simulated output may pass acceptance.

## 3. System boundaries

```text
Human filmmaker
    | creative direction / approvals
    v
NVP Film Studio (workspace; canonical project state, tools, review UI)
    | versioned, scoped FilmContextPacket / PerformanceCard proposals
    v
Pluggable Film Intelligence (general LLM, optional fine-tuned acting adapter)
    | structured proposals, no arbitrary tool authority
    v
Control compiler + tool host (typed schemas, permission, deterministic validation)
    |                                  |
    +--> speech alignment             +--> camera / collision / IK / rig solver
    +--> face / gesture synthesis     +--> audio and render engines
    v
Frozen PerformanceSource -> versioned camera/render derivatives -> dailies
    |
    +--> independent EvaluationRecord, licensed data provenance, human review
```

The **research lab** is a separate benchmark and experimentation boundary. Its outputs are claims, aggregate statistics, methods and independently publishable original research; commercial reuse is permitted *only* where the underlying inputs and permissions allow. No data or checkpoint automatically flows from the research lab into the commercial NVP system.

### Existing NVP surfaces to integrate with later (not audited in this branch)

- `backend/nvp_story_bible.py`, `backend/nvp_story_context.py`: accepted story facts and bounded story context.
- `backend/nvp_crew_roles.py`: role-specific read-only task packets and proposal validation, *not* working AI crew execution.
- `backend/nvp_digital_capture.py`, `backend/nvp_film_index.py`: frozen take / indexed revision concepts.
- `backend/nvp_production_scene.py`: deterministic set constraints.
- `backend/nvp_b14_picture_conform.py`, `backend/nvp_audio01_picture_follow.py`: picture/audio infrastructure, not acting synthesis.

Those filenames are based on the development handoff; this research document does **not** certify their status. Do a source-and-exact-SHA audit before an integration PR, and keep active B14/audio acceptance independent.

## 4. Acting and filmmaking knowledge curriculum

**Dramatic craft:** screenplay structure, beats, objectives, obstacles, tactics, relationships, subtext, character knowledge, lies, revelations, story arcs, rehearsal and retake language.

**Acting craft:** listening and reacting, eye contact, restrained emotion, changing objectives across beats, pauses, breath, body orientation, gesture timing, interpersonal distance and continuity across camera coverage.

**Biology and physiology:** anatomy of face, jaw, tongue, throat, spine and limbs; respiration; vocal articulation; muscle and joint limits; fatigue and physical effort. Biological evidence informs physical constraints but is **not** a deterministic mapping from psychological emotion to facial expression.

**Filmmaking craft:** blocking, eyelines, lens effects, composition, shot motivation, coverage, lighting, scene rhythm, editing, continuity, sound perspective, sound bridges and changing audience knowledge through edits.

**Long-form performance:** evolving character state and relationships over feature-length sequences, distinct character beliefs and audience beliefs, scene-to-scene performance continuity, and retrieval of earlier approved takes.

Use original or lawfully licensed craft references; every imported item retains source, permission scope, attribution and version. Retrieval should be tested before model fine-tuning.

## 5. Film-length memory design

MovieChat/MovieChat+ are relevant **research references** for memory compression and query-aware video selection, not mandated model dependencies. Video consolidation is lossy and cannot substitute for approved story facts or micro-expression evidence. NVP already has scene, shot, take and beat boundaries; use those rather than rediscovering them from video similarity.

Maintain three explicit time axes:

- **Story time:** event order, scene, beat and in-scene state transitions.
- **Production time:** shoot/take event time with provenance and version.
- **Media time:** integer audio sample indices and rational video frame timebases, never floating-point timestamps as authority.

Structured store: project/character/actor/set/prop/event IDs; accepted canon; assertions and lies; beliefs per character and scene; audience knowledge **per edit version**; take lineage; immutable audio/motion/rig/environment hashes; dependencies and stale statuses.

Searchable store: per-scene/beat notes, craft references, reviewed dailies, shot-level keyframe embeddings and numeric movement evidence. Every embedding cites source hash and embedding-model version. Query planner routes exact state to SQL, temporal event relationships to ordered/graph queries, and uncertain semantic/video analysis to retrieval + optional VLM.

A `FilmContextPacket` carries immutable project/context hashes, mandatory canon, relevant scene state, character knowledge, explicit omissions, retrieved evidence citations and token budget. Stale context is rejected or clearly flagged. Summary invalidation follows changed child asset hashes. Never silently promote a VLM observation to canon.

## 6. Typed creative-to-performance contracts (proposed)

### PerformanceCard v0 (AI proposal; director approval required)

- `project_id, scene_id, beat_id, character_id, source_context_sha, card_schema_version`
- `dramatic_objective, obstacle, tactic, subtext, perceived_partner_state`
- `emotional_intent, restraint, beat_boundaries, important_reactions`
- `voice_direction`: pauses, tempo envelope, breath intent, articulation intent; **not** a demand to synthesize physical impossibilities
- `gaze_targets, posture, gesture_intents, interpersonal_constraints`
- `preserve`: dialogue timing, other actor performance, set, props, camera, or specified assets
- `provenance`: model/adapter, prompt and retrieval hashes, proposer, creator approval state

A card is artistic direction, **not** verified motion. Do not represent a coarse emotion label as a complete performance interface.

### PerformanceSource v0 (immutable baked artifact)

Content-address `card_hash, actor/rig ID, dialogue waveform hash, baked facial/body motion-channel hashes, relevant contact geometry, solver/model versions, seed, source assets`. Store the actual baked channels and audio. Camera moves/lens changes create separate `CameraSetup` and `RenderDerivative` referencing the same source. New acting direction creates a new card and child take; never mutate a previous take.

A scene/set change invalidates performance only if it changes relevant contacts or constraints; otherwise re-render may suffice, subject to validation. GPU reproducibility is *not* assumed.

### Control compiler v0 (largest engineering uncertainty)

A deterministic adapter translates an approved card into time-indexed, bounded controls: emotion-strength envelopes if supported, gaze targets/holds, breath events, silence, pose offsets, gesture clip selection and constraints. It must report unsupported controls rather than pretending the synthesis backend obeyed them.

Separate forced speech/phoneme alignment, facial synthesis, gesture/body synthesis, inverse kinematics/rig validation, prop contact and camera rendering. A2F-class systems may accept only waveform + coarse emotion; detailed acting commands require additional authored controls and verified mappings.

### CreativeChangePlan v0

Classify each proposed change as `new_take`, `camera_only`, `set_only`, `audio_edit`, `editorial_only`, or `mixed`; emit exact impacted asset/take IDs, stale dependencies, validation result, and required approval. A model can propose the plan; dependency analysis and permission enforcement remain host-controlled.

## 7. Candidate datasets and use rights — provenance first

**Dataset license labels below are preliminary screening notes, not legal clearance.** Check dataset card, actual license text, performer consent and all third-party sources before access, download, training, evaluation, derived annotations, checkpoint release or commercial use.

| Resource | Relevant signal | Research value | Commercial track |
| --- | --- | --- | --- |
| **InterAct** (HKU) | Two-person acted interactions; audio, face/body movement, relationship and acting directions | High-priority interaction research | **CC BY-NC-SA 4.0** reported; do not use in commercial development, testing or training without specific permission or independent legal basis |
| **IEMOCAP** (USC) | Scripted/improvised dyadic emotion, video, audio, motion, transcripts | Interpersonal behavior and acting evaluation | Agreement and rights audit |
| **BEAT / BEAT2** | Speech/body/face/gesture coordination | Timing and synthesis research | Audit research/noncommercial restrictions |
| **MEAD** | Emotional face/speech, intensity and multi-view actors | Face/voice variation studies | Research/noncommercial restrictions reported |
| **VOCASET / VOCA** | 4D facial movement and voice | Phoneme/face alignment baseline | Check noncommercial terms |
| **CREMA-D** | Emotional acting clips, human judgments | Emotion perception baseline | Check ODbL/contents and performer rights |
| **RAVDESS** | Professional actors, emotion/intensity speech and song | Human ratings and contrastive delivery | CC BY-NC-SA reported; separate commercial permissions |
| **PhysioNet Kinematic Actors Expressing Emotions** | Anatomical nodes and emotional movement | Physical posture/motion evidence | Participant consent/research restrictions review |
| **Original/commissioned acting sessions** | Direction ↔ multiple takes ↔ released motion/audio | Most useful supervised commercial target | Secure specific signed training, redistribution and commercial releases |
| **Synthetic scenes with cleared assets** | Known geometry, timing, invariant ground truth | Deterministic benchmark families | Audit every rig/model/asset license and output rights |

Primary resources: https://hku-cg.github.io/interact/ ; https://sail.usc.edu/iemocap/ ; https://github.com/PantoMatrix/BEAT ; https://github.com/uniBruce/Mead ; https://github.com/TimoBolkart/voca ; https://github.com/CheyneyComputerScience/CREMA-D ; https://zenodo.org/records/1188976 ; https://physionet.org/content/kinematic-actors-emotions/2.1.0/ .

### InterAct separation: no licensing workaround

The intended CC BY-NC-SA 4.0 research route is **genuinely noncommercial research only, where permitted by the full applicable terms**. Publishing weights as open source, using a separate process, a model-to-model API, or calling a research model from NVP does **not** automatically remove NonCommercial obligations. Likewise, "research benchmark for choosing/improving a commercial NVP model" may itself be commercially directed. No InterAct-backed benchmark should be assumed cleared to validate a commercial product merely because it runs in a research repository.

Create two permission-gated data domains:
- **ACTLAB-NC:** research-only datasets, checkpoints, examples and evaluations; access/outputs limited by specific terms; no commercial product dependency.
- **ACTLAB-CLEAN:** original or explicitly commercially licensed material, with verifiable performer rights; training, model selection, release and commercial NVP evaluation allowed **only** as authorized.

No automatic copying of trained weights, samples, generated motion clips, feature embeddings, derived labels, pseudo-labels, teacher outputs, or memorized examples from NC to CLEAN. Generic published methods and non-restricted aggregate research insights can inform an independently developed clean pipeline, but do not assume all derived outputs are unrestricted. Obtain counsel or a license for ambiguous transfers.

### Required dataset manifest (design)

`dataset_id, source_url, version, sha256, license_spdx_or_text, legal_rights_review, allowed_purposes, redistribution, derivative_use, commercial_training, commercial_evaluation, model_weight_distribution, attribution, consent_document_refs, retention_rules, data_domain, reviewer, reviewed_at`.

Default deny on any missing commercial-right field. Store a provenance DAG for downstream examples, checkpoints and evaluations. A model trained on NC sources is not relabeled CLEAN by distillation or having another model converse with it.

## 8. Evaluation program

### Arms

A. General open-weight model, well-prompted; no specialized memory or tools.  
B. Same model + scoped filmmaking knowledge retrieval and FilmContextPacket.  
C. Same model + structured state queries, deterministic constraints and production tools.  
C+. Same as C plus a strong few-shot example pack, to avoid overstating fine-tuning gains.  
D. C+ with a specialized acting/filmmaking LoRA or adapter (trained solely on permitted data).  
E. C+/D with VLM evidence for real rendered acting; evaluate visual observations against movement tracks and human judgments.

Compare on identical held-out projects, scripts, actors, assets and seeds where technically meaningful. Separate model reasoning, source retrieval, control compiler, synthesizer and rendering failures. Pre-register thresholds before running the final held-out test.

### Task families

1. Human direction → PerformanceCard (objective, subtext, restraint, gaze, timing).
2. Same screenplay line, three distinguishable acting interpretations.
3. Partner reaction coherence across two actors and staged contact.
4. Story/character knowledge retrieval across 100+ scenes; no belief leakage.
5. Audience-knowledge differences between alternative edits and J/L cuts.
6. Camera-only re-render preserving baked performance and dialogue exactly.
7. New-take revision changing targeted acting channels, preserving untouched channels.
8. Speech/phoneme/viseme synchronization and breath timing.
9. Rig/IK collision/foot-contact and plausible physiological constraints.
10. Shot/acting critique using rendered evidence, with known hallucination traps.
11. Correct refusal, uncertainty, request for human direction or unsupported-backend control.
12. Runtime/VRAM stability, cold starts, recovery, cancellation and artifact persistence.

### Objective metrics

- Immutable source hashes and zero unintended mutation of approved take.
- Correct affected-asset classification and staleness propagation.
- SQL/ground-truth story fact and character/audience belief recall; false-fact rate.
- Alignment offset in audio samples and rational frames; report latency and errors.
- Targeted gaze/gesture/pose changes vs. unchanged channels, measured against frozen source.
- Collision, joint-limit, foot-lock and prop-contact violations.
- Task success, tool call correctness, model/tool failure breakdown, memory/VRAM, runtime.
- Data license/provenance gate precision: default-deny, reject seeded NC-to-commercial transfers.

### Human metrics

Blinded qualified reviewers score intention fidelity, credible reaction, emotional nuance, continuity, unnatural motion, dialogue delivery and how much editing the director needed. Include inter-rater agreement, multiple scenes/actors, diverse performances, reviewer provenance, randomized display order and uncertainty intervals. No claim that facial-action-unit match alone proves compelling acting.

**No invented benchmark numbers or pass statuses.** Set provisional targets only as experimental hypotheses: adapter improvement over C+ should be statistically supported, creator correction time should decline, and "no unintended edits" must not regress.

### Split and contamination controls

Group holdouts by project, screenplay, scene template family, actor/voice ID, creator and production. Never split adjacent takes or near duplicates across training and test. Check text MinHash, scene-graph hashes and audio/visual fingerprints. Keep hidden out-of-distribution cases inaccessible to trainers.

Use human-curated dramatic labels; generate ground-truth geometry/timing/invalidation with deterministic host tools, not AI authority. Record annotator disagreements and perform adjudication; generated training examples without independent review are not automatically labeled truth.

## 9. Minimum end-to-end acting demonstration

**Goal:** prove pipeline integrity, not professional-level acting quality.

- Two virtual actors, 8–12-second exchange, one short line each, 24 fps with 48 kHz audio.
- An ARKit-compatible facial rig (or documented equivalent), pinned voice/audio, known scene geometry.
- Director-approved PerformanceCard for Take 1, actual forced alignment, facial animation via a permitted inference engine or explicitly documented fallback, and authored/retargeted body clips if necessary.
- Freeze **baked** PerformanceSource, hashes and provenance for Take 1.
- Render both medium shot and close-up from the same exact PerformanceSource. Assert byte-identical baked motion/audio references.
- Create Take 2 with new card, change restraint and gaze holding; preserve original dialogue and untargeted environment/actor state.
- Verify phoneme/viseme timing, gaze delta, constraints, lineage, hash invariants, recovery and no unauthorized mutation.
- Have independent blinded filmmakers judge whether the intended difference is perceptible; report disagreement and small-N limitations.

No model may claim to support detailed throat/tongue, fine emotional control or full-body partner-aware motion until independently observed and tested. A generated video that merely looks convincing does not satisfy persistence/invariance gates.

## 10. Candidate model and training experiments

- Baseline first: an appropriately licensed 7–9B general open-weight instruct model for acting-direction interpretation; a larger model as a stronger inference reference.
- Visual analysis: an independently licensed Qwen-VL-class or similar VLM; inspect video and compare observations with explicit movement/evidence tracks. MovieChat-style token consolidation is a research hypothesis, not an exact-memory layer.
- Speech: forced-alignment tools (MFA/WhisperX class) subject to license and platform verification.
- Facial motion: evaluate Audio2Face-class models only after weights, performer rights, output-control limitations and AMD/CPU inference tests.
- Gesture/body: benchmark authored retargetable clips and mature animation tools before research-licensed neural gesture models.
- Fine-tuning: supervised LoRA/QLoRA on reviewed, legally cleared original direction-to-plan examples. No adapter warranted unless D beats C+ reliably.
- Train locally only after exact AMD R9700/ROCm/Windows or Linux package tests, peak-VRAM sweep, 100-step training experiment, checkpoint/restart and resource protection. Do not treat throughput estimates as measured.
- Training data and research lab should be separately permissioned; no mandatory runtime dependence of NVP on a Python training stack.

## 11. Rights, consent, and release operations

Secure written rights for every real performer's likeness, voice, motion and any AI training/weight redistribution or commercial use. Consent must be specific, revocable where promised, and not substituted by a dataset hosting license. Film scripts, recorded dialogue and music may carry separate third-party rights. Log attribution obligations and license notices. Audit outputs for memorization, private likeness reproduction and unauthorized derivative uses.

A public research model is **not automatically open-source** in the unrestricted OSI sense when its training dataset is NonCommercial. Distinguish research code, checkpoint weights and training data licenses on release pages. Avoid publishing NC-trained checkpoints before verifying model-specific licensing implications.

For any proposed commercial evaluation using InterAct or derived models, first secure explicit permission or independent legal assessment for that precise use. This document is engineering risk management, not a definitive legal opinion.

## 12. Work breakdown and acceptance gates

| Gate | Work | Done only when |
| --- | --- | --- |
| ACTLAB-00 | Inventory actual NVP source and license requirements | Exact HEAD SHA + module/CI evidence; candidate datasets each classified permitted/blocked/unknown |
| ACTLAB-01 | Dataset provenance and domain isolation | Manifest validator blocks all seeded prohibited NC→CLEAN transitions; test coverage |
| ACTLAB-02 | Epistemic story/belief/audience-time schema and FilmContextPacket | 100+ scene tests, edit-specific audience knowledge, stale/context omission diagnostics |
| ACTLAB-03 | PerformanceCard and change-plan schema | Round-trip schema/version tests, no AI-origin approvals or direct writes |
| ACTLAB-04 | Performance-control compiler proof | One targeted gaze/restraint change measured; unsupported inputs reported; original take unchanged |
| ACTLAB-05 | Two-actor frozen-take demonstration | Exact motion/audio hash invariants, sync/rig checks and independent human scoring |
| ACTLAB-06 | Benchmark A/B/C/C+ with clean data | Reproducible held-out scores, tool-failure separation and VRAM/cost measurement |
| ACTLAB-07 | Optional clean-data LoRA + arm D | Dataset/split/legal audit, frozen baseline and statistically supported added value |
| ACTLAB-08 | Visual evidence / arm E | Provenance of each observed claim; comparison to numeric tracks and human critique |
| ACTLAB-09 | Optional NVP-facing adapter | Creator approval, permissions, worker cancellation/recovery, clean license metadata, general-model fallback |

**Immediate next implementation:** ACTLAB-00 source and rights inventory, followed by ACTLAB-01 manifest validator. Do not start training or link an NC checkpoint to commercial NVP before these boundaries are real. Existing B14/audio acceptance continues on its own branch and must not be blocked by ACTLAB.

## 13. Decisions to be made explicitly

1. Separate repository for eventual open-weight Film Intelligence model vs. this NVP research design branch.
2. Is the research lab genuinely noncommercial, and who may access its datasets/results?
3. Which InterAct activities are permitted by the specific license and rights review? Is additional commercial benchmarking permission needed?
4. Which acting motion rig is authoritative for the first demonstration? What channels are supported?
5. Which vocal/face engine has verified AMD/CPU execution and commercially suitable output rights?
6. Are canonical character beliefs and edit-specific audience knowledge in the current StoryBible, or must they be added?
7. What is the reproducibility boundary for frozen performance assets and derivative renders?
8. Which human filmmaker reviewers will author labels and score outcomes?
9. Who approves dataset rights and performer consent for commercial model release?
10. Which exact empirical results would justify funding or distributing a specialized adapter?

## 14. Research references and cautionary notes

- InterAct project: https://hku-cg.github.io/interact/ — reported CC BY-NC-SA 4.0; check actual distributed license and terms.
- Creative Commons BY-NC-SA 4.0 legal code: https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode
- Creative Commons NonCommercial interpretation: https://creativecommons.org/licenses/by-nc-sa/4.0/
- MovieChat research project: https://github.com/wenhaochai/MovieChat — useful memory-consolidation concept; code/weights/data need independent license evaluation.
- FilmAgent research: https://filmagent.github.io/ — role-coordination reference, not demonstrated professional acting synthesizer.
- Audio2Face platform/model: verify current official NVIDIA model card, terms and runtime before selecting.
- Existing handoff source: prior NVP Film Intelligence / Claude engineering review, 2026-11-04. The review explicitly states it **did not inspect the NVP repository** and flags model/dataset/platform assertions as needing primary-source verification.

### Notes carried forward from the design discussion

- NVP is a workspace; the filmmaking AI is modular.
- The chief competitive feature is translating the human filmmaker's vision into actual tool-directed production, not claiming an omniscient AI.
- MovieChat's relevance is coherent feature-film-length visual context, not unbounded raw-context processing.
- Acting craft and human physiology require different evidence and controls; learned synthesis does not replace biomechanics or human artistic judgment.
- Original/commissioned paired retakes with director annotations are a priority future **commercially clean** dataset.
- Human director approves creative changes. Failed constraints are evidence to adapt or ask, never permission to silently rewrite a take.
- Treat an NC-trained research model, its outputs and its interactive API as **not automatically commercially cleared**; do not use a second model to launder rights.
- Do not let enthusiasm for a computational technique outrun strong deterministic baselines, measurable benchmarks and explicit licensing evidence.
