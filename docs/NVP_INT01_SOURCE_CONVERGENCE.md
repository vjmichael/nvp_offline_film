# NVP INT-01 — Cross-branch source convergence inventory

**Date:** November 12, 2026. **Scope:** reviewed independent source integration, **NOT** a merge or accepted full installed application. **Status:** **INT-01A inventory COMPLETE; INT-01B DA-03 Linux filming host/custody source integration AUTHORED (focused native acceptance pending); INT-01C Studio/G06→G09 ABI convergence NEXT**.

## Stable evidence and source heads

| Source | Exact Git head inspected | Integration ownership |
| --- | --- | --- |
| Canonical data-first [PR #74](https://github.com/vjmichael/nvp_offline_film/pull/74) | `e0f729b3d68d33f9b2c280edce378b46091b9d65` | Original FilmIndex, DA-03 host filming/custody, exact Film Time and native source-AV authority |
| Lu-hosted NVP adapter [PR #154](https://github.com/vjmichael/nvp_offline_film/pull/154) | `fcd73d2cfc07903b7857b273139bbb79e91b064e` | Source-bound proposal-only Lu model status and requests; **not** a working installed Lu/NVP DLC |
| G03 film-home/security [PR #155](https://github.com/vjmichael/nvp_offline_film/pull/155) | `03a260d1ee4a6a07d273e301f5d003bc33d3897d` | Director home, project access, native Window/WebView, Windows vault / AppContainer foundations |
| G09-F source | `b83ac974ae4295da32e09ea8e6ebe739c71f912b` | Native working-film packages, transport and distribution (not a theatrical master) |
| W1-F accepted runtime | `8f743784167893005e99f06cca3d35ccda8e64f3` | Four-job automated native W1-F pass [43170210995](https://github.com/vjmichael/nvp_offline_film/actions/runs/43170210995); one-frame synthetic encrypted installed acceptance |
| Current Wave 1 branch at inventory | `070ae84fa71ef1e405a9628a1da678cd56b28a64` | Stacked G04–G09 source and Wave 1, plus updated master ledger, **not** merged with canonical PR #74 |

The Wave 1 source tree has **894** Git blobs at this inventory and the inspected canonical PR #74 tree has **763**. Wave 1 has **152 different/new** paths versus canonical (of which **135 are new**), but **21 canonical paths are missing or modified** in Wave 1. **These are tree SHA differences, not a count of semantic conflicts or an invitation to cherry-pick everything.** Recheck moving PR heads before any write.

## Initial concrete interface conflicts and missing source

1. **DA-03 original filming custody is not converged.** Canonical PR #74 contains **four files absent from Wave 1**:
   - `backend/nvp_filming_host_bridge.py` — gated source freeze after trustworthy Linux process-tree exit.
   - `backend/nvp_filming_linux_session.py` — actual Linux worker/cgroup host lifecycle.
   - `tests/test_nvp_filming_host_bridge.py` — source publication and failure-race contracts.
   - `tests/test_nvp_filming_linux_session.py` — independent lifecycle/recovery contracts.
   These must be inspected for production API compatibility and selectively integrated with W1-D/E, not copied into an unreachable module and called complete.
2. **Seventeen shared canonical files have different SHA identities**, including `backend/nvp_api.py`, `backend/nvp_studio.py`, `backend/nvp_worker_containment.py`, `backend/nvp_filming_cgroup_custody.py`, `backend/nvp_slate08b_native_camera_ipc.py`, `tools/nvp_desktop_alpha.py`, `frontend/src/App.jsx`, `packaging/nvp-alpha.nsi`, and the native/DA-03 acceptance tests. Resolve host lock sequencing, grant lifetime, worker idempotency, SQLite and FilmIndex ownership, launch/IPC policy, exact tick and audio bounds before claiming compatibility.
3. **G02 Lu proposal adapter is NOT in the Wave 1 source tree.** Draft PR #154 introduces `backend/nvp_lu_g02_port.py`, `tests/test_lu_g02_film_port.py`, and a G02 workflow. The adapter's own contract states that the host callbacks are simulated/provided by an external trusted Lu host: no connection, loaded GGUF, Workspace lifecycle, model readiness or OS approval is proven. Port and integrate only after verifying an actual Lu-owned host boundary. Never let an NVP API bypass native Lu authorization or start a second GGUF process.
4. **G03 security and UI branches have shared, modified implementation.** Wave 1 has subsequent encrypted source-custody, one-use desktop approvals and installed one-frame AppContainer work; do not overwrite them with the earlier G03 branch. Cross-check `nvp_g03_live_store.py`, `nvp_api.py`, `nvp_project_access.py`, `nvp_g03_windows_appcontainer.py`, `FilmmakerHome.jsx` and the protected/ordinary render routes for no plaintext downgrade, replay or stale revocation.
5. **G04–G09 and Wave 1 code stacks already coexist in Wave 1**, but W1-F tested a scoped subset, not an owner-directed whole-film sequence. New Wave 1 files relative to G09-F include sealed microphone and reel workers, durable streaming original PCM, tests and the W1-F exact-head gate. The actual New/Resume → Scene → immutable Take → Edit → 720-frame Export → real viewer is **INT-02**, not demonstrated by W1-F's synthetic one frame.

## INT-01B — Canonical filming host and process-custody source integration

**Implementation scope (not a native acceptance claim):**

- Copied the exact canonical DA-03 `nvp_filming_linux_session.py` host-owned Linux worker session and `nvp_filming_host_bridge.py` original PCM source publication boundary from the inspected PR #74 branch into Wave 1, preserving original source types and the `NativeSceneSoundCapture` / `FilmIndex` publication API. The canonical original 306-line host-bridge and 388-line Linux session contract tests were included.
- Restored canonical `LinuxFilmingCgroup.verify_still_empty()` in Wave 1. The source class was missing a required fresh post-reap kernel observation; previously consumed empty-tree receipts cannot authorize publication after a group has been repopulated. Linux session shutdown verifies original pinned group identity, whole cgroup kill, child exit, and a **fresh** post-reap empty-group observation under one bounded deadline.
- Added a trusted host-only `NativeSceneSoundCapture.capture_supervised_linux()` and `launch_and_capture_supervised_linux()`. The host binds attach-before-exec of the *actual retained* worker to spooled source PCM, freeze metadata, independent kernel custody, and subsequent source publication. A failed cgroup admission tries recovery using only the original retained group and child, then refuses publication even if cleanup succeeded; no normal `Popen` fallback.
- New `tests/test_nvp_int01b_host_integration.py` checks the service-to-host delegation, explicit worker launch and session identity, failed-admission reconciliation/denial, fresh kernel observation and rejection of unconsumed cgroup receipts.
- **Deliberate separation:** G06's in-process PortAudio callback, W1-D ordinary SQLite five-second capture chunks, and W1-E AES-GCM sealed originals do **not** become cgroup-owned workers merely by importing DA-03 code. DA-03's canonical `FilmIndex` and G06's `Studio`/scene SQLite remain distinct source stores until **INT-01C** provides exact source/identity and secure authorization reconciliation. Linux cgroup process-tree custody is **not** a file/network sandbox; G03 encrypted-film Linux native execution remains denied without independent confinement. Windows W1-F AppContainer worker/grant logic is unchanged.
- **Evidence:** Changes have been source authored but **no** exact-head INT-01B pytest/native cgroup, Linux delegated host run, physical microphone, or installed cross-branch acceptance was executed in this source-first task. Prior W1-F automated acceptance is bound only to its older accepted source SHA.

**Next:** **INT-01C** reconcile `FilmIndex`/Studio ownership, SceneID/ActorID/PCM sample and Film Time mapping, host grants, G06 original Takes and G09 source-window readers. Only wire an end-to-end G06 publication seam after the trusted source-origin and authority differences are resolved; do not mistake a previously passing canonical DA-03 test for a unified NVP film.

## Source and integration task order

| ID | Work | Exit evidence |
| --- | --- | --- |
| INT-01A | Static Git head/path comparison and source ownership decisions | **DONE**: this reviewed inventory, no source mutation |
| INT-01B | Canonical DA-03 Linux host bridge/cgroup session vs Wave original sample/Take producer | **Source authored:** host-owned attach/kill/reap/fresh empty-group verification, FilmIndex capture facade, original canonical tests and focused integration tests; runtime acceptance and G06 cross-store mapping remain open |
| INT-01C | Reconcile Studio/SQLite, G06→G09 source windows, W1-E AES-GCM and W1-F fixed worker entrypoints | A single original source ABI and project-specific authorization through installed host |
| INT-01D | Lu Workspace PR #154 host/proposal seam vs current Film Home/creative stage; G03 security | No second GGUF loader; observable ready/busy/failure; NVP cannot model-approve native actions |
| INT-01E | Merge-free reviewed source handoff preparation and codebase-wide integration test inventory | Full set of exact-head tests and true native/installed evidence only after accepted source changes |
| INT-01F | Product/physical release acceptance handoff | Explicit human/GPU/physical results separately; **no auto-merge or release** |

**Next source action:** execute **INT-01C** Studio/FilmIndex and G06/G09 source ABI reconciliation while retaining INT-01B's unexecuted native custody tests, five-second immutable capture and Windows AppContainer fail-closed worker. No autonomous source publication without an actual host custody receipt. A Linux cgroup alone is not a private encrypted-film filesystem/network sandbox. G02 and G03 remain separately blocked by actual Lu host integration, historical protected film recovery and physical owner gates.

**Excluded by policy:** no blind rebase of PR #74, no CI-green status transplant, no silent file deletions, no FFmpeg active workflow, no unrestricted native/model privileges, no Docker, no automatic OS consent.
