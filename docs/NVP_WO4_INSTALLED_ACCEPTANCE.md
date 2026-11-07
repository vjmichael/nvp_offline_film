# WO4 — Installed NVP/Lu DLC Production Acceptance

**Status: OPEN.** This is an operational acceptance protocol, **not a claim of a completed physical installation**. The NVP developer FastAPI/Vite harness is not the installed Lu NVP DLC. A GitHub CI runner does not certify a user's physical Windows/Linux workstation. Do not bypass real user authorizations or treat the manual NVP window lock as OS security.

## Implementation baseline

- Real native Linux 2K picture + PCM24 + full DCP at former exact head, run 42359312665: passed complete independent picture/audio decode and FilmIndex receipt. Does not certify calibrated theatrical picture, hours-long throughput, or a full install.
- The single independent supervisor and SQLite WAL/FULL journal have actual process crash/restart tests. Native Windows/Linux Python 3.11/3.13 tests must pass again at the updated exact head.
- Native resource planner partitions 2–3 hours into contiguous 24fps Film Time reels and computes conservative 2K/4K scratch space. Multi-reel feature publisher and FilmIndex journal were implemented; multi-hour native throughput is **not** measured.
- NativeProductionHost launches a standalone supervisor and offers project-scoped read-only reconnect. This is trusted host-library functionality, not a public HTTP/browser endpoint or a finished installed Lu IPC binding.
- Suspended-first Windows CreateProcessW is now wired before Job Object assignment; child-side Windows CI tests are the first acceptance gate. Restricted startup handle inheritance, protected service identity and signer validation remain separate release gates.
- Native bundle audit requires each declared distributed component's exact version, binary SHA, upstream license and notice hashes, and declared transitive dependencies; a complete platform dependency scan and legal review remain mandatory.

## Physical release acceptance protocol

1. Build an actual Lu/NVP DLC installer with protected native host runtime, OpenJPEG, CineCert/asdcplib and transitive runtime DLLs or shared libraries. Bundle exact upstream full LICENSE/NOTICE texts for every redistributed dependency. Record installer, codec and manifest SHA-256, versions and OS builds. Never invent upstream license contents.
2. Install under normal Windows/Linux account privileges without a command-line procedure. Verify trusted project grants, singleton supervisor, host service lifecycle, no remote/cloud dependency, and uninstall/reinstall preservation of original Digital Takes.
3. From installed NVP, freeze a real OpenUSD temporal Take and approved FilmIndex edit, then authorize picture, PCM sound, multiple ordered reels and final feature assembly through an authenticated native UI, not browser-supplied consent flags.
4. Export at least two different real reels, then a two-hour and extended three-hour 24fps feature with 2K/4K profiles. Record CPU/GPU peak, RAM resident sets, source and J2K/MXF SHA, disk budget, elapsed wall-clock time and throughput. The assembly remains light; no full decoded feature in RAM.
5. Start an export; manually lock NVP using Home/slide controls, minimize/close the editor, use another app, optionally lock the OS session, then reconnect. Neither UI lock nor editor closure cancels work. Verify the same immutable assembly and supervisor job continue.
6. Explicitly request in-flight cancellation through native authorized host. Verify actual child process tree termination on both platforms; Windows must demonstrate Job Object membership before the child's first instruction, Linux complete process-group cleanup. Denied cancellation and app lock never stop a job.
7. Force failures before/after J2K write/fsync/checkpoint, picture/sound MXF, DCP copies, XML, atomic publish, FilmIndex commit and final SQLite commit. Preserve uncommitted output; only full independent source/UUID/hash review permits creator-approved orphan adoption. Partial or changed stage remains REVIEW_REQUIRED.
8. Independently validate SMPTE/DCI, picture/color/peak/loudness, exact 24fps sync and cinema hardware ingest. These specialist acceptance gates are separate from engineering acceptance.
9. Repeat restart, approved pause/cancel, normal completion and installed-app uninstall. Archive test machine metadata, exact Git head, native CI, package SHA and release license notices.

## Seven package statuses

| Task | Implementation progress | Still required |
| --- | --- | --- |
| 01 Supervisor recovery CI | Fixed requeue report to include interrupted RUNNING only | Exact-head Win/Linux result |
| 02 Orphan final DCP | Full SHA/UUID/source checked, creator-approved adoption of verified complete folder | Real installed crash fault injection |
| 03 Multi-reel | Approved FeatureJournal, bounded-memory multi-reel CPL/PKL/AssetMap and FilmIndex checkpoint | Real multi-hour scale and native E2E |
| 04 Long-form resources | 2/3h exact Film Time capacity planner, disk admission and 4K short native pilot | Physical sustained 2K/4K throughput/energy/disk |
| 05 Desktop background | NativeProductionHost and read-only project reconnect | Actual Lu DLC IPC/autostart/installed GUI |
| 06 Windows and packaging | Suspended-first Job Object launcher, exact binary/license/notice manifest checks | Windows CI, restricted handles, actual signed installer and upstream notices |
| 07 Installed E2E | Protocol, backend recovery/cancel tests and UI manual-lock tests | Physical install→export→lock→reopen→cancel/crash/restart→uninstall |

**Boundaries:** The finished film is an immutable approved assembly of source decisions; user access to the NVP window is separate from worker permissions. The convenience lock must never create or cancel jobs. No FFmpeg. Unknown or unlicensed native components cannot ship.
