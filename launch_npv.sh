#!/bin/bash

echo "======================================================="
echo "    BOOTING NEURAL VIRTUAL PRODUCTION OPERATING SYSTEM"
echo "======================================================="

# 1. Start FastAPI Backend in background
echo "[1/3] Launching Local AI Validation Server..."
cd /home/yourusername/nvp_v2_workspace/backend
python3 -m uvicorn nvp_api:app --host 127.0.0.1 --port 8000 &

# 2. Start React Frontend in background
echo "[2/3] Launching Web Interface System Hub..."
cd /home/yourusername/nvp_v2_workspace/frontend
npm start &

# 3. Wait momentarily and open the default browser
echo "[3/3] Initializing Control Room View..."
sleep 3
xdg-open http://localhost:3000

echo "NVP Studio Online. Keep terminal open to maintain session."
