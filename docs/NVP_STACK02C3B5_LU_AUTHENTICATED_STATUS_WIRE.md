# STACK-02C3B5 — Read-only Lu status over authenticated AF_UNIX

**Gate:** development contract, NOT a shipped Lu alpha feature. The stable functional Lu 0.1.0-alpha.2 desktop is unchanged. NVP cannot currently load a model through Lu.

## Implementation

- backend/nvp_lu_status_wire.py: Version 1 canonical status-only request/response, strict field and shape checks, bounded 8 KiB frames. A host-injected fresh 256-bit key binds the film project, host epoch, one-use request identity and 5-second request expiry with HMAC-SHA256. Request and response have different signing domains.
- StatusHostProof: test-only host authority with SQLite BEGIN IMMEDIATE replay rejection and durable project/epoch revocation. This is not registered into the Lu Tauri desktop.
- backend/nvp_lu_status_socket.py: true operating-system AF_UNIX status client using length-delimited network byte order and read timeout. It cannot generate, load, cancel or unload a Lu model.
- The existing PassiveLuStatusObserver records externally managed model activity without NVP model ownership, RAM reservation or fabricated progress.

### Tested behavior

Native Windows and Linux CI opens real local sockets between the client and an explicitly simulated Lu status service. It checks valid status, cross-project/epoch rejection, expired and revoked requests, replay across reopened SQLite ledgers, altered authentication and response correlation, malformed/oversized frames, and no inference control. An authenticated status observation is NOT verified provider model custody or evidence of real GGUF execution.

## Why there is no Lu runtime connection yet

The accepted independent Lu desktop exposes model commands as internal Tauri methods, not a supported external NVP interface. Its llama.cpp HTTP backend uses a private ephemeral loopback port and host-generated API key. The separately tested AF_UNIX ToolCall/ToolReply carrier exists only on an experimental jan_alt branch and was not shipped in the accepted independent desktop. NVP must not scrape the model key, use a guessed socket, or impersonate an approved user.

[Lu source defect #7](https://github.com/vjmichael/Lu-AI-GUI/issues/7): Windows checked-in persistent engine invokes a missing Job::assign_and_resume_suspended worker method. Do not weaken Windows suspended-launch containment to make compilation succeed.

## Next gates

A Lu-owned, opt-in native status service with verified creator approval, protected OS-local credentials, Windows ACL/peer identity and Linux permission gates must be implemented in a *new* Lu development branch. Run the exact NVP client against that genuine Rust host on both operating systems; a Python simulated host is insufficient. Only afterward add separately authorized inference operations with host-held session identity, model admission, streaming and recovery. Real GGUF/AMD resource co-admission, Blender coexistence and physical Windows tests remain release-blocking.
