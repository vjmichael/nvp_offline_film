> **NVP DATA-FIRST FILMMAKING — GOVERNING PRODUCT DIRECTION (2026-11-03):** NVP builds a persistent, editable **Digital Film World**. The director stages with **low-fi 3D**, captures an **immutable Digital Take Package**, and chooses conventional/AI video and voice engines to produce one or more **versioned Presentation Packages**. A source-aware editor selectively rerenders only affected shots/lines and masters a final **flat 2D film with sound**. Every revision and result is **indexed back to its source**. This is an **accepted architecture, not yet a completed integrated pipeline**. [Architecture Decision](docs/NVP_ADR_2026_11_03_DATA_FIRST_FILMMAKING.md) · [Package and regeneration specification](docs/NVP_DIGITAL_FILM_PACKAGES_AND_REGENERATION.md) · [Master Design v1.1](docs/NVP_MASTER_DESIGN.md).

> **PROD-06E2C3B BVH + FOOT ANATOMY EVIDENCE (2026-11-03):** Native Blender 5.2.3 real-character **triangle BVH floor support** passed Linux and Windows, including independent 12-degree-slope geometry, off-surface refusal and 25 actual corrected toe-marker samples with no penetration. Four-region plantar annotation records now require independently attested reference data and actual imported source mesh geometry; **Cesium Man has no certified heel/MT1/MT5/hallux attachment yet.** [Engineering evidence](docs/PROD06E2C3B_FOOT_ANATOMY_AND_BVH.md) · [NVP Master Design](docs/NVP_MASTER_DESIGN.md).

> **PROD-06E2C3 BOUNDED CONTACT (2026-11-03):** The imported Cesium Man's selected skinned toe-region contact marker was corrected against the **actual approved floor mesh** by modifying thigh/shin IK only. Independent full-take Blender 5.2.3 audits on **Linux and Windows** accepted contact, 25 changed stance leg-frames, 215 preserved noncontact leg-frames, and unchanged actor roots/cameras. **This does not certify heel/ball/toe anatomy or complete gait.** [Evidence and limitations](docs/PROD06E2C3_MESH_CONTACT_CORRECTION.md) · [Master design](docs/NVP_MASTER_DESIGN.md).

> **PROD-06E2B NATIVE ANKLE-LOCK IK (2026-11-03):** A director-approved two-leg stance and knee-pole plan now bakes **real thigh/shin IK** on a separately imported Cesium Man armature and compares pristine versus reopened modified Blender files. Both Linux and Windows Blender 5.2.3 dedicated acceptance steps passed. This is ankle-marker locking, **not verified shoe-sole contact or biomechanical gait**. See [native IK evidence](docs/PROD06E2B_ANKLE_LOCK.md) and [master design](docs/NVP_MASTER_DESIGN.md).

> **PROD-06E2A LEG IDENTITY (2026-11-03):** The eight explicit left/right Cesium Man anatomical joints were independently inspected in native Blender 5.2.3 on Linux and Windows. This proves imported rest-chain identity, **not** active foot IK. See [PROD-06E2A evidence and limitations](docs/PROD06E2A_LEG_IDENTITY.md) and the [NVP master design](docs/NVP_MASTER_DESIGN.md).

> **NVP MASTER DESIGN (2026-11-03):** [NVP Master Design — World-Aware Personal Film Studio](docs/NVP_MASTER_DESIGN.md) is the cross-subsystem product/architecture and gated-roadmap baseline on this development branch. It separates creator requirements, current implementation, future options, and acceptance evidence. Film-production code must conform to it; subordinate specifications do not silently supersede it. The historical proprietary license below remains unchanged.

> **NVP-PROD-01 → PROD-04 development (November 2, 2026):** The film-only
> production path now includes an actual Blender acceptance **runner**,
> durable layered WorldState edits with creator locks and undo, immutable
> licensed local GLB mesh import and packaging, and static actor blocking
> plus measured virtual camera placement. The full local Python suite ran
> **264 tests: 263 passed, 1 skipped** (native Blender).
> **Blender is not installed in the execution host; no .blend or Blender
> render has been verified.** The React directing panel passed JSX syntax
> parsing, not a full Vite production build. See
> [production engineering and gate status](docs/PROD01_TO_PROD04_ENGINEERING_ACCEPTANCE.md)
> and [machine-readable acceptance report](docs/PROD01_TO_PROD04_ACCEPTANCE_RESULT.json).
> This is still a development harness; Lu work remains deferred until v1.0.
>
# NVP — A personal film-making pipeline

> **NVP-WRITE-05 (November 2, 2026):** A project-scoped Story Timeline now
> records creator-approved event ordering, explicit scene time anchors and
> character knowledge. These are used conservatively by the writing assistant,
> with revision checks preventing stale approvals. Lu work remains frozen until
> Lu v1.0. See
> [Story chronology and knowledge](docs/STORY_CHRONOLOGY_KNOWLEDGE_20261102.md).
>
> **Development focus (2026-11-02):** All Lu work is deferred until Lu v1.0.
> NVP continues film-specific development independently, while retaining its
> eventual Lu Film Workspace DLC product contract. This development branch
> strengthens the creator-approved idea-to-screenplay chain and does not
> change the Lu repository. See
> [Creator-approved story context](docs/CREATOR_APPROVED_STORY_CONTEXT.md).

