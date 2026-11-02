# Local writing model connection — developer preview

NVP now lists models reported by an optional, *locally running* OpenAI-compatible
server. This does **not** download GGUF files or guarantee the reported models
are in GPU memory. The user can choose a model in **Develop the idea**.

## Windows with LM Studio — no terminal configuration needed
1. In LM Studio, load an existing GGUF, such as Gemma 4 31B or Qwen3.8.
2. Open LM Studio's **Developer** page and start its local server.
   LM Studio commonly uses port 1234. Leave the server on loopback.
3. Launch the NVP developer preview through its normal launcher.
4. Open **Develop the idea**, select **LM Studio — port 1234**, and press
   **Refresh local models**.
5. Select the model ID that LM Studio reports, then try generating a short
   logline. You may switch to another model after loading it in LM Studio
   and refreshing the list.

For llama.cpp's OpenAI-compatible **llama-server**, choose the
**llama.cpp server — port 8080** preset when using port 8080.
Both use GET /v1/models and POST /v1/chat/completions.

## Optional developer-configured port
If your local model server uses another port, set NVP_LLM_URL before launch,
then choose **Developer-configured local server** in the NVP UI. For example:

    set NVP_LLM_URL=http://127.0.0.1:5000/v1/chat/completions

Only loopback HTTP URLs are accepted. Environment configuration is **optional**
for the common 1234 and 8080 presets; NVP does not yet start or switch
GGUF models automatically.

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
