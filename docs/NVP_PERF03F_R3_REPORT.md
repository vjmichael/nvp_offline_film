# PERF-03F-R3 — isolated hierarchy, publication lifecycle and native preflight

Historical engineering report, 2026-11-18. Source base: `e1bfe13be3503207d87da4f9d44c3d297125fe19`, existing draft PR #161. The earlier R2 report described eleven files and 36 portable tests but no recoverable revision or archive. R3 was a reconstruction, not a recovery of the exact historical source.

## Portable implementation and verification

The standalone R3 fixture used SQLite WAL/FULL, fixed 64-entry immutable manifest pages, ordered section roots, 1 MiB file hashing, exact file membership, duplicate/path/link/tamper rejection, cancellation and durable historical receipts. Its feature coordinator aggregated ordered section receipts, bound the precise 24 fps / 48 kHz planned clock and destination approval, independently rehashed the destination and required a trusted external index proof before logical delivery. Interrupted work entered review; no automatic replay, orphan adoption, deletion or overwrite. This was NOT a native worker grant, publisher, FilmIndex implementation or OS containment proof.

23 portable tests passed: 66 section directories, 132 real fixture files; 30,000 synthetic one-minute descriptors representing 500 hours, 2,651 bytes peak traced Python allocations for feature root hashing only. This is not footage, rendering, total process memory or native cinema acceptance.

## Native integration preflight

NativeProductionHost reconnect and ProductionMonitor previously walked whole production catalogs. R3 candidate introduced indexed keyset windows of up to 64 job/feature records (65-row lookahead), independently verified job status, protected project database scope, explicit continuations and no paths/tokens. Four original native source blobs were pinned before transformation. Four additional local tests passed on disk-backed SQLite (30,000 jobs, 3,000 features, scope denial and cursor integrity), total 27 with earlier R3 tests. Exact native integration was pending; no Git/CI writes were performed at R3.

## Dynamic-loading audit and creator requirements

Existing SLATE-04 loads one selected Take/scene with bounded preview tickets; PERF-03C supports durable paged source checks; PERF-03E supports keyset navigation; resource ledger/watchdog and disk admission are in place. Preview cache defaults to 256 MiB and 1,024 ready previews; its eviction and recovery still needed audit. Finished review sliced a fully allocated catalog; native feature worker materialized the finite approved reel plan. Neither metadata fixtures nor bounded individual paths prove global safety.

Final runtime and original media inventory are independent: illustrative stress targets 3–6+ hours finished, 100+ hours original performances, 500+ aggregate camera/revision/alternate-take hours, not runtime limits. Preserve raw and unused material; edits refer to source instead of duplicating it. Enforce bounded ingress/indexing/selection, proxy seek, cache eviction, native memory and storage admission, and actual measured RAM/VRAM/disk. Basic UI should expose simple export progress and recovery guidance, not internal checksums or worker details.

Next native work: reconstruct R2 lineage; integrate original protected FeatureJournal and single native owner lease; preserve source authority and consent; verify actual media, output destination and FilmIndex receipt; independently exercise decode, cancellation, crash/recovery and installed Windows. No FFmpeg, no automatic release acceptance.
