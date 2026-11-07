# NVP — One Durable Production Supervisor and Manual Workspace Lock

**Creator decision: 2026-11-07.** This document is normative for WO4-LF01–LF05 and later long-running production tasks. The implemented lock UI is a first increment. The durable out-of-process supervisor and native optional operating-system lock are **not yet accepted**.

## Core distinction

The creator wants a **single durable NVP Production Supervisor** for rendering, picture and audio mastering, JPEG2000, MXF/DCP packaging, and later other deterministic long-running tasks. A full film is an *immutable, approved assembly of source identities and time-based decisions*, never a single giant in-RAM buffer or a mutable source recording.

**Locking the NVP window is a convenience, not authentication and not the job supervisor.** Manual locking does not authorize, pause, cancel, destroy, or modify any production job. The user can leave NVP unlocked, minimize NVP and use other software while work runs. Locking the operating-system session is **separate and optional**. No default automatic lock and no mandatory screen takeover.

### Implemented manual lock UI (WO4-LF03-A)

- In the desktop frontend header, explicitly press **Lock NVP**.
- An app-owned full-window modal covers the NVP editor; the existing editor remains mounted and inert while the modal is displayed.
- Unlock by pressing the visible **Home · Open NVP** button or completing the **Slide to unlock NVP** slider. Either is a manual user action; neither requests credentials.
- State persists only in the browser/webview **session storage** so an accidental refresh does not automatically open the workspace. This is not secure state storage or a protection against users who can control the computer.
- Lock does not start, pause, cancel or terminate native workers; it does not lock the desktop, inhibit sleep, manipulate power settings, affect other programs or automatically save uncommitted edits.
- A convenience lock does **not** prevent an authorized OS user or external process from viewing or altering local files. Host authorization for cancellation, project deletion, overwrites, and tool/worker capabilities remains mandatory.
- `frontend/src/WorkspaceLock.jsx`, `WorkspaceLock.css`, `WorkspaceLock.test.jsx` and `App.jsx` implement this. `.github/workflows/nvp-workspace-lock-ui.yml` tests interactions and builds the bundle on native Windows/Linux. Installed-app native acceptance remains open.

### Future explicit OS lock (WO4-LF03-B)

A separate **Lock computer** action may be offered **only** by a trusted native desktop host with a verified OS-lock capability. It must never be triggered implicitly when clicking **Lock NVP** or when starting an export. Do not expose an inert button, send OS commands from browser JS, or guess a native bridge method name. OS lock availability/error must be shown truthfully; if unsupported, the user may use Windows **Win + L** or their Linux session lock. An OS lock must leave the production supervisor running where the platform allows. Automatic sleep prevention is a separate, user-understood power policy, not a substitute for job checkpoints.

## Proposed production lifecycle

1. **Submit:** Host resolves and pins exact immutable assembly revision, Take/scene/temporal/audio/color revisions and SHA receipts; records output profile, resource policy, authorization and scratch-disk budget. Separate edits cannot silently change a submitted job.
2. **Admit:** One trusted local supervisor obtains an exclusive SQLite-backed job lease and starts supervised native workers. There is one scheduler and one authoritative durable journal rather than independent ad hoc recovery databases per codec.
3. **Execute:** Incremental render→color→J2K→MXF work proceeds from bounded, file-backed segments. Native workers are supervised by OS-specific process ownership and containment; the GUI does not own their lifetimes.
4. **Checkpoint:** Commit verified segment manifests after flushing durable outputs. Keep hashes, source-dependency revisions, exact Film Time ranges, worker/build identifiers, byte counts and the last safe commit boundary. A ledger row without durable output does not count as complete.
5. **Recover:** On restart, stale worker leases are reconciled. Rehash and inspect completed segments; stages or outputs without trusted receipts are classified as **REVIEW_REQUIRED**, never silently deleted or promoted. Resume only verified remaining ranges.
6. **Publish:** Durable final no-replace staging→published transition, followed by FilmIndex registration and independent DCP checks. A published-but-uncommitted directory is not an approved presentation. Physical cinema acceptance remains an external gate.
7. **Cancel/pause:** User must explicitly request cancellation/unload through the native host. It is a job state transition with cooperative worker termination, subprocess tree cleanup, durable receipts and explicit recovery semantics. The app-level lock provides no cancellation permissions and cannot itself block host recovery/admin actions.

## Recovery/power/AFK acceptance

- Close/minimize/reopen NVP frontend: the supervisor keeps a running job alive and reconnects the UI without changing its authorized immutable assembly.
- **App lock ON:** job state, worker leases, progress, checkpoints and output bytes stay identical to app lock OFF. The user can continue to use other software. Unlocked NVP can view job progress.
- **OS lock ON:** the approved job continues if the OS session, process, power and storage remain available. No assertion that it survives actual sleep/hibernate, abrupt power loss or forced shutdown without recovery.
- **GUI crash:** worker process supervision must belong to a genuine separate native host/service (Windows service/helper or Linux systemd user/service), not merely a React component or a child that disappears with the UI. Not implemented by the current UI-only lock.
- **Worker crash/power loss:** verify last committed checkpoints and rebuild only unfinished segments. Explicitly test both pre/post-fsync, pre/post-atomic-publish and pre/post-FilmIndex-commit windows on native Windows/Linux.
- **Two-hour-plus feature target:** the assembly remains lightweight; no assumption that two hours of decoded pixels/audio fit into RAM. Verify sustained 2K/4K rendering, scratch capacity, downstream MXF file streaming, bounded RAM and 3-hour+ film-time edge cases.
- **Process/privacy policy:** no network requirement, no cloud account, no AI model held resident merely to encode. Inhibiting system sleep while an active approved export runs is opt-in and must be released afterward. Never suppress necessary OS security updates or forced shutdown.
- **Protection separation:** UI convenience lock is not a security boundary; supervisor authorization and OS account privileges are separate from the lock. Accident prevention must not be advertised as a defense against malicious local users.

