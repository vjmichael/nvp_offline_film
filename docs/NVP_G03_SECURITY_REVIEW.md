# G03 independent film-project security review

**Status: security review performed; project access controls improved; full confidentiality NOT accepted.** Lu G02 remains deferred; canonical PR #74 remains unchanged.

## Attacker model and limits

The G03 passphrase only restricts access through NVP's local API and its current WebView2 UI. It does NOT encrypt the movie. Someone with the same Windows account, direct filesystem access, administrator access, access to backups or access to another native tool can still read or copy plaintext film data. A salted scrypt verifier protects the passphrase itself, not the film.

Plaintext may include SQLite planning tables, screenplay and Production Bible, SQLite WAL/SHM, OpenUSD layers, original spatial PCM, Takes, preview caches, journals, temporary files, export derivatives, backups, crash dumps and copies made before protection. The project list intentionally exposes a display title, ID and lock status.

| Surface | Verified safeguard | Outstanding risk |
| --- | --- | --- |
| Project-specific HTTP routes | Deny protected movie reads and mutations before registered handlers, revisioned writes, HttpOnly SameSite=Strict session cookie, non-simple custom header for protected mutations | Header is CSRF friction, NOT OS authentication; same-account processes can issue API requests |
| Whole API route inventory | Tests enumerate every registered project-ID route, not only examples | Newly introduced non-project URI surfaces must receive independent review |
| Unlock, replay and restarts | scrypt verifier, SQLite-serialized persistent failed-attempt accounting/cooldown, persisted project generation revocation across live NVP processes, per-project volatile token, relock and restart revoke access | Same-account or filesystem attacker can read data and may tamper with DB/time; offline verifier guessing remains possible |
| Native camera/sound/rail IPC | The installed host refuses old native source calls when ANY project is protected; existing worker cleanup/cancel remains accessible | Conservative shutdown also disables other movies' native A/V; no fine-grained host-owned grant or proof about previously started worker outputs |
| Browser interface | Only five creative stages; a separate Post-Production shell clears its cached content on localStorage relock and rechecks authorization | Other already-rendered content or browser memory may remain; no confidentiality guarantee |
| Global system activity endpoint | Task titles and resource details are redacted while any movie is protected; no film title leaked through this alternate route | Underlying host SQLite worker journal remains readable on disk |
| Data on disk | None | SQLite, WAL, OpenUSD, PCM, media objects, journals, cache and backups are NOT encrypted |
| OS credential/identity boundary | Per-user install and trusted loopback Host check | Not a Windows DPAPI/CNG film vault; lack of independent host/account authorization |
| Physical Windows | Automated NSIS, WebView2 and OS UIAutomation gates added | Owner's actual workstation keyboard/screen-reader and restart acceptance remain separately required |
| Lu/GGUF and film render | No integration or generated film claimed | Deferred G02, future G05/G06/G07/G08 |

## Encryption design and acceptance required before a "confidential movie" claim

1. Distinguish the existing **Lock in NVP** (interface gate) from any future **Encrypt Film** (content confidentiality). Never treat a padlock icon as a security attestation.
2. Establish a **host-owned random per-project content key** with audited Windows DPAPI/CNG ownership or separately specified passphrase-derived recovery. Never send keys, raw file paths or plaintext buffers through browser/model IPC.
3. Authenticated encryption must bind project ID, artifact identity, revision, type and an independently unique nonce to each protected object. Use vetted AES-GCM or equivalent. The scope must include **every** native source and derivative: SQLite/WAL, original OpenUSD and PCM, Takes, Production Bible, logs, worker journals, caches, draft media, staging, temporary recovery files and backups. Encrypting the screenplay column alone is insufficient.
4. Preserve immutable originals with crash-safe migrate/journal/reopen cycles: compute source hashes, stage encrypted copies, fsync, independently verify authentication and exact bytes, atomically switch reference indexes, perform forced-kill/restart recovery, and never delete originals before durable independent reopens succeed. Existing plaintext copies may remain in the filesystem or backups even after successful migration; no absolute erasure claim.
5. Every native worker, IPC bridge, original source reader and new tool must consume one **host-controlled project/session grant** that expires/revokes at relock and restart. No model-generated authorization; prevent A/V playback after a locked project's grant is revoked. Verify CPU/GPU worker containment and recovery.
6. Test wrong passwords and restart brute force, tampered ciphertext/AAD/nonce, copied authorization tokens, cross-project access, WAL retention, malicious symlinks, backup restore, interrupted encryption, physical Windows ACLs and key custody. Test independent native access bypasses, not just FastAPI.

**Release decision:** Security controls in G03 are suitable for preventing inadvertent opening inside NVP, not protecting film data from an OS-account adversary. Full confidentiality is an unresolved **security release blocker** and must not be marked complete based on the current CI evidence. Zero FFmpeg in the active pipeline remains mandatory.

## Evidence and next steps

- Grouped project API/full inventory tests, windowed-server runtime tests and frontend checks: workflow nvp-g03-film-home.yml.
- Windows NSIS installed, two-film restart/relock and physical Windows UIAutomation role/focus tests: nvp-g03-windows-installed.yml.
- Native source IPC denial regression: test_nvp_slate08b_native_camera_ipc.py.
- G02 Lu integration remains deferred by the creator. Do not modify canonical PR #74.

The remaining G03 acceptance items are Windows exact-head installed evidence, OS-keyed source-content protection and a human-operated accessibility/restart test on the physical Windows machine.
