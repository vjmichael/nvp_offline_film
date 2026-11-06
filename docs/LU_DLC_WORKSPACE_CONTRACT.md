# NVP / Lu Film Workspace DLC — canonical integration plan

**Date:** 2026-11-02
**Status:** Architecture reconciliation; proposed NVP adapter, NOT yet installed,
registered, integrated or released.

## Authoritative Lu source

Lu repository: https://github.com/vjmichael/jan_alt

The Lu roadmap on branch lu/windows-alpha-r16-per-model-folders-20261101,
at docs/lu/roadmap.md, places a minimal IDE Workspace before the flagship
NVP Film Studio Workspace in its v2.0 DLC phase. Lu Core is general-purpose
and remains useful when all DLCs are disabled.

The Lu DLC containment contract at
docs/lu/dlc-generic-interface-containment-gate-2026-10-31.md explicitly
names IDE, Film/NVP, Research and Writing and requires their shared Lu-owned
registration, typed IPC, authorization, worker containment and effect journal.
Installing or finding a DLC does not authorize it.

Lu source at src-tauri/lu-core/src/contracts.rs distinguishes
ModuleKind::Workspace from ModuleKind::CoreExtension. A Workspace offers
a separate specialized UI and may declare panels, workflows and tools;
a Core Extension adds optional reusable tools to general Lu chat.
NVP is a **Workspace**.

Lu source at src-tauri/lu-core/src/workspace.rs defines a trusted-host
WorkspaceHost with register/open/suspend/resume/close lifecycle and
active-instance ownership checks. All requests still require host policy
authorization. Registration metadata is NOT a permission grant.

Lu source at src-tauri/lu-core/proto/lu/v1/core.proto defines the versioned
typed ToolCall and InferenceFrame contracts. The current host and broker
must validate types, resources, ownership, task scope and worker requests.

The shared-inference architecture in
docs/lu/lu-development-mode-shared-inference-rfc-2026-10-31.md
(branch lu/ide-dev-mode-shared-inference-rfc-20261031) proposes one
loaded Lu model reused by authorized clients, with foreground priority,
per-task cancellation and resource admission. No DLC may automatically
load a second large model just because it starts.

All above Lu interfaces are **source and design evidence, not proof**
that an external signed NVP DLC is already running on physical Windows.
The Lu containment document explicitly states that Windows arbitrary signed
external DLC launching remains unsupported and requires a separate security
design and acceptance.

## Responsibility boundary

Lu owns:
- Model catalog, loaded GGUF, inference, session and GPU resource lifecycle.
- Trusted workspace registry, instance ownership, scoped permissions.
- Native Protobuf transport, schema/type validation, tool effect grants.
- Signed package admission when implemented; integrity and lifecycle control.
- Effect journal, supervision, cancellation, revocation and worker cleanup.
- Host-scoped project resource access and resource guardian.

NVP owns:
- Idea-to-screenplay collaborative creation and revisions.
- Story bible, continuity, character/prop/set timeline and stable references.
- Specialized film workspace panels and human creative approvals.
- Shot recipes, blocking, acting, dialogue, camera, lighting and sound plans.
- Blender/Unreal/other media worker logic behind Lu-authorized operations.
- Production media provenance, shot versions, editorial timelines and exports.

Lu Core must not embed NVP-specific screenplay or render code.
NVP must not implement an independent privileged dispatcher, model lifecycle
or unrestricted local filesystem/server in production.

## Proposed module interface (not a registered manifest)

Kind: ModuleKind::Workspace
Suggested module ID: nvp.film (not approved or registered yet)
Suggested panel contributions: Story, Screenplay, Production Bible,
Set/Actors, Directing, Shot Review, Timeline, Sound, Export.
Suggested workflows: idea_to_script; script_to_scene; scene_to_shots;
shots_to_edit; edit_to_export.

Suggested tool families (IDs are placeholders, NOT accepted tool definitions):
- nvp.film.story.propose: host model inference, creates a proposal only.
- nvp.film.project.read: read authorized film project data.
- nvp.film.project.commit: explicit revisioned project write.
- nvp.film.scene.layout: bounded geometry/scene-generation worker.
- nvp.film.performance.animate: supervised animation worker.
- nvp.film.render.shot: supervised render worker.
- nvp.film.edit.export: supervised edit/audio/export worker.

Actual registration must use the host's then-current contract version,
approved Protobuf input/output codecs, exact ToolEffect classifications,
host-owned workspace instance and per-task policy. No JSON file or
NVP-declared ID can confer authority on itself.

## Intended operation

1. User installs or enables NVP inside Lu once the DLC package host is ready.
2. Lu verifies package identity, signed bytes, host scope and user grants.
3. Lu opens the NVP Workspace surface within its own desktop.
4. NVP supplies film-specific instructions to Lu's already-loaded model,
   and receives a reviewable creative proposal with provenance.
5. User explicitly accepts or edits screenplay, scene, or shot decisions.
6. Approved production jobs invoke vetted native tool contracts. Lu starts
   contained, supervised production workers with brokered resources only.
