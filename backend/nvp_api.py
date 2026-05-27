import asyncio
import io
import numpy as np
import scipy.io.wavfile as wavfile
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from TTS.api import TTS

# Abstracted import for the new SSM-Hybrid engine
from core.ssm_hybrid import VideoMambaDirectorPipeline 

app = FastAPI(title="NVP Core - Multimodal SSM")

# Load localized models into GPU VRAM
print("Loading SSM and TTS models onto GPU...")
tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
vision_ssm = VideoMambaDirectorPipeline(model_path="models/videomamba-nvp-v1")

@app.websocket("/ws/touchless_director")
async def touchless_director_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        while True:
            # 1. Receive CLEAN TEXT from the frontend (routed from the STT service)
            transcription = await websocket.receive_text()
            print(f"Director Command Received: {transcription}")
            
            # 2. The SSM Brain evaluates the spoken text against the live visual state
            engine_state = await vision_ssm.capture_ue5_viewport_ndi()
            ssm_decision = await vision_ssm.evaluate_and_adjust(
                prompt=transcription, 
                visual_context=engine_state
            )
            
            # 3. Trigger the local Python bridge to adjust UE5 Control Rigs / Lighting
            await dispatch_to_ue5_bridge(ssm_decision.ue5_commands)
            
            # 4. Synthesize the AI's verbal response
            audio_response = tts_model.tts(
                text=ssm_decision.verbal_response,
                speaker_wav="personas/dp_voice_ref.wav",
                language="en"
            )
            
            # 5. Build WAV header in-memory to ensure browser playback compatibility
            # XTTSv2 outputs raw float32 at a 24000Hz sample rate
            audio_np = np.array(audio_response, dtype=np.float32)
            wav_io = io.BytesIO()
            wavfile.write(wav_io, 24000, audio_np)
            
            # 6. Stream the valid WAV bytes back to the React frontend
            await websocket.send_bytes(wav_io.getvalue())
            
    except WebSocketDisconnect:
        print("Director Dashboard disconnected from the touchless socket.")

async def dispatch_to_ue5_bridge(commands):
    # Pushes the JSON adjustments to nvp_ue5_bridge.py running inside Unreal Engine
    pass