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
