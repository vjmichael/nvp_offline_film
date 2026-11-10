# USD-FILM-01T — Durable original 720-frame film, 01S batch admission and exact original PCM

**Current status: SOURCE-CODE AND FULL-FILM NATIVE ACTIONS COMMITTED.**
The **720 genuine Cycles pictures and 30s movie have NOT been observed as
produced** unless the exact-head native CI/installed host job executes
and independently passes. The GitHub Windows/Linux and Blender workers
of 01S/01Q/01R were inspected while still QUEUED, with no native test
logs/artifacts to judge. Source inspection repairs are not accepted
as independently verified OS results.

## Non-negotiable data-first direction

One original 30s OpenUSD actor/prop/light/physics/sound performance.
Any number of permitted virtual viewpoints (1–96 in the current
bounded implementation) can observe it. A director-approved 01Q
FilmIndex `edit` revision chooses ONE source camera per output film
frame. Neither 9 × 720 camera rolls, another performance, nor 90
independent simulation runs are required. **One film has 720 selected
24fps frames and ONE original 48k PCM source mix.** Never infer image
frames from authored camera names or manifests.

## 01Q ↔ 01S integration

`backend/nvp_usd_film01t_selected_queue.py` is a direct facade over
the existing:
- `ReviewedSelectedViewFilm`: exact source-bound 01Q Blender/Cycles
  output, journal, PNG/ActorID and camera verification;
- `NVPAdaptiveShotService`: measured RAM/CPU/VRAM and the existing
  bounded director-selected Auto/manual shots-per-batch;
- `DurableShotBatchQueue`: SQLite WAL/FULL original plan/ticket state;
- `BlenderWorkerSupervisor`: the sole NVP native process launcher,
  containment, memory admission, timeout/cancellation and journal.

One 01T plan ID is deterministically derived from **actual project,
edit ID/revision/document SHA, original performance and USD SHA,
and first-party reviewed Cycles quality-profile SHA**. Source identity
is reverified against the immutable original 01E Take, 01M rig, 01O
retimed native USD source and 01Q selected camera for every one of the
720 output frames. A different edited source/quality profile creates
a distinct queue and worker job namespace; no stale frame or shader
cache is silently accepted.

01T registers exactly **90 unique eight-frame tickets**:
`Source_0000` through `Source_0712`. Each has a genuine original
source evaluation (01S `lofi` stage) followed by one separately
authorized genuine 01Q Cycles worker (01S `hifi` stage). The total
180 durable ticket states are displayed as progress. Low-fi stage
does actual `pxr` evaluation of original actors and selected camera
poses across all eight original film frames and SHA-verifies the USD
source; this is **source geometry verification, NOT human visual
approval or a fake rendered preview picture**. The 01R WebGL UI
remains the actual cheap visual source viewport.

A native approval scopes an **exact group** of 1–64 selected source
tickets: immutable performance/edit/profile SHA, stage, 01S manifest
SHA, exact start frame and original camera IDs/selected frame SHAs.
Each claimed ticket and each real Blender worker receives its own
fresh, host-minted, single-use scope within the approved group.
A 12-shot group can run one job at a time on a low-power PC.
Available hardware and outstanding NVP RAM/VRAM reservations are
rechecked before every claim; a group is NOT a bypass around resource
admission. This is sequential bounded production, never 12 Blender
executables forced into 2GB RAM. GPU mode requires a separately
verified compatible renderer/device and is not auto-enabled by Lu's
GPU telemetry.

## Durable crash/recovery

SQLite `RUNNING` claims left after a host crash become
`INTERRUPTED`; the queue cannot silently restart or reuse the former
approval. A genuinely completed original source result can be
**adopted** without rerendering ONLY if the exact original attempt,
original-source ticket SHA, actual native 01Q journal/8 PNGs and
independent descendant-process custody pass. `DurableShotBatchQueue.
reconcile_verified_completed` is the narrow transaction. A true
low-fi CPU geometry check had **no native worker** and can be
independently re-evaluated from OpenUSD. A Blender job that has not
independently proved OS custody stays blocked. Unverified file
existence or stale journal text is never called a completed frame.

Each successful eight-frame Cycles chunk is independently re-opened
through 01Q's SHA-pinned inputs/script/Blender audit, actual PNG
decoding, 01Q selected cameras/ActorID pose and original Film Time
evidence before it can complete the durable hi-fi ticket. On
final conform **all 90 native results are independently reverified
again**, not merely counted from SQLite.

## Installed NVP UI / native consent

