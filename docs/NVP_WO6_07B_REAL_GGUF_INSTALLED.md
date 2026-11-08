# WO6-07B — Genuine local GGUF and installed Windows director interaction

**Implementation date:** 2026-11-07. **Stack:** WO6-07A PR #99 and
WO6 native lifecycle PR #98. **Status:** new native implementation and
CI submitted; **no execution acceptance until the exact-head logs pass**.

## Actual director behavior

The existing NVP WebView2 director panel, not a separate model window,
discovers an explicitly configured loopback local model. Only a selected
original frozen Take and exact Film Time are reopened from FilmIndex and
OpenUSD. The native host forms a bounded scene/actor/camera/light/temporal
context with current-versus-historical source status and omissions.
The model returns **plain-language suggestions**, not executable
commands. The director chooses any subsequent action independently using
a fresh impact preview and both separate OS approvals. No auto-apply.

WO6-07B adds `ProvenLocalModelWriter`, used by default by
`TrustedDesktopWO6Bridge`. This reuses the existing loopback model
selector, does not create another model runtime, rejects remote or
deceptive loopback-looking URLs, proxy routing and redirects, and demands
a bounded **completed** chat response with exact model-ID echo,
`finish_reason=stop`, positive prompt and generation token counts,
and source/response SHA evidence. This is strong **provider-response
accounting** but not an independent proof that an arbitrary HTTP
server truly executed neural weights. The provider can falsify usage;
the report explicitly distinguishes it from a native GGUF run.
The original selected Take and its two scene/timeline heads are checked
again after inference. Concurrent source edits discard an obsolete
proposal, without altering either original.

## Genuine GGUF evidence path (not an HTTP mock)

`tools/nvp_wo6_07b_real_gguf_smoke.py` is a separate, explicitly
approved acceptance-only workflow that takes an absolute real GGUF file,
an absolute real `llama-server` executable and the literal consent
`I_APPROVE_DISPOSABLE_LOCAL_GGUF_TEST`. It hashes both real files,
requires the GGUF magic/size, starts a **fresh CPU-only**
`llama-server` on random loopback port with a unique model alias,
waits for actual model readiness, and creates its own throwaway
OpenUSD scene, source event ledger and frozen original Digital Take.

The same native NVP model suggestion path is used to generate at least
one returned token and a source-bound English director suggestion.
The evidence records actual binary/model SHA, source/Take SHA,
prompt/response SHA, selected model/positive token usage, and clear
denials of source mutation, worker grants and film delivery. The
acceptance-owned server process is terminated before any successful
receipt is published. It never touches an existing LM Studio instance.
It does not assert whole descendant-tree termination (separate WO6
Job Object/cgroup attestation).

The Linux CI job builds the official llama.cpp server locally and
resolves an exact Hugging Face commit of the ~105MB
`tensorblock/SmolLM2-135M-Instruct-GGUF`
`SmolLM2-135M-Instruct-Q4_K_M.gguf`, recording model and binary SHA
in the evidence. The repo's moving test `llama.cpp` checkout is recorded
by exact CI commit, not falsely described as pinned release source.
**This tiny integration model is not a film-quality benchmark.**
Failures to download, build, load, generate or report completed tokens
are genuine test failures: there is no fixture substitution or skip.
The source model is test-only and is not distributed with NVP; any
eventual production bundling requires distinct upstream LICENSE,
notice, redistribution audit and transitive dependency inventory.

## True installed Windows WebView2 acceptance

The existing **single NSIS installer** and PyInstaller onedir NVP.exe
bundle are built in the Windows CI job. It verifies installed/built
EXE SHA equality and runs an opt-in
`NVP.exe --smoke-wo6-real-gguf ... --gguf-visible-webview2`
mode. The same still-running acceptance-owned GGUF server is then
used by the visible installed WebView2 and actual React
`WO6CreatorActionsPanel`, on a second disposable frozen Take.
Automation clicks **Find local models**, selects the real alias,
enters the director's request, clicks **Ask local model for read-only
advice**, polls the actual native proposal and confirms the resulting
plain-text advice is displayed on screen, with a matching original
Take/context hash and positive provider token receipt.

The native bridge must have **zero** creative grants, native
execution grants or started worker queues during this AI-only path.
The routine then closes the WebView2 window and proves the
acceptance-owned server main PID has stopped before publishing the
JSON. The normal desktop is not modified to auto-download/auto-load
models, bypass consent or auto-apply model suggestions.
A separate installed `--smoke-window` verifies baseline window
reopening. The model/server test binaries are audited as **absent**
from installed NVP files.

## Tests and acceptance

- Native HTTP suite deliberately uses a synthetic HTTP *server* only
  to challenge forged model IDs, missing token counts, nonfinal output,
  zero text, redirects, misleading loopback-looking remote hosts and
  unapproved GGUF magic/consent. This **does not count as real
  inference**.
- Genuine Linux model job and installed Windows NSIS+visible React
  job are in
  `.github/workflows/nvp-wo6-07b-real-gguf-installed.yml`.
  The native scanner and CI-specific model downloader are separate
  first-party test tools. Both require real GGUF/real llama.cpp, not
  mocked model output.
- Existing WO6-07A source context test additionally simulates a
  legitimate concurrent revision to verify old AI advice is discarded.
- **OPEN** until final exact-head native test artifacts show genuinely
  nonempty model-generated text, token accounting, hash provenance,
  source preservation, installed WebView2 UI interaction and zero grants.
- **Separate OPEN**: real creator-approved follow-on Take editing with
  a production representative local model, representative larger GGUF
  quality/latency/VRAM benchmarks, interactive OS human review,
  30-minute original film and 24fps picture/mastered audio, physical
  display/color and independent DCP Bv2.1/theatrical ingest.
- Native CI human OS prompts are not replaced with fake approval;
  test-only source freeze creates a disposable film with a clearly
  labelled *test* policy, never a creator production decision.

No FFmpeg, Docker, new source-of-truth DB, direct remote model URL, or
automated screenplay/scene grant is introduced.
