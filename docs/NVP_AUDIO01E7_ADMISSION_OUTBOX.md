# NVP AUDIO-01E.7 — Recoverable native admission and strict guardian acceptance

**Status:** Native admission outbox committed, Windows/Linux crash-injection tests added, exact-head CI pending. Delegated Linux cgroup guardian acceptance is **not yet verified**.

## Split-commit failure addressed

Audio creation previously used two SQLite databases and multiple transactions: an audio journal/immutable plan, a native grant and staging lease, then an `ApprovedTaskBindings.enqueue` call that atomically inserts a TaskLedger task and its approved spec. A host crash between the grant and enqueue left the job permanently stranded, despite a valid creator authorization. Simply synthesizing a task or claiming the worker ran would be unsafe.

AUDIO-01E.7 adds `audio_native_admission_outbox` in **the same TaskLedger transaction** as the native grant and staging-lease claim. The outbox persists the canonical immutable operation document, its SHA-256, the approval ID, owner key, memory reservation request and `pending` state.

`NativeAudioHost.reconcile_admission_outbox(job_id)` replays that intent only when the original source/worker hashes, creator approval policy, audio journal identity, staging lease and sealed document all still match:

- **Crash before queue commit:** Recreate the *queued* task using existing `ApprovedTaskBindings.enqueue`, which makes the durable task and approved spec one atomic transaction.
- **Crash after queue commit, before outbox acknowledgment:** Verify the existing `QUEUED` task and its original immutable spec. Never create a second task.
- **Already ACTIVE or terminal:** Refuse outbox replay. No resource release, new admission, worker restart or fabricated stop receipt.
- **Creator approval revoked, worker plan altered or grant mismatch:** Refuse replay without changing resource or authorization records.
- **Legacy incomplete grant without a persisted outbox:** Keep it quarantined for native audit; no guesswork.
- **SQLite state transitions:** Outbox moves to `enqueued` only after the durable TaskLedger task and sealed spec have been verified.

`tests/test_audio_admission_outbox.py` injects crashes on *both sides* of the TaskLedger enqueue transaction, reconstructs the native host from the same databases, checks exactly one queued task, and tests revoked creator approval and corrupted worker plans. These tests are added to the B14 production Windows/Linux contract workflow.

## Strict Linux descendant guardian requirement

The existing cgroup-v2 launcher and out-of-tree guardian are now the default for the Linux production audio host. Ordinary process-group mode is explicitly test-only or reduced-assurance use.

`tests/test_audio_linux_strict_cgroup.py` distinguishes:
- No cgroup delegation: strict launch fails closed.
- Real delegated cgroup: actual host death, detached worker descendant and kernel `cgroup.events` verify the guardian kills the entire cgroup.

Hosted runners commonly lack writable systemd cgroup delegation. The real guardian test therefore skips in ordinary CI when the environment cannot perform it. **Skip is not acceptance.** To enforce genuine acceptance on a configured delegated host, execute:

```bash
NVP_REQUIRE_DELEGATED_CGROUP=1 python -m unittest discover -s tests -p test_audio_linux_strict_cgroup.py -v
```

With that setting, missing delegation is a **test failure**, not a skip. A delegated host should also run the actual AUDIO-01E native worker tests with strict mode explicitly enabled and inspect guardian exit and kernel cgroup evidence before production closeout.

## Boundaries and next steps

The outbox fixes the **grant-to-queue split commit**, not the journal-to-grant split. The journal and worker-plan files are still staged before the grant, so a crash there can leave a journal-only orphan. That must remain quarantined until a trusted cleanup/reconciliation path is implemented. Filesystem directory-fsync, descriptor-relative no-follow operations and OS-backed exclusive admission across noncooperating processes still require independent hardening.

No audio is auto-approved, mastered or muxed to the picture. AUDIO-01F follows after strict guardian evidence and native containment reliability gates.
