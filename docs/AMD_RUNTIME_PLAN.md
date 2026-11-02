# NVP GPU portability contract

NVP cannot require an NVIDIA purchase to create a movie. One-person creators
must be able to choose affordable hardware and accept slower rendering.

## Runtime rules
1. Start the UI and open/save projects on **CPU-only** hardware.
2. Probe each compute service separately. Do not infer global readiness from
   one successful GPU detection.
3. Provide interchangeable providers for language models, image/video models,
   audio generation, motion and rendering. Report capabilities honestly.
4. Do not load TTS, VLM, LLM and renderer into VRAM together by default.
   Queue heavy tasks, unload idle workers and report real VRAM usage.
5. Keep intermediate assets and approval records backend-neutral.
6. Never promise a model runs on AMD solely because a framework supports ROCm
   or Vulkan in general. Verify exact GPU, OS, driver, model and build.
7. Prefer reversible, saved scene edits to opaque full regeneration.

## Candidate paths (not yet integrated)
- Local LLM: llama.cpp Vulkan backend on supported AMD/Windows systems;
  CPU fallback. Production inference is Lu-managed and shared; the existing separate NVP HTTP model adapter remains a temporary testing harness only.
- 3D rendering: Blender EEVEE or Cycles with supported AMD HIP devices;
  CPU rendering when needed. Unreal remains an optional provider.
- Lip sync: CPU phoneme-to-viseme baseline; advanced facial generation
  optional. NVIDIA Audio2Face is not mandatory.
- STT: CPU Whisper variants as a fallback; GPU path selected by runtime probe.
- Final output: local FFmpeg when packaged and license reviewed.

## What is verified in this branch?
No GPU computation is used. Only the CPU planning service and its local
persistence/API tests are verified. No Vulkan, HIP, ROCm, UE5, Blender,
TTS, or video rendering integration should be claimed operational.
