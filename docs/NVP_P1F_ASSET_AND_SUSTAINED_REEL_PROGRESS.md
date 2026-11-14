# NVP P1-F — Production Assets and Sustained Multi-Reel Execution

This ledger continues the canonical data-first NVP sequence after the passing public-fixture Windows SCM AppContainer/WFP/Job Cycles and original Linux delegated-cgroup/namespace acceptance. The current branch is draft PR #159, not a production release.

## P1-F-A1 — Reviewed UV/PBR source maps (implemented, native acceptance pending)

- `backend/nvp_p1f_reviewed_pbr_materials.py` and `OpenUSDAssetRegistry.import_reviewed_pbr_materials` admit exact frozen PNG source bytes for base color, roughness, metallic and normal into project-scoped SHA-addressed FilmIndex blobs.
- The texture set is bound to one immutable imported environment revision, the exact original USD material path, and every genuinely authored mesh UV primvar. Reject materials without bounded vertex/face-varying UVs, incompatible/unreadable images, missing base color, inconsistent dimensions, changed material bindings and changed frozen source bytes.
- A human-approved operation must cover the exact source digests, material/UV binding and supplied rights evidence (owner, license identifier and explicit render/derivative/distribution uses). An evidence document is stored immutably. This is **evidence custody, not independent legal verification** or a blanket commercial license.
- Does **not** allow an external USD resolver, arbitrary texture path, downloaded asset, model-selected file, protected worker admission or automatic film release.
- Native test: `tests/test_nvp_p1f_reviewed_pbr_materials_native.py`; original environment/actor tests remain unchanged. Actual licensed detailed assets, UV-to-Blender transfer, MaterialX and Cycles source-to-pixel material validation still OPEN.

## P1-F-R2 — Sustained source-range sequencing (implemented, native acceptance pending)

- `backend/nvp_p1f_sustained_reel_queue.py` independently reopens verified original picture/audio coverage, finds the next missing contiguous frame window and caps it at the current 240-frame / 10-second native reel boundary.
- Returns a review-only source manifest including plan document SHA, original Take and camera identities and exact source/output Film Time. The creator must approve the exact review SHA before the finite durable batch can be reserved. A batch does **not** authorize worker execution.
- `P1FDurableShotReels.create_batch` now checks historical overlapping original source frames under the same SQLite `BEGIN IMMEDIATE` writer lease. Distinct batch IDs cannot double-dispatch a queued, running, accepted or untrusted frame; terminal interrupted/failed frames need a fresh separately approved batch.
- Each actual frame still requires individual one-use host authorization, independent private OS worker boundary, verified Cycles PNG and original 48k actor-owned PCM. No unattended multi-hour batch authority, silent retry or accepting a partial film as master.
- Native tests extend `test_nvp_p1f_multishot_recovery.py` with overlap, partial acceptance, stale review, creator refusal and finite next-source admission. Earlier genuine public 2-frame Cycles and WAV coverage acceptance remains separate.
- **No 30-minute or 3-hour film has been rendered.** Required outputs are 43,200 / 259,200 genuine picture frames and 86,400,000 / 518,400,000 independently validated 48k samples per channel.

## Remaining execution backlog (do not conflate with implementation)

1. Reconcile original P1-F-A1/R2 Windows/Linux Python 3.11/3.13 native suite, preserving all original tests and the no-FFmpeg policy. Repair only demonstrated failures at one SHA.
2. Derive reviewed UV/PBR texture maps onto actual imported original environment geometry in a fixed, fully authorized Blender/Cycles worker; independently verify source image SHA, original USD, decoded result and frame receipt. Production-private source must use the accepted native kernel boundary, not a public fixture shortcut.
3. Import genuinely detailed licensed character and environment assets with reviewed rights, full articulated body, face/visemes, stage lighting and continuity. Miniature CI actors do not qualify.
4. Run multiple source-verified finite reels under genuine installed Windows SCM AppContainer/WFP and root-owned Linux cgroup+namespace custody. Test cancellation, guardian death, restart, revoked approval, missing frame and replay denial without weakening the original security matrix.
5. Deliver independently audited picture/audio segments with cross-reel continuity, then secure film mastering and creator-controlled export. Only accept actual complete 30-minute production after genuine full output; then scale to 3 hours.

**Status:** source implementation in draft, no merge/production install; all asset, sustained film and distribution acceptance above remain independent gates. The optional speculative photoreal 2D generative-transfer concept has not been implemented.
