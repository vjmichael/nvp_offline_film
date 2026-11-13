import asyncio
import numpy as np
import concurrent.futures
import subprocess
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from faster_whisper import WhisperModel

app = FastAPI(title="NVP Dedicated STT Engine")

# 1. Model Initialization
# compute_type="int8_float16" aggressively cuts VRAM usage by ~50% with near-zero accuracy loss.
print("Loading faster-whisper (INT8) onto GPU...")
stt_model = WhisperModel("large-v3", device="cuda", compute_type="int8_float16")

# 2. Thread Pool for Parallel Execution
# We restrict to a single worker to prevent Whisper from spawning multiple CUDA contexts.
# Using an executor prevents the transcription from blocking the main ASGI event loop.
executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

def decode_webm_to_pcm(audio_bytes: bytes) -> np.ndarray:
    """
    Decodes browser WebM/Opus chunks into 16kHz raw PCM float32 for Whisper 
    using FFmpeg in memory, bypassing disk I/O.
    """
    # Legacy browser WebM/FFmpeg STT is NOT NVP's native original PCM
    # capture or the production desktop's speech-recognition path.
    # A direct Windows Popen would escape the original release-wide
    # Job Object/launch-slot admission policy. Refuse rather than
    # quietly permit a second unmanaged installed media runtime.
    if os.name=="nt":
        raise RuntimeError("Retired WebM/FFmpeg STT cannot launch a Windows worker; use native PCM capture")
    process = subprocess.Popen(
        ['ffmpeg', '-i', 'pipe:0', '-f', 'f32le', '-ac', '1', '-ar', '16000', 'pipe:1'],
        stdin=subprocess.PIPE, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.DEVNULL
    )
    out, _ = process.communicate(input=audio_bytes)
    return np.frombuffer(out, dtype=np.float32)

def block_and_transcribe(audio_np: np.ndarray) -> str:
    """Synchronous function that actually hits the GPU."""
    # vad_filter=True is critical. It drops silence before passing to the GPU, saving compute.
    segments, _ = stt_model.transcribe(
        audio_np, 
        beam_size=5, 
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    return " ".join([segment.text for segment in segments]).strip()

@app.websocket("/ws/stream_mic")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Decouple receiving from processing using an async queue
    audio_queue = asyncio.Queue()

    async def receiver_task():
        """Continuously pulls bytes off the wire and queues them."""
        try:
            while True:
                # Expecting compressed WebM audio bytes from the React frontend
                audio_bytes = await websocket.receive_bytes()
                await audio_queue.put(audio_bytes)
        except WebSocketDisconnect:
            print("Microphone stream disconnected.")

    async def processor_task():
        """Pulls from the queue, decodes via FFmpeg, and offloads GPU work to the thread pool."""
        loop = asyncio.get_running_loop()
        try:
            while True:
                audio_bytes = await audio_queue.get()
                
                # 1. Decode WebM to PCM on the CPU in memory
                audio_np = decode_webm_to_pcm(audio_bytes)
                
                # 2. Offload the blocking transcription to the ThreadPoolExecutor
                transcription = await loop.run_in_executor(
                    executor, 
                    block_and_transcribe, 
                    audio_np
                )
                
                # 3. Only dispatch if speech was actually detected
                if transcription:
                    print(f"Transcribed: {transcription}")
                    await websocket.send_text(transcription)
                
                audio_queue.task_done()
        except asyncio.CancelledError:
            pass

    # Fire the parallel streams
    receiver = asyncio.create_task(receiver_task())
    processor = asyncio.create_task(processor_task())
    
    # Wait until the client drops the connection, then clean up
    await receiver
    processor.cancel()