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
- **Not yet implemented/accepted:** genuinely independent supervisor service, durable job journal/worker leases and exact crash-recovery tests; native OS-lock API; optional sleep inhibitor; verified installed app.
- **Priority:** WO4-LF01 persistent supervisor + bounded resource and authorization contract; WO4-LF02 file-spooled picture/MXF pipeline; WO4-LF03 native OS-lock optional adapter and installed app lock acceptance; WO4-LF04 universal crash recovery; WO4-LF05 sustained native export acceptance.

No FFmpeg reintroduced. Do not mark this work order production-closed because the lock interface works or because an earlier three-frame codec test passed.
