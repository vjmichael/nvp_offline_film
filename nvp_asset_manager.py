import shutil
import json
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

router = APIRouter(prefix="/api/assets")
WORKSPACE_DIR = Path("./nvp_projects")

@router.post("/upload/actor")
async def upload_actor_asset(
    project_id: str = Form(...),
    actor_name: str = Form(...),
    height_cm: float = Form(...), 
    lora_file: UploadFile = File(...)
):
    # [Your existing actor upload logic remains here]
    pass 

@router.post("/upload/reference")
async def upload_reference_plate(
    project_id: str = Form(...),
    description: str = Form(""),
    image_file: UploadFile = File(...)
):
    """
    Uploads a visual reference frame (storyboard/shot design) for VLM processing.
    """
    project_path = WORKSPACE_DIR / project_id
    if not project_path.exists(): 
        raise HTTPException(status_code=404, detail="Project not found")

    plates_dir = project_path / "Asset_Library" / "Reference_Plates"
    plates_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = image_file.filename.replace(" ", "_")
    destination_path = plates_dir / safe_filename
    
    with destination_path.open("wb") as buffer:
        shutil.copyfileobj(image_file.file, buffer)

    state_file = project_path / "project_state.json"
    with open(state_file, "r") as f:
        project_data = json.load(f)

    # Generate reference metadata ID
    plate_id = f"NVP_Ref_{len(project_data.get('reference_plates', [])) + 1:03d}"
    new_plate_entry = {
        "id": plate_id,
        "description": description,
        "file_path": str(destination_path)
    }

    project_data.setdefault("reference_plates", []).append(new_plate_entry)

    with open(state_file, "w") as f:
        json.dump(project_data, f, indent=4)

    return {
        "status": "success", 
        "id": plate_id, 
        "message": "Reference plate registered for VLM inference."
    }