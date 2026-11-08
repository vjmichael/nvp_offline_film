# WO1 — Integrated native regression closeout

**Started:** 2026-11-07 (America/Phoenix). **Branch:** `nvp/wo1-integrated-native-regressions-20261107`.
**Review:** [draft PR #94](https://github.com/vjmichael/nvp_offline_film/pull/94), stacked on WO6 PR #93.
**Acceptance:** OPEN until the **exact-head** Linux/Windows tests actually complete successfully.
No implementation change or queue status establishes installed or film acceptance.

## Five required regression families

| Gate | Previous evidence | Submitted code/test | Remaining acceptance |
| --- | --- | --- | --- |
| WO1-HANDLE | WO4 run 42396285587 Windows Python 3.11 reported `UNLISTED_HANDLE_LEAKED` based solely on `GetHandleInformation(HANDLE)` with a parent handle value. | Replaced test with child `WriteFile` of a unique marker to the parent-owned pipe and parent `PeekNamedPipe` readback plus host-side positive control. Existing `STARTUPINFOEXW` three-stdio-only `HANDLE_LIST`, suspended-start and Job Object containment unchanged. | Real Windows 3.11/3.13: zero marker bytes through unlisted handle; job before first code instruction; descendant kill/cancel/timeout. If real pipe data leaks, repair runtime rather than weaken acceptance. |
| WO1-SLATE | WO2 runs 42346237241 (SLATE-05) and 42346237206 (SLATE-06) failed native admission with `Creator approval missing, changed or revoked`. | Added categorical **native-private** refusal-stage diagnostics covering consent/spec, source ticket, worker SHA, sealed manifest, camera, and PENDING cache evidence. Existing creator and SHA checks are unchanged; both source fixture tests now identify unexpected admission stage. | Execute real Linux/Windows OpenUSD native fixtures; fix the specifically reported denial, retaining all fail-closed invariants. **Current root cause is unverified; not accepted as repaired.** |
| WO1-MATERIALX | Older WO4 DATA-AV job 42396285556 failed when a legitimate original roughness/metallic image map was connected to the approved OpenPBR scalar. | The newer WO6 parent already contains the restricted allowlist for exact `MtlxMap_Metallic`/`MtlxMap_Roughness` paths while checking the authored source scalar. Added a regression that verifies legitimate sources and refuses cross-wired channels and altered defaults. | Run actual USD 26.11 fixture and varied PBR source; original WO4 branch remains historically red, not rewritten to green. |
| WO1-PCM | Product `FinishedFilmPlayer._pcm24_window` originally allocated one verified 24-frame region, but a 4-frame request starting at 22 crossed the segment and could return too few bytes. | Explicitly split requests at segment boundary, then concatenate only original 48 kHz PCM24 bytes. Test uniquely labels original frames 22–25 and confirms all four exact stereo sample windows, two and only two MXF unwraps, adjacent cache reuse and stop invalidation. | Exact-head native Python tests, installed MXF PCM24/Canvas/WebAudio acceptance and sustained measured performance remain separate. |
| WO1-WO6 | Recent native desktop bridge moved worker execution off pywebview IPC but had an unbounded queue and allowed already-queued notices to start after the UI was closed. | Bounded queue (64), truthful `QUEUED_NOT_DISPATCHED` on overflow, discard unstarted in-memory notices on close, recheck closing state before admission, redacted host-private failure category; test blocked child, resource denial, overflow, native exception and close/restart non-replay. | Run exact native matrix and installed real NVP.exe tests; verify active worker/whole-tree behavior after actual process death, explicit task retry grants and creator-UI status. |

## Exact-head test entrypoint

`.github/workflows/nvp-wo1-integrated-regressions.yml` checks Windows 2025 and Ubuntu 24.04, Python 3.11/3.13, genuine OpenUSD 26.11, source-verified test data, and these suites:

- `tests/test_nvp_supervised_codec_process.py`
- `tests/test_nvp_slate05_preview_native.py`
- `tests/test_nvp_slate06_geometry_native.py`
- `tests/test_nvp_wo2_pbr_channels.py`
- `tests/test_nvp_wo5_finished_playback.py`
- `tests/test_nvp_wo6_desktop_bridge.py`

**No external executable, model, browser or CI fixture receives the authority to create a creator approval.** Source FilmIndex, original Take, authored world and delivered DCP must remain immutable. A locally successful unit test does not claim physical Windows app, real feature, theater/speaker measurement, or cinematic acceptance.

## Exit criteria

1. All four **exact-head** WO1 jobs complete successfully; no skipped relevant Windows handle test.
2. Earlier WO2 SLATE-05/06 denial has an evidenced root cause and a code fix, not merely better diagnostics.
3. Real Windows restricted handle-list and Job Object native tests prove actual process isolation.
4. MaterialX source-map, PCM24 cache boundary and WO6 lifecycle positive/negative tests pass across the specified platform matrix.
5. Any new real native defect is fixed and the final head is rerun; document exact passing run/job evidence.
6. Do not close WO2–WO6 production/installed/creative/cinema release gates simply because this integrated WO1 regression sprint passes.
