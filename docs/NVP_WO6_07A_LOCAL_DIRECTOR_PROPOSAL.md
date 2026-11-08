# WO6-07A — Local-model director suggestions over verified NVP Takes

**Scope:** Narrow **read-only** desktop integration of a *real optional local model*
with the existing creator's FilmIndex/OpenUSD context. Implemented on
`nvp/wo6-director-model-proposal-20261107`, stacked on WO6 lifecycle PR #98.

## Interaction

The creator opens the existing **Director-approved native source operations**
panel, explicitly clicks **Find local models** (only the configured loopback
OpenAI-compatible server is queried), selects a locally reported model and
an immutable Take, enters exact Film Time tick and direction, and clicks
**Ask local model for read-only advice**. The native bridge begins one
nonblocking in-memory local request. The creator can poll
**Read local model proposal status** to display its result in *plain React
text*, not dangerously interpreted HTML or executable JSON.

An external model is optional. No local model automatically downloads,
loads, receives source context, calls tools or writes source. The browser
cannot provide a model URL or executable and cannot manufacture creator
consent. The backend uses existing `writer_for` in
`backend/nvp_model_service.py` and its limited loopback
`LocalScriptModel.complete` transport. Inability to connect results in a
redacted failure, never a synthetic suggestion.

## Source and authority contract

`backend/nvp_wo6_director_model_proposal.py`:
- Reopens the exact existing frozen FilmIndex Take and validates its SHA,
  then reopens the native OpenUSD scene and TemporalLedger at the selected
  exact Film Time via existing `assemble_film_crew_context`.
- Includes bounded actor/camera/light prims, original audio/event evidence,
  current versus historical scene heads, and accepted canon only;
  omissions and unverified character↔USD bindings remain explicit.
- Hashes a bounded *verified context packet*. No arbitrary file path,
  remote URL, shell/worker command, dynamic plugin, unbounded source
  dump or model-requested tool selection is admitted.
- Calls the native host-owned model adapter exactly once. A nonempty
  bounded UTF-8 model response is marked **UNTRUSTED** and SHA-bound to
  that Take, Film Time, verified context and exact model ID.
- Does **not** create a WO6 task, grant approval, issue a new Take/shot/
  color/film edit, render a picture, publish sound or approve a DCP.
  Model-generated instructions or JSON are *display-only text*;
  manual native source-impact preview and both OS dialogs are still
  required for an independently chosen actual source mutation.

The desktop runs inference on a daemon thread, permits only one
generation at a time, retains at most four completed proposals, and
discards all drafts on close/restart. A request currently executing
through the local model may still finish server-side after close;
its result is never applied or read by a reopened desktop.
This is **not native model process cancellation** or durable model
recovery, and must not be advertised as either.

## Required acceptance

Dedicated `.github/workflows/nvp-wo6-model-director-proposals.yml` runs
real OpenUSD `usd-core==26.11` source-context and fake-model negative
authority tests on Windows 2025 / Ubuntu 24.04 with Python 3.11/3.13.
A separate real React build and Vitest exercise source-bound UI selection,
literal malicious model output display (no HTML), and zero calls to
native source-writing operations before the existing human workflow.
The model adapter is **deliberately mocked for CI tests**; those tests
prove source provenance, IPC boundaries and lifecycle behavior but
**do not prove actual local-model inference**.

Separate **OPEN** gates: a real completed generation with a locally
loaded GGUF/other model and authenticated model-ID/version receipt;
genuine human direction quality assessment; repeated installed NVP.exe
WebView2 proposals plus both actual OS permissions; safe model-request
interruption; full native sound/edit/animation/render operations;
authoritative installed screen/speaker playback and 30-minute original
film; independent theatrical DCP Bv2.1 and calibrated color accuracy.
Never promote code submission or queued CI into acceptance.
