# Model connection: developer harness only

**Production product:** NVP runs as the optional Film Workspace DLC within
Lu. Lu owns and authorizes the chosen GGUF model and inference session.
NVP requests inference through Lu's model/runtime IPC and must not require
an independent LM Studio, llama-server, second model load, or external API
endpoint to function as a DLC.

## Temporary development mode

Until Lu's DLC host interface is integrated, the NVP Python/React prototype
can connect to a developer-run, loopback-only OpenAI-compatible model server.
The UI includes LM Studio (commonly port 1234), llama.cpp (commonly port
8080), and a custom local endpoint option. These paths are **not** the
production model selection mechanism. No model or GPU is verified by merely
listing an ID on the server.

## Migration requirement

1. Replace direct model HTTP calls in NVP with a Lu-owned inference adapter.
2. Use host-issued model/session references and current user/task scope.
3. Let Lu prioritize the foreground chat and arbitrate GPU/VRAM resources.
4. Do not auto-load a second large GGUF in an NVP workspace.
5. Keep NVP's model-generated screenplay changes as reviewable proposals.
6. Never expose raw filesystem permissions or unauthenticated model access.

Lu model, permission, resource and cancellation capabilities are separate
from NVP's film-specific data and directing workflows. The Lu DLC host
is not yet a released Windows external-DLC integration.

See docs/LU_DLC_WORKSPACE_CONTRACT.md.