## Status and follow-on implementation

- **Implemented, submitted for native UI CI:** manual app lock/unlock, session-scoped UI state, screen-reader dialog and inert underlying controls.
- **Implemented as first LF01 core (native CI acceptance open):** separate Python supervisor entrypoint, SQLite WAL/FULL durable job journal, exact approved source-assembly and segment SHA binding, exclusive Windows/Linux supervisor lock, per-segment worker ownership, read-only integrity worker and explicit host-authorized cancel/review retry. A real separate-process process-kill/restart suite has been submitted, but production codec workers and installed daemon/service integration are not yet accepted.
- **Not yet implemented/accepted:** installed Windows/Linux supervisor service/host launch + UI reconnect; OS child-process containment/termination for codec workers; general output-job journaling and checkpoint/publish recovery; native OS-lock API; optional sleep inhibitor; full feature-length encoding.
- **Priority:** WO4-LF01 persistent supervisor + bounded resource and authorization contract; WO4-LF02 file-spooled picture/MXF pipeline; WO4-LF03 native OS-lock optional adapter and installed app lock acceptance; WO4-LF04 universal crash recovery; WO4-LF05 sustained native export acceptance.

No FFmpeg reintroduced. Do not mark this work order production-closed because the lock interface works or because an earlier three-frame codec test passed.


## WO4-LF01 executable first increment (2026-11-07)

Implemented native modules: `backend/nvp_production_journal.py` and `backend/nvp_production_supervisor.py`. First **actual executable** task is `VERIFY_APPROVED_MEDIA_V1`, which streams SHA-256 over read-only, host-approved media without writing original files. This deliberately precedes full J2K/MXF production jobs: the editor is not trusted to select arbitrary native executables or publish outputs on its own.

**Journal contract:** a trusted host must provide a real `FilmIndex` instance, an existing immutable exact-revision `edit`/`presentation`, its stored SHA-256, contiguous bounded `start_tick`/`end_tick` source spans, absolute host-approved paths, per-segment SHA/size receipts and an in-process creator authorization callback that accepts the exact operation scope. The callback gets a copy of the scope, never an authorization boolean supplied by a webpage. The journal persists a canonical manifest SHA, source dependencies, segment states and event trail in SQLite WAL with synchronous=FULL. New POSIX production journal directories are owner-private; actual Windows ACL packaging remains outstanding.

**Native supervisor process:** the standalone `python -m backend.nvp_production_supervisor serve --state-root ABSOLUTE_DIR` entrypoint holds a single OS advisory file lock via `flock` on Linux or `msvcrt.locking` on Windows. The UI process does not own its lifetime, and no localhost network port is opened. The `once` command is available for deterministic native acceptance. Future installed Windows helper/Linux systemd-unit registration must use a trusted host and packaged runtime; users are not expected to install/operate the finished application via CLI.

**Safety:** each segment is claimed transactionally under the single supervisor owner token/PID. Work is a bounded-size read-only source scan, with verified digest and byte count committed in a separate transaction. Long scans refresh a native owner heartbeat. A cancellation request requires a distinct authenticated host callback and cannot be generated by the manual NVP screen lock. A completed verification job is `VERIFY_COMPLETE`, **not** a DCP, a rendered movie or a certified cinema master.

**Failure/recovery:** an interrupted read-only scan is safe to requeue under a new exclusive supervisor owner; previously verified evidence is rehashed on restart and mismatches become `REVIEW_REQUIRED` without deletion or automatic repair. A reviewed source retry requires fresh explicit host approval and the restored original SHA/size. Unknown output-producing worker types cannot be auto-replayed. The verified event history is bounded for the native host's future UI. SQLite journal presence is not a substitute for filesystem durability tests or independent DCP acceptance.

**Submitted native Windows/Linux acceptance:** `tests/test_nvp_production_journal.py`, `tests/test_nvp_production_supervisor_process.py` and `.github/workflows/nvp-production-supervisor-native.yml`. Tests create real NVP projects/FilmIndex assembly revisions, submit jobs, verify single ownership, denied authorization/cancel, three-hour Film Time manifest sizing, tampered source review and restored-SHA retry, and run **actual separate native interpreter processes**, including `os._exit(79)` after claiming a segment, restarting into the same durable database, and proving the same source bytes survived. A second concurrent supervisor fails on the OS mutex. Native tests were **queued at submission**; no unobserved pass is claimed.

**Next LF01 acceptance:** exact-head four-platform CI (Windows/Linux Python 3.11/3.13) and actual failure repairs, native installed service/autostart and UI status stream, proper OS process-tree containment for a first codec worker, and binary/license release packaging. LF02 picture/MXF output-publishing journals and large-feature workload integration remain separate work; no claim of full AFK cinema export from the initial read-only verifier.
