# W1-G / W1-F — Release-wide kernel custody, owner approvals, supply review and full-film verification

**2026-11-12 — engineering implementation checkpoint, not a release approval.**  
**Branch:** `nvp/int02-w1g-native-film-package-20261112`  
**Prior exact-head accepted W1-G desktop:** `f04140e`, [installed Windows 43322395438](https://github.com/vjmichael/nvp_offline_film/actions/runs/43322395438) and [native Windows/Linux 43322395462](https://github.com/vjmichael/nvp_offline_film/actions/runs/43322395462). A green test runner does not operate the creator's actual PC.

## 1. Release-wide original kernel worker custody

**Demonstrated prior weakness:** `WindowsReleaseWorkerStopEvidence` was based on one `WindowsJobProcess` even though multiple Blender, editorial, capture, audio and delivery domains use independent Jobs. That singular handle cannot establish an entire release is quiescent.

**New implementation:** `backend/nvp_w1g_release_gate.py` uses a shared per-user Windows kernel lock file with one launch guard and 128 independent lifetime worker slots. The original central `launch_contained` Windows process holds a slot from before suspended CreateProcess until `WindowsJobProcess.close()` confirms original Job Object `ActiveProcesses==0`. The normal installed WebView2 host also holds a lifetime slot so a running desktop denies upgrade. A program mutation obtains the launch guard plus ALL slots exclusively and holds it through the full operation; any worker start or continuing child causes denial. A crashed NVP host releases kernel handles and kills Job-contained descendants; previous journals remain separately UNCERTAIN, never automatically approved.

The production stop authority now demands five independently declared workspace/journal roots — `cycles`, `filming`, `editorial`, `audio`, `delivery` — acquires their original host leases **before** the release gate (avoids lock inversion), and checks interrupted/failed tasks before admitting mutation. Missing domains are not silently inferred. Original source program and prior/failure directories are re-hashed before/after renames.

New native Windows negative and positive tests run two concurrent Job-contained children, deny upgrade until both trees close, force a real hard host crash, verify child death and lock release, and deny a stale interrupted journal. The OS lock is not a remote-PID or JSON receipt.

**Important remaining release gate:** complete verification of all original domain launchers, including existing direct-child filming and device-capture paths, against the same release-long journal/registration policy, and live physical restart/power-cut evidence. A successful fixture proves kernel exclusion for instrumented launch paths, not that every legacy native tool has yet been migrated.

## 2. Upgrade/rollback and exact release source enrollment

`tools/nvp_w1g_release_build_marker.py` adds a hash-bound build-time marker covering the central launch path, desktop lifetime gate, five intended release domains, and kernel cleanup protocol. The marker is added **before** the installed bundle is audited and becomes part of the independently signed release file inventory. Production activation refuses old/current or staged binaries without that marker. Existing unfenced older installations therefore require a new, reviewed clean install before production update promotion.

`NativeNSISActivation` admits only exact native Windows creator approval, a real release mutation gate and all five original worker journals; CI simulation remains explicitly separated. Production rollback records `PRODUCTION_ROLLBACK_INTENT` and `ROLLED_BACK` in the activation journal and maintains the independent rollback ledger. Interrupted first or second renames, registry failure and inconsistent old/new identities remain read-only review states; no stale approval is replayed.

`tools/nvp_w1g_owner_windows_acceptance.py` provides the owner-only native Windows coordinator for explicit prepare, activate, rollback and inspect actions. It requires a pinned external reviewer public key, signed precise release receipt, five original workspaces and the genuine native Windows consent dialog. **Not exposed as a browser/model API; not auto-dispatched in CI.** Genuine physically authorized upgrade and locked-file/power-loss recovery remain OPEN.

## 3. Real native-worker/offline dependency provisioning and licenses

`tools/nvp_w1g_supply_candidate.py` inventories existing, downloaded native wheel SHA and metadata and produces an **unsigned** exact-byte redistribution template tied to the real PyInstaller build receipt. `REVIEW_REQUIRED`, `UNKNOWN`, `NOASSERTION` and similar placeholders are now forbidden at both wheel-lock and signed-review admission. A candidate's manifest cannot sign itself or grant legal rights. Existing compiled executable roster checking, wheel traversal bounds, offline `--require-hashes`, and independently pinned Ed25519 release-review signature remain mandatory.

**UNPROVISIONED and therefore blocking:** actual reviewed first-party PE/ELF executable workers for each required capability; complete platform wheelhouses and exact transitive version/architecture locks; an independent redistribution/license approval and Ed25519 signature from the real reviewer; external pinned public key and license evidence; actual installation. The tools can prepare an honest candidate, not manufacture a vendor license or approval.

## 4. Encrypted original source and physical EFS test

Original Cycles USD source continues to require EFS-encrypted worker scratch BEFORE its first source write, and every source input is checked after staging and rendering. `tools/nvp_w1g_windows_efs_proof.py` provides a two-process disposable nonsecret test: `prepare` creates an EFS-protected scratch source and fsyncs a randomized sentinel; `reopen` from a fresh process re-verifies Windows EFS encryption and SHA then deletes ONLY the sentinel workspace. Failed EFS admission refuses protected film staging, without plaintext fallback.

**Still physically open:** EFS certificate/key availability and recovery backup, storage/ACL policy, encrypted FilmIndex originals and take key custody, crash-residue retention, output derivative encryption decisions, Windows physical user source tests. CI or this source-only tooling cannot authenticate the owner's recovery backup or certify a non-Windows protected stage.

## 5. W1-F / INT-02 genuine sustained film

`tools/nvp_w1f_reel_audit.py` adds a read-only long-form original-source verification boundary. It accepts **exactly 60 (30-minute) or 360 (three-hour) distinct native 30-second committed edit packages**, verifies contiguous temporal intervals, and independently calls the existing native 720-frame Cycles plus original PCM verifier on EACH segment. Any missing original Take, changed camera/worker receipt, retimed gap or repeated edit fails closed. A verified set of source segments is **not** falsely presented as a playable single-file finished master, synchronized continuous reel, mixed spatial audio or owner-reviewed cinema.

**OPEN:** producing actual continuous 30-minute native USD picture/audio, 720 production-quality Cycles samples per verified 30-second segment, seam and acoustic conform, proper secure source and final mastering, true sustained GPU/CPU/memory tests, actual physical playback/color/sound/filmmaker acceptance. A manifest without real original camera, worker receipts and PCM does not pass the audit.

## Acceptance classifications

- W1-G visible Windows WebView2 / automated installed alpha: **CLOSED** on existing exact-head green source.
- W1-G release-wide original worker custody and recovery: **implemented and native regression candidate**, real full-domain/physical release acceptance **OPEN**.
- W1-G legal/native worker/wheelhouse provisioning: **candidate tooling implemented; real approved inputs UNPROVISIONED**.
- W1-G protected EFS source: **preflight implementation; key/custody and creator physical acceptance OPEN**.
- W1-G production human-authorized upgrade/rollback: **source implementation, physical execution OPEN**.
- W1-F long-form + INT-02 full movie: **read-only native source integrity audit implemented, real sustained production / single master OPEN**.

No release, merge, fake human consent, signing key, license approval, or physical test result has been authorized or fabricated. Original immutable Digital Takes are not rewritten. No retired FFmpeg-primary film path is re-enabled.
