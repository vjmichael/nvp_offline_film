import json
from pathlib import Path
from datetime import datetime

WORKSPACE_DIR = Path("./nvp_projects")

def prepare_take_directory(project_id: str, scene_id: str, scene_name: str) -> Path:
    project_path = WORKSPACE_DIR / project_id
    render_base_path = project_path / "Rendered_Takes"
    
    safe_scene_name = "".join(c if c.isalnum() else "_" for c in scene_name)
    scene_path = render_base_path / f"{scene_id}_{safe_scene_name}"
    scene_path.mkdir(parents=True, exist_ok=True)
    
    existing_takes = [d for d in scene_path.iterdir() if d.is_dir() and d.name.startswith("Take_")]
    take_folder_name = f"Take_{len(existing_takes) + 1:02d}"
    current_take_path = scene_path / take_folder_name
    current_take_path.mkdir()
    
    return current_take_path

def log_take_metadata(take_path: Path, dp_payload: dict, script_text: str):
    metadata = {
        "timestamp": datetime.now().isoformat(),
        "script_action": script_text,
        "engine_payload": dp_payload
    }
    with open(take_path / "take_metadata.json", "w") as f:
        json.dump(metadata, f, indent=4)