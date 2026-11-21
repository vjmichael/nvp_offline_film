# NVP-STAB-01A — Initial exact-branch repository inventory (2026-11-21)

**Status:** initial source-tree taxonomy and integration-risk register only; NOT a completed line-by-line source audit, comprehensive native build, installed acceptance, or source freeze.

- NVP authoritative repository: `vjmichael/nvp_offline_film`.
- Branch: `nvp/mainline-convergence-20261113`, original PR #161.
- Original tree inspected at `efb6ed67e5511879a9138315577842dce65f9151` through GitHub Git Trees recursive API; `truncated=false`, 1,499 tree entries, **1,480 tracked files**. The same-head 45-run CI cohort remained active at time of audit.
- Task planning from staged candidate `15b821803a05d59f7cc8e4e2dffad926f728fd1c` is not yet published. Local R1 code here is independently authored and tested, not part of PR #161. Do not treat it as a full working checkout.
- Lu interoperability source: `vjmichael/Lu-AI-GUI`, draft PR #244 at `cb338dd3490ddf308e520742a8066cbf9f5a3fa5`, including `lu.workspace.v0` Protobuf over Windows named pipes/Linux AF_UNIX. Lu's installed Windows peer-signing/credential-broker positive is OPEN.

## Root-level files (from the exact Git tree)

| Root | Tracked files | Stabilization owner/scope |
|---|---:|---|
| `backend/` | 472 | Canonical NVP film/domain logic, state, worker, audio, render/POST-01F, Lu adapter |
| `tests/` | 414 | Tests, fixture-only evidence, negative/positive native gates, test map |
| `frontend/` | 134 | React + filmmaker five-stage UX and native WebView2 bridges |
| `tools/` | 157 | Native broker executables, development acceptance and audit utilities |
| `docs/` | 176 | Design/contract/ledger/installer documentation and historical truth |
| `.github/` | 93 | Acceptance workflow triggers and source-specific CI coverage |
| `packaging/` | 7 | Install/build/update scripts and Windows/other install assets |
| `native/` | 6 | Native implementation and bridge components |
| `src/` | 7 | Source entry points; verify current production ownership |
| Other root files | 14 | Launch, deps, packaging manifest, workstation scripts and notices |
| **Total tracked files** | **1,480** | Exact Git tree, no missing pages |

Extensions on this source: Python 1,020; JSX 93; YML 93; Markdown 174; C++ 14; CSS 24; JS 17; NSIS 1; PowerShell 7; plus other build/media files. **Counts are source labels, not coverage or quality proof.**

## Initial cross-component coverage register (not yet verified end-to-end)

| Workstream | Source anchors seen in exact tree | Initial open verification |
|---|---|---|
| Lu Core typed IPC | `backend/nvp_lu_workspace.py`, `nvp_lu_alpha_contract.py`, `nvp_lu_status_wire.py`, `nvp_lu_status_socket.py`, `nvp_lu_g02_port.py` | Replace only production-facing historical JSON/HMAC and old alpha status source with draft Lu native Protobuf; keep tests/historical contract but forbid silent HTTP/JSON fallback. No signed installed package proof |
| Story / scene / project | `backend/nvp_studio.py`, `backend/nvp_ai_refs.py`, `docs/NVP_MASTER_DESIGN.md` | Exact source/revision/project read; fresh load/reopen; Story Bible and scene references; no model-authored approval |
| Native cinema and audio | Native mastering and DCP paths; multiple existing WO4/WO3/AUDIO source/tests | Replay actual source-linked PCM sample/time continuity, native no-FFmpeg export, independent output decode and creator-approved sound |
| Low-poly/visual post | `backend/nvp_post01f_ltx_native_handoff.py`, `nvp_post01f_ltx_native_command.py`, `nvp_post01f_ltx_broker.py` | Actual LTX interface contract, model provisioning and R9700 GPU samples still separate. Never relabel synthetic fixtures as LTX generation |
| Windows SCM/crypto | `backend/nvp_post01f_scm_cng_v2.py`, `nvp_post01f_installed_receipt_transport.py`, `nvp_post01f_g03_nonce_ledger.py`, `tools/nvp_post01f_windows_scm_ltx_broker.cpp` | Source/negative gates vs real installed positive CNG/Windows key/LocalSystem/Job/AppContainer/WFP/EFS; all still need independent installed evidence |
| Encrypted human review | `backend/nvp_post01f_encrypted_review.py`, `nvp_post01f_native_film_review_bridge.py`, Windows native creator signoff | Real authenticated local playback + explicit approve/reject/reopen and exact original PCM preservation are open |
| Native desktop + packaging | `frontend/`, `tools/`, `.nsi`, `.ps1`, `docs/NVP_LOCAL_WINDOWS_INSTALLER_TOOLCHAIN.md` | Real one-installer Windows first install, launch, update/rollback and recovery, no second LTX installer, not ready for final signoff |
| Large-film performance | FilmIndex, SLATE and CONV/PERF source/workflows | Bounded source paging, 30/60/90-min and long project responsiveness, crash/restart and original media lineage |

## P0/P1/P2 initial backlog (hypotheses, verify before calling defects)

1. **P0 integration gap:** No native Lu `lu.workspace.v0` client running in NVP; existing status-only JSON AF_UNIX and fake-host prompt seam do not constitute installed enrollment or authorized tool dispatch. [NVP-INT-LU-01A–G]
2. **P0 security acceptance gap:** No genuine Windows installed signed NVP↔Lu connection, verified SCM positive CNG picture receipt, native encrypted filmmaker preview/approve/reject closure. Do not claim source tests establish either. [SEC-Q-01 / INST-AC-01]
3. **P1 source/feature mapping gap:** Inventory all 1,480 files and map each **advertised** creator feature to a live UI entry, callable backend, relevant unit/native test, approval and durable recovery step; remove orphan routes only after traced usage. [STAB-01A/B]
4. **P1 legacy overlap:** `backend/nvp_lu_alpha_contract.py` and `nvp_lu_status_socket.py` are historical/fixture only, not a substitute for the 1.0 Protobuf workspace gateway. Audit every import/call site for accidental production reachability. [STAB-01D]
5. **P1 rendering truth:** distinguish low-poly scene/Take render, LTX interface source tests, authentic installed GPU inference, encrypted preview and certified DCP output in status/UX. [STAB-01C/E]
6. **P1 original-data invariants:** Trace precise source index and original PCM across all post/editor/export paths, including cancellation/upgrade/rollback. [STAB-01B/E]
7. **P2 simplification:** Investigate duplicate renderer/service/worker/model wrappers and stale documentation; do not remove them before full static/dynamic usage audit and regression proof. [STAB-01D]

## Stabilization acceptance sequence

- **01A**: produce exhaustive feature↔entrypoint↔code owner↔test↔risk coverage matrix and genuine component health report. The table above is a seed only.
- **01B**: actually follow Script Optional → Set up Scenes → Film Scenes → Edit Film → Export Film with human review and local original audio. Verify connected and standalone paths, not only mocks.
- **01C/01D**: reproduce, repair and simplify in reviewed batches while protecting creator authority and source lineage.
- **01E**: independent exact-source Windows native, long-film, offline, IPC/cancel/recovery and source-preservation regressions.
- **01F**: one consolidated release-candidate source and no critical defects, explicit receipt/evidence register, then final Security qualification.

**No new CI trigger, GitHub branch update, main merge, installer release, model-generated picture or installed positive claim is authorized by this inventory.**

## R2 extension — cross-repository executable boundary analysis (2026-11-21)

Latest Lu IPC draft `6932ace156ddaae728a2967660fc37aa986471ae` introduced a guarded Core DLC host bridge. The compiled native registry still exposes only one `ToolEffect` per descriptor; the wire schema's repeated effect declarations cannot be treated as automatically enforceable native policy. `nvp.film.render.shot` and `nvp.film.edit.export` require an explicitly reviewed composite domain authorization path. The production Core host currently refuses incoming object refs until an independent host resolver is implemented. Only genuinely installed Windows signed sessions can enter the production invocation boundary, and the handler requires the original user-turn/canonical workspace binding, an exact typed-input verifier and durable journal. **Any UI that implies arbitrary AI-proposed film edits/render are already authorized is an integration defect candidate to investigate, not a confirmed active runtime exploit.**

Native Protobuf descriptor compilation of the 16 local NVP film payload types now succeeds with `libprotoc 3.13`; source-level codegen with current installed Python runtime remains incompatible and will need an approved compiler update. Actual Lu/Rust prost registration, Windows signed endpoint and a full NVP source checkout audit remain open. Historical Python JSON/HMAC Lu status code must never be silently treated as the new signed Protobuf channel. No original Take or PCM mutations were performed in this source-only R2 task.
