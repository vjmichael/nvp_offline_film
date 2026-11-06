# NVP AUDIO-01F — Native creator-authorized picture/sound mux

**Implementation status:** Committed to `nvp/stack02c3b14-picture-conform-20261104`. **Windows Job Object and full real Blender integration CI pending.** Do not report acceptance without exact-commit job logs.

## End-to-end host boundary

`NativeAudio01FHost` in `backend/nvp_audio01f_native_host.py` reuses NVP's B14 native authorization and resource architecture:

1. Read immutable, project-scoped B14 technical picture and AUDIO-01E audio revisions from FilmIndex.
2. Independently verify actual edited movie and published WAVs/underlying chunk receipts **before presenting the creator approval request**.
3. Ask the native desktop's trusted creator-policy callback to approve the exact project, picture SHA, audio SHA, technical-review presentation ID, output destination, RAM budget and unapproved status. No model/web-supplied callback is an authority.
4. Persist a SHA-256 sealed worker plan under a unique native job directory and a durable, non-overwriting grant row in the existing TaskLedger SQLite database.
5. Add an immutable `ApprovedTaskBindings` queue entry. A claimed task cannot execute until current grant, creator decision, exact plan digest, worker executable digest and original source revision SHA checks pass again. Revocation refuses queued execution.
6. Use NVP's existing `launch_contained` (Windows Job Object; Linux strict delegated cgroup by default), resource admission and `wait_guarded` watchdog to run `tools/nvp_audio01f_native_worker.py`. Only the worker may call `build_picture_sound_preview` after native admission.
7. The worker produces a real 24-fps/48-kHz MOV, binds its exact picture/audio/timeline revisions in FilmIndex and writes a technical-only unapproved completion receipt.
8. **Do not trust worker exit code or receipt alone.** The host independently calls `verify_picture_sound_preview`, replays original indexed source verification, FFprobe/FFmpeg decode checks and compares the sealed worker receipt with the immutable FilmIndex result before marking the TaskLedger job SUCCEEDED and persisting result SHA.
9. A restarted host can independently reverify the completed result against its immutable FilmIndex record via `verify_completed`. Creator approval events are intentionally not restored as authority for starting another job.

## Native test coverage

`tests/test_audio01f_native_authorization.py` exercises creator-denied admission, queued approval and creator revocation, changed sealed worker plan, and a new host that lacks prior ephemeral creator approval. It uses mocked expensive picture/audio preflight verification to isolate **authorization-contract** behavior; it is not a genuine media render test.

`tools/nvp_stack02c3b14_real_conform.py` now invokes `NativeAudio01FHost` instead of calling the mux directly: its real Blender-produced edited ProRes picture, two independent PCM stems and indexed WAV mix go through native task admission, OS containment, resource watchdog, independent output verification, and post-restart `verify_completed`. That Blender test explicitly uses non-strict Linux process-group mode because hosted CI does not offer delegated cgroups; it does not satisfy the deferred strict Linux guardian gate.

`.github/workflows/nvp-audio-windows-job-object.yml` runs the authorization contracts and separately launches and terminates an actual contained FFmpeg mux inside Windows Job Objects. The full B14 Windows/Linux/Blender workflow provides source-grounded end-to-end acceptance.

## Intentional limitations

The current native host does not offer power-loss recovery and transactional cleanup for a partially published AUDIO-01F MOV or FilmIndex result; such a failure remains fail-closed for trusted investigation. It does not expose a safe creator UI event broker by itself: embedding NVP must supply a true creator-authenticated policy callback, not simply return True for arbitrary AI/model requests. Windows OS kill-on-close tests are required but are not considered verified until their exact-head CI results pass.

The present B14 picture conform supports at most 480 frames (20 seconds at 24fps). AUDIO-01F is a **technical review**, not final master, picture lock, automated loudness mastering, or a theatrical delivery. The separate Linux strict cgroup-v2 delegated-guardian acceptance remains OPEN / DEFERRED per user direction.

## Executable pinning hardening

Stage-time preflight resolves the actual `ffmpeg` and `ffprobe` executable paths through the trusted host, computes SHA-256 for each, and saves those absolute paths in the sealed plan and digests in the immutable approved operation. Before admitting native execution, the host recalculates their SHA-256 hashes. Mutating or replacing either tool after the original approval fails closed. FFmpeg is launched without a shell, and the user/model is not authorized to replace the native host's trusted executable selection.
