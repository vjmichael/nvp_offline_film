# NVP-STAB-01A — Exact-checkout AST and critical test reconciliation (R6)

**Audit source:** PR #161 original application commit \`581ce161dcaecb4c6a8935e8c0e470a6022d48a4\`; audit-only child \`b6ce50d508072227cb9b340e31e7aef4ba0e306f\`. The child changed only \`scripts/nvp_stab_01a_ast_inventory.py\` and \`.github/workflows/nvp-stab-01a-ast.yml\`. No application, tests, installer, worker or model source changed.

## Executed full-checkout static analysis

[Audit run #44968522557](https://github.com/vjmichael/nvp_offline_film/actions/runs/44968522557) **PASS** from genuine GitHub checkout, pinned to audit child SHA. Its 150,425-byte archived report contains CSV import edges, dynamic callsites, test definitions, package-lock inventory, missing references, workflow declared test patterns, and native lexical callsite candidates.

- 1,563 Git-tracked files, 1,325 inspected relevant sources.
- 485 backend Python modules; 431 Python test modules; 108 frontend JS/JSX/MJS sources; 97 workflow definitions.
- 4,930 AST/literal import edges (4,774 AST \`from\` + 16 AST \`import\` + 3 literal dynamic + 120 JS + 17 C/C++ local includes); 694 dynamic/launch/API AST callsite candidates; 1,810 native/codec lexical candidates.
- 2,920 static test definitions (not executed-case totals); 385 declared npm/Cargo/Python lock/dependency records.
- 265 unresolved candidates: 257 dynamic/reflection callsites and 8 JS relative imports. No Python syntax or source-read errors.
- Static reachability from four registered desktop/API/frontend roots reaches 359 files. It deliberately excludes independent executable entrypoints and cannot prove runtime execution, credential/signer provisioning, license compliance, or creator consent.

**Actual root chains:** desktop \`tools/nvp_desktop_alpha.py\` → \`backend/nvp_api.py\`, main React \`main.jsx\` → \`App.jsx\` → \`FilmmakerHome.jsx\`, separate editor \`postproduction-entry.jsx\` → \`PostProduction.jsx\` → \`DirectorFilmEditor.jsx\`; native G06/G07/G08/G09E/F route mounts appear in source.

**Not statically root-reachable:** \`nvp_post01f_ltx_broker.py\`, LTX handoff/encrypted review, \`nvp_lu_gpu_lease_v1.py\`, \`nvp_lu_win32_client.py\`, optional NVP-owned LM Studio manager, \`DirectorDiffusionMusicToggle.jsx\`. This means *no ordinary static import path from the four inspected roots*, NOT dead code: original SCM, CLI, callbacks, native owner services and tools can be separate legitimate entrypoints.

**Dynamic binding inspection:** \`nvp_audio01e3_native_host.py\`, \`nvp_audio01f_native_host.py\`, \`nvp_b14_native_conform.py\` and \`nvp_source_window_native_host.py\` use fixed \`__import__("sqlite3")\`; \`nvp_usd_film02m_d_cells.py\` uses fixed \`pxr\` import; \`nvp_g09f_runtime.py\` imports from a fixed optional-dependency roster; \`nvp_post01f_ltx_broker.py\` imports fixed \`ltx_pipelines.ic_lora\`, checks its installed path and calls its entrypoint only under separate native custody. Other ordinary \`getattr\`/\`setattr\` are tracked as reflection. No independently installed LTX/model result is established by source reading.

**Eight unresolved JS imports:** \`src/main.js\` refers to absent \`./App.jsx\`; \`src/App.js\` refers to absent \`./NvpReconstructedPanel\`; six root/\`frontend/src\` dashboard/wizard/version panels refer to absent \`./nvp_config.json\`. These are candidate legacy or unreferenced modules and must not be deleted without build-reference review.

## Original exact-source CI and critical per-case logs

All **46 original** workflows at \`581ce161\` are terminal \`success\`; job results: 155 success, one intentionally skipped; 26 conditional steps skipped. Workflow success is not equivalent to executing every test.

- [CONV-12 #44959426800](https://github.com/vjmichael/nvp_offline_film/actions/runs/44959426800): genuinely executed Windows EFS/AppContainer, 90×8=720 native Blender/Cycles frames with OS cancellation/recovery; five-test suite. Verifier evidence SHA256 \`c6eb1eb5c50c496fe3a744a0239edf28245111209a41e76ca163e040f7a95a62\`. Does NOT establish LTX or user film approval.
- [POST01F Windows #44959426757](https://github.com/vjmichael/nvp_offline_film/actions/runs/44959426757): 101 cases, 2 skipped for absent FFmpeg/FFprobe external media binaries. Real Windows SCM/CNG/CMS source compiled and unprovisioned/unattended attempts refused; no authorized installed LTX positive.
- [Lu GPU #44959422173](https://github.com/vjmichael/nvp_offline_film/actions/runs/44959422173): 75 original Windows Python cases in four suites; one installed-supervisor case skipped. Native Rust/prost/P256 negative evidence marked \`NOT_INSTALLED\`.
- [AUDIO01I/J #44959426776](https://github.com/vjmichael/nvp_offline_film/actions/runs/44959426776): 21 Windows cases, two Linux-cgroup-only cases skipped; actual native WAV/crash/SQLite checks run.
- [WO3/WO4 native](https://github.com/vjmichael/nvp_offline_film/actions/runs/44959426960): short real 2K/4K OpenJPEG/MXF/PCM pilots pass, but \`production_dcp_accepted=false\` and \`creator_film_throughput_verified=false\`.
- [DATA-AV #44959426632](https://github.com/vjmichael/nvp_offline_film/actions/runs/44959426632): real installed Windows NVP.exe/NSIS/WebView2/PCM smoke positive. The genuine Qwen GGUF job is intentionally skipped unless \`[PLAN-02-C gate]\` is in the push commit; no GGUF inference credit.
- 2,920 AST-defined tests must not be labeled 2,920 executed/passed. The original workflow logs are the positive/negative receipts.

## Defect-register additions

- **A-031 — unresolved/legacy JS imports:** eight relative import references, including two wrong root \`src/\` paths. Determine active module roots before repairs/deletion.
- **A-032 — dynamic native/IPC reachability:** 257 AST dynamic/reflection sites categorized, including fixed legitimate native imports; real installed Lu/LTX and native SCM paths still require explicit host binding, original user consent and receipt proof.
- **A-033 — positive coverage skips:** Qwen job omitted; POST01F media and Lu installed-supervisor cases skipped. Real Windows Cycles 720 and installed NVP.exe smoke are independently positive, not substitutes for model/film.
- **A-034 — CI trigger fan-out:** the two-file audit-only push \`b6ce50d5\` unexpectedly scheduled **46 workflows** including a redundant long CONV-12 run. That is a material operations defect; no further branch push while the batch runs. Narrow legacy trigger scopes in later stabilization.

**Policy:** The Nov 20 approved design permits FFmpeg/PyAV **only at a bounded external media boundary**, not as a core dependency. DA-00 zero-FFmpeg entrypoint audit and separately protected POST01F visual conform require exact documented packaging/authority scope; lexical FFmpeg references alone do not prove an active violation.

## Admission and publication decision

The 01A **source/AST inventory and critical test-truth reconciliation is materially complete**. Outstanding physical installed Lu signing/authentication, actual R9700 LTX, direct structured model-input contract, license/redistribution review, full-length film throughput, UI/orphan integration, and CI over-triggering are **recorded release and 01B–01F implementation/qualification deficits**, not silently accepted.

**Do not move the PR head or start STAB-01B until the unintended 46-run cohort is terminal and this report is safely published in the canonical ledger.** This document and ledger patch are prepared objects, not a claim of final main merge or release acceptance.
