# POST-01F R5-R2-R2 — exact-source MSVC correction and installed acceptance obligations

**Status: reviewed source correction prepared; native compiled/installed proof not yet obtained.** This document is not Windows acceptance, a model-generation receipt, or permission to merge.

## Exact-SHA GitHub evidence

- Existing PR #161, source `149f6ddd3627a5c4643e82ff02672731191d36fd`, produced 45 original workflow runs. At the first R5-R2-R2 reconciliation: 43 passed, dedicated POST01F Windows SCM/CNG failed, and CONV-12 real Windows 90×8 Cycles was still running.
- Original W1-G/INT-02C [run 44864936603](https://github.com/vjmichael/nvp_offline_film/actions/runs/44864936603) and independent Gate 1 [44864936684](https://github.com/vjmichael/nvp_offline_film/actions/runs/44864936684) **passed** at `149f6ddd3627...`. The earlier audited media-launch regression is resolved on this exact source.
- Original Windows [SCM/CNG run 44864941951](https://github.com/vjmichael/nvp_offline_film/actions/runs/44864941951) ran 75 Python/source tests successfully, then real MSVC compilation failed with **C2039** at `tools/nvp_post01f_windows_scm_ltx_broker.cpp:342`: `STARTUPINFOW` has no `lpAttributeList`. **The native service executable was not produced, so unapproved SCM-start denial was skipped.** No native SCM/CNG positive or negative result is inferred from this failure.
- The narrowly reviewed correction replaces `start.StartupInfo.lpAttributeList=attrs;` with `start.lpAttributeList=attrs;`: `STARTUPINFOEXW` owns `lpAttributeList`, while the `STARTUPINFOW` `cb`, `lpDesktop`, and `CreateProcessW(...,&start.StartupInfo,...)` remain unchanged. The required `EXTENDED_STARTUPINFO_PRESENT|CREATE_SUSPENDED`, AppContainer SID, WFP blocks, Job assignment and one-use grant remain unchanged.
- Added static source-regression tests; they **do not replace** the hosted MSVC build and installed SCM negative gate. Preserve all prior workflow tests and original refusal assertions.

## Stage A — Windows SCM/CNG negative native gate (required next)

On the new exact successor SHA, independently verify: actual MSVC Windows SDK compile+link; no compiler/linker warnings obscuring rejection; exact source SHA; ordinary direct execution refused; direct non-SCM service execution refused; real LocalSystem SCM service with absent protected HKLM one-use grant refused, stopped nonzero and produced no original or picture bytes. Preserve native service diagnostics and artifact SHA. No automatically accepted release from a negative-only run.

## Stage B — installed positive custody (separate provisioned-machine gate)

A trusted installer/operator must provision an actual non-exportable ECDSA P-256 **machine** key in Windows KSP with service-only private-key ACL, and independently pin its SEC1 public key in host HKLM trust. Provision real user-approved detached CMS creator scope (not a model/UI switch), one-use admin HKLM ticket, separate durable spent-ticket directory, fixed verified native broker, exact original Take/layout/look/model/runtime hash lock, EFS source/output directories, Windows SCM service identity, AppContainer SID and zero network capabilities, WFP v4/v6 connection/accept blocks and a kill-on-close Job.

Acceptance must observe **actual** suspended child launch -> Job/SID proof -> allowed source read-only rights and denied forbidden file/network access -> nonzero/timeout/cancel/replay refusal and durable spent ticket -> completely drained Job/descendants -> exact independent EFS rehash and no generated audio -> SCM-held machine P-256 signing of canonical exact picture/plan/worker/nonce -> installed host signature verification against pinned key and durable authenticated G03 nonce-spend. A synthetic fixed worker can test OS custody without claiming LTX inference; its provenance must be explicitly labelled.

## Stage C — encrypted filmmaker review (separate installed app/UI gate)

The trusted Windows host passes only authenticated SCM verified pending picture to `EncryptedLtxReview.publish_pending`; the G03 project session wraps derived video in authenticated AES-GCM and commits immutable ciphertext SHA into encrypted HEAD. Reopen must verify original Take, picture bytes, metadata, SCM receipt hash and G03 nonce. Native app UI must present authenticated playable **picture only** (original 48 kHz dialogue/PCM remains authoritative and unmodified) and distinguish preview permission from approval permission. Creator explicitly chooses approve or reject. Test cancellation, double-click/replay, rejection, unsigned result, key/session revocation, crashed partial output, removed ciphertext/decision and restart/restore. No auto approve, browser-accessible raw media URL, plaintext preview cache, original Take mutation or synthetic result accepted as native positive evidence.

## Stage D — physical inference, separately

The Radeon AI Pro R9700 and licensed pinned LTX-2.5 runtime remain unprovisioned in this build environment. Produce authentic visual samples only from a genuinely loaded model on the user's provisioned host. Keep this gate open and do not post synthetic images as LTX output.

## Integration rule

Wait until all workflows on exact predecessor `149f6ddd3627...` are terminal. Publish **one** non-forced compare-and-swap fast-forward commit to existing draft PR #161, no new branch/PR/merge and no manual CI dispatch. Inspect original Windows SCM/CNG and W1-G results at the new unchanged SHA before closing any native gate.
