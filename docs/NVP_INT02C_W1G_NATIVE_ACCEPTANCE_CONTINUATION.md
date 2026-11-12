# INT-02C / W1-G — Native integration and acceptance continuation
12 November 2026, source-only checkpoint, separate integration branch

## INT-02C actual native film evidence

The tools/nvp_int02_native_acceptance.py read-only audit now checks an
existing 30-second edited film against the *original* FilmIndex and the
committed SlateSequenceAssembly revision. All 720 picture samples and
1,440,000 original PCM sample values are independently reopened.
Every nonblank Full-HD picture must match its source-relative Film Time,
the exact native BlenderWorkerSupervisor job, its registered Cycles
audit/source USD SHA, and the delivered picture SHA. An altered picture,
changed source, missing worker receipt or all-black source is rejected.
The audit does not render or grant approval. Its status cannot stand in
for physical color, acting, sound or filmmaker acceptance.

Repaired previous unrun source test: the mocked film project was called
OriginalProject despite FilmIndex requiring 32 lowercase hexadecimal
characters. The fixture now uses the real identity format.

## W1-G native process and upgrade safety

backend/nvp_w1g_kernel_custody.py now performs OS-provenance-dependent
checks on the original supervised worker process, not on a supplied PID.
Windows uses the real Job Object handle and demands kernel accounting
ActiveProcesses == 0, terminating remaining descendants before closing
the handle. Linux requires a genuine CgroupTreeProcess, successful
guardian shutdown and removal of its delegated cgroup-v2 leaf.
No generic callback may substitute for this internal OS verification.
backend/nvp_w1g_protected_native_worker.py uses this witness before
accepting any independent application-domain result.

The NSIS installer creates a complete NVP.pending release (including
its own uninstaller and version file), but does NOT replace the active
installation during a normal update. The older direct-rename-on-upgrade
and restart auto-restore paths were unsafe without verified OS worker
custody; both are removed. Only new clean installs are promoted by
the installer itself.

tools/nvp_w1g_nsis_activation.py implements the separate trusted-host
update transaction: exact per-file audited payload, newer registered
version, original film preservation, two fresh Windows kernel stop
witnesses surrounding one-use creator approval, program-only atomic
renames, durable state, and uncertain recovery inspection. No old
film/project directories are recursively removed.

tools/nvp_w1g_windows_installed_acceptance.py verifies a real installed
NVP.exe from an exact external package receipt and executes new
create/reopen + WebView2 + original A/V tests as Windows Job Object
processes. Every process-tree exit must have independent kernel proof;
the original project hashes are rechecked at the end.

The EXISTING MANUAL-ONLY Windows installer workflow now contains these
negative source tests and the native installed Windows runner. It also
repairs NVP_HOME cross-step propagation. No CI workflow was dispatched.

## Remaining native and physical acceptance

INT-02C: actual Blender/Cycles 720-frame render, shot composition,
rigged actors, materials, lighting/occlusion, color science, proper
encrypted-source staging, correct verified spatial sound and a playable
single-file FFmpeg-free final master remain open.

W1-G: real compiled NSIS installer upgrade/cut-power/rollback,
tested Windows Job Object process trees and Linux delegated cgroup,
actual reviewed native workers, license/dependency provisioning,
and an accepted exact release candidate remain open.

W1-F: human-operated creator Windows acceptance and real sustained
30-minute/feature-length filmmaking, shutdown/restart/scale/quality
verification remain separately open.

## Evidence honesty

This execution environment is Linux without Blender, OpenUSD pxr,
Windows WebView2, NSIS or a locally mountable repository checkout.
The GitHub connector allowed code/source commits, not actual native
subprocess tests. None of the new tests, real renderer runs, installer
upgrades or physical owner sessions has been completed here. No
test pass is inferred from test source being written.

No FFmpeg primary path or retired proxy workflow reintroduced; no
merge/release to main was authorized.

### 2026-11-12 — W1-G visible WebView2 and installed automation ACCEPTED (bounded scope)

