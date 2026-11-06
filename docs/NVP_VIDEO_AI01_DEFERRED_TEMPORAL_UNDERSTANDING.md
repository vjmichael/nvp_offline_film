# NVP-VIDEO-AI-01 — Deferred native video-understanding research

**Decision:** Document and defer. Not a dependency for NVP B14, production mastering, FILM-01, Lu v1.0 or the initial technical presentation inspector. No model selected, runtime accepted, or integration implemented here.

## Why revisit

NVP will eventually benefit from interpreting actual motion and audiovisual events in finished presentations: continuity, action verification, performance consistency, object identity across shots, editorial search, temporal scene understanding and comparison with frozen Digital Take instructions. Technical QA (FFprobe, decoded-frame checks, timestamp/audio sync, hashes and deterministic picture provenance) must be shipped **without** this AI dependency.

## Candidate families to benchmark, not prematurely select

- Open-weight local general vision-language models with advertised video input, such as Qwen3-VL variants; verify actual backend support, video temporal semantics and memory use.
- Purpose-built temporal/video representation systems (e.g. InternVideo family); inspect licensing, model/runtime support, audio capability and real motion understanding.
- Lightweight video-capable VLMs such as SmolVLM2; useful as low-resource baselines but may sample sparsely.
- Future open-weight models that genuinely understand temporal relationships and optionally sound; assess against accessible production hardware before commitment.

Do not claim native ingestion of an MP4 means processing every video frame. Differentiate file decoding, sparse sampling, consecutive-window temporal input, video-specific spatiotemporal encoders, and genuinely streaming/cross-window state.

## Proposed acceptance before adoption

1. Run on real NVP-edited presentation with reference shot/action times and compare predictions to frozen production data.
2. Test missed subsecond events, fast actions, object permanence, shot cuts, flicker, actor continuity, motion, audio events, uncertainty and adversarially misleading frames.
3. Measure on actual constrained home PC and capable GPU; report peak RAM/VRAM, inference speed, decoder throughput, accuracy and degradation under explicit resource pressure.
4. Bounded stream pipeline: native sandboxed decoder → timestamped frames/audio windows → model adapter → durable timecoded observation/evidence with links to FilmIndex; checkpoint and restart at window boundaries.
5. No package installs or npm registry dependency inside active tasks. Package pinned codecs and runtime with NVP's normal installer/build pipeline. No external FFmpeg/Whisper manually required at run time when their functions are included.
6. Long background analysis must use the existing native TaskLedger and worker supervisor, not a UI/network request timeout. Constrained worker permissions, cancellation, OS resource containment and resumable checkpoints.
7. Human review for inferred subjective visual flaws. AI observations are hypotheses, never independently certified render errors or automatic authorization to alter creative assets.

## Scope boundary

Current priority: B14 authorized native picture conform, production-quality source-linear edited master, audio synchronization, comprehensive technical QA, then a verified 30–60-second NVP-produced short film. Begin AI model research/integration only after these gates or an explicit subsequent prioritization decision.

**Status:** Deferred research and design only.
