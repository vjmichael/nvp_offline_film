# NVP — Theatrical DCP compatibility and production-platform end state

Decision recorded: 2026-11-07. **Approved product destination; not a conformance claim.**
Applies to NVP's data-first pipeline, cinema export, other professional exports,
creator-facing GUI, and model-independent AI execution layer.

## 1. The theatrical delivery target

**The default professional theatrical export target SHALL be an interoperable
SMPTE DCP conforming to the SMPTE DCP Bv2.1 Application Profile described in
SMPTE RDD 52:2020**, together with all applicable underlying normative SMPTE
D-Cinema standards, operational constraints and any relevant DCI requirements.

Important wording: **RDD 52 is a SMPTE Registered Disclosure Document (RDD),
not itself a SMPTE Standard.** Bv2.1 is an application profile specifying a
well-tested, constrained, interoperable subset of the SMPTE DCP ecosystem,
not permission to invent a proprietary variant. SMPTE ST 429-2 specifies DCP
operational constraints; applicable SMPTE ST 428/429/430 and MXF/metadata
standards are mandatory where referenced. Revalidate the applicable revisions
and supported features at packaging/release freeze.

Specifically plan and independently verify, to the extent applicable:

- Real native cinema XYZ12/JPEG 2000 essence at supported picture profiles,
  edit rates and JPEG 2000 bit-rate/profile limits; correct color/white
  transformation and externally calibrated mastering.
- SMPTE MXF picture and uncompressed 24-bit/48 kHz cinema sound, proper
  speaker-channel layout and **MCA (multichannel audio) labeling**, not merely
  an unlabeled sequence of WAV channels.
- Required composition information/markers, CPL metadata and extensions
  including the Bv2.1 application-profile declaration where applicable,
  timed-text/subtitle/accessibility behavior, correct reel/asset references,
  PKL/AssetMap naming, UUID/size/hash/namespace/file integrity and exact timing.
- Appropriate encrypted and unencrypted delivery variants; certificate,
  KDM/signature/encryption handling when required by cinema distribution.
- Authoritative source Take/FilmIndex provenance plus clean producer approvals
  kept as **NVP-internal evidence or sidecar reports** without adding arbitrary
  nonconforming required assets to Bv2.1 DCP structure.
- A truly **independent** Bv2.1/DCP validator, second decoder/essence audit,
  and professional cinema-server/projector ingest with picture and audio
  signoff. Internal hashes or a valid CPL never mean certification.

**Required self-reporting:** A package may be labeled "SMPTE DCP Bv2.1
conformant" only after implementing the constraints and obtaining sufficient
independent evidence. Today's WO3/WO4 SMPTE-*style* structural/native wrapping
does NOT meet this claim. NVP itself and theater hardware must not be called
"DCI-certified" merely because NVP can create a valid DCP.

The ultimate user-visible delivery should provide a simple **Theatrical DCP —
SMPTE Bv2.1** choice, honest validation outcomes, and actionable remediation.
More ambitious theatrical profiles may be separate, explicitly identified
targets if standards and actual venue compatibility support them; they must
never masquerade as Bv2.1 when outside its constraints.

## 2. Exceed DCI's baseline *outside*, not *inside*, its interchange limits

NVP is free to surpass theatrical minimums in **authoring, internal signal
fidelity, rendering, creative tools, sound and non-DCP export formats**, as
long as each format truthfully describes its contract. The authoritative
digital film is the immutable original OpenUSD/scene-performance/audio Take,
not a reduced 12-bit DCP frame sequence.

Examples of future NVP output profiles: higher-resolution scene-linear
masters, floating-point OpenEXR, wide-gamut HDR/SDR masters, higher-frame-rate
and high-bit-depth non-DCP media when supported by native encoders/containers,
image sequences, archival intermediates and specialized delivery formats.
Those alternate outputs have their *own* precise color/audio specs,
encoder/decoder validation and reference-display QC; none automatically
qualifies as theatrical DCP or DCI-conformant. The same authoritative film
may produce both compliant Bv2.1 theatrical output and higher-fidelity
non-DCP products, without source mutation or FFmpeg.

DCP compatibility takes priority at its delivery boundary; NVP's creative
quality and non-DCP format ceiling need not be bounded by that boundary.

## 3. Product readiness equals complete workflow, not just a codec

The complete **non-destructive, data-first, accessible filmmaking workflow**
should run from idea/storyboard/script and production planning through
source asset preparation, scene construction, actor direction/performance,
blocking, camera, lighting, audio/room acoustics, live preview and take
capture; into immutable Takes, slate/source catalog, editorial assembly,
color/grade and sound mix; then through final verification and multiple
export targets. Real interactive playback must reflect the source-authoritative
assembly; failed or canceled workers must reconcile after restart; one native
durable supervisor protects long operations and source data.

A *genuine original film of up to 30 MINUTES*, with non-trivial authored
scenes, varied original picture, actor/camera action, sound, edits and
human inspection of intent versus the result, is the creator's intended
initial near-production end-to-end production validation. Synthetic
benchmarks remain technical pipeline diagnostics, never creative acceptance.

