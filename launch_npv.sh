#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if ! command -v python3 >/dev/null || ! command -v npm >/dev/null; then
  echo "Python 3 and npm are needed for this developer preview." >&2
  exit 1
fi
if [ ! -d frontend/node_modules ]; then
  echo "Run 'cd frontend && npm install' before launching this preview." >&2
  exit 1
fi
python3 -m uvicorn backend.nvp_api:app --host 127.0.0.1 --port 8000 &
API_PID=$!
cleanup() { kill "$API_PID" "$WEB_PID" 2>/dev/null || true; }
WEB_PID=""
trap cleanup EXIT INT TERM
(cd frontend && npm run dev) &
WEB_PID=$!
echo "Open http://127.0.0.1:3000/ in a browser."
wait "$WEB_PID"
