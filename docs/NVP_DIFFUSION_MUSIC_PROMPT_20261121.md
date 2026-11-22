# NVP — No background music for diffusion prompts

**Scope:** NVP-side creator preference, frozen input contract and bounded LTX CLI
prompt assembly. This does not constitute installed LTX generation or approval.

**Creator-facing option:** a controlled checkbox labeled **No background music**
adds one standalone line, `No background music.`, after the original visual
prompt. The optional `no_background_music` Boolean must be true to add it;
false/absent leaves existing prompts unchanged. The line is idempotent. It does
not remove scene backgrounds, silence dialogue/ambience/sound effects, alter
original NVP PCM, or add music to a finished movie. NVP keeps audio ownership.

## Data path

1. The filmmaker UI control receives/passes an explicit Boolean through
   `onChange`. Its prompt preview uses `frontend/src/diffusionPrompt.js`.
   The component is **reusable**, not yet mounted to a production LTX Process
   button: the current NVP UI does not expose a full Basic/Advanced diffuser
   graph. UI persistence + endpoint integration remain future work.
2. The trusted NVP host uses
   `backend.nvp_diffusion_music_prompt.freeze_diffusion_conditioning` with the
   checked source Take hash and camera. It emits canonical JSON containing
   original positive_prompt and the Boolean, and a SHA-256 digest; the digest
   must be inserted in the exact source-locked LTX intent by the trusted owner.
   The Boolean itself is a **user preference, not an authorization grant**.
3. The original `ProtectedLtxHandoff.run` verifies immutable conditioning
   bytes against `conditioning_sha256`, and NVP creator approval and Windows
   Job/AppContainer/SCM/receipt checks remain mandatory.
4. `build_layout_to_render_argv` allows only the *optional* Boolean as a new
   key, checks the original Take/camera reference, composes the final prompt,
   and passes it to `ltx_pipelines.ic_lora --prompt`. It refuses bad types,
   unknown keys, NUL/control codes and post-addition overlong prompts.
5. Other diffusion backends must call the same `compose_diffusion_prompt`
   before their own authenticated model-specific render call. No second model
   runtime or prompt-only substitute for NVP structured production data.

**Compatibility:** Old `conditioning.json` records with the original three
keys retain legacy behavior. New creator-authored records include the flag and
change the source digest when toggled, requiring new reviewed authorization.

**Actual output:** LTX may not obey every natural-language directive; the
existing NVP picture-only output path removes model-produced audio and verifies
zero audio streams. Creator-recorded and approved sound remains separate.

## Qualification and open gates

Portable Python tests prove prompt on/off, idempotency, bounds, Take binding,
legacy inputs and exact LTX argv composition; independent JavaScript tests
prove identical UI preview semantics. They do **not** prove an actual GPU model
honored the negative prompt, a visible installed Basic/Advanced node option,
or installed Windows execution. The checkbox is prepared for those future
entrypoints; avoid implying that a cosmetic screen state has been committed
as a native film production decision.
