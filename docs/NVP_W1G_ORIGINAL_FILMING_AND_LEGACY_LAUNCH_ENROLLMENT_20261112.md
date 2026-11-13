# W1-G / DA-03 — Original filmmaking and legacy native launch release enrollment

**2026-11-12, source integration stage.** Branch `nvp/int02-w1g-native-film-package-20261112`, no merge/release authorization.

## Concrete unmanaged launch paths found

The prior native package contained an original DA-03 `OwnedFilmingWorker(subprocess.Popen)` which deliberately verified direct-child exit only. It never proved grandchild or Windows Job custody. The Linux original uses a distinct delegated cgroup-v2 attach-before-exec + original group kill/empty proof and is not a Windows release fence participant. The original Windows source-publication bridge previously accepted **only** Linux sessions. Earlier scene/rigging/blender inspection and motion paths (`nvp_blender_acceptance`, `nvp_retarget`, `nvp_rig_motion`, `nvp_foot_blender`, `nvp_plantar_blender`, `nvp_plantar_anatomy_blender`) used direct `subprocess.run`. A retired browser WebM/FFmpeg STT service used direct `Popen`, and the legacy FFmpeg color pipeline used direct `subprocess.run`.

These paths were distinct from already supervised production audio/mixing, delivery, color, source-window, native edited-film and protected-worker hosts that use `backend.nvp_worker_containment.launch_contained`.

## Source work

- `backend/nvp_filming_windows_session.py`: original Windows filming worker is created **suspended**, assigned to the original OS Job Object before it runs, and holds the global Windows release slot as well as the original `WorkerHostLease`. `stop_and_verify` kills the original Job, verifies both direct worker exit and kernel `ActiveProcesses == 0` before release. The original lease remains held until Take publication returns or fails. No PID/JOURNAL reconstruction accepted.
- `backend/nvp_filming_host_bridge.py`: the existing immutable PCM spooling and deep-snapshot publication sequence now has an exact Windows counterpart `finish_windows_recording_and_freeze`; OS custody is required even after malformed input or recorder cancellation. The worker's original lease stays held through `capture.capture`, preventing an upgrade race with the source commit.
- `backend/nvp_filming_worker_custody.py`: Windows now **refuses** the retired direct-child-only `Popen` wrapper; Linux's explicitly limited prior behavior is preserved. Corresponding legacy tests skip the retired Windows path, and real Windows negative/positive tests cover the new original Job mechanism.
- `backend/nvp_w1g_legacy_blender_launch.py`: previous calibration/rigging Blender `subprocess.run` sites have been moved to one host adapter. Windows uses the original `launch_contained` suspended Job/128-slot admission and kernel-zero reaping; stdout/stderr are bounded local temporary files, never unbounded pipes, shell or unbounded child trees. Linux keeps the prior standalone acceptance command behavior; **not** a Linux production cgroup attestation.
- `backend/nvp_stt_service.py` and `backend/nvp_color_ocio.py`: retired FFmpeg/browser media adapters now refuse unmanaged Windows process launches; original source-native PCM, USD and native picture remain authoritative.
- `tools/nvp_w1g_launch_surface_audit.py`: AST-based source audit of the backend rejects any unreviewed `Popen`, `subprocess.run`, `os.spawn`, `os.system`, `asyncio.create_subprocess` or hidden import aliases. The explicit Linux-only and Windows-blocked legacy exceptions are reviewed and pinned by markers. This is a **source code gate**, not independent Windows kernel proof.

## Native test gates

`tests/test_nvp_filming_windows_release.py`: launches an actual contained Windows filming worker, denies release mutation while it runs, verifies stop-before-publication and original PCM spool, checks original lease lifetime and error cleanup. `tests/test_nvp_w1g_legacy_blender_launch.py`: verifies real Job-covered Blender-style command exclusion while active, bounded output and later release. `tests/test_nvp_w1g_launch_surface_audit.py`: requires exact complete runtime launch audit and proves injected direct subprocess calls fail source review. All are added to exact-head native Windows/Linux and Windows packaged smoke workflows.

## Honest remaining gates

These integration changes must pass the consolidated **new head** native and installed Windows test matrices. They do not create a signed native worker package or legal redistribution approval, do not certify physical EFS key recovery, do not perform real creator-authorized upgrades, and do not generate the sustained 30-minute/three-hour film. There are independent filming journal/restart reconciliation and physical power-loss acceptance requirements. The shared launch fence protects **instrumented Windows native workers**, while the original uninstalled/unsigned runtime must never be misrepresented as OS-authenticated release-grade. No original immutable Take is rewritten by this source enrollment.


## Reconciled native process adapter and durable post-crash admission gate

Parallel source integration added `run_owned_subprocess` and connected further color, character, source-window, camera, DCP, motion and media inspection adapters to the same Windows suspended Job Object. The release implementation uses **one** shared adapter, not a competing second supervisor.

A native privacy defect was identified during reconciliation: the first adapter revision staged original stdin and decoded media output to unencrypted `TemporaryDirectory` files. The reviewed replacement uses bounded in-memory Win32 inherited pipes for stdin/stdout/stderr, preserving exact PCM/bytes without creating plaintext spool files. The inherited handles remain under the original Job Object until `WindowsJobProcess.close()` proves zero descendants; a Windows release slot remains held throughout.

`OriginalWindowsLaunchJournal` is attached directly to **every** `launch_contained` Windows worker, not just one native tool group. `PREPARED` is durably written before CreateProcess, `RUNNING` after original Job assignment and resume, and `TREE_REAPED_VERIFIED` only after native Job zero-descendant evidence and process-handle closure. The production upgrade authority independently scans the canonical original process journal root, refusing incomplete or unknown entries even after a hard host crash releases kernel file locks. A real Windows hard-host-death fixture proves the original `RUNNING` receipt survives after all child processes are killed and the admission lock becomes available; only that throwaway fixture may clean its own journal. Production cannot auto-clear an uncertain worker from its PID.

The legacy source audit continues to reject unregistered backend launch calls. The kernel and source checks do not replace real creator authorization, signed executable/redistribution provenance, physical disk EFS recovery acceptance, or a completed filmmaker-approved film.