The existing installed WebView2 trusted WO5→WO6 native bridge (not an
HTTP writer) now includes the `OriginalSelectedFilmDesktopMixin`:
`film01t_preview_queue`, `enqueue`, `status`, `advance`, `poll`,
`reconcile`, `conform`. Source SHA and native OS approval are
checked BEFORE dispatching the background worker group; the
background thread is not permitted to create its own creator
approval. All new capabilities reuse NVP's existing
`NativeSlatePreviewHost.supervisor`; no new process manager or
unreviewed external program operations are authorized.

Director tab **22 · Direct the data** now includes real 01S native
source queue preview/approval, actual durable progress reopen, native
source-group approval, and full movie conform only after 180 actual
source/hi-fi tickets have succeeded. The browser cannot send file paths,
command lines, worker binary IDs, bearer tokens or fabricated
`creator_approved` to any of those native operations.

## Real 30-second movie production

`OriginalSelectedFilmBatch.conform` first re-verifies all 90 actual
Cycles chunk results and the immutable 720-frame original edit. It
gathers exactly 720 picture PNGs, then uses the existing 01Q/01P
FFmpeg/FFprobe conform: lossless FFV1 MKV at 24fps; exactly ONE
original 30s 48kHz mono PCM16 sound mix derived from the frozen
source sound events, authoring gain and sample timing. Native final
audio is decoded to raw PCM and compared against the exact source mix
hash (1,440,000 mono samples). The completed film receipt contains
the final movie SHA and explicitly does NOT grant creative acceptance.

A previously gathered original picture set may be reverified and
reused when a director denies the first final export; no original
native image is silently overwritten. The film output is in the
host-owned production runtime, not a user-supplied browser path.
A finished film is not claimed until `verified_film_receipt.json`
and decoded original PCM/picture checks pass.

## CI and actual artifact

`.github/workflows/nvp-usd-film01t-native-full-30s-film.yml`:
1. Native Win2025/Ubuntu24.04 Py3.11/3.13 tests exercise true `pxr`
   original actor/camera 8-frame evaluation, actual existing 01S
   FULL-sync queue, source-dependent original approval, restart,
   interrupted preview reconciliation and no fabricated Cycles success.
2. React 01T director source/queue interface tests and Vite production
   build.
3. A separate **real** Ubuntu24.04 host downloads the official Blender
   5.2.3 SHA-pinned binary, native OpenUSD, FFmpeg/FFprobe.
   It freezes the original Donut/Box/Sphere/Craft 30-second performance
   with nine optional source views and a single original recorded tone
   (technical **fixture** soundtrack); performs 90 01T low-fi source
   groups and **90 actual protected eight-frame Blender/Cycles CPU
   chunks** at 320×180 and 8 samples, checking a frame-four camera cut
   between two angles; resumes a previously completed group across a
   host reopen; independently verifies all 720 original pictures and
   exports source-selected FFV1+PCM film.
4. On real pass, artifact
   `USD-FILM01T-GENUINE-30s-original-720-Cycles-selected-picture-and-PCM-UNREVIEWED`
   contains `original_30s_data_first_film_with_sound.mkv`, source
   receipt, original audio proof, and sampled genuine Cycles contact
   sheet. The actual **creative direction, sound quality, lighting,
   continuity, materials, camera treatment and film master status
   still require human visual/listening review**.

**Gates OPEN:** complete exact-head native CI jobs/results/artifact,
real installed Windows WebView2 editing + safe cancellation and
post-power-loss worker custody proof, low-spec performance
measurements, longer scene resource testing, actual comparison of
low-fi source vs high-quality real footage, and director picture/audio
acceptance. The optional 6480-frame nine-full-camera-roll test is not
a normal-film blocker.

Source implementation is not an executed original film.

## Consolidated 720 real frames + PCM acceptance handoff (2026-11-09)

The genuine 720-selected-frame first-party Cycles pipeline exists: one continuous original 30-second actor performance, nine source viewpoints, one original source-selected view per frame, 90 bounded 8-frame protected native jobs, independent durable SHA re-verification, exact original 48kHz PCM conform and FFV1 lossless edited output. It does not render 9x720 unused viewpoint rolls. The previous old-head [run 42570891151](https://github.com/vjmichael/nvp_offline_film/actions/runs/42570891151) **FAILED** across all six jobs: original 01E world Take parsing rejected a 32-hex StoryBible ActorID with an incorrect FilmIndex object-ID rule; that validation is now corrected in the passing 02M-H foundation at the new branch head. Old React 01T source queue tests also had four interaction failures, not yet re-run at this integrated head. Real 720 Cycles frames and 48kHz audio master remain OPEN. This new isolated branch retains a complete original 360-minute Blender acceptance workflow but restores **manual-only** dispatch until genuine CAM-FX-05 source camera rendering acceptance succeeds. The file is prepared, not executed. Avoid false `human_approved` claims; physical Windows creative/dialog and local 7B+ GGUF remain separate gates.