**Product direction (November 2026):** NVP is for *one person with an idea*,
including someone who has never written a screenplay or made a film. Its purpose
is to help that person create their own movie through a guided, offline-first
workflow. Studio terminology is optional, the creator retains final control,
and AMD/NVIDIA/CPU support is a design requirement.

**Canonical product architecture:** NVP is the **Film/NVP DLC Workspace
for Lu**, not a second standalone AI application. Lu hosts model loading,
inference, the Workspace lifecycle, native tools and Protobuf IPC, security,
resource admission and supervised workers. NVP retains its specialized
screenplay, film production, continuity, shot/editing interface and project
data. This repository is the source for that DLC, and the current Python/React
standalone entrypoint is a **development harness only**. It must not be
shipped as a separate NVP consumer installer. See
[Lu DLC integration contract](docs/LU_DLC_WORKSPACE_CONTRACT.md).

**Current working foundation:** local project storage, basic screenplay scene
breakdown, cast/location summaries, editable shot ideas, revision recovery,
and creator-reviewed story drafts. A local OpenAI-compatible writing model can
be connected as an **optional developer-configured service**; no writing model
is bundled or verified on the user's GPU. **Not yet connected:** 3D production,
animation, TTS, rendering, or video export. See [foundation runbook](docs/FOUNDATION_RUNBOOK.md)
and [design contract](docs/SOLO_CREATOR_DIRECTION.md).

The original project description, development history and proprietary terms
remain below.

---

# nvp_offline_film
The neural virtual production (NVP) is a AI coded film studio utilizing a SSM hybrid combining a VLM to realize serious film production. The goal of the creation of a NVP that features data accuracy, consistency and a production bible was made for serious AI film making. The NVP will be an offline model utiling a SSM-VLM and other tools. The NVP has files that will enforce certain rules to ensure consistency. The NVP relies on the demployment of AI agents to perform certain roles like director (orchestrator), DP (director of photography), acting coach, script supervisor, asset management and etc. I have worked on it and may continue to work on it. It features asynchronous process with scaling in mind and potential deployment into a distributed computing environment utilizing interconnected mutlicore and multi-gpu machines.

The NVP was created using Google Gemini. I tried my best to make sure Gemini Pro Extended Thinking would do the bulk of the coding and drafting of JSON files for the frontend and backend of the NVP.

My motivation to make a NVP was due to my frustration with commercial cloud film platforms like RunwayML and Google Flow. I can tell the development team do not have an understanding of how film is made. Serious film making is so much more than AI generated film clips that are 4s to 10s long then stitched together. In actual film making, you have an idea. You can turn your idea into a script or just film it. But in film making, you have a scene. A scene is made up of the location and characters. These characters are the principal actors (actors who say lines) and background actors (actors or people who do not have lines and help create an environment). If there is a script, the script has sluglines. These sluglines contain information on a scene. The script has lines that the principal actors say. Platforms like Google Flow cannot distinguish who says what lines and sometimes you have the wrong characters saying the wrong lines. Theses scenes are building blocks for the film or TV series. Another issue with Google Flow and other AI generated video content is that the characters are not consistant. From use, I noticed that the generative AI videos reason in 2D. You can tell because the characters will walk through objects and this happen consistently where it revealed current generative AI lack 3D spatial awareness. This prompted me to utilize a 3D engine like Unreal Engine 5 (UE5) to build the location and the characters. In the scene, a virtual camera is added to film the screen and convert the data into 2D. In fact, multiple virtual cameras could be deployed.

#                                                           #
#                Software License and TOS                   #
#                                                           #

TLDR - You pay for the executable, you can use it. The source code is off limits. No software subscription, no license fees. One time purchase for lifetime, unlimited use for only one real person and not a ficticious entity. You cannot hold me liable for the stupid stuff you do with this software after purchase.

The Software License? I do not have a formal one but this software is proprietary. I do not grant the license for others to use this software, whether partially or full, without payment. I do not grant permission to access the source code. I do not grant the permission to modify and/or change the soure code. I do not grant permission to share my source code, either in partially or in its entirety, the NVP architect. I do not grant the permission to improve on this code. All these things can be waived only by the dev, Michael Vang.

Only the executiable software will be available for purchase. If the executable software is purchased, I  grant single unlimited, lifetime use, private or commercial, to a single real person. Any ficticious entity or person must purchase the software for everybody that will use it. Real means a real, single human being -  a single human that is not a legal business i.e. sole proprietor or LLC. The word "ficticious" recognizes a business whether sole proprietor, partnerships, limited liability corporation (LLC), corporations (S, C or etc.) or any other legal business formation (benefit corporation, for profit, not-for-profit, non-profit or etc.). This statement is trying to communicate 2 things: 1. if someone wants to use this software, they have to buy their own copy. If a business wants to buy it for their team, they have to buy a copy for everyone that is going to use it. I do not like software subscription models and prefer the retail model of buying once with unlimited use until a person dies. So even if it is 50 years from now and a person wants to install and run it, that person can. I know I could rake in the money with software licenses but I don't really care. 

