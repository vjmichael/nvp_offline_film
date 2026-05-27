import os
import json
import shutil
import asyncio
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
WORKSPACE_DIR = Path("./nvp_projects")
WORKSPACE_DIR.mkdir(exist_ok=True)

class ProjectConfiguration(BaseModel):
    project_id: str
    genre: str          
    cinematic_style: str 

async def async_read_json(file_path: Path) -> dict:
    """Non-blocking JSON read utilizing the asyncio thread pool."""
    def _read():
        with open(file_path, "r") as f:
            return json.load(f)
    return await asyncio.to_thread(_read)

async def async_write_json(file_path: Path, data: dict):
    """Non-blocking JSON write utilizing the asyncio thread pool."""
    def _write():
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    await asyncio.to_thread(_write)

async def async_copy_directory(src: Path, dest: Path):
    """Offloads heavy disk I/O cloning to prevent API stalling."""
    await asyncio.to_thread(shutil.copytree, src, dest)

@router.post("/api/projects/gatekeeper_check")
async def request_style_mutation(payload: ProjectConfiguration):
    """
    Validates incoming project configurations against the locked state ledger.
    """
    project_path = WORKSPACE_DIR / payload.project_id
    state_file = project_path / "project_state.json"
    
    if not state_file.exists():
        raise HTTPException(status_code=404, detail="Project state ledger not found.")

    current_state = await async_read_json(state_file)
        
    old_style = current_state.get("cinematic_style")
    old_genre = current_state.get("genre")
    
    # The Matrix Enforcement Logic
    if old_style != payload.cinematic_style or old_genre != payload.genre:
        return {
            "status": "mutation_warning_triggered",
            "message": "Altering primary genre or style requires complete spatial recalculation.",
            "details": f"Attempting structural change: {old_style} -> {payload.cinematic_style}.",
            "action_recommended": "CREATE_RESTORE_POINT_AND_BRANCH"
        }
    
    return {"status": "safe", "message": "No destructive style changes detected."}

@router.post("/api/projects/branch_and_mutate")
async def clone_and_mutate(payload: ProjectConfiguration):
    """
    Executes a clean, asynchronous structural fork of the project directory.
    This creates the safe 'Restore Point' branch before applying new AI parameters.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    src_dir = WORKSPACE_DIR / payload.project_id
    dest_id = f"{payload.project_id}_FORK_{payload.cinematic_style.replace(' ', '_')}_{timestamp}"
    dest_dir = WORKSPACE_DIR / dest_id
    
    if not src_dir.exists():
        raise HTTPException(status_code=404, detail="Source project directory not found.")
    
    try:
        # 1. Asynchronously duplicate the physical asset structure on disk
        await async_copy_directory(src_dir, dest_dir)
        
        # 2. Update the JSON ledger in the new branch
        cloned_state_path = dest_dir / "project_state.json"
        branch_data = await async_read_json(cloned_state_path)
        
        branch_data["project_id"] = dest_id
        branch_data["genre"] = payload.genre
        branch_data["cinematic_style"] = payload.cinematic_style
        
        await async_write_json(cloned_state_path, branch_data)
            
        return {
            "status": "success",
            "new_project_id": dest_id,
            "message": f"Restore point secured. Branched to environment: {dest_id}"
        }
    except Exception as e:
        # Cleanup partial copies if the drive operation fails
        if dest_dir.exists():
            await asyncio.to_thread(shutil.rmtree, dest_dir)
        raise HTTPException(status_code=500, detail=f"Branching failed: {str(e)}")