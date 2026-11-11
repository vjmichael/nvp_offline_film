# G03 — Director-first NVP home, project access and separate editor

**Work-order date:** November 10, 2026 (America/Phoenix)  
**Decision:** G02 Lu integration **deferred at creator request**. Build G03 against existing standalone NVP source, without loading Lu, guessing endpoints or changing the shared model design.  
**Branch:** `nvp/g03-film-home-project-access-20261110`, stacked on G03 source contract/documentation branch `nvp/docs-filmmaker-workflow-20261110`.  
**Canonical DATA-AV PR #74:** no merge or changes made here.  
**Scope:** G03 only; G04 AI screenplay ingestion / G05 visual scene generation, G06 recording, G07 editing and G08 export are NOT claimed implemented.

## Product behavior actually implemented

### G03-A — Film project home and onboarding
- The only shipped React entry point is `FilmmakerHome`; the older 18-tab technical App is not imported into the bundle.
- On first open, show chat-first home, left sidebar with saved movie titles and lock status, and a **New Movie / Resume Working** modal.
- **New Movie** offers an optional, dismissible **I have a script / Just an idea** prompt, then script upload/paste or idea input and a lower-right **Next**. A screenplay can be committed atomically with movie creation; failed validation does not leave a half-created blank film.
- **Resume Working** lists movies, unlocks protected movies before fetching content, restores last selected filmmaking phase from local client metadata, and does not read locked movie screenplay before successful server-side authorization.
- Disabled/missing AI capability is truthfully labeled. No fake ChatGPT completion, scene generated or render produced. Manual screenplay editing and line-numbered search remain available.

### G03-B — Server-side project access, bounded claim
- `backend/nvp_project_access.py` stores per-film scrypt salted/verifier credential in the project's SQLite, not plaintext password. No token or password is exposed in React.
- `nvp_api` HTTP middleware guards **every existing `/api/projects/{project_id}/...` endpoint**, including screenplay, Production Bible, shot planning, world/asset operations, and film native-time records. Unlocked objects use short-lived, HttpOnly, SameSite=Strict project-bound cookie sessions; relock/restart invalidates them.
- Locked list metadata contains only project ID, display title, revision/timestamp and lock status, never movie idea, screenplay or preview.
- Password attempts are rate-limited within the process and lock is persisted across restart. Mutations under a protected movie require a non-simple same-origin custom header, not merely the cookie.
- **SECURITY LIMITATION — MUST NOT REPRESENT AS ENCRYPTED:** the SQLite film, OpenUSD assets, source PCM, backups and other direct OS files are not encrypted by this gate; project IDs/titles are visible. A local process with direct file access may still read them. Lock recovery, OS-user identity, race-safe key custody, direct-file protection, multi-process session revocation and all secondary native exposure surfaces require independent design and physical acceptance. Until then UI says plainly that lock restricts NVP access, not disk access.
- Protecting a movie requires a passphrase of 12–256 characters; no password reset exists today. A failed or bypassed lock is never described as full privacy.

### G03-C — Filmmaker steps and separate editor window
The visible phase navigation is exactly **Script (optional) → Set Up Scenes → Film Scenes → Edit Film → Export Film**. It shows understandable creative objects and honest current limits.

- Script inventory auto-populates from parsed Fountain scene headers, characters and dialogue. The screenplay is **not** a frozen performance. Actor-free scenes are valid.
- Set Up Scenes shows scene cards/setting/dialogue and a truthful *scene preview not generated* placeholder, not invented geometry. Actual OpenUSD stage generation is G05.
- Film Scenes shows familiar wide / medium / close-up suggested views without pretending 2D video was captured. Freeze/retakes belong to G06.
- Edit Film opens an independent `postproduction.html` document/window with its own React root, served by the same protected native desktop loopback process. It cannot rewrite originals or pretend an editing timeline has shipped (G07).
- Export Film is disabled until an actual authorized package pipeline exists (G08).
- No engineering panels, native tool transport, resource journals, API keys, FFmpeg controls or model-server configuration are exposed.

### G03-D — Interaction and verification
- Dialogs have accessible names and focus targets, forms labeled, status/errors live roles, buttons/links have keyboard-visible focus styles, responsive sidebar and reduced-motion preferences.
- No model loading, GPU claims, source Take writes or artificial completed movie render.

## Source changes
- `frontend/src/App.jsx` (single director entry point)
- `frontend/src/FilmmakerHome.jsx`, `filmmaker-home.css`, `FilmmakerHome.test.jsx`
- `frontend/src/PostProduction.jsx`, `postproduction-entry.jsx`, `frontend/postproduction.html` and Vite multi-entry build
- `backend/nvp_project_access.py`, API route guard + protect/unlock/lock, `backend/nvp_studio.py` atomic optional screenplay creation, `tests/test_nvp_g03_project_access.py`
- `tools/nvp_desktop_alpha.py`: bundles and serves both pages, adds an isolated `--smoke-g03-window` native WebView2 director/resume/editor interaction gate
- `.github/workflows/nvp-g03-film-home.yml` source/API/React and actual local server two-entry test
- `.github/workflows/nvp-g03-windows-installed.yml` Windows NSIS build, installed smoke, native visible WebView2, uninstall/data preservation and installer artifact

## Verifications and acceptance truth
- Python contract tests run on Windows/Linux 3.11/3.13 and existing FastAPI user journey retained.
- React Vitest tests cover startup, New Movie, resume, actor-free scenes, locked movie preflight, and explicit absent AI; Vite builds both independent HTML entrypoints.
- The G03 source run is **not itself physical Windows installed acceptance**. Grouped CI status and exact-source head must be checked on GitHub Actions.
- The NSIS workflow gives Windows runner installed-app evidence and a downloadable candidate only if it passes. The creator's actual installed Radeon workstation, screen reader/keyboard traversal, project lock attack tests against secondary native interfaces, and disk encryption remain separately unaccepted.
- G01 PLAN-04 physical closeout and G02 native Lu mount both stay outside this G03 work. G02 is intentionally on hold; no NVP Film Workspace is represented as connected to Lu.

## Remaining G03 closeout
1. Inspect exact-head Windows/Linux compiler/API/UI logs and repair all demonstrated source, API or native WebView failures.
2. Finish Windows installed NSIS original user data preservation and verify New/Resume in actual WebView2 with keyboard/modal accessibility.
3. Security: independently audit all secondary native endpoints and file/storage/asset access for bypass; design and accept actual OS-bound key/cipher protections if locked movies are to be advertised as confidentiality rather than local API restrictions; physical lock/restart/recovery test.
4. Profile real large movie lists, long screenplays and app restart, including separate editor selection and stale lock changes.
5. Only after those passes can G03 be marked complete. **Next planned group G04; G02 remains deferred.**

**Do not merge this UI branch blindly with canonical DATA-AV PR #74; source/ABI and installed desktop acceptance must be reconciled at the then-current exact head. Zero FFmpeg remains absolute.**
