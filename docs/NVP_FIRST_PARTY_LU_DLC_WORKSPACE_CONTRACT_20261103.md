# NVP Film Workspace ↔ Lu — first-party bidirectional DLC Host API

**Date:** 2026-11-03  
**Status:** Approved design direction; separate Lu host implementation/Windows installed acceptance **not yet delivered**.  
**Platform issue:** [Lu #8 — First-party DLC Host Services](https://github.com/vjmichael/Lu-AI-GUI/issues/8)  
**Lu contract:** [LU-DLC-API-00](https://github.com/vjmichael/Lu-AI-GUI/blob/lu/dlc-api-first-party-host-contract-20261103/docs/LU_FIRST_PARTY_DLC_HOST_API_RFC_20261103.md)

## Decision: first-party NVP is a host-service consumer, not a read-only dashboard

NVP will be both a **Film DLC Workspace** that may run within Lu and an independently runnable film-production application that may optionally connect to Lu as a local AI provider. In either mode it must request **real inference and authorized native host services**, not merely watch model status.

A successfully authenticated AF_UNIX connection is **not** permission to use a model, launch Blender, read film assets or unload Lu's weights. The Lu host owns the AI runtime. NVP owns the film's world/takes, scene layout, Blender/FFmpeg rendering, archive manifests, DCP and film-specific persistence. The common DLC service API arbitrates resources and results without conflating their authority.

**Reconciliation of NVP B4/B5:** The B4 status observer and B5 8-KiB, HMAC-bound one-operation AF_UNIX test host are *proof-of-contract fixtures*. B5 had actual OS-native socket pair tests on Windows and Linux, but the peer was a **simulated Python Lu host**; the accepted Lu alpha had no such public listener. B5 must remain disabled for production use until migrated into Lu's canonical native Protobuf host service. Do not simply append \`load\` and \`unload\` strings to the HMAC status socket and call it the DLC API.

## Two NVP deployment modes — one logical interface

| Mode | Process boundary | How NVP talks to Lu | Who owns resources? |
| --- | --- | --- | --- |
| **Lu Film Workspace** | Vetted first-party host/UI integration | Host service facade via native Rust/Tauri bridge; no local socket necessary | Lu owns model, ANSF, host tickets; NVP owns film production/take state |
| **Standalone NVP app** | Independent local application | Authenticated local IPC adapter to the same Lu services; AF_UNIX only if Windows/Linux security gates pass; named-pipe fallback if necessary | Lu model lease + NVP Blender worker separately accounted; no direct engine access |

Standalone NVP must be able to degrade honestly when Lu is absent: its production data, deterministic render pipeline and explicit alternative model-provider integration remain independent. It must not spawn an old Jan fork or silently replace Lu with unknown tooling.

## Required bidirectional service operations

| Lu service | NVP use | Who decides/effects |
| --- | --- | --- |
| \`catalog.list\` | Discover supported host capability/ABI and film-relevant CEs | Lu reviewed registry; no permission from discovery |
| \`model.list/status\` | Populate local model UI, effective backend, measured RAM/VRAM and ready/busy state | Lu host |
| \`model.admission.estimate\` | Check film-production resource headroom before loading/reconfiguring model | Lu resource guardian; NVP supplies measured Blender tickets |
| \`model.session.acquire\` | Request GGUF/MMProj model session/lease, context and approved profile | Lu host & creator approval; never NVP chooses raw GGUF path/exe |
| \`inference.start/stream\` | Screenplay interpretation, shot breakdown, character guidance, structured scene descriptions, asset planning and multimodal reference analysis | Lu checks request, model capabilities and project/turn scope; streams typed ordered chunks |
| \`inference.cancel/recover\` | Cancel one filmmaker request; resume durable stream/status after UI restart | Lu only for calling DLC's task; no killing foreign worker |
| \`model.session.release\` | Release **NVP's session lease** when authoring job completes | Lu decides whether any shared model can unload |
| \`ansf.query\` | Read explicitly selected source/provenance or production knowledge if creator grants it | Lu read broker, project-scope only |
| \`artifact.resolve/commit\` | Pass file-safe host-admitted script/image/asset references and write user-approved artifacts | Distinct Lu file/ANSF permission; NVP durable Digital Film World remains authoritative |
| \`resources.snapshot/reserve\` | Coordinate Lu model memory and Blender/FFmpeg/GPU workloads | Independent OS telemetry and mutually accounted reservations; no VRAM guesses |
| \`ce.invoke\` | Request a reviewed Cognitum operation when film work needs math, geometry, verification or causal reasoning | Lu routes to Cognitum, verifies typed output; NVP gains no direct CE privileges |

The exact method names are **provisional RFC labels**, not currently implemented calls. Internal Lu \`InferenceFrame\` and \`ToolCall/ToolReply\` may be adapted, but the canonical public DLC boundary belongs to Lu.

## Concrete NVP authoring turn (intended)

1. Filmmaker opens an NVP Film project/take and authorizes a bounded task from a trusted native UI. NVP records source project/take/revision IDs. Lu independently verifies first-party package identity and the exact creator-approved project/session/effect grant.
2. NVP asks Lu for model discovery/status and an admission estimate. Lu checks actual GGUF/MMProj profile, model overhead, context/KV buffers, available RAM and commit, dedicated/budgeted VRAM, and current Lu/NVP occupancy. If pressure is uncertain or unsafe, it queues/refuses rather than launching an engine blindly.
3. NVP requests a **lease** on an admitted model and receives an opaque \`session_ref\`, \`lease_ref\` and effective model profile. Lu may multiplex/reuse the loaded model without giving NVP permission to unload other Workspaces.
4. NVP submits typed scene/take references and prompt/history. Lu validates reference permissions, processes generation in a supervised host queue, and emits ordered output chunks and distinct states/errors. NVP commits accepted structured AI suggestions to an explicitly versioned Digital Film World revision, **never** silently treats an LLM response as a verified rendered frame or user approval.
5. Blender produces actual high-bit-depth scene-linear image/video outputs using NVP's separately host-approved, contained worker and immutable input/output manifests. Film rendering remains deterministic where required; Lu model generation and Blender effects have separate receipts and admission requirements.
6. Creator can cancel the **specific NVP generation** without killing Lu's model or a separate IDE job. Missing reply/worker crash yields \`UNCERTAIN\` and a reconciled host event chain, not a duplicated task or silently lost partial output.
7. NVP releases only its model lease; Lu retains the model if another valid session remains. NVP keeps film artifacts and output custody in NVP.

## First-party is a software trust tier, not blanket execution authority

Even though NVP and Cognitum are the owner's first-party DLCs, Lu must never accept \`first_party=true\` in a model-generated JSON request, arbitrary project string, or guessed AF_UNIX socket as an authority token. Grant origin is trusted Lu UI / authenticated creator project; grants are scoped to model/session/stream, file/memory/artifact, resource reservation, worker-effect and exact type/version. They expire and can be revoked.

**NVP does not require MCP, Docker, shell-first tooling or the Jan runtime.** Its conventional film stack is separately verified, pinned and supervised. No file path, API key, model worker PID or host process kill is exported over the workspace inference contract.

## Resource guardian and model custody agreement

- Lu model workers remain Lu's property. NVP's **ReleaseOwnLease** is not a global unload.
- Lu's guardian owns model load preflight and runtime critical-pressure handling. NVP exposes *measured* resource tickets for Blender, FFmpeg and film compositing to avoid double allocating host RAM/VRAM. One platform cannot promise reliability while silently ignoring the other's reservations.
- Treat RAM availability, system commit and VRAM budget separately. High-bit-depth/scene-linear NVP rendering and GGUF/MMProj model weights may compete on the same GPU, especially on the Windows AMD physical host. Unknown telemetry must produce an explicit unsafe/unknown decision, not a fabricated free-memory figure.
- A model worker failure cannot delete Digital Film World authoritative state or silently corrupt a frozen Digital Take Package. The presentation/render is derived and can be reverified from immutable inputs, not confused with those inputs.
- Force unload, killed workers or resource interventions require Lu's own supervised lifecycle and durable reconciliation, not NVP's socket connection ending.

## Workspace versus CE use of Cognitum

Cognitum is an optional Lu-native Core Extension providing domain computations and evidence; it does *not* need to own the model to serve NVP. When NVP requests a Cognitum computation, Lu verifies that the CE is installed/enabled/authorized and routes the typed request to Cognitum. A computation with zero effects does not inherit workspace file permission, while host-minted ANSF/artifact effects require separate grants. NVP can use the result if Lu's independent verification accepts it. The first-party workspace/CE API stays generic, with no NVP-specific or Cognitum-specific hacks in Lu Core.

## Tests and promotion gates

- **B4/B5 — already shown:** NVP read-only source/status adapter, authenticated single-purpose AF_UNIX fixture and native Windows/Linux test pairs. Their test host was **not** the real Lu desktop. Status-only != inference.
- **DLC-API-00:** Lu-owned generic versioned Protobuf service contract, first-party role/permission matrix, Cognitum/NVP mapping docs; no installed alpha changes.
- **DLC-API-01:** Real Lu Rust/Tauri first-party host SDK with typed discovery/status/inference permission denial; NVP mock-adapter tests are insufficient.
- **DLC-API-02:** Real Lu-owned local IPC listener and NVP native client, verified Windows ACL/peer identity and Linux profile endpoint ownership, replay/cross-project revocation; native OS tests, no assumed AF_UNIX privilege.
- **DLC-API-03:** One real host-loaded GGUF shared safely across two sessions (e.g. NVP Film + IDE), streaming distinct outputs, cancellation isolation and lease release without cross-session unload.
- **DLC-API-04:** Cognitum native calculator evidence through the generic host CE path, with no fake read permission.
- **DLC-API-05:** Actual NVP generation → structured film data and contained Blender execution under joint resource admission; no project data loss, no UI freeze; worker death and restart tests.
- **DLC-API-06/07:** Native Windows/Linux failure injection, installed-app acceptance, session/memory/artifact privacy, revision upgrade, SDK documentation.

[Lu issue #7](https://github.com/vjmichael/Lu-AI-GUI/issues/7) tracks the **missing Windows Job::assign_and_resume_suspended** method in checked-in Lu source. Do not replace safe suspended Job startup with unsuspended launch just to pass CI. The accepted 0.1.0-alpha.2 Windows binary remains a frozen functional baseline; it does not prove a DLC API already exists.

## Cross-repository references

- [Lu platform RFC](https://github.com/vjmichael/Lu-AI-GUI/blob/lu/dlc-api-first-party-host-contract-20261103/docs/LU_FIRST_PARTY_DLC_HOST_API_RFC_20261103.md) / [Lu #8](https://github.com/vjmichael/Lu-AI-GUI/issues/8) is the primary logical host API authority.
- [Cognitum provider alignment](https://github.com/vjmichael/cognitum/blob/cognitum/first-party-lu-dlc-interface-rfc-20261103/docs/LU_FIRST_PARTY_DLC_PROVIDER_HOST_CONTRACT_20261103.md) explains pure computation, Protobuf/evidence and CE dispatch ownership.
- [B5 status-only prototype](NVP_STACK02C3B5_LU_AUTHENTICATED_STATUS_WIRE.md) remains a non-production developmental building block requiring explicit migration into the shared host service API.
