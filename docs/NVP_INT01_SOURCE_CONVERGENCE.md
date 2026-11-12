# NVP INT-01 — Cross-branch source convergence inventory

**Date:** November 12, 2026. **Scope:** static Git object/file SHA inventory, **NOT** a merge or accepted full application. **Status:** **INT-01A inventory complete; INT-01B actual source/ABI reconciliation OPEN**.

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

## Source and integration task order

| ID | Work | Exit evidence |
| --- | --- | --- |
| INT-01A | Static Git head/path comparison and source ownership decisions | **DONE**: this reviewed inventory, no source mutation |
| INT-01B | Canonical DA-03 Linux host bridge/cgroup session vs Wave original sample/Take producer | Typed lifecycle/FilmIndex/PCM adapter; no false process custody; focused tests |
| INT-01C | Reconcile Studio/SQLite, G06→G09 source windows, W1-E AES-GCM and W1-F fixed worker entrypoints | A single original source ABI and project-specific authorization through installed host |
| INT-01D | Lu Workspace PR #154 host/proposal seam vs current Film Home/creative stage; G03 security | No second GGUF loader; observable ready/busy/failure; NVP cannot model-approve native actions |
| INT-01E | Merge-free reviewed source handoff preparation and codebase-wide integration test inventory | Full set of exact-head tests and true native/installed evidence only after accepted source changes |
| INT-01F | Product/physical release acceptance handoff | Explicit human/GPU/physical results separately; **no auto-merge or release** |

**Next source action:** inspect exact canonical DA-03 interfaces and current G06 long-capture lifecycle side by side; implement **INT-01B**, preserving existing five-second immutable capture and Windows AppContainer fail-closed custody. A Linux cgroup alone is not a private encrypted-film filesystem/network sandbox. G02 and G03 remain separately blocked by actual Lu host integration, historical protected film recovery and physical owner gates.

**Excluded by policy:** no blind rebase of PR #74, no CI-green status transplant, no silent file deletions, no FFmpeg active workflow, no unrestricted native/model privileges, no Docker, no automatic OS consent.
