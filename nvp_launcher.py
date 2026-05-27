import subprocess
import time
import sys
import os
import atexit
import webbrowser

# Define paths relative to the launcher
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

# Keep track of spawned processes so we can kill them later
processes = []

def cleanup():
    """Triggers when the launcher is closed to terminate all invisible background tasks."""
    print("Shutting down NVP services...")
    for p in processes:
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            p.kill() # Force kill if it hangs

# Register the cleanup function to run on exit
atexit.register(cleanup)

def start_service(command, cwd):
    """Spawns a hidden background process on Windows."""
    # This flag explicitly prevents Windows from popping up a terminal window
    CREATE_NO_WINDOW = 0x08000000 
    
    process = subprocess.Popen(
        command,
        cwd=cwd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW
    )
    processes.append(process)
    return process

if __name__ == "__main__":
    print("Booting Neural Video Producer...")

    # 1. Start the main API (Visual/SSM Bridge)
    start_service("uvicorn nvp_api:app --host 127.0.0.1 --port 8000", cwd=BACKEND_DIR)
    
    # 2. Start the STT Microservice (Whisper Audio)
    start_service("uvicorn nvp_stt_service:app --host 127.0.0.1 --port 8001", cwd=BACKEND_DIR)
    
    # 3. Start the React Frontend (Vite)
    # In production, this would serve static HTML via FastAPI. 
    # For development/local execution, we spin up Vite.
    start_service("npm run dev", cwd=FRONTEND_DIR)

    # Wait a few seconds for the servers to initialize
    time.sleep(3)

    # 4. Open the NVP Dashboard in the user's default web browser
    webbrowser.open("http://localhost:5173")

    # Keep the orchestrator alive. If this script dies, the atexit cleanup runs.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)