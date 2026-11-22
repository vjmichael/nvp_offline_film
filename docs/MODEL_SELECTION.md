> **Model ownership:** Compare Gemma and Qwen using the existing development
> bakeoff, but in production invoke the chosen model through Lu's shared
> inference manager. There is no independent NVP model loader.

# NVP Model Bakeoff — Existing Local Models (November 2, 2026)

**Do not download another model yet.** Compare the creator's existing quantized models:

1. Gemma 4 31B — screenplay/dialogue candidate.
2. Qwen3.8 27B — story/continuity/structured-production candidate.
3. Qwen3.6 35B-A3B — creative iteration and faster planning candidate.

These are hypotheses. **No winner has been selected or tested with the user's actual models.** Keep NVP's model adapter swappable so a feature film can change writing models without rewriting the project's persistent story bible.

## Benchmark: NVP-WRITE-01

**Category weighting (100 points)**

- 35: Dialogue, distinct character voices, playable subtext, filmable action, dramatic turning points.
- 25: Chronological continuity, objects, wardrobe/knowledge states, contradiction avoidance.
- 20: Creator intent, surgical edits, respect for explicit protected content.
- 10: Fountain screenplay conventions, formatting and scene/dialogue extraction.
- 10: Speed, completion reliability, measured peak VRAM and context stability.

Do not equate easy-to-parse JSON with good writing. Judge creative work blind and report objective failures separately. Repeated prompts are essential, because a single creative scene is not a reliable winner selection.

### First pass

Run five supplied test cases for all three models with identical temperature, top-p, context, max output and runtime version; capture at least two runs per case and ideally three. Evaluate at 16K context first; then try 32K when memory permits. Keep a manual key between A/B/C labels and exact model filenames.

**Capture tool**: `benchmarks/nvp_writer_bakeoff.py` requires standard-library Python only and an already-running local OpenAI-compatible server (e.g. llama.cpp's `llama-server`). It intentionally does not download or load weights, does not call external APIs, does not use system proxies, and refuses redirects. It saves the outputs for human scoring. The limited built-in objective checks are not quality scores.

Example after loading *one* model into the local server:

```bash
python benchmarks/nvp_writer_bakeoff.py --url http://127.0.0.1:8080/v1/chat/completions --model local --alias A --out results/A.json --repeat 3
```

Stop the server, load the next model, and repeat as aliases B and C. Store the A/B/C mapping in a private note, separate from reviewer output. Never load all three dense/large models together by default on a 32 GB GPU.

### Record for each run

- Model filename and SHA-256; GGUF quantization, whether mmproj is used.
- llama.cpp build and Vulkan offload mode (not CUDA); model chat template and thinking setting.
- Target PC Windows version, GPU driver and actual measured peak VRAM.
- Configured context (not the theoretical maximum), number of tokens processed/generated, latency, failure reason.
- Human ratings, complete model outputs and inter-rater disagreement.

### Later held-out stage

Test 8–12 scenes of an original movie, including out-of-order chronology, character secrets, screenplay rewriting, persistent props and dialogue style. Use the same continuity bible for each model. Evaluate whether the model makes useful scene revisions *without* changing approved lines, and whether it can take critique and improve a scene over multiple passes.

### Provisional model selection

- Gemma wins writer role only if its scene writing and revisions are consistently stronger after blind review.
- Qwen3.8 wins planner/bible role only if its structured extraction, continuity and revision discipline are stronger.
- Qwen3.6 wins fast-iteration role only if response quality remains acceptable at its measured speed/VRAM cost.
- One model may win multiple roles. NVP must never assume a permanent hardcoded winner.

Model cards: [Gemma 4](https://ai.google.dev/gemma/docs/core/model_card_4), [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B), [Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B).