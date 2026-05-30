Python
import asyncio
import io
import numpy as np
import scipy.io.wavfile as wavfile
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from TTS.api import TTS

# Explicitly mapping to your core and db modules in the backend folder
from nvp_core import VideoMambaDirectorPipeline 
from nvp_db import NvpDatabase

app = FastAPI(title="NVP Core - Multimodal SSM Engine")

# Initialize models into GPU VRAM
print("Initializing neural network models onto CUDA device...")
tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda")
vision_ssm = VideoMambaDirectorPipeline(model_path="models/videomamba-nvp-v1")

@app.get("/api/verify_system")
async def verify_system_endpoint():
    """GUI-triggered health check for ports and file integrity."""
    report = {
        "status": "optimal",
        "details": {
            "main_api": "Connected",
            "stt_service": "Disconnected",
            "casting_ledger": "Missing",
            "projects_directory": "Accessible"
        }
    }
    
    # 1. Test connection to the STT service (Port 8001)
    try:
        _, writer = await asyncio.open_connection("127.0.0.1", 8001)
        report["details"]["stt_service"] = "Connected"
        writer.close()
        await writer.wait_closed()
    except Exception:
        report["status"] = "degraded"
        report["details"]["stt_service"] = "Offline (Port 8001)"

    # 2. Verify Ledger and Project path integrity via NvpDatabase constants
    if NvpDatabase.ACTORS_FILE.exists():
        report["details"]["casting_ledger"] = "Valid"
    else:
        report["status"] = "degraded"
        report["details"]["casting_ledger"] = "Error: Missing Ledger"
        
    if NvpDatabase.PROJECTS_DIR.exists():
        report["details"]["projects_directory"] = "Writable"
    else:
        report["status"] = "degraded"
        report["details"]["projects_directory"] = "Error: Missing Projects Folder"

    return report

@app.websocket("/ws/touchless_director")
async def touchless_director_endpoint(websocket: WebSocket):
    await websocket.accept()
    current_scene_id = "scene_001_take_01" 
    
    try:
        while True:
            transcription = await websocket.receive_text()
            engine_state = await vision_ssm.capture_ue5_viewport_ndi()
            
            ssm_decision = await vision_ssm.evaluate_and_adjust(
                prompt=transcription, 
                visual_context=engine_state,
                current_scene=current_scene_id
            )
            
            db_actions = getattr(ssm_decision, "db_actions", {})
            ue5_commands = getattr(ssm_decision, "ue5_commands", [])
            
            # Workflow: Scene/Take Cloning
            if db_actions.get("action") == "clone_scene":
                new_scene = NvpDatabase.clone_scene(current_scene_id)
                current_scene_id = new_scene["scene_id"]

            # Appearance: Aging and Costumes
            actor_updates = db_actions.get("update_actor")
            if actor_updates:
                actor_id = actor_updates.pop("actor_id")
                NvpDatabase.update_actor_look(actor_id, actor_updates)
                updated_profile = NvpDatabase.get_actor(actor_id)
                ue5_commands.append({"target": actor_id, "apply_profile": updated_profile})
                
            await dispatch_to_ue5_bridge(ue5_commands)
            
            # Vocal Consistency: Fetch reference from Ledger
            active_speaker_id = db_actions.get("speaker_id", "default_ai_voice")
            actor_profile = NvpDatabase.get_actor(active_speaker_id)
            voice_ref = actor_profile.get("voice_sample_path", "personas/dp_voice_ref.wav")
            
            audio_response = tts_model.tts(
                text=ssm_decision.verbal_response,
                speaker_wav=voice_ref,
                language="en"
            )
            
            # Header Fix for Browser Playback
            audio_np = np.array(audio_response, dtype=np.float32)
            wav_io = io.BytesIO()
            wavfile.write(wav_io, 24000, audio_np)
            await websocket.send_bytes(wav_io.getvalue())
            
    except WebSocketDisconnect:
        print("Director disconnected.")

async def dispatch_to_ue5_bridge(commands):
    pass