You do not have the license to pirate this NVP software, whether partially or full software, or use the software without purchase.

You do not have the license to clone or copy this repository at all whatsoever so help you God, on yo momma.

You do not have the license to backward engineer this software or even make an attempt.

When the dev(s), excluding AI, decides to make the software open source, that branch that is open source will be licensed under an open source license. Until then, this repository is private and proprietary.

If the dev(s), excluding AI, has met his/our untimely death, this codebase will fall into the public domain immediately.

You buying this software to use it is assumed to be in good faith. You will assume any and all responsibility, accountability, liability and culpability, good or bad, for how you use this software. I made this software in good faith for personal use and with no ill intent. It is up to you the user to double check to integrity of the software incase someone tampered with it maliciously. And this is my CYA, I am not responsible, accountable, liabilbe and culpable, good or bad, for how you use this software.

Ex.1 if you use my software and make $1 million. You made that and I cannot ask for a cut.
Ex.2 if you use my software for evil, and you get sued and/or get incarcerate or worse things happen, that was your by own choice(s) and you cannot hold me responsible, accountable, liable and culpable for your poor life decision(s) even if you claim insanity.

#                                                           #
#                       Requirements                        #
#                                                           #

It is recommended to get a workstation grade CPU or server grade CPU like an AMD Threadripper Pro and a workstation grade motherboard. You will need as many PCIe lanes as possible. Recommended at least PCIe 4.0 to get started.
System RAM of more than 32GB DDR4 ECC RDIMM or server grade memory modules. A single bit flip error could derail any processing and create errors.
A nVidia Tesla V100 is okay but a nVidia RTX 3090 with a NVLINK would be suitable. Recommended newer generation graphics card or AI accelerator card. Meaning at least a A100 or at least a RTX 5060. The best would obviously be the Blackwell Tesla H200.
A NVMe solid state drive of 2TB.

Hardware Configurations
Running multiple neural networks concurrently alongside Unreal Engine 5 is highly resource-intensive. Below are the specific requirements to avoid Out-Of-Memory (OOM) failures and ensure a seamless, real-time director experience.

Minimum Specifications (1080p / High Latency)
This configuration will run the system, but you may experience latency during voice processing and lower framerates in Unreal Engine.

GPU: NVIDIA RTX 3060, RTX 4060 Ti, or equivalent with 12GB to 16GB VRAM.
VRAM Budgeting: UE5 (~6GB) + XTTSv2 Base (~4GB) + faster-whisper INT8 (~3GB).
CPU: Multi-core processor (e.g., Intel Core i5 12th Gen or AMD Ryzen 5 5000 series).
System RAM: 32GB DDR4.
Storage: PCIe Gen 3 NVMe SSD.
Recommended Specifications (4K / Real-Time Inference)
This configuration provides the intended seamless, low-latency "touchless" experience.

GPU: NVIDIA RTX 3090, RTX 4090, or RTX A6000 with 24GB+ VRAM.
VRAM Budgeting: 24GB provides ample headroom for UE5 asset caching, XTTSv2 peak generation (~10GB), faster-whisper, and your localized VideoMamba Vision SSM without context switching.
CPU: Intel Core i9 13th/14th Gen or AMD Ryzen 9 7000/8000 series (Required to handle asynchronous I/O and continuous FFmpeg memory decoding without blocking).
System RAM: 64GB DDR5 memory.
Storage: PCIe Gen 4 or Gen 5 NVMe SSD (Required for rapid initialization of heavy model weights and daily version control).
Required Software Dependencies
Windows Deployment
Ensure the following are installed and properly configured in your Windows environment before running the Start_NVP.vbs orchestrator:

Operating System: Windows 10 or Windows 11.
Core Engine: Unreal Engine 5.x.
Backend Environment: Python 3.10+ (with pip and venv recommended).
Frontend Environment: Node.js (v18.x or higher) and npm.
System Libraries & Accelerators:
FFmpeg: Must be installed and added to the Windows System PATH variables for on-the-fly WebM to raw PCM audio decoding.
NVIDIA CUDA Toolkit & cuDNN: Explicitly required for hardware-accelerated local model inference.
Linux Alternative Deployment
For developers deploying on Linux (e.g., Ubuntu 22.04 LTS), the backend services run natively with superior performance, but Unreal Engine 5 configuration requires additional steps.

Operating System: Ubuntu 22.04 LTS or equivalent Debian-based distribution.
Core Engine: Unreal Engine 5 for Linux (Must be compiled from source via the Epic Games GitHub repository; pre-compiled binaries are not provided by Epic).
Environment Managers: Conda or standard Python venv.
System Packages: Install FFmpeg via package manager: sudo apt install ffmpeg.
