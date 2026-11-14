# NVP — Canonical Mainline Convergence Ledger (repository-wide)

**Owner directive:** NVP is being developed to converge **every active/historical branch's compatible work into one authoritative `main` branch.** Completing isolated PRs is not the objective; keep a comprehensive branch census, reconcile unique work and existing tests, integrate into a **single temporary candidate**, and merge that verified candidate once into `main` through protected review. Branches are disposable after audited absorption/explicit supersession, not independent future products.

**Snapshot:** GitHub branch and OPEN-PR API enumeration, Nov 13–14 2026.
- Canonical target: `main` at `75611266ef2670d561b3761b3352d3d25b0b3296`.
- Active consolidation candidate: `nvp/mainline-convergence-20261113` at snapshot `0490398e76fd1b1a81e00f2acdbfe56353f4158d`, created from PR #160's exact `0490398e76fd1b1a81e00f2acdbfe56353f4158d`. This candidate currently **contains the historic source sequence through #159 and #160 only**; other divergent lines are NOT merged.
- Enumerated branches: **209** total, including `main` and the temporary candidate. Enumerated open PRs: **139**. No branch/PR was silently marked integrated, verified, or retired solely because its older code *resembles* current code.
- Against `main`, PR #160's candidate is **2,357 commits ahead, 0 behind** (main is an ancestor), but includes many unaccepted native/installed/release gates. The audited HEAD alone is not production approval.
- The separate `nvp/w1g-p1a-sec06-integrated-20261112` security branch **diverges** from the P1-F candidate: 290 unique commits on W1-G versus 277 on PR #160, common ancestor `c1e5706d615108d05554946e0ffbb87588cc8135`. Neither branch is a safe automatic substitute for the other. The genuine W1-G/SEC-06 host-control/security work must be brought into the same candidate without discarding private worker restrictions.
- Other branches include parallel UI/G02/G03/G04–09, original USD-FILM/DA, production assets, native containment, sound, export, and historical design and FFmpeg-proxy paths; **each unique change requires explicit disposition**.

## Binding integration rules

1. **One release target:** `main`. The temporary candidate is a staging vehicle, not a competing perpetual mainline. All new NVP changes should land on or be promptly reconciled against the candidate. Avoid endless single-bug branch proliferation.
2. **Audit ALL branches:** for each exact SHA, compare to the candidate, inventory unique non-merge commits and touched interfaces, classify as (a) already present identically, (b) unique compatible changes to integrate, (c) superseded with named replacement tests and a cited equivalence proof, or (d) rejected/quarantined with a specific policy/security reason. Never claim completion because a branch name disappeared.
3. **Integration order:** authoritative data-first FilmIndex/OpenUSD/Take/PCM baseline; G02/G03 creator-facing UX and model boundary; native P1-A/W1-G/SEC-06 worker custody; G04–G09 filming/editing/export/actors/materials; P1-F body/face/terrain and genuine Cycles; provenance-preserving delivery; native Windows/Linux/installed release gate. The order can be interleaved when branches do not conflict.
4. **No regressions by consolidation:** retain original tests and original negative kernel cases, per-turn creator authorization, one-use SCM/AppContainer/WFP/Job Windows and root-owned delegated cgroup/namespace Linux custody. No debug/public fixture toggle in production code. No arbitrary executable/provider egress or private-source sandbox bypass.
5. **No legacy import by accident:** preserve the creator's active no-FFmpeg source policy. Old FFmpeg/proxy/unsafe test paths may need historical evidence and an explicit *superseded* disposition rather than blindly copying executables or workflows into main.
6. **Evidence gate:** a consolidated exact source SHA must pass full native Windows/Linux matrix, independent process-custody/guardian-loss/cancellation/restart/replay tests, original FilmIndex/source receipts, genuine licensed Blender/Cycles and audio verification where relevant, with separate physical and installed gates. A successful small public fixture does not mean whole-film or production installation acceptance.
7. **Merge protocol:** integrate changes into candidate via reviewed commits or real merges; resolve conflicts in code/tests rather than taking an arbitrary side. Run exact-head baseline. Create/maintain one **draft candidate → main** PR, mark ready and merge only after evidence and required explicit creator/release approvals. Retire superseded draft PRs/branches *after* ancestry/content review, never preemptively.
8. **Reconcile drift:** this snapshot must be refreshed when branch refs, open PRs or `main` advance. Never assume a parent PR's old pinned SHA reflects the latest compatible source automatically.

## Initial candidate integration topology