7. Lu owns effects, cancellation, worker cleanup and recovery. NVP stores
   project-specific creative and production results with durable references.
8. Render and edit outputs display in NVP's Lu Workspace, not a second app.

NVP must not automatically reload the active user's model, assume an
unauthenticated localhost server, or start a second GPU-resident model.
The heavy video worker competes for VRAM: the Lu Resource Guardian must
queue or throttle jobs and preserve the foreground user's interaction.

## Existing repository code and migration

- backend/nvp_studio.py: reuse story/script/shot database logic, but the
  project storage root must be chosen and authorized by Lu's trusted host.
- backend/nvp_idea_pipeline.py: reuse proposal/approval logic, replacing
  direct model HTTP calls with the Lu model inference contract.
- backend/nvp_model_service.py: development-only standalone server discovery;
  do not ship as the production model manager.
- backend/nvp_api.py: development-only FastAPI adapter, not the DLC host.
- frontend/src/App.jsx: reusable UX prototype, to become Lu Workspace UI.
- Legacy UE5/CUDA services: legacy prototypes; no mandatory NVIDIA runtime.
- benchmarks/nvp_writer_bakeoff.py: local test harness only; final acceptance
  should include the loaded model operating inside Lu.

## Required engineering and acceptance gates

NVP-HOST-00: Do not destabilize Lu Windows alpha; no embedded NVP code.
NVP-HOST-01: Verify signed, enableable/disablable Workspace delivery on
             the target OS before claiming an installed DLC.
NVP-HOST-02: Verify WorkspaceHost registration and active/suspended/closed
             instance authorization with the NVP module.
NVP-HOST-03: Verify shared Lu model inference and task-scoped cancellation;
             no duplicate model weights loaded by NVP.
NVP-HOST-04: Verify project-scoped broker writes, no raw home-file/network
             access, durable effects and revocation behavior.
NVP-HOST-05: Verify isolated renderer/voice/edit worker progress, failure,
             restart recovery, resource budgeting and cleanup.
NVP-FILM-01: Produce a real, editable 60–90-second two-actor scene and export
             a playable file with visible continuity.
NVP-RELEASE-01: Enable/use/disable NVP **inside Lu** without another installer,
                server or model runtime; plain Lu remains functional.

**Implementation policy:** Keep NVP's source/experiments in its own repo.
Develop the film pipeline independently; integrate via Lu's generic
Workspace interfaces when those are verified. GitHub is a repository and
milestone record only, not the development hub. Do not merge into alpha
or change Lu core to special-case NVP.

Lu registry compatibility: all declared tools, panels, and workflow IDs must begin with the `nvp.film.` namespace. The actual Lu host remains authoritative over approved IDs, Protobuf types, effect classes and grants.


## Implementation checkpoint: Lu native bridge v1 (2026-11-02)

Lu draft PR #107 now contains a real host-owned Rust bridge, built on Lu's
generic DLC containment branch. It uses Lu's registered Workspace instances,
HostSessionRegistry/OwnershipStore, native Protobuf, PolicyEngine-compatible
per-operation authorization, existing TrustedInferenceSupervisor, token stream
and task cancellation, SQLite proposal-only persistence and EffectJournal.
The Lu desktop has a trusted Rust-only accessor to its current supervisor,
but **no NVP Workspace has been mounted in Tauri** and no signed Windows
external DLC has been installed or tested.

Do not mix up implementation with runtime acceptance: 13 new Rust tests are
present but not executed, while the existing NVP-side Python tests (32)
passed locally with simulated Lu host operations. Film/NVP remains a DLC
and Lu Core is not to absorb film production logic. The Rust implementation
is an integration branch subject to security/code review before productization.

## 2026-11-05 source-of-truth clarification (do not attempt early integration)

The historical references above describe an earlier Lu Jan-fork development branch and its *proposed* DLC contract. The current independent Lu product source repository is [vjmichael/Lu-AI-GUI](https://github.com/vjmichael/Lu-AI-GUI), whose [current v1.0 design reconciliation](https://github.com/vjmichael/Lu-AI-GUI/blob/main/docs/LU_V1_0_DESIGN_RECONCILIATION_20261103.md) now includes LU-AIW-01 (AI-accessible workspaces and operational continuity). **Do not treat old jan_alt paths as proof of the current shipped Lu interface.** Reinspect exact Lu source and signed/runtime support when actual integration is approved.

NVP remains standalone for the current Windows alpha. The AI-readable adapter and [NVP-AI-01 review](NVP_AI_ACCESSIBLE_ARCHITECTURE_REVIEW_20261105.md) are domain-service preparation only. They must not be used to assume the Lu alpha has a working external Model/Workspace API, add a guessed AF_UNIX endpoint, or request model unload/reload without host-issued authority. Use [NVP engineering-state ledger](NVP_ENGINEERING_STATE.md) to locate current repo/branch, tested artifacts and pending installer gate.