**Accepted source head:** `46d59d3719363774b1e6c9b8c658bb5573230c40` on isolated branch `nvp/int02-w1g-native-film-package-20261112`; **no merge or release to main**. The exact-head [Windows NSIS/installed alpha run 43311316164](https://github.com/vjmichael/nvp_offline_film/actions/runs/43311316164) finished **SUCCESS** and the [four-job genuine Windows/Linux native Cycles and worker run 43311316271](https://github.com/vjmichael/nvp_offline_film/actions/runs/43311316271) finished **4/4 SUCCESS**. The Windows workflow independently passed native installed `NVP.exe` save/reopen, original OpenUSD/PCM, genuine visible WebView2 page/React/native IPC, staged candidate NSIS activation/rollback **in the acceptance transaction matrix**, native Windows Job Object process custody, and uninstall without changing original films. Original installer build and installed bytes were audited. This closes the **W1-G visible desktop startup and automated installed acceptance subtask**, not the full W1-G release gate.

**Demonstrated defect and repair:** installed native bridge initialization previously hung in pywebview's recursive JavaScript API function inspection after `before_load`. The trusted camera bridge exposed public references to the GUI window and FilmIndex/SQLite authority; recursive object traversal prevented the WebView2 `loaded` event. The accepted fix introduces the explicit 28-method `NativeWebviewIPCSurface` with no public authority/window/data objects, while the underlying trusted bridge retains native origin, human authorization, cancellation and immutable-source checks. Matching unit regressions and the actual installed WebView2 IPC smoke passed.

**Not accepted by this result:** unattended or production-authorized upgrades/cut-power recovery, original kernel custody across a real operator-approved production upgrade, redistributable signed/licensed worker and wheelhouse provisioning, encryption/key-custody release, physical creator-operated Windows acceptance (W1-F), sustained real 30-minute/feature film, a full 720-frame production render/finished master and real hardware spatial-sound acceptance. The staged NSIS matrix uses simulated creator authorization; its success is not live authorization for upgrading the owner's machine. No physical-human gate or release approval is implied. W1-G **automated desktop/installed slice: CLOSED**; W1-G **production-release slice: OPEN**; INT-02C **full-film acceptance: OPEN**; W1-F **physical and sustained acceptance: DEFERRED/OPEN**.

Detailed closeout: [W1-G WebView2 automated installed acceptance](NVP_W1G_WEBVIEW2_AUTOMATED_INSTALLED_CLOSEOUT_20261112.md).


### 2026-11-12 — W1-G production release gates: implementation, acceptance OPEN

New dedicated source/design record: [W1-G production authority, dependency review and protected original staging](NVP_W1G_PRODUCTION_AUTHORITY_DEPENDENCIES_ENCRYPTION_20261112.md). Production NSIS activation now rejects callback-based simulated owner/kernel receipts; genuine Windows native approval, original Job Object handle and held WorkerHostLease across check/consent/rename, a signed exact-artifact Ed25519 license inventory and a reviewed worker roster are required. A separate production-only rollback preserves old/new binaries, registers the restored version and remains fail-closed on interrupted recovery. The Windows NSIS filesystem regression matrix alone is still a TEST simulation (no owner consent or kernel-custody acceptance).

Native dependency/wheel and worker-roster validation gained zip traversal/links/expansion bounds and alias/device-name refusals. Real licensed binary rosters, platform wheelhouse, an owner-pinned reviewer key and independently signed redistribution record are **not supplied** and thus UNPROVISIONED. Original USD sent to Blender now requires EFS-encrypted worker scratch by default with pre-write inheritance proof; Windows EFS keys, physical device behavior, full key management and Linux protected staging are unverified. Original FilmIndex encryption itself is not claimed. **W1-G production-release acceptance stays OPEN**; W1-G visible WebView2/automated installed acceptance remains CLOSED at the earlier successful commit `46d59d3`. INT-02C full native film and W1-F creator physical/sustained acceptance stay OPEN.


### 2026-11-12 — W1-G/W1-F release-wide worker custody, owner-only gates and sustained film audit (SOURCE IMPLEMENTATION)

See [W1-G/W1-F release-wide native/owner acceptance engineering](NVP_W1G_W1F_RELEASE_WIDE_NATIVE_OWNER_ACCEPTANCE_20261112.md). The prior single Windows Job Object closeout witness did not cover independent original worker supervisors. New shared native Windows 128-slot lifetime release fence covers central `launch_contained` process trees and normal GUI host lifetime; an upgrade obtains all slots and all explicitly declared five domain WorkerHostLease roots, then checks exact original program/worker journal identities. Windows regression cases exercise multiple live jobs, hard host death, and interrupted worker journal denial. Activation refuses old or candidate programs lacking a signed-inventory source-build release fence marker. The original owner-only Windows upgrade/rollback path retains OS approval; rollback journals now represent `PRODUCTION_ROLLBACK_INTENT` and `ROLLED_BACK` for read-only interruption review.

Unreviewed offline wheel/package bytes can now be inventoried into a **review candidate** that release admission explicitly rejects until independent license review, executable roster, full pinned supply, external signing key and signed approval exist. Windows EFS disposable source prepare/reopen is available for real owner hardware; genuine key recovery and physical EFS security remain unverified. W1-F receives a read-only 30-minute/three-hour original reel audit requiring all genuine Cycles and original PCM subfilms; it does not construct a complete master. **W1-G production physical acceptance, reviewed native binaries/legal approval, complete direct-child filming/legacy worker enrollment, full-film INT-02, and W1-F long-duration physical filmmaking all remain OPEN.** No release/merge/physical claim. Source head at time of this ledger update will need exact-head CI, not inferred from prior green.
