# PERF-03F-R6 — consolidated integration preflight and source recovery

Status: IN PROGRESS / native whole-feature publication OPEN. Historical source base `e1bfe13be3503207d87da4f9d44c3d297125fe19`; existing draft PR #161.

- Recovered R3–R5 candidate and verified recorded R5 SHA256 checksums.
- Reran 51 portable R4/R5 tests, 5 exact-source modified PCM tests, and 23 prior R3 tests: 79 passed. Test guards/fixture limitations from R5 continue to apply. No new rendered-film acceptance.
- Retrieved archived source at b2d97efa08e88a1e372251c52ba5f6e696f6cd36. GitHub compares 28 commits ahead, 112 changed files, no divergence; the archive is NOT exact current source. Git direct checkout remains blocked by DNS, historical R2 unavailable. Do not apply unverified patches to current head.
- Reconstructed current FilmIndex using the exact GitHub delta and verified blob e17a99b6ac4d804a368038ff81f8629452f2860d. Existing ten FilmIndex tests passed on archive dependency base prior to reconstruction; further exact-source tests needed.
- Existing SHA cohort returned 36 completed workflows: 35 success, private-kernel/adversarial custody failure run 44464499159. Do not waive it or treat those receipts as tests of later code.
- Publish historical engineering reports here; retain all original test gates and the existing draft PR. This documentation update is not native acceptance, release authority or proof the R3–R5 candidates are integrated.

Next: finish source recovery, apply complete consolidated candidate, exercise native host and journal in exact source, qualify real codecs, Windows EFS/OS singleton/cancellation and independent picture/audio decode. Preserve original consent, no-replace publication, immutable source and no-FFmpeg. A grouped set of existing DCPs is not a single whole-feature export; keep finite admission limits explicit until streaming publication is proven. No automatic merge or acceptance.
