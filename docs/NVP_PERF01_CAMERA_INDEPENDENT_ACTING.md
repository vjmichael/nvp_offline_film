# NVP PERF-01 — Camera-independent character performance

Status: deferred design, after current B14 film and AUDIO-01 gates. No model/runtime acceptance claimed.

Core invariant: changing the director's shot list, including a close-up or mid-dialogue cut, does not replace the authoritative character performance. The Digital Take keeps versioned voice recording, phoneme timing, emotional trajectory, gaze, jaw/lip/tongue articulation, neck, breath, shoulders, posture, hands and whole-body movement in a shared source timebase. Camera and edits reference that state and never reset it at a cut.

A closer shot can request more accurate derived skin, face, neck or mouth deformation; regenerate the detail from the same approved character-performance revision and record its provenance. Do not silently invent animation that contradicts the performance. Simulate unseen characters continuously as needed for return shots. Preserve continuous dialogue through reaction shots and J/L cuts; distinguish genuine edits between two different takes and check match-on-action and audio continuity.

Performance source and movie presentation must have distinct revisions and dependency invalidation. Frozen intent, voice, action, expression and body pose survive re-render; camera-only updates affect camera-dependent outputs. Audio or acting changes invalidate only dependent products. Use bounded temporal processing with checkpointed animation state, overlap and OS resource guard.

Acceptance: one emotional line rendered wide, medium and close-up; changed shot list after take freeze; cut during speech; visible neck/shoulder and breathing response; overlapping dialogue and J/L cut; independently verified source hashes and restart continuity. Measure speech sync/anatomical collisions; require human acting assessment. The initial pipeline may validate the data interfaces before any photoreal actor model is selected.
