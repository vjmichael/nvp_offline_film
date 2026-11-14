# NVP-STACK-02A — Verified external Blender worker and durable production tasks

**Engineering status:** **TECHNICALLY ACCEPTED** as a pinned external worker, on [successful GitHub CI run 41763801958](https://github.com/vjmichael/nvp_offline_film/actions/runs/41763801958): **3/3 jobs green**, Linux **6/6** contracts, Windows **6/6** contracts, and actual native Blender 5.2.3 scene/render/cancel/restart acceptance. Commercial packaging, OS post-crash containment and legal redistribution remain **NOT ACCEPTED**. 2026-11-03.

**Architectural basis:** [STACK-001](NVP_ADR_STACK01_REUSE_FIRST_AND_ONE_INSTALLER.md), [STACK-002](NVP_ADR_STACK02_BLENDER_WORKER_USD_DEFERRED.md). The standard Blender process performs the actual 3D work. NVP only supplies typed source files, supervises the process, independently audits its results, and stores durable provenance.

## Implemented scope

| Component | Purpose |
| --- | --- |
| `backend/nvp_blender_worker.py` | Fixed SHA-pinned Blender executable and exact version, trusted bpy script SHA, source SHA, sandbox-relative paths, approved output kinds (BLEND/PNG/EXR/audit JSON), bounded arguments, one-task identity and bounded subprocess |
| `BlenderWorkerSupervisor` | Durable SQLite FULL synchronous state/events and periodically checkpointed worker output size, idempotency conflict refusal, process cancellation, timeout/process-group termination, independent readback and re-hashing |
| `backend/nvp_supervised_production.py` | **Uses existing NVP ProductionScene and independent AUDIT_SCRIPT**: produce approved scene → external Blender build → independent second Blender process reopen/audit/preview. Two separate worker jobs with content hashes; no second renderer |
| `tests/test_blender_worker.py` | Pure contract tests for pinned executable/version, untrusted path/flag refusal, idempotency, restart interruption, hash tamper and cancellation |
| `tools/nvp_stack02a_worker_fixture.py` | Native real Blender 5.2.3 render and verified BLEND+PNG+audit JSON, failure/cancel checks, independently restarted output recheck, and an approved NVP original scene via the same supervisor |
| `.github/workflows/nvp-stack02a-blender-worker.yml` | Linux and Windows supervised-worker contract tests plus SHA-checked actual Blender binary and production-scene acceptance |

## Durable lifecycle and verification

1. A trusted NVP host configures the **absolute external Blender executable** and its verified SHA-256 and version. NVP does not import or link GPL Blender libraries. The exact packaged executable is tracked separately.
2. Approved producer files are copied to a per-job workspace and pinned with SHA-256. A Blender operation declares exact input hashes, approved output relative paths/types and a short allowlist of positional file flags. The model/browser does not have access to this privileged executor.
3. NVP starts the external Blender process with `subprocess.Popen(...,shell=False)`; execution is bounded by a timeout. Linux uses a new process session/process group and kills the group on cancellation. Windows uses a new process group and attempts `taskkill /T /F` for an owned child.
4. The SQLite WAL journal records `PREPARED → RUNNING → SUCCEEDED | FAILED | CANCELLED | TIMED_OUT`; the host requests a cancellation through the active worker token. Output hashes only become accepted if the process exits successfully **and** input files still match, declared output magic/size/audit contents match and every output receives a SHA.
5. A subsequent independent `verify_completed` rereads the job specification, verifies source hash identity, validates outputs and recomputes their current bytes against the committed receipt. Corrupt output is refused even if the original SQLite record was `SUCCEEDED`.
6. On a genuine cold restart, `recover_interrupted` changes `RUNNING` or `CANCEL_REQUESTED` jobs to **INTERRUPTED**. NVP deliberately does not trust abandoned outputs or automatically replay. A fresh unique job must be planned from the original frozen take.

## Production-worker limitation gates — NOT YET ACCEPTED

- **Windows crash-safe kernel process containment:** A Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` or equivalent must be established, with verification that children die when their supervisor crashes. Current `taskkill` is only a cooperative live-host fallback; it is not proof of crash cleanup.
- **Linux process group after parent crash:** Running children may survive a hard host crash; a persistent host-level supervisor, cgroup, `PR_SET_PDEATHSIG` or audited containment mechanism is needed to guarantee orphan cleanup. Current recovery rejects untrusted outputs but cannot honestly certify child termination.
- **Multiple NVP host instances:** The current SQLite ledger implements per-job primary key uniqueness, but cold-start recovery assumes a single host owns the worker journal. Introduce a robust cross-process host lease or lock before supporting concurrent desktop instances.
- **Memory/GPU guardrails:** Bounded timeout and Blender's fixed thread argument are not RAM/VRAM quotas. Introduce OS-enforced worker memory/CPU constraints and retain a conservative renderer load guardrail.
- **Full execution coverage:** This integration covers approved proxy scene build/audit; extend all capture/animation/Cycles and meshpack operations through the same proven supervisor, replacing direct subprocess call sites while preserving acceptance.
- **Commercial distribution:** The exact Blender build, bpy adapter scripts, source offers, notices, transitive binary dependencies and installer behavior need GPL legal review. This work does not declare GPL compliance or a redistributable retail installer.
- **Source authority:** Technical acceptance is not user creative approval. The original Film World, approved screenplay and Digital Take remain authoritative; output derivatives cannot be silently registered or misrepresented as finalized film delivery.

## Native acceptance expectations

- Linux, Windows, and actual native Blender gates **must be measured**. A source commit or unit test alone does not imply a Blender render occurred.
- **Verified:** the native fixture produced a real 128×72 Blender PNG and compressed Zstandard `.blend` scene; recognized Blender's legitimate Zstd container signature (not only the legacy raw `BLENDER` magic). A second actual Blender process reopened the original approved NVP stage and completed **9 independent geometry/identity checks**. Exact launch/version hashes, independent restart rehash, deliberate output tamper, failing Python child, active-process cancellation and interrupted-host recovery all passed.
- **Verified SHA-256s in the native artifact:** Blender executable `b8b07a190fb25db76aae6de08dbc6c2b3d64e22e82bed6ba90de9545859f3431`; real PNG `4a99067d5742d44979b1c34cda2c973c153be2fc7bedb8fad98a0d6531c8fd8f`; real compressed Blender scene `efa5864d0de2f317089b04fc1ea51fb1f57e776750eb8af186c75bb2d5a8baaa`. All independently rehashed after downloading the [native acceptance artifact](https://github.com/vjmichael/nvp_offline_film/actions/runs/41763801958).
- **Real Windows bug found/fixed:** Python's standard SQLite connection context manager does not close handles; explicit close is now enforced so clean deletion/uninstall does not fail with WinError 32.
- **Run 41763801958:** 3/3 jobs passed on the exact code implementing `--python-exit-code`; Blender 5.2.3 LTS version string included build hash and date. The audit report confirms `commercial_redistribution_license_cleared=false` and `orphan_cleanup_after_real_host_crash_proven=false` rather than making false release claims.
- The existing `ProductionScene.export_manifest` + `export_blender_script` and existing `AUDIT_SCRIPT` must complete the approved NVP scene build and independent geometry recheck in separate supervised Blender subprocesses.
- Source NVP movie data must be unchanged throughout; no tool result grants final creative approval.

## Where to go next

**STACK-02B:** Windows Job Objects, OS resource containment and crash-kill proof; supervised integration with all Blender/Cycles pipeline paths, not just staging. **STACK-01E:** reproducible one-click Windows installer and thorough GPL script/binary notice/source-compliance audit. **STACK-01A/B:** use OCIO/OIIO and OTIO/MLT instead of further custom color/edit math.
