# NVP AUDIO-01E.8 / AUDIO-01F — Native recovery closeout and synchronized picture + sound

**Status:** Code, failure-injection and authentic FFmpeg acceptance tests committed; exact-head Windows/Linux CI pending. The strict Linux detached-descendant guardian requires its own **genuinely delegated** cgroup-v2 execution evidence before claiming production certification.

## Native recovery checks

AUDIO-01E.8 adds `NativeAudioHost.reconcile_journal_only(job)` to close a narrow crash window before a native grant/outbox exists. It requires an `approved`, generation-zero, zero-sample journal, no TaskLedger row, no native grant, no staging lease, no output directory and an exclusive staging lock. It commits a terminal `failed` journal event, **never** fabricates an OS-stop receipt, creator approval, queued task, source audio or resource release. If any downstream effect exists, the job remains quarantined for trusted investigation.

This complements AUDIO-01E.7's grant/lease/outbox repair: outbox replay may queue only a source-bound, still-approved never-active job and must verify an existing queued task rather than duplicate it. A host restart cannot assume an ACTIVE worker or detached Linux descendants have stopped.

### Strict Linux guardian

Default Linux audio host mode is `strict_linux_tree=True`, routed through NVP's already-existing delegated-cgroup launcher with an independent guardian. Lack of delegation fails closed, not silently downgraded to process groups. `NVP_REQUIRE_DELEGATED_CGROUP=1` makes the detached-grandchild host-crash guardian test fail rather than skip when delegation is missing.

**Do not mark strict host-crash containment accepted on GitHub-hosted Linux where the real delegated test is skipped.** It requires a configured delegated systemd scope, real cgroup.kill evidence, and real worker startup/shutdown. Windows uses NVP's existing kill-on-close Job Object.

## AUDIO-01F first functional scope

**Authoritative sources:**
- B14: project-scoped, frozen edited ProRes technical MOV candidate, verified through `verify_edited_technical_mov` against the exact B13 edit revision, FLOAT32 EXR lineage, source hashes and full decoded picture audit.
- AUDIO-01E: immutable 48kHz/PCM16/stereo dialogue, ambience, SFX and music stems and a composite WAV preview. Each source is independently replayed through the AUDIO-01D chunk receipts and FilmIndex; source WAVs and registered hashes are not rewritten.

**Clock contract:** picture is 24 frames/s and soundtrack is 48,000 samples/s: **exactly 2,000 audio samples per video frame**. AUDIO-01F refuses even a one-sample discrepancy rather than using `-shortest`, padding, invented edit frames or silent time stretching.

**Mux:** use real FFmpeg, `-map 0:v:0 -map 1:a:0 -c:v copy -c:a pcm_s16le` and write an MOV technical review. Original B14 video codec packets are copied, rather than regrading or recompressing them. Independently FFprobe exactly one video stream, one PCM16 stereo audio stream, sample rate, video count and video/audio durations. Then fully decode and hash source and output video pixels plus source and output soundtrack PCM. An output with changed pixels, changed PCM, wrong channel layout, missing frames or duration drift fails.

**Durability:** the review MOV is copied into FilmIndex as immutable `video/quicktime`, a revision-level `presentation` record binds the precise original picture presentation, original AUDIO-01E audio revision and editor timeline revision. A canonical JSON manifest states `unapproved_synchronized_picture_sound_review`, `picture_locked=false`, `director_approved=false`, `final_mix=false`, `final_master=false` and `dcp_delivered=false`.

`verify_picture_sound_preview` reopens all exact FilmIndex records and dependencies, verifies both independently, checks output manifest SHA and registered MOV SHA, repeats FFprobe checks, and rehashes both decoded streams against immutable source data.

### Implemented files

- `backend/nvp_audio01f_picture_sound.py`
- `tests/test_audio01f_picture_sound.py`
- `tests/test_audio_journal_only_recovery.py`
- `tools/nvp_stack02c3b14_real_conform.py` extended for an actual two-stem → indexed WAV → synchronized ProRes review → fresh-SQLite reopen pipeline
- `.github/workflows/nvp-audio01f-picture-sound.yml` (genuine independent Windows/Linux FFmpeg unit acceptance)
- `.github/workflows/nvp-stack02c3b14-conform.yml` (full real Blender-through-AUDIO-01F integration acceptance)

### Known limits

AUDIO-01F uses the current genuine B14 picture gate: **at most 480 picture frames at 24fps**, not feature length. AUDIO-01D's two-hour capable audio worker is not proof that the picture renderer is feature-length.

This is a **worker-side technical mux**, not yet routed through an independently approved NVP native mux launch/grant (that gate follows); only a trusted native host must invoke it for genuine user productions. No picture or soundtrack is marked finally approved, mastered, loudness-normalized, theater-ready or distributed.

The strict delegated Linux guardian test still requires environmental evidence; source code and conditional tests do not alone close that production gate. Real CI must be checked for **the exact current commit SHA**, with run, job logs and actual execution outcome recorded rather than inferred from added tests. A failed CI or skipped containment test blocks the corresponding acceptance claim.

## Next gates

1. Inspect exact-head Windows/Linux output and correct any native CI failures.
2. Complete strict delegated Linux guardian acceptance in a kernel-controlled systemd scope; handle external host crash recovery without ever guessing orphan absence.
3. Add native creator approval, process containment and durable resource admission to FFmpeg mux itself; apply sidecar transactional publication and power-loss durability.
4. Lift the short B14 picture edit limit through full-length streaming picture conform, then introduce higher-quality bus automation, LUFS/true-peak QC and director review before any final master.
