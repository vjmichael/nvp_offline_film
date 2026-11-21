# NVP AUDIO-01E.2 — Explicit orphan-chunk reconciliation gate

**Scope:** Crash simulation and recovery of the AUDIO-01D durable PCM renderer. Implementation is committed to the production branch but cross-platform CI is not yet verified. It does **not** complete native worker supervision, host authorization or durable filesystem transactions.

## Concrete failure mode

The AUDIO-01D worker writes each new stem PCM chunk and composite PCM chunk, then atomically replaces a JSON checkpoint. An interrupted or killed worker may leave one or more valid chunk files that are absent from the last committed checkpoint. The ordinary AUDIO-01D runner deliberately refuses these files and will not overwrite them.

`backend/nvp_audio01e2_orphan_recovery.py` adds `reconcile_next_chunk(plan, sources, total_samples, directory)` as an **explicit trusted-host reconciliation operation**, not an automatic action by arbitrary AI or the rendering worker.

## Validation and adoption

1. Require an existing incomplete job checkpoint and exact original source and clip plan.
2. Rehash and audit **all** receipt-bound chunks, preserving their bytes.
3. Refuse an unfinished `checkpoint.json.new` replacement rather than guessing whether it committed.
4. Enumerate checkpoint-bound and expected-next file names. Refuse symlinks, unexpected names, subdirectories and future-chunk artifacts.
5. Re-render the **one** expected next chunk from the original sources using the deterministic AUDIO-01D renderer.
6. Validate every existing unreceipted file against exact expected bytes and length **before** writing any missing files.
7. If all existing files match, fill only the absent expected files, append a receipt with SHA-256 hashes, and atomically replace the checkpoint.
8. Re-audit the full receipt chain; ordinary AUDIO-01D resume can then continue from the recovered sample offset.
9. If there is no orphan file, return `NO_ORPHAN_CHUNK` without advancing or mutating the receipt.

A corrupted chunk, modified source recording, changed gain/clip plan, unexplained file, symlink or incomplete checkpoint stage triggers an error without silently making another take or marking a mix complete.

## New regression suite

`tests/test_audio01e2_orphan_recovery.py` uses **genuine WAV PCM data** and simulates:

- First of three next-chunk outputs exists; recover missing outputs and resume to completion.
- All three next-chunk outputs exist; adopt their verified bytes into the missing receipt.
- No orphan: idempotent no-op.
- Corrupted orphan: reject and preserve the earlier checkpoint.
- Changed original edit plan: reject.
- Unexpected future file or `checkpoint.json.new`: reject.
- Already completed render: do not append/overwrite.

The native Windows/Linux CI contract invokes this test independently of real Blender conform acceptance. Each local and CI result must be recorded for the exact commit SHA; a test committed to GitHub is not automatically a passed acceptance gate.

## Deliberately unfinished

The current API assumes a **trusted host has already stopped and excluded concurrent workers**, admitted the file paths and acquired appropriate exclusive filesystem access. Neither a secure OS lock, host journal, full transactional directory-fsync chain, automatic `.new` recovery nor Windows Job Object/Linux process containment is provided by this file. Recovery is therefore **source-verified cooperative reconciliation under a trusted staging directory**, not a production-ready malicious-adversary defense.

AUDIO-01E.3 should integrate the operation into a host-supervised effect journal, durable lock/restart lifecycle, and attempt-specific staging plus fault-injection tests after process kills and filesystem transaction interruptions. AUDIO-01F will independently bind film-length picture and soundtrack timebases. Keep human director approval and final mastering separate.
