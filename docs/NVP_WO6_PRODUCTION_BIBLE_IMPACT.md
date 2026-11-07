# WO6-04 — Source impact, Production Bible and creator approval preview

**Implementation:** Draft PR #93, stacked on WO5 PR #92. Code is in
\`backend/nvp_wo6_impact_preview.py\` and the existing trusted read host
\`backend/nvp_ai_read_host.py\`. Windows/Linux exact-head acceptance requires
actual CI receipts; implementation by itself does not close the gate.

## Where the Production Bible lives

The **Production Bible is the unified creator-approved project authority**,
not a large free-form AI memory or a separate model-maintained database.
It is a *read-time composition* of existing versioned domains:

| Domain | Authoritative existing records | What AI can infer |
|---|---|---|
| Story canon | \`StoryBible\` entities, creator-accepted facts, aliases, explicit scene links | Exact approved facts and declared scopes; not invented biography |
| Story chronology | \`StoryTimeline\` accepted event precedence, scene anchors, accepted knowledge | Only proven partial order; unordered events remain unordered |
| Character beliefs and deception | \`SceneMind\` accepted scene beats, subjective beliefs, claims and reviews | Belief is not truth; deception is not knowledge transfer |
| Writing | \`Studio\` screenplay and creator-approved writing-stage provenance | Exact scene revision and text SHA; not current if stale |
| Casting, sets, lenses, performances, sound | FilmIndex/OpenUSD source/TemporalLedger/recorded PCM and verified tool manifests | Only explicitly bound native source IDs/SHA and observed states |
| Takes, edit, master, finished DCP | Immutable FilmIndex dependencies, edit custody, FeatureJournal and published hash receipts | Derived revision lineage only where recorded; no DCP→USD reconstruction |
| Director intent, creative review | Native host-controlled records and separate human confirmation | Cannot be authorized by an AI role or prompt |

The original production-bible JSON registries in \`backend/nvp_bible/\`
(casting, environments, optical rules and temporal tracker) preserve useful
design vocabulary. **They are not automatically trusted as live verified
production state.** Linking those legacy roles to genuine FilmIndex/OpenUSD
entities, workforce capabilities and creator-approved technical rules is an
explicit future migration. The WO6-04 preview does not silently import them
as canon. \`docs/NVP_CREW01_PRODUCTION_BIBLE_ROLE_RECOVERY.md\` remains the
architectural source for the existing role concepts.

The existing \`backend/nvp_bible_context.py:canon_snapshot\` is reused for
a **canonical approved-canon SHA digest** and bounded scene-relevant context.
Its digest includes selected approved facts even if omitted from the model
excerpt and includes event/knowledge/mind authority. It refuses a stale
explicit scene link. When the necessary Story Bible/timeline/mind tables are
not initialized, the preview reports that full approved-canon evidence is
**unavailable** instead of creating tables as a side effect or inventing facts.

## WO6-04 native preview contract

\`nvp.film.preview_source_impact.v1\` is advertised through the *original*
\`NativeAiReadHost.catalog\`; discovery is not authorization. The host
requires a fresh \`TrustedReadScope\`, per-turn trusted authorizer callback,
exact project ID, FilmIndex object/revision/SHA and a typed proposed change.
The optional exact screenplay scene+revision and previously observed
approved Bible digest enable tighter canon/continuity checks.

The recognized **non-executable** proposal types are:

- \`revise_scene\`, \`revise_actor_performance\`, \`revise_camera\`,
  \`revise_sound\`, \`retake\`;
- \`revise_edit\`, \`revise_color\`, \`remaster\`, \`republish_dcp\`;
- \`revise_bible_fact\` (requires a currently creator-accepted fact ID,
  exact existing scene link and approved scene Bible availability).

The preview checks that the source kind is appropriate to that proposal.
For a Bible fact, only creator-accepted and explicitly linked canon may be
targeted; an unapproved AI proposal is never converted into accepted canon.
No story-scope label implies scene chronology, and no matching character
name is proof of an OpenUSD rig/actor identity.

It returns a **bounded, typed and SHA-cited** graph of downstream
*existing* FilmIndex consumers. In addition to ordinary FilmIndex dependency
edges, it checks normalized scaled-editorial and sparse temporal-event
source bindings using query limits. It reports the exact extent of known
indexed effects and flags graph truncation. Crucially, it **does not claim**
all unindexed FeatureJournal, historical package, texture/asset, production
or external delivery artifacts have been found. Future source changes
will create new revisions and must be independently resolved rather than
modifying frozen Takes or an old DCP.

The preview shows potential affected domains, the existing object revisions
affected, director creative decisions, separate native worker grants and
explicit blockers. It does **not** generate an edit, grant source permissions,
reserve hardware, create a new Take, change a sound mix, approve canon,
publish a new DCP or mark any cinematic quality gate passed.

### Native resource estimate (optional)

Creator-supplied delivery metadata may request deterministic WO4
\`plan_feature\` estimates for bounded 24-fps 2K/4K profiles, 2/6/8 sound
channels, reels and maximum scratch demand. These are conservative estimates,
not performance results, not an installed codec readiness proof and not a
decision about available RAM, GPU budget or actual free disk. Real
admission must be checked again by native supervisor and resource guards
when a host-authorized worker is actually scheduled.

### Stale and race safety

- Exact original source SHA mismatch, source kind mismatch, invalid request
  shape, unauthorized project or unsupported edit type: fail.
- Source head superseded: report that the snapshot is historical and that a
  creator must refresh before acting; frozen prior versions remain valid.
- Approved Bible digest changed since the creator last viewed it: fail
  and request a new preview rather than silently using the new canon.
- A source head, screenplay revision or approved canon changes **during**
  preview: discard the computed preview before returning it.
- An incomplete indexed graph, missing Bible, unknown/unindexed deliveries
  and missing genuine resource verification are *clearly disclosed*.
  A preview is never authorization for a worker, even when no warnings appear.

## CI and scope

Tests: \`tests/test_nvp_wo6_impact_preview.py\` — existing
scene→Take→edit→master→presentation dependency chain, normalized timed-event
consumers, approved Story Bible versus unapproved AI fact, exact linked
scene scope, digest invalidation during read, cross-project isolation,
old-versus-current scene, bounded and truncated graph, optional 30-minute
resource estimate, explicit absence of any mutation/worker/creator approval
and fresh turn-permission denial. CI Windows/Linux 3.11/3.13, plus original
AI-01/02/03 regressions.

**Not acceptance for:** WO5 actual installed finished-film playback;
30-minute human-authored, rendered and reviewed original film; independent
SMPTE Bv2.1 cinema ingest; WO6-05 native approved execution; or long-form
60–90-minute/three-hour genuine creative filmmaking. None of those are
waived by a satisfactory WO6-04 preview.
