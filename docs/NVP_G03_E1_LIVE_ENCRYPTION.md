# G03-E1 — Host-owned encrypted live film storage

**State:** Implemented in draft PR #155; native Windows/Linux test and installed NSIS acceptance pending exact-head verification. Standalone NVP; G02 Lu integration deferred; canonical DATA-AV PR #74 unchanged; zero FFmpeg.

## Creator behavior

New Movie offers an optional **Encrypt this new movie on this Windows account** choice with a director-supplied passphrase. The idea, screenplay, scene headers, dialogue, revisions, first source OpenUSD/PCM files and recovery/worker receipts go directly into the encrypted host service, never through a working plaintext SQLite file. The existing shared catalog contains only movie ID/title and empty placeholder rows; titles remain PUBLIC.

An encrypted film reopens via the host protected /live route and can be manually edited, relocked and viewed in the separate Post-Production shell. Production capture, rendering and final export are not turned on by encryption. **Existing plaintext movies are not automatically converted**, so the existing Lock in NVP API-only feature must not be described as encryption of older film files.

## Cryptographic and crash-safety design

- The per-film random 256-bit AES-GCM content key is wrapped with current-user Windows DPAPI and a scrypt-derived passphrase entropy binding. The key never enters React, model prompts, HTTP requests, process arguments, worker messages or a plaintext key file.
- Host in-memory SQLite uses Python 3.11+ serialize/deserialize and memory-only journal/temp storage. All live ideas, screenplay revisions, source-asset index, native receipts and recovery decisions reside inside authenticated encrypted immutable SQLite snapshots.
- Private root: NVP_HOME/nvp_g03_encrypted_live/{project_id}. It stores key.nvpdpapi, a non-secret HEAD.json revision pointer, immutable encrypted revisions/db.<sequence>.nvpsealed and opaque keyed asset ciphertext in assets/*.nvpsealed. No plaintext .sqlite/.usda/.pcm/-wal/-shm is written by this new mode.
- For every revision the host takes a Python and native Windows/Linux OS-level per-film mutex, validates the host grant and expected revision, writes/flushes a new encrypted immutable snapshot, then atomically updates HEAD. Previous snapshots remain encrypted. After power loss, an orphan encrypted revision can be retained and a later commit advances to a fresh sequence without overwriting it.
- Original source bytes are encrypted before the SQLite index is published, independently decrypted/hashed and never edited in place. A crash after ciphertext but before index is recoverable only if an authenticated original matches the expected identity and digest. Logical source names remain only inside encrypted SQLite; filenames use opaque keyed HMAC identities.
- A human-reviewed screenplay recovery can replay a prior authenticated checkpoint as a **new** encrypted revision with a recovery receipt. Original takes/assets are not rewound or deleted.

## Native worker authority

Legacy WebView2 camera/audio and production APIs are denied for encrypted movies. Native camera/sound access also remains conservatively closed if any protected film is present.

The host-owned worker broker supports one-use, 30-second, actor/asset-operation-scoped authority (read original or seal new original), separately requiring explicit human approval. The broker consumes a grant once, checks live project session state, and stores an encrypted receipt. It never gives a model, browser or worker the content key or original filesystem path. **This is a trusted in-process source broker, not a production external Blender/Cycles/PortAudio worker.** External workers and their process custody remain denied until host-supervised per-project protected worker integration passes on real Windows/Linux.

## Verification gates

The real Windows DPAPI test matrix covers encrypted in-memory SQLite create/restart, screenplay revision, original source audit, no plaintext film markers in the secured root or public catalog, wrong passphrase/foreign project denial, tamper rejection, cross-process concurrent writer conflict, one-use worker grant/replay/expiry, relock revocation, sealed receipts, interrupted HEAD commit, interrupted original index commit, independent recovery readback and human-approved history restore. Non-Windows test explicitly rejects DPAPI instead of using fake security.

The Windows installed NSIS workflow runs the real packaged executable to create an encrypted live movie and OpenUSD, then reopens that exact data in a fresh executable/process, verifies SHA-256, encryption-at-rest invariants, recovery revisions and relock. The source matrix separately runs FastAPI, React and native test suites.

**Never count queued CI runs as passing.** CI native Windows acceptance is distinct from creator-operated physical workstation accessibility and restart checks.

## Remaining confidential-film release blockers

1. Safely migrate already-existing shared Studio/FilmIndex plaintext movies, including SQLite/WAL, OpenUSD layers, original PCM, Takes, asset caches, recovery journals, previews, derivatives and backups. Migration must be human-approved, crash-safe, independently verified, and preserve originals until acceptance; source copies in snapshots cannot be presumed erased.
2. Connect actual protected Blender, render, device/audio and capture workers through host authorization, native Windows Job Object/AppContainer and Linux delegated cgroup custody, cancellation/restart, and encrypted temporary/derived output. Current encrypted films have this production pipeline DISABLED.
3. Independent physical Windows filesystem and machine-account key custody review, screen-reader/keyboard, multi-process approval/revocation, and backup-recovery tests; plan DPAPI account/device recovery before offering irreversible protection.
4. Recognize that AES-GCM gives modification detection, but does NOT prevent a same-account attacker with direct file access from replaying an older genuine HEAD and snapshot. A trusted monotonic revision ledger is required for anti-rollback.
5. Report key-residency risk (active host memory), inability to guarantee secure deletion of preexisting plaintext and public movie titles honestly.

**Security classification:** New encrypted live storage is an isolated production-bound design currently UNDER NATIVE ACCEPTANCE. Existing projects and external production workers remain an explicit open G03 security gate. No claim of complete NVP confidentiality.
