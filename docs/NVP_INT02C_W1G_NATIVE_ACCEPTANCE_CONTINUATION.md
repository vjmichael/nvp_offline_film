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