| Workstream | Source | State |
|---|---|---|
| Canonical target | `main` | Behind current 2,357-commit candidate; no production merge |
| Data-first source, P1-D/E/P1-F/P2 | [PR #159](https://github.com/vjmichael/nvp_offline_film/pull/159), base lineage from [PR #74](https://github.com/vjmichael/nvp_offline_film/pull/74) | In candidate ancestry; native acceptance not yet consolidated |
| Full-body/face/foot source | [PR #160](https://github.com/vjmichael/nvp_offline_film/pull/160) | In candidate ancestry; moving-rig/actual licensed picture remains open |
| Native audio, process custody, SEC-06 | [PR #158](https://github.com/vjmichael/nvp_offline_film/pull/158), [#157](https://github.com/vjmichael/nvp_offline_film/pull/157), [#156](https://github.com/vjmichael/nvp_offline_film/pull/156) | DIVERGED; not integrated/accepted into candidate |
| Creator-facing home, shared Lu proposal | [PR #155](https://github.com/vjmichael/nvp_offline_film/pull/155), [#154](https://github.com/vjmichael/nvp_offline_film/pull/154) | DIVERGED; functionality comparison required |
| Older historical branches | Census below | FULL disposition pending; do not assume unique work gone |

## Exhaustive branch census at snapshot

Each row is a tracked original ref, not a declaration it should be merged as-is. Exact SHA allows subsequent compare/cherry-pick/test/explicit supersession records. A branch without an open PR still matters.

| # | Git ref | Snapshot SHA | Open PR(s) | Consolidation disposition |
|---:|---|---|---|---|
| 1 | `docs/nvp-world-aware-film-studio-design-2026-10-26` | `487c8446e625d35ff4540269f9ed0c6411f000cb` | [#1](https://github.com/vjmichael/nvp_offline_film/pull/1) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 2 | `main` | `75611266ef2670d561b3761b3352d3d25b0b3296` | — | CANONICAL TARGET — do not overwrite without full acceptance |
| 3 | `nvp/acting-research-lab-20261104` | `d51f460de1852b436f6111b0195bd02acd4a39c7` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 4 | `nvp/adr-data-first-film-pipeline-20261103` | `8012ea20edfb1f4ad7a67249cf9d87d679f5a3ae` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 5 | `nvp/area2-02mh-camfx-consolidated-20261109` | `120cc1c6aed737e006755e7ed9af3a6a484da2fd` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 6 | `nvp/area2-02mh-worker-stderr-diagnostics-20261109` | `0e8488e98017201d4a4a621ba43e1649d00c919f` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 7 | `nvp/area2-camfx01-04-native-acceptance-20261109` | `9f6a8309295ec40003266f0be13bb959656f0804` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 8 | `nvp/area3-720-frames-original-pcm-group-20261109` | `2c59eca326ba469d1d4179d576a400d187a8caef` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 9 | `nvp/cam-fx01-02-typed-rails-usd-layers-20261109` | `cb3cec444b57d3638378519218e9207e7ddcff55` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 10 | `nvp/cam-fx03-04-gizmos-guidance-drafts-ai-20261109` | `7a0bd98f96d013e77ece8ca1469e25360e44fc9b` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 11 | `nvp/cam-fx04-genuine-gguf-camera-proposals-20261109` | `7ed65308db8f5d59c3fe57e32fc73ce1eab20758` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 12 | `nvp/cam-fx05-real-moving-cycles-20261109` | `7b4c36839daa3cb801399ec3f63ce3c101dc16f6` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 13 | `nvp/cam-fx05b-protected-rail-cycles-20261109` | `0c670f0b6f33fe0ed339ae0e34c44de12d80410f` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 14 | `nvp/capture01-immutable-timed-takes-20261103` | `24fa7916f19f546eb7e92538aa56936f6216aac1` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 15 | `nvp/cinema01b-jpeg2000-mxf-evidence-20261103` | `53cce63eab06c8715d3d78bc2b6c4d693f9a62b5` | [#16](https://github.com/vjmichael/nvp_offline_film/pull/16) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 16 | `nvp/cinema01c-duration-lineage-replay-20261103` | `8e449c405b204072f18c7d8758fa2015b9a92f2e` | [#17](https://github.com/vjmichael/nvp_offline_film/pull/17) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 17 | `nvp/color01a-native-scene-linear-exr-20261103` | `62cbb18123810859e32302c56ee63f2b140bbc0a` | [#18](https://github.com/vjmichael/nvp_offline_film/pull/18) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 18 | `nvp/color01b2-prores-dnxhr-graded-master-20261103` | `0ffbeb7365b2d9be2c4429d2fc2d30b6c04ba26f` | [#20](https://github.com/vjmichael/nvp_offline_film/pull/20) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 19 | `nvp/color01b-ocio-aces2-mastering-20261103` | `bd154080574c7a326a8ad58372c3427b7f533e80` | [#19](https://github.com/vjmichael/nvp_offline_film/pull/19) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 20 | `nvp/da05-06-native-sequential-closeout-20261106` | `df4cb514ea9f32633eaa2362656eedd478c8682b` | [#76](https://github.com/vjmichael/nvp_offline_film/pull/76) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 21 | `nvp/da05b-2d-package-integrity-20261106` | `bacb5b16dc475862a2221aacbec5273f7c46491a` | [#75](https://github.com/vjmichael/nvp_offline_film/pull/75) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 22 | `nvp/data01-film-lineage-index-20261103` | `78dac342a233843a031a734687f2526654d1fefd` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 23 | `nvp/data-av01-native-scene-playback-20261106` | `d11df9366183df8a5a098376030d71d83d20a5b4` | [#74](https://github.com/vjmichael/nvp_offline_film/pull/74) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 24 | `nvp/data-first-temporal-ledger-bench-20261105` | `22c6dbcbd26281c93272a165c650550fe88b4ef6` | [#48](https://github.com/vjmichael/nvp_offline_film/pull/48) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 25 | `nvp/datafirst-batch1-2d-quarantine-editorial-20261107` | `d60abf96b0361befe40e2e41c1d9b7c0f19e4ae4` | [#77](https://github.com/vjmichael/nvp_offline_film/pull/77) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 26 | `nvp/datafirst-batch2-live-spatial-world-20261107` | `0bcef380b20945ac58c5dba1c2033f389d489cfa` | [#78](https://github.com/vjmichael/nvp_offline_film/pull/78) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 27 | `nvp/datafirst-batch2b-live-skinning-acoustics-20261107` | `099e9c3360ca689ebce3947ff25f4bcf24b3c962` | [#81](https://github.com/vjmichael/nvp_offline_film/pull/81) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 28 | `nvp/datafirst-batch2c-full-livestage-20261107` | `faf89959006440882adc9810144a62937b73872b` | [#82](https://github.com/vjmichael/nvp_offline_film/pull/82) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 29 | `nvp/datafirst-batch3-native-aces-color-20261107` | `54351bb41d72cb1ea07aabb8defdf8f075a4dd73` | [#79](https://github.com/vjmichael/nvp_offline_film/pull/79) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 30 | `nvp/datafirst-batch3b-source-linear-aces-20261107` | `114a9bbb0ff6c8a53cb448804bdafdacf32dbd92` | [#84](https://github.com/vjmichael/nvp_offline_film/pull/84) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 31 | `nvp/datafirst-batch3c-color-render-delivery-closeout-20261107` | `e03c1e7f2920e8a7a3504a9cddf54bd525dab50b` | [#85](https://github.com/vjmichael/nvp_offline_film/pull/85) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 32 | `nvp/datafirst-batch3d-native-uv-textures-20261107` | `63fb563c523052d7b550307b7ebfeb3524af0a6a` | [#86](https://github.com/vjmichael/nvp_offline_film/pull/86) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 33 | `nvp/datafirst-closeout-ci-repair-20261107` | `64545bdaf9631012fc7be4a7f816cf07843fe082` | [#80](https://github.com/vjmichael/nvp_offline_film/pull/80) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 34 | `nvp/datafirst-da02e-independent-device-clocks-20261107` | `8632bbcf58225af909ee0f07ee0c6cf0026492e4` | [#83](https://github.com/vjmichael/nvp_offline_film/pull/83) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 35 | `nvp/design-hybrid-usd-ai-appearance-20261109` | `a8f1046bc56560e8067d856dfbc1266b60806f5b` | [#146](https://github.com/vjmichael/nvp_offline_film/pull/146) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 36 | `nvp/docs-filmmaker-workflow-20261110` | `a2a6639270ab6f2cee6961137baf9daaf598f3a0` | [#153](https://github.com/vjmichael/nvp_offline_film/pull/153) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 37 | `nvp/film01-donut-actor-lighting-20261108` | `34020ba156c83bd039f69a0d88757e11cea54c35` | [#109](https://github.com/vjmichael/nvp_offline_film/pull/109) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 38 | `nvp/film01-donut-three-actor-occlusion-20261108` | `aabd1c0848c8ec49c177c5aa17ad719d48c36c56` | [#110](https://github.com/vjmichael/nvp_offline_film/pull/110) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 39 | `nvp/film01-native-visual-audio-qc-20261108` | `e73e1f06cf95d24c8545fc6c9d4ad3a03b16227e` | [#108](https://github.com/vjmichael/nvp_offline_film/pull/108) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 40 | `nvp/film01-original30s-digital-fx-20261108` | `c80f101de3f42e67c6fdd6abb0fb192e72216d21` | [#106](https://github.com/vjmichael/nvp_offline_film/pull/106) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 41 | `nvp/film01-real-blender-cycles-donut-20261108` | `3cb085a5647e347213ddd33e15718125718344d4` | [#111](https://github.com/vjmichael/nvp_offline_film/pull/111) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 42 | `nvp/film02-03-original-pcm-cycles-playback-20261108` | `c2d1ca2ddfdced293fe92cb44a71a6dafa06a238` | [#113](https://github.com/vjmichael/nvp_offline_film/pull/113) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 43 | `nvp/film02-04-real-30s-av-screening-closeout-20261108` | `65ffadc885875e435d36c351a6ea1f75b0652e7f` | [#116](https://github.com/vjmichael/nvp_offline_film/pull/116) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 44 | `nvp/film02-30s-blender-handoff-20261108` | `6bb878eeb774c4c799ec98e978e9ebb2e7c39815` | [#112](https://github.com/vjmichael/nvp_offline_film/pull/112) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 45 | `nvp/film03-01-object-actor-dialogue-script-lineage-20261108` | `da3e1881816f04bf59bfa6276512bdfc55544319` | [#114](https://github.com/vjmichael/nvp_offline_film/pull/114) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 46 | `nvp/film03-02-production-bible-actorid-editor-20261108` | `29c78b8bb26c1a40d64f04f16e3a322e81739e4c` | [#115](https://github.com/vjmichael/nvp_offline_film/pull/115) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 47 | `nvp/film03-03-actorid-dialogue-routing-20261108` | `1700f654603942948ff9d3d7cbca1c660345950f` | [#117](https://github.com/vjmichael/nvp_offline_film/pull/117) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 48 | `nvp/film03-04-actor-voice-continuity-20261108` | `fd06881f244cfccd1f9777a6a3ef13d5624af7ce` | [#118](https://github.com/vjmichael/nvp_offline_film/pull/118) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 49 | `nvp/film03-05-actor-identity-voice-type-ai-20261108` | `238cc372c733d589a95c3c2fd28ea4595b17e44f` | [#119](https://github.com/vjmichael/nvp_offline_film/pull/119) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 50 | `nvp/film03-06-supervised-voice-animation-workers-20261108` | `c40aa5abc92a90bdbc79b0a332309d5188ecae22` | [#120](https://github.com/vjmichael/nvp_offline_film/pull/120) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 51 | `nvp/film03-07-expressive-voice-audition-lab-20261108` | `14c352e28647255410798112ef904daa9b68cedd` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 52 | `nvp/film03-08-guide-performance-voice-conversion-20261108` | `8dd2cfec3b95f40923bf4f464dad84cd47c2988c` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 53 | `nvp/film03-09-independent-facial-direction-20261108` | `90a785b2e69a1848c1cbeaa595ba253c4e3aad60` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 54 | `nvp/film03-09b-human-voice-actor-intake-20261108` | `d0d0980495ec02a2c9dcfe0a4b701d6e734a6d68` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 55 | `nvp/film03-09c-phoneme-alignment-scope-cleanup-20261108` | `f84b76c2c8a2f480760db2260f4cbe31360b5e4a` | [#125](https://github.com/vjmichael/nvp_offline_film/pull/125) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 56 | `nvp/film03-09d-usd-actor-mouth-rig-20261108` | `2556c0f88fbebe950017d35bceff6cd27f26c8f3` | [#126](https://github.com/vjmichael/nvp_offline_film/pull/126) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 57 | `nvp/first-party-dlc-interface-rfc-20261103` | `e25e2653de0856f4e45934e6794ab32fa2acbbcd` | [#35](https://github.com/vjmichael/nvp_offline_film/pull/35) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 58 | `nvp/g02-lu-shared-model-boundary-20261110` | `fcd73d2cfc07903b7857b273139bbb79e91b064e` | [#154](https://github.com/vjmichael/nvp_offline_film/pull/154) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 59 | `nvp/g03-film-home-project-access-20261110` | `03a260d1ee4a6a07d273e301f5d003bc33d3897d` | [#155](https://github.com/vjmichael/nvp_offline_film/pull/155) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 60 | `nvp/g04-director-ai-screenplay-build-20261111` | `6086f4ba2c9c0bf07db05a640ffea8da079d62e3` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 61 | `nvp/g05-visual-scene-authoring-20261111` | `addd9474d71cd4baebf944f387502e22c27895c5` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 62 | `nvp/g06-filming-performances-original-takes-20261111` | `594b767692ccb59e723c54b3454aeddc4192c72a` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 63 | `nvp/g07-source-editing-20261111` | `d936d3af2382935516088bcb095ea0d2a70dc274` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 64 | `nvp/g08-native-film-export-20261111` | `96a39cb42ed3e6a922328b3ca8960edcf4fc6368` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 65 | `nvp/g09-production-environments-20261111` | `94498a215f7c208fd40f44e445f45564a336559f` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 66 | `nvp/g09b-actor-performance-20261111` | `840a3209d99b862229d1a5a47d2ea91eb867b561` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 67 | `nvp/g09c-native-spatial-av-20261111` | `55e517671506ed5c20825ccd58dbc6a4e5271c71` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 68 | `nvp/g09d-finishing-delivery-20261111` | `8820afd6522395242dcc2157e90f40265a7c7127` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 69 | `nvp/g09e-sustained-scale-20261111` | `3f89493c2af993e0b03fbccb8a9b0de9a5889cd3` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 70 | `nvp/g09f-portable-film-distribution-20261111` | `b83ac974ae4295da32e09ea8e6ebe739c71f912b` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 71 | `nvp/grade-ui01-workspace-preview-20261103` | `9e1c17ba95c7b85b8b2023fa55c109d66b7075e3` | [#21](https://github.com/vjmichael/nvp_offline_film/pull/21) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 72 | `nvp/grade-ui02a-shot-wheels-scopes-20261103` | `fb6bb193ab9fa40a52b3b8be06e2018aabe371ee` | [#22](https://github.com/vjmichael/nvp_offline_film/pull/22) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 73 | `nvp/grade-ui02b-curves-reference-lut-20261103` | `96841f5f5b7b2d2ae7ec2b98256496025739e582` | [#23](https://github.com/vjmichael/nvp_offline_film/pull/23) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 74 | `nvp/human-surface-ai-material-roadmap-20261108` | `beeda6e846b6e51064fc2e3e7f045aae7b4d860b` | [#133](https://github.com/vjmichael/nvp_offline_film/pull/133) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 75 | `nvp/index-pts-film-time-20261105` | `e8f5098436528372ec6f1662dd7119641d81bcb3` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 76 | `nvp/index-time02-durable-editorial-20261105` | `3246a2e9ea1d0fb0c603f5e84f4713b8e2d4dca7` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 77 | `nvp/index-time03-native-preview-conform-20261105` | `738a131f3861449fce07ae582f9ad8f1578a6942` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 78 | `nvp/index-time04-film-time-seek-20261105` | `d7565a03e6dfa8a70b347ff12baaca688c93c449` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 79 | `nvp/index-time05-editor-seek-20261106` | `ca348dedee42b0bbbb5092b9da0183c044fdf0eb` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 80 | `nvp/index-time06-native-import-review-20261106` | `8e9a11c4372c0da0bdd960dab4235f66bbcfbbc9` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 81 | `nvp/index-time07-immutable-footage-assembly-20261106` | `42d37a8fc3d20ee3789e8f2a0d8c5449d7ba68a5` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 82 | `nvp/index-time08-safe-assembly-playback-20261106` | `847f0b89e62ca05838934051aa7e066b57d0c26c` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 83 | `nvp/index-time09-continuous-av-proxy-20261106` | `974f2413b384e5970462fa6398924ada39c532d6` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 84 | `nvp/index-time10-progressive-longform-20261106` | `3f33436aa79f62ad869b0046139595c79e360255` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 85 | `nvp/indexing-closeout-20261105` | `59c1627285f3f014246d507c86c5eacf6402e3ae` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 86 | `nvp/int02-w1g-native-film-package-20261112` | `37a61b3656bd0b9faf06471fb302667cc3175dda` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 87 | `nvp/mainline-convergence-20261113` | `0490398e76fd1b1a81e00f2acdbfe56353f4158d` | — | ACTIVE SINGLE MAINLINE CANDIDATE — unaccepted |
| 88 | `nvp/p0-f01-installed-native-windows-group-20261109` | `5e9bf2cea90e332833edc7f36200c0f4ef59e365` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 89 | `nvp/p0-f01-installed-timeout-diagnostics-repair-20261109` | `fa87fffdf8eacb94a92598510a3f32af8837c543` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 90 | `nvp/p0f01-async-model-draft-recovery-20261109` | `acac9753f8e441dd39a11083dc94a4a0d573b246` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 91 | `nvp/p0f01-camera-rails-shot-fx-ledger-20261109` | `9d1760edabfaaf655db3172598b9892ea343cc40` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 92 | `nvp/p1a-device-producer-custody-20261112` | `5b533492d9ec4aa0d37fee18d132461512648d74` | [#156](https://github.com/vjmichael/nvp_offline_film/pull/156) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 93 | `nvp/p1de-p1f-p2-source-reconciliation-20261113` | `35039feb432b1cc3d32ed3c2f31140e53f3edd66` | [#159](https://github.com/vjmichael/nvp_offline_film/pull/159) | INCLUDED IN CANDIDATE'S STARTING HISTORY — PR #159 |
| 94 | `nvp/p1f-fullbody-foot-dialogue-20261113` | `0490398e76fd1b1a81e00f2acdbfe56353f4158d` | [#160](https://github.com/vjmichael/nvp_offline_film/pull/160) | INCLUDED IN CANDIDATE'S STARTING HISTORY — PR #160 |
| 95 | `nvp/pipe01-blender-presentations-20261103` | `e1a7d1496e234309bf31c781f84ee152aa8f6db6` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 96 | `nvp/pipe01b-full-motion-pbr-video-20261103` | `db1bb6eda65bf664504745496c7fd4ee44fda9bf` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 97 | `nvp/pipe01b-professional-mezzanine-prores-20261103` | `82110473c5ae2da0f7c6be79ae4f3949bbf7c699` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 98 | `nvp/plan02d-exact-source-window-20261109` | `23511f3eb23df177129dd9ba302cc77492055894` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 99 | `nvp/plan02d-repair-integration-20261109` | `504315889b1344e2df1a475ad52752b3d98b52db` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 100 | `nvp/plan02e-canonical-integration-20261110` | `68ad69f9487cbc458a82f250f9804baa0d4aa1ba` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 101 | `nvp/plan03-filmmaker-source-integration-20261110` | `a4ebab9d25b614de3256aa19dc254613cf5e3b8b` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 102 | `nvp/plan04-physical-gates-20261110` | `2725e45dfa45f6ca6780d1cf152ed1155f3057e3` | [#151](https://github.com/vjmichael/nvp_offline_film/pull/151) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 103 | `nvp/plan04-qwen-blender-production-20261110` | `53bd132524415f196fed34673a803cf5671914b3` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 104 | `nvp/pro02-cinema-dcp-and-dnxhr-20261103` | `14b899fad0277b383d78d35eaa238224864b10f9` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 105 | `nvp/prod01-acceptance-through-prod04-20261102` | `013f11489dea79f8749b1f03c33afb26f598c7ae` | [#10](https://github.com/vjmichael/nvp_offline_film/pull/10) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 106 | `nvp/prod01-deterministic-blender-stage-20261102` | `5df2dc215951953e0f3ba729122cd098e87d32c5` | [#9](https://github.com/vjmichael/nvp_offline_film/pull/9) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 107 | `nvp/prod05-timed-shots-20261102` | `e1136b92877ee05e88c5ad0cda79e9578c3a3eb3` | [#11](https://github.com/vjmichael/nvp_offline_film/pull/11) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 108 | `nvp/prod06-rigged-motion-20261102` | `005c22a99ceb36ee3198fc0d2feb868fdfad0ef2` | [#12](https://github.com/vjmichael/nvp_offline_film/pull/12) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 109 | `nvp/prod06b-weighted-skin-20261102` | `c32e62531f8cfa34b77dd91ca3a492d8771286e1` | [#13](https://github.com/vjmichael/nvp_offline_film/pull/13) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 110 | `nvp/prod06c-external-rigged-glb-20261102` | `3d0eb6a6a2b1dee62e2f48177c7f6b5de9b5a499` | [#14](https://github.com/vjmichael/nvp_offline_film/pull/14) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 111 | `nvp/prod06d-real-character-calibration-20261102` | `fc1877e983c9c4aacfd50849702559e20f83293a` | [#15](https://github.com/vjmichael/nvp_offline_film/pull/15) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 112 | `nvp/prod06e1-footplant-preflight-20261102` | `aee2b63dae62151ed18ee6aa7ea529bee8ee2bbd` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 113 | `nvp/prod06e2-leg-identity-20261103` | `2bb3f33e957898bc1694445db214d92649f4616a` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 114 | `nvp/prod06e2b-foot-lock-20261103` | `ddf6114706022bcdf4a2807cd757e02fe8096b08` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 115 | `nvp/prod06e2b-staged-pose-contact-20261103` | `4cc8557e6cef051073b22c302d53199af189c85e` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 116 | `nvp/prod06e2c2-plantar-markers-floor-20261103` | `ff944ede21092ec1aa0f52653fe7203d6823b923` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 117 | `nvp/prod06e2c3-bounded-mesh-contact-20261103` | `7a9e6173be603edc1937d10f2665be2abff1b7a3` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 118 | `nvp/prod06e2c3b-anatomical-landmarks-bvh-20261103` | `b9d95f80a39297180c9c7e24ef9b877e53e09cd4` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 119 | `nvp/prod06e2c-sole-region-audit-20261103` | `cd632a46249abee69a5b8dc584bfbef1ff2cdfc5` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 120 | `nvp/scale03c-ffms2-indexed-seek-20261105` | `98d29e591961968738820b344b620c5548e3b35b` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 121 | `nvp/scale03c-nvp-native-frame-index-20261105` | `e77da78e03c52e320c2b346788378f4f2a575845` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 122 | `nvp/scene-mind-beliefs-deception-20261102` | `10e4bbf8ee891ae65cf0c731b3cd431a24d51946` | [#7](https://github.com/vjmichael/nvp_offline_film/pull/7) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 123 | `nvp/screenplay-evidence-review-20261102` | `26ce9738a837a2b9f90fd2a9966eb5593e8811fe` | [#8](https://github.com/vjmichael/nvp_offline_film/pull/8) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 124 | `nvp/sec06-gate1-independent-20261112` | `a7f9481bce9508a3ea9a46d5bc810386e86c0954` | [#157](https://github.com/vjmichael/nvp_offline_film/pull/157) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 125 | `nvp/shot01-director-usd-overrides-20261106` | `90da4c58add70a37a925b34ffa1a5f28f1d1dd71` | [#58](https://github.com/vjmichael/nvp_offline_film/pull/58) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 126 | `nvp/slate01-branching-takes-20261106` | `31ff641fc9cfeabf1d714326fed02a5d810ddbca` | [#59](https://github.com/vjmichael/nvp_offline_film/pull/59) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 127 | `nvp/slate02-assembly-preview-commit-20261106` | `6b9d592214ec13c488846bc6068ee13f36a356f4` | [#60](https://github.com/vjmichael/nvp_offline_film/pull/60) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 128 | `nvp/slate03-paged-metadata-20261106` | `b2b376daefe2c660614816af95ab89a4007435a7` | [#61](https://github.com/vjmichael/nvp_offline_film/pull/61) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 129 | `nvp/slate04-lazy-preview-source-custody-20261106` | `c1d860b449d8c25237e5591baf9478eaa310c913` | [#62](https://github.com/vjmichael/nvp_offline_film/pull/62) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 130 | `nvp/slate05-demand-preview-cache-20261106` | `59f6c902bd4b305546ef3d04cf58ae0387b3654c` | [#63](https://github.com/vjmichael/nvp_offline_film/pull/63) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 131 | `nvp/slate06-openusd-geometry-presentation-20261106` | `28a9c24c3802a662d4dc79d4a36994d1de10dbde` | [#64](https://github.com/vjmichael/nvp_offline_film/pull/64) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 132 | `nvp/slate07-skinning-live-camera-20261106` | `6dfd5cf90a9250d1f332dffecc47b355a4eb6208` | [#65](https://github.com/vjmichael/nvp_offline_film/pull/65) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 133 | `nvp/slate08-desktop-camera-readbridge-20261106` | `8ae91aa99461604093d47d26104d73ba4beedd2a` | [#66](https://github.com/vjmichael/nvp_offline_film/pull/66) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 134 | `nvp/slate08b-trusted-desktop-optics-20261106` | `c866c3a93998b020d3ceec5e96190f54e74e58e9` | [#67](https://github.com/vjmichael/nvp_offline_film/pull/67) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 135 | `nvp/solo-creator-foundation-20261102` | `e9e20058f11db4b6249e3829024fe0a6be5b2c2e` | [#2](https://github.com/vjmichael/nvp_offline_film/pull/2) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 136 | `nvp/stack01-reuse-first-component-bundling-20261103` | `00e925e47284651f419e438ec14ea53d44b99a32` | [#24](https://github.com/vjmichael/nvp_offline_film/pull/24) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 137 | `nvp/stack02a-durable-blender-worker-20261103` | `edde018aec55a83825cadc38e5ae98f6f8284a64` | [#25](https://github.com/vjmichael/nvp_offline_film/pull/25) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 138 | `nvp/stack02b-os-contained-blender-workers-20261103` | `0fc0abe71c3a4797c31e86fc4a8c98e744c4f17e` | [#26](https://github.com/vjmichael/nvp_offline_film/pull/26) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 139 | `nvp/stack02c2-linux-cgroup-guardian-20261103` | `06f837bc546b8204e7417244b29e15997401dd6c` | [#28](https://github.com/vjmichael/nvp_offline_film/pull/28) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 140 | `nvp/stack02c3-resource-governor-progress-20261103` | `ac2cf37c8a7785b862cd97f071d50cae875f6f00` | [#29](https://github.com/vjmichael/nvp_offline_film/pull/29) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 141 | `nvp/stack02c3b1-priority-admission-20261103` | `37dfa63387cfa6538d4834745384dd8c7a2ac012` | [#30](https://github.com/vjmichael/nvp_offline_film/pull/30) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 142 | `nvp/stack02c3b2-owned-native-lifecycle-20261103` | `c32170fc98d848157060be6b2d86a851195bb00b` | [#31](https://github.com/vjmichael/nvp_offline_film/pull/31) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 143 | `nvp/stack02c3b3-estimated-model-recovery-20261103` | `d962e5cedb3cb98e0bff98f8d4b67e466635c4e5` | [#32](https://github.com/vjmichael/nvp_offline_film/pull/32) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 144 | `nvp/stack02c3b4-lu-alpha-evidence-20261103` | `9bb12b5013d183a2fb79bcb9700991d93eba709f` | [#33](https://github.com/vjmichael/nvp_offline_film/pull/33) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 145 | `nvp/stack02c3b5-authenticated-lu-status-20261103` | `363fd131c7df5307e7e90ff75494f07509f12111` | [#34](https://github.com/vjmichael/nvp_offline_film/pull/34) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 146 | `nvp/stack02c3b6-project-render-preflight-20261103` | `8331b27103dfbd90bf624f252a3500f14899485f` | [#36](https://github.com/vjmichael/nvp_offline_film/pull/36) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 147 | `nvp/stack02c3b7-native-approved-proxy-render-20261103` | `b3c950bd4e7042e3303f79ebb3baa1efa69de215` | [#37](https://github.com/vjmichael/nvp_offline_film/pull/37) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 148 | `nvp/stack02c3b8-frozen-take-native-replay-20261104` | `7931a8c24f41b128ad71ac2611c9c17515480db3` | [#38](https://github.com/vjmichael/nvp_offline_film/pull/38) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 149 | `nvp/stack02c3b9-native-exr-sequence-20261104` | `784afda2e79179d3c7aa226655ba76049488132d` | [#39](https://github.com/vjmichael/nvp_offline_film/pull/39) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 150 | `nvp/stack02c3b10-ocio-aces-highres-20261104` | `4eb41ae367214088286cd83f727b77416c3d4b3a` | [#40](https://github.com/vjmichael/nvp_offline_film/pull/40) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 151 | `nvp/stack02c3b11-sdr-editorial-handoff-20261104` | `722b180e19bf34a7174f2c89304288478b5714c6` | [#41](https://github.com/vjmichael/nvp_offline_film/pull/41) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 152 | `nvp/stack02c3b12-editorial-interchange-delivery-20261104` | `894b3ba41775b82ed12eec7f879d3b138786fcea` | [#42](https://github.com/vjmichael/nvp_offline_film/pull/42) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 153 | `nvp/stack02c3b13-otio-reimport-revisions-20261104` | `895e376fddbec136e0d86f2fa093547b8e1b0eac` | [#43](https://github.com/vjmichael/nvp_offline_film/pull/43) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 154 | `nvp/stack02c3b14-picture-conform-20261104` | `760e2e742f30c991da89c3fdddc29be4c03d474d` | [#45](https://github.com/vjmichael/nvp_offline_film/pull/45), [#44](https://github.com/vjmichael/nvp_offline_film/pull/44) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 155 | `nvp/stack02c-host-lease-windows-native-blender-20261103` | `9f96772cdddd8582645fa21c0af7af196cafb568` | [#27](https://github.com/vjmichael/nvp_offline_film/pull/27) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 156 | `nvp/story-approved-context-20261102` | `888e4c8e5579e396c3b05025f1a4ce5777ad6533` | [#3](https://github.com/vjmichael/nvp_offline_film/pull/3) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 157 | `nvp/story-bible-continuity-20261102` | `787ed061b375c4e0bcd47b2b5453f77ec10abc01` | [#4](https://github.com/vjmichael/nvp_offline_film/pull/4) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 158 | `nvp/story-bible-writing-context-20261102` | `d833fb1c5af2c2fabf208e0be7fbc7b14f87db4f` | [#5](https://github.com/vjmichael/nvp_offline_film/pull/5) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 159 | `nvp/story-chronology-knowledge-20261102` | `ddd156b17dd06ba7e9853c119697af26c818bbc2` | [#6](https://github.com/vjmichael/nvp_offline_film/pull/6) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 160 | `nvp/usd01-compose-time-take-20261105` | `aa9ce3e7382c55c18d45694a9615796a0070229c` | [#49](https://github.com/vjmichael/nvp_offline_film/pull/49) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 161 | `nvp/usd02-reusable-assets-state-20261105` | `b8724add15461c1a9efdf0afc3093826a7fd458b` | [#50](https://github.com/vjmichael/nvp_offline_film/pull/50) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 162 | `nvp/usd02c-typed-performance-channels-20261105` | `adbd270b1b86f6176ada58567ff54423b605ba56` | [#51](https://github.com/vjmichael/nvp_offline_film/pull/51) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 163 | `nvp/usd02d-native-schemas-20261105` | `6bebb609f1baf19a30ca1ad3adc9d4f6af36fa96` | [#52](https://github.com/vjmichael/nvp_offline_film/pull/52) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 164 | `nvp/usd-film00-native-capability-audit-20261108` | `c80293fb59dadb36862d8888a751781f36faf577` | [#128](https://github.com/vjmichael/nvp_offline_film/pull/128) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 165 | `nvp/usd-film01-scalable-world-composition-20261108` | `24285bafd8ac3f8dba66bbeca7b045142c74fd72` | [#129](https://github.com/vjmichael/nvp_offline_film/pull/129) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 166 | `nvp/usd-film01c-scoped-lazy-resolver-20261108` | `976928971fd524d3765a2eb9e38dcdc5e55a355c` | [#130](https://github.com/vjmichael/nvp_offline_film/pull/130) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 167 | `nvp/usd-film01d-shot-working-set-20261108` | `700b07d8d8cf2961a7f283c807ca12774e740f29` | [#131](https://github.com/vjmichael/nvp_offline_film/pull/131) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 168 | `nvp/usd-film01e-world-digital-take-20261108` | `eca7264d7da0389b82f665ef84ffb5dfc10b7533` | [#132](https://github.com/vjmichael/nvp_offline_film/pull/132) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 169 | `nvp/usd-film01f-world-render-20261108` | `68590cd36ca3e7ab0db2cca29d6a42317f9a4d50` | [#134](https://github.com/vjmichael/nvp_offline_film/pull/134) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 170 | `nvp/usd-film01i-ninecam-source-20261108` | `aa5f50d1b5ef950173a9d57397cc26f35c101b8a` | [#135](https://github.com/vjmichael/nvp_offline_film/pull/135) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 171 | `nvp/usd-film01m-director-flex-camera-20261108` | `f231c9b0f8ebc72401188ee699e75202b072e5c9` | [#136](https://github.com/vjmichael/nvp_offline_film/pull/136) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 172 | `nvp/usd-film01n-render-director-cameras-20261108` | `2324f106d7a3baf24c30788f8acd022c3c896c88` | [#137](https://github.com/vjmichael/nvp_offline_film/pull/137) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 173 | `nvp/usd-film01o-reconciled-20261108` | `4895c8be30545c71c1aa3e1eeb3781172dc76132` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 174 | `nvp/usd-film01o-resumable-camera-rolls-20261108` | `34ce2f751923290a3af9363c7d613c98b34ce7e1` | [#138](https://github.com/vjmichael/nvp_offline_film/pull/138) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 175 | `nvp/usd-film01q-selective-view-render-20261108` | `06ea8752b2d4ec38ee46129949019a15f586aeb0` | [#140](https://github.com/vjmichael/nvp_offline_film/pull/140) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 176 | `nvp/usd-film01r-interactive-editor-20261108` | `25eb5456a53d3abc56e42c92b3d2015d5b3a3090` | [#141](https://github.com/vjmichael/nvp_offline_film/pull/141) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 177 | `nvp/usd-film01s-adaptive-resource-batching-20261108` | `d80392b9c6c0c727dc8b572eb679df55bfaf444c` | [#139](https://github.com/vjmichael/nvp_offline_film/pull/139) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 178 | `nvp/usd-film01t-durable-selected-conform-20261109` | `f7b07ed46abe857f4e2dd23ba0c79a5053f67bfd` | [#142](https://github.com/vjmichael/nvp_offline_film/pull/142) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 179 | `nvp/usd-film02m-d-openings-interiors-cells-20261109` | `1ac45751e8b42d19fbbdf86870776ebeb28c05e2` | [#144](https://github.com/vjmichael/nvp_offline_film/pull/144) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 180 | `nvp/usd-film02m-e2-native-material-light-lod-20261109` | `ad79b092d4c400332775a1363b522d2ad85566df` | [#147](https://github.com/vjmichael/nvp_offline_film/pull/147) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 181 | `nvp/usd-film02m-e-layered-district-instancing-20261109` | `c2536c7614abda28ec3d367940821dfd50763973` | [#145](https://github.com/vjmichael/nvp_offline_film/pull/145) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 182 | `nvp/usd-film02m-f-trusted-director-authoring-20261109` | `6215f53b5a975d46674886bb9e2e50074b45ac32` | [#148](https://github.com/vjmichael/nvp_offline_film/pull/148) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 183 | `nvp/usd-film02m-module-socket-assembly-20261109` | `6f4d7c106413d8f774f4a6fe0d7790b0f97d3065` | [#143](https://github.com/vjmichael/nvp_offline_film/pull/143) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 184 | `nvp/usd-film02mf-fgh-native-repair-round2-20261109` | `1bce6e4a563312d21646b399cfa8c7ab94249f40` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 185 | `nvp/usd-film02mf-grouped-model-world-staging-20261109` | `1bce6e4a563312d21646b399cfa8c7ab94249f40` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 186 | `nvp/usd-film02mh-real-shot-cycles-20261109` | `101b4fbf31b72687362571b10e9c12702613ca0f` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 187 | `nvp/usd-world-full-film-integration-roadmap-20261108` | `1bab34f683b23b2202eac0ac131d253c3d36ea7c` | [#127](https://github.com/vjmichael/nvp_offline_film/pull/127) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 188 | `nvp/vlight-digital-preview-raster-20261108` | `efaf455db734266df3cab9935d8dfcd7535421f6` | [#107](https://github.com/vjmichael/nvp_offline_film/pull/107) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 189 | `nvp/vlight-fx-clock-bounce-dci-20261108` | `28f20fab42d4a3e4874dbe3f0f32266b6598e675` | [#105](https://github.com/vjmichael/nvp_offline_film/pull/105) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 190 | `nvp/w1g-p1a-sec06-integrated-20261112` | `14ebd6da05d0e6b18d5ad0826cedea03d9cd6d34` | [#158](https://github.com/vjmichael/nvp_offline_film/pull/158) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 191 | `nvp/wave1-longfilm-runtime-pcm-20261111` | `f2ddf5d76ed0739163463428a2d2ac8d4e5355e0` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 192 | `nvp/wo1-integrated-native-regressions-20261107` | `414aa0d55deaca2d13bfe4fe66737ff19d50268f` | [#94](https://github.com/vjmichael/nvp_offline_film/pull/94) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 193 | `nvp/wo2-slate-native-approval-consistency-20261107` | `914ed985bce8af2f9f56be2b4d1fc0d1fb65b501` | [#95](https://github.com/vjmichael/nvp_offline_film/pull/95) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 194 | `nvp/wo2-usd-uv-verified-20261107` | `4945151a189ad8568ae5181284f7472bd180e446` | [#87](https://github.com/vjmichael/nvp_offline_film/pull/87) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 195 | `nvp/wo3-materialx-renderer-integrity-20261107` | `f37068198418a4fb47169d2cfe5b56cfb3f21296` | [#96](https://github.com/vjmichael/nvp_offline_film/pull/96) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 196 | `nvp/wo3-native-dcp-complete-20261107` | `ee9f159fcda444d483a005861870e080a2b32c8f` | [#89](https://github.com/vjmichael/nvp_offline_film/pull/89) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 197 | `nvp/wo3-native-dcp-package-20261107` | `7385f48d9b83b5b11fe88fc390eb591c730e76bd` | — | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 198 | `nvp/wo4-cinema-mastering-20261107` | `483a7d444e6e2530e864ec19fe786f33a7a444e5` | [#90](https://github.com/vjmichael/nvp_offline_film/pull/90) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 199 | `nvp/wo5-installed-sustained-original30-20261107` | `d49910076290f67f98d6d50ad36710cacc135c2c` | [#92](https://github.com/vjmichael/nvp_offline_film/pull/92) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 200 | `nvp/wo5-preview-pcm-custody-closeout-20261107` | `b99a0fd1e09edcf838e5b524b82be5e21fc9fad1` | [#97](https://github.com/vjmichael/nvp_offline_film/pull/97) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 201 | `nvp/wo5-production-proof-20261107` | `efa091f7bda65f6f5e49c9176eb2de5a0c57203f` | [#91](https://github.com/vjmichael/nvp_offline_film/pull/91) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 202 | `nvp/wo6-07e-synchronized-director-preview-20261108` | `581a857ad54d37dca6ba19545dca6a448303d742` | [#103](https://github.com/vjmichael/nvp_offline_film/pull/103) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 203 | `nvp/wo6-07f-rendered-source-av-20261108` | `638d5e8f6be787d75ccbfdd50ed7ea73007cbf2a` | [#104](https://github.com/vjmichael/nvp_offline_film/pull/104) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 204 | `nvp/wo6-ai-creator-guidance-20261107` | `a28af7d17563f7a25a7cc9da316e8385ee169f8a` | [#93](https://github.com/vjmichael/nvp_offline_film/pull/93) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 205 | `nvp/wo6-director-model-proposal-20261107` | `2f7a2ab3a40bb2fd72db2d47b263dbf7e7ff03db` | [#99](https://github.com/vjmichael/nvp_offline_film/pull/99) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 206 | `nvp/wo6-exact-dispatch-recovery-20261107` | `b4c98a913a36a7685c62783d00ea7a2bfd3aa7e0` | [#98](https://github.com/vjmichael/nvp_offline_film/pull/98) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 207 | `nvp/wo6-real-model-installed-director-20261107` | `7feccdf69eb6d04c24cce9c0cf3028b20b52b2ee` | [#100](https://github.com/vjmichael/nvp_offline_film/pull/100) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 208 | `nvp/wo6-reviewed-ai-sound-editorial-20261107` | `99f5803146570ab07513183c54547e69ceec8447` | [#102](https://github.com/vjmichael/nvp_offline_film/pull/102) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |
| 209 | `nvp/wo6-reviewed-ai-to-approved-shot-20261107` | `e05febde2e81c230ba4499c2b44941698a108770` | [#101](https://github.com/vjmichael/nvp_offline_film/pull/101) | INVENTORIED; UNIQUE COMMITS/RECEIPTS NOT YET RECONCILED |

## Open PR refs not found in current branch listing

None in this snapshot.

**Stopping rule:** No 'all branches consolidated' claim until every census row is marked absorbed, equivalently superseded, or rejected with original evidence; the chosen candidate is fully proven and integrated into `main`. The existence of this inventory is not merge completion.
