# WO6-07C — Human-reviewed local AI advice to one real native director shot

**Date:** 2026-11-07. **Status:** implemented; exact-head native and installed Windows acceptance OPEN.
**Stack:** WO6-07B draft PR #100, WO6-07A PR #99 and earlier WO6 native runtime PR #98.
**Branch:** `nvp/wo6-reviewed-ai-to-approved-shot-20261107`.

## Director-facing behavior

The creator requests local-model advice from a specific immutable Digital Take
and exact Film Time. A generated response is explicitly **untrusted advice**,
not an operation. The native desktop shows the original Take and suggestion
text/context SHA. WO6-07C adds a button **Review advice and plan my own shot**,
enabled only after the human separately selects one of three trusted source
operations: camera adjustment, actor/prop blocking or lighting adjustment.
This selection is not chosen or inferred from the AI's prose.

The host reopens the exact original frozen OpenUSD Take and existing FilmIndex
/ TemporalLedger source context. It requires a matching Take SHA, model text
SHA, verified source-context SHA and valid current scene/timeline heads;
historical Takes with stale live source heads are rejected as new *current*
edits. It then creates an **ephemeral, nonauthorizing** consultation receipt.
No task, tool, permission, rendered image or asset is created by that step.

The UI deliberately clears editable shot value, new immutable shot identity,
and human-written reason on taking up an AI suggestion. It requires a **new
human keystroke** to set the numeric camera/light/position parameter, a
human-written reason of at least 12 characters, and a separate new shot ID.
The human must then inspect a fresh source-impact preview for the manually
selected operation. Nothing from the model response fills those fields.

After review, the *existing* `wo6_create_shot` accepts only one extra
source-bound field: the already reviewed proposal ID. The native host
reopens the same immutable Take/context again, verifies a completed actor-
and project-owned review for the exact shot action, checks the original
scene SHA and creator-written reason, then reserves that proposal against
concurrent duplicate use. It passes a small provenance-only record into
the first-party NativeShotActionHost. This is NOT a model tool call.

Two existing independent OS native dialogs still control:
(1) the human's creative decision, displaying exact normalized numeric
opinions plus consultation SHA and explicit model nonauthority;
(2) the matching SHA-pinned first-party worker spec, tool and resource
admission. A denial clears the pending review reservation but does not
create a shot. An accepted native operation consumes the review ticket and
cannot use it for another shot. Closing/restarting NVP never restores an
unused review or source-write authorization.

## Durable source custody

A successfully queued native shot stores `reviewed_ai_consultation`
in the original immutable, SQLite-admitted job `task.json` and the
OS-displayed `creative_scope`. It includes only:
`proposal_id`, original `take_sha256`, generated-text SHA,
verified source-context SHA, exact Film Time tick, and director-selected
action kind. No raw model text becomes an executable field or USD opinion.

The contained native shot worker separately verifies that consultation
exactly matches the signed spec and approved creative scope. After
creating and reopening the genuine OpenUSD shot-local override it writes
the original source's native receipt with the *same* reviewed SHA data,
plus explicit `model_approval_accepted: false` and
`model_instruction_executed: false`. The parent native host checks
those values against the sealed spec **before** durable SUCCEEDED status.
Authenticated `WO6DurableRecovery.status` reads back provenance from
the original sealed SQLite task after process restart, again without
replaying model text, permission or execution.

The original frozen Take, scene, actor performance and prior derived
sources remain immutable. New camera/actor/light edits are identified by
new shot revisions. No final film or cinema deliverable is claimed.

## Test groups

`tests/test_nvp_wo6_reviewed_director_shot.py`:
- Reopens a real source-authored OpenUSD actor/camera/light scene with a
  frozen original Take and TemporalLedger.
- Injects a *fake-model* response specifically to prove the AI boundary,
  then observes a human consultation click, typed native parameter and
  exact current-source preview. Before the human review no worker is
  permitted.
- Passes both independent OS consent callbacks, queues an actual durable
  first-party native job, executes the real contained shot worker, reopens
  the final new immutable shot, checks original Take SHA unchanged,
  verifies task.json + receipt.json + authenticated SQLite status show
  the same consultation SHA and do not claim AI authority.
- Rejects wrong text SHA, wrong action, stale original scene head,
  single consent denial, duplicate review and cross-restart replay.

`tests/test_nvp_wo6_native_shot_action.py`: positive genuine shot
execution and negative malformed/falsified provenance.

`frontend/src/WO6CreatorActionsPanel.test.jsx`: verifies the
**manual** sequence, not just a mock "approved" response:
local advice→human-selected operation→native review→blank numeric/new
source fields→human typed number and reason→fresh impact→existing
two-consent native request. A model reply alone never calls the
source-writing bridge or clicks any native dialog.

Dedicated exact-head GitHub Actions matrix:
`.github/workflows/nvp-wo6-07c-human-reviewed-native-shot.yml`.
Four genuine OpenUSD Windows 2025 / Ubuntu 24.04 × Python3.11/3.13
jobs plus a real React build/Vitest job. **Queued, skipped or nonexistent
results are not passing evidence.** Inspect failures and rerun against
final code before closing anything.

## Separate remaining gates

- Real GGUF, loaded model/version and installed Windows
  WebView2 suggestion output: WO6-07B's distinct CI acceptance.
- The **actual human** authoring, viewing and confirming the
  exact AI-reviewed shot in a physical installed NVP.exe Windows
  session: remains OPEN. CI uses simulated OS approvals solely for
  a regression fixture, never asserts human consent.
- Sustained 30-minute original film, continuous picture+mastered audio,
  renderer color accuracy/independent comparison, user performance
  assessment and theatrical SMPTE DCP Bv2.1 acceptance: OPEN.
- Future native soundtrack/editorial operations, actual camera/actor
  direction quality, hardware performance and other WO6-07 work can
  proceed before these independent gates close.

Do not treat project ledger stages as test results. GitHub is the code
repository and evidence collection tool, not the runtime execution
authority. No Docker, FFmpeg or MCP is required for this source operation.
