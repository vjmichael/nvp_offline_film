> **PRODUCT ARCHITECTURE CORRECTION (2026-11-02):** NVP is an optional Lu
> Film Workspace DLC. This standalone Python/React runbook is for isolated
> development tests only, not a consumer installation or another Lu app.
> See the Lu DLC contract in docs/LU_DLC_WORKSPACE_CONTRACT.md.

# NVP foundation: local development and test runbook

## What works now
This branch is a **planning prototype**, not a film-rendering engine. You can create
projects, save screenplay text, parse basic Fountain-style scenes and dialogue,
propose simple camera coverage, edit shots, mark approvals, and reopen it later.

## Local developer run
Requires Python 3.10+, Node.js, npm (development only).
Run from the repository root.

    python -m pip install -r requirements-foundation.txt
    python -m uvicorn backend.nvp_api:app --host 127.0.0.1 --port 8000

In a second terminal:

    cd frontend
    npm install
    npm run dev

Then open http://127.0.0.1:3000/. Projects are stored in
~/NVP_Projects/nvp_studio.sqlite3 by default; set NVP_HOME to customize.

Test core with:

    python -m unittest discover -s tests -p "test_studio.py" -v

For the API test install httpx, then run:

    python -m pip install httpx
    python -m unittest discover -s tests -v

## Explicit limits
- All screenplay and shot planning works on CPU, no AI model or CUDA.
- Fountain parsing is deliberately conservative; inspect scene and speaker output.
- A scene heading change may archive an old plan for later reconciliation.
- The application does not yet create images, video, 3D assets, animations or audio.
- Do not use old launch_npv.bat / launch_npv.sh scripts; they refer to missing paths
  and legacy GPU services and will be replaced by a packaged desktop launcher.
- Existing legacy UE5, VLM, STT and TTS modules remain in the repository for
  audit and selective reuse; they are not wired to the foundation API.

## Known technical debt
- Repo has case-only duplicate README.md / readme.md, which can break Windows checkouts.
  Consolidate without changing the original proprietary license intent.
- Older frontend/root copies and legacy placeholder services require archival.
- Build Windows GUI/installer and tests independent of GitHub CI.
- Add story-bible persistence, actor/prop continuity, camera geometry,
  animation and real media rendering in subsequent work.


## Creative development and local AI
Creators can start with an idea or import/paste a plain-text/Fountain script.
The Develop the idea tab saves editable loglines, synopses, beat sheets,
treatments and screenplay drafts. A local writing model is optional.

To connect a separately running OpenAI-compatible loopback server, set:
    NVP_LLM_URL=http://127.0.0.1:8080/v1/chat/completions
    NVP_LLM_MODEL=local
These are examples, not a verified running model or installer requirement.
NVP rejects remote addresses, HTTP redirects and proxy routing for scripts.

An AI draft is never auto-applied. "Use as screenplay" is an explicit action
that checks revisions, preserves the previous screenplay in local history and
retains shot planning data when scenes change. Manual screenplay saves also
record old revisions; the history API allows restoring a prior script.


## Verification record, 2026-11-02
On a local mirror of the backend modules, 15 Python unit/API regressions passed:
story drafting, proposal approval, revision conflicts, screenplay restoration,
and recovery of previously approved shot plans. The new branch also includes
creative-development regression tests. This is not a claim that the React UI,
actual local LLM, video/3D renderer, or Windows installer have passed acceptance.

## Local model picker (Nov 2)
The **Develop the idea** screen now offers LM Studio on port 1234 or llama-server
on port 8080 with a model ID picker and an explicit Refresh action. It can use a
configured custom loopback NVP_LLM_URL if necessary. Advertised models are not
proof of successful inference; validate with the actual GGUF loaded on the
physical Windows/R9700 machine. See docs/LOCAL_MODEL_CONNECTION.md.
