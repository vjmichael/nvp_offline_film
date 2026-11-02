# Local writing model connection — developer preview

NVP now lists models reported by an optional, *locally running* OpenAI-compatible
server. This does **not** download GGUF files or guarantee the reported models
are in GPU memory. The user can choose a model in **Develop the idea**.

## Windows with LM Studio
1. Load one of your existing GGUF models in LM Studio.
2. Start its local server from **Developer** and check which port it uses.
   LM Studio commonly uses port 1234.
3. In the Command Prompt you use to launch NVP, set:

       set NVP_LLM_URL=http://127.0.0.1:1234/v1/chat/completions

   Or in PowerShell:

       $env:NVP_LLM_URL="http://127.0.0.1:1234/v1/chat/completions"

4. Launch the NVP developer preview *from that same environment*, create/open
   a project, choose **Develop the idea**, and press **Refresh local models**.
5. Select the exact model ID that the local server returns.
6. Request a *logline first*, check the proposal, then try a screenplay scene.

If using llama.cpp's llama-server, use its bound loopback port instead.
The endpoint must support GET /v1/models and POST /v1/chat/completions.

## Limits and protections
- Project creation, screenplay editing, and saved draft review work without any
  local AI server. No CUDA package is required for NVP's planning backend.
- The model list is only what the local server advertises. A generation call
  may still fail if the model is not loaded or memory is insufficient.
- NVP only permits local loopback HTTP endpoints and refuses redirects/proxies.
  Do not make the local model server accessible on public network interfaces.
- Current UI does not launch or unload models, show VRAM utilization, stream
  tokens, or cancel a started inference job. These are upcoming tasks.
- Use one large model at a time on the Radeon AI Pro R9700. The exact
  quantization and backend still require physical-machine acceptance.
- AI text is always a proposal until creator review. The existing
  screenplay and its revision history remain the authoritative source.
- This development preview still requires Python/Node, unlike the eventual
  packaged single-installer NVP.

Source documentation:
https://lmstudio.ai/docs/developer/openai-compat
https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