**Correction to 2026-11-07 earlier notes:** "30 seconds" was a misunderstood
duration and is superseded. At 24fps 30 minutes is 43,200 presentation frames.
The previous WO5-01 gate in `backend/nvp_wo5_original_short.py` still limits
itself to 720 frames/30 seconds and to a one-reel indexed DCP. **That
implementation does not yet support the requested proof.** Before running or
claiming the real 30-minute creative validation, redesign the gate for
durable approved multi-reel/FilmIndex timelines and bounded streaming
verification, and update native test fixtures. Do not silently relabel
30-second CI or write fake success receipts. This decision is documentation
only; no codec/worker/UI change is authorized by recording it.

## 4. First-class desktop experience

NVP must be usable by someone who has never made a film. The main desktop
application is the *normal* production interface—not a CLI notebook, a pile
of developer utilities, a command-only shell, or a collection of unrelated
wizards. Target:

- Clear project creation/resume, guided first production, non-technical
  terminology where practical, discoverable advanced controls, and sensible
  defaults without hiding professional settings.
- Film-centric workspaces for scenes, actors, camera, takes, editing, sound,
  color and mastering; consistent tool states and single source of truth.
- Responsive real-time previews, easy source vs derived visual comparison,
  accurate progress/ETA and error diagnosis, autosaved non-destructive
  revisions, undo/redo, robust recovery and accessible controls.
- Honest readiness displays: "render successful", "source verified",
  "creator reviewed", "SMPTE Bv2.1 validated", and "external theater tested"
  are **different** statuses. No green indicator may collapse those gates.
- Native runtime/package discovery and single-installer ambitions; no Docker
  and **no FFmpeg** dependency in active NVP pipelines.

## 5. NVP-aware AI execution layer

The AI layer's advantage must be that it **knows how NVP works**, and can
actually use NVP's authorized capabilities, not merely describe instructions
in chat. It should be model-independent, able to run locally when supported,
and implemented as a capability-aware assistant/agent on top of NVP's trusted
native tools and durable production ledger.

**Execution contract:**
1. Discover NVP's machine-readable capabilities and constraints from a
   versioned semantic tool registry. The AI should know exactly which
   project/scene/asset/Take/worker operations are available, their schemas,
   preconditions, expected receipts and safe rollback options.
2. Translate a director's request into an understandable plan with visible
   assumptions and dependencies. Present creative choices and request
   appropriate user decisions rather than silently improvising approvals.
3. Use a host-authorized operation bridge to invoke real native scene,
   authoring, editorial, rendering, audio, QC and export functions—never
   confuse model-generated prose with execution. Tool discovery is **not**
   tool authorization; apply scoped creator grants, isolation and audit.
4. Observe actual success/failure/progress from verified job receipts; report
   what was done, what is partial, what needs user review, and what failed.
   Repair or retry only permitted operations, protect original Takes, and
   support cancellation/reconnection and long-running worker supervision.
5. Ground responses in NVP's actual documented feature state, current
   version, source provenance, project ledger and active jobs. The AI must
   not claim that scene, film, mix or DCP exists until NVP's native records
   prove it. Human authority remains paramount over story, performance,
   edit, grade, final approval and distribution.

A production-ready **AI-assisted first-film experience** should let a novice
describe a scene, inspect/edit the proposed staging, direct a Take, watch
playback, approve changes and create a properly validated output, without
learning internal worker commands. Experts keep detailed direct controls.
The exact future Lu/DLC transport ABI is **deferred** until that interface is
stable; document the semantic contract now rather than prematurely coupling
NVP to one IPC implementation.

## 6. Separate acceptance gates

| Gate | Required demonstration | Today |
| --- | --- | --- |
| Technical pipeline | Native codec, PCM/MXF, package and durable recovery integrity | Partial implementation and synthetic CI evidence |
| Real authored production | One **<=30-minute** original through full NVP workflow; human sees intended film | OPEN / deferred until near-production |
| Bv2.1 package | RDD 52 profile + referenced SMPTE standards, MCA/metadata/timed text/security where applicable, independent validator | OPEN; current structural SMPTE output insufficient |
| Professional theater | Real calibrated audio/video, reference screening and cinema ingest | OPEN / specialist |
| Other high-fidelity outputs | Honest independent non-DCP output-format profile and visual/audio QC | OPEN / per format |
| GUI/usability | Successful novice and professional complete-film workflow on installed desktop | OPEN |
| AI execution | Real capability-aware user-authorized actions with durable receipts and human creative control | OPEN |
| Distributable release | Exact reviewed third-party LICENSE/NOTICE/SBOM, native installer and uninstall acceptance | DEFERRED BUT REQUIRED |

**References (standards, not claims about current code):**
- [SMPTE RDD 52:2020 — SMPTE DCP Bv2.1 Application Profile](https://doi.org/10.5594/SMPTE.RDD52.2020) — application profile RDD, not a new interchangeable standard in isolation
- [SMPTE ST 429-2 — DCP Operational Constraints](https://pub.smpte.org/doc/st429-2/20201027-pub/st429-2-2020.pdf)
- [ISDCF Technical Documents — RDD 52 and audio guidance](https://www.isdcf.com/resources/documents/)
- [ISDCF CPL Metadata Extensions](https://www.isdcf.com/registry/cplmetadataexts/)
- [DCI official specifications](https://www.dcimovies.com/) — DCSS v1.5.1 approved 2026-10-20, CTP v1.6.0; verify later revisions before release

Do not claim a new registered format standard, successful mastering,
theatrical certification or original film production from this design decision.
