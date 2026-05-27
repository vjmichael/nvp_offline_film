import os
import json
import shutil
import asyncio
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()
WORKSPACE_DIR = Path("./nvp_projects")

# --- Pydantic Data Matrix ---

class TakeMetadata(BaseModel):
    take_uid: str               
    scene_id: str               
    shot_id: str                
    attempt_number: int         
    camera_id: str              
    timestamp: str              
    recorded_file_path: str     
    notes: Optional[str] = None

class HourlySnapshot(BaseModel):
    snapshot_id: str            
    timestamp: str
    takes: List[TakeMetadata] = []

class TakeBranchRequest(BaseModel):
    project_id: str
    take_uid: str
    branch_name: str # e.g., "Director_Cut_Voxel_Edit"

# --- Async I/O Handlers ---

async def async_read_json(file_path: Path) -> dict:
    def _read():
        if not file_path.exists():
            return {}
        with open(file_path, "r") as f:
            return json.load(f)
    return await asyncio.to_thread(_read)

async def async_write_json(file_path: Path, data: dict):
    def _write():
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
    return await asyncio.to_thread(_write)

async def async_copy_asset(src: Path, dest: Path):
    """Safely duplicates massive compiled frame sequences or voxel data."""
    if src.is_dir():
        await asyncio.to_thread(shutil.copytree, src, dest)
    else:
        await asyncio.to_thread(shutil.copy2, src, dest)

# --- Versioning Endpoints ---

@router.post("/api/versioning/record_take")
async def append_take_to_dailies(project_id: str, payload: TakeMetadata):
    """
    Called asynchronously by nvp_dp_engine for every active camera 
    the moment a recording stops.
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    project_path = WORKSPACE_DIR / project_id
    
    # Target Daily Ledger: ./nvp_projects/{id}/Dailies/2026-05-25/daily_ledger.json
    ledger_dir = project_path / "Dailies" / current_date
    await asyncio.to_thread(ledger_dir.mkdir, parents=True, exist_ok=True)
    
    ledger_file = ledger_dir / "daily_ledger.json"
    daily_data = await async_read_json(ledger_file)
    
    # Initialize daily ledger structure if empty
    if not daily_data:
        daily_data = {
            "date_stamp": current_date,
            "hourly_snapshots": [],
            "floating_takes": [] # Takes not yet rolled into a snapshot
        }
    
    daily_data["floating_takes"].append(payload.model_dump())
    await async_write_json(ledger_file, daily_data)
    
    return {"status": "success", "message": f"Take {payload.take_uid} committed to Dailies."}

@router.post("/api/versioning/snapshot")
async def trigger_hourly_snapshot(project_id: str):
    """
    Rolls all 'floating' takes into an immutable hourly snapshot. 
    Can be triggered by a CRON job or manually by the user UI.
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    hour_stamp = datetime.now().strftime("%H00")
    snapshot_id = f"H_{hour_stamp}_V{datetime.now().strftime('%M%S')}"
    
    ledger_file = WORKSPACE_DIR / project_id / "Dailies" / current_date / "daily_ledger.json"
    
    if not ledger_file.exists():
         raise HTTPException(status_code=404, detail="No active shooting data found for today.")

    daily_data = await async_read_json(ledger_file)
    floating_takes = daily_data.get("floating_takes", [])
    
    if not floating_takes:
        return {"status": "idle", "message": "No new takes to snapshot."}

    # Bundle takes into the new snapshot and clear the floating array
    new_snapshot = {
        "snapshot_id": snapshot_id,
        "timestamp": datetime.now().isoformat(),
        "takes": floating_takes
    }
    
    daily_data["hourly_snapshots"].append(new_snapshot)
    daily_data["floating_takes"] = [] # Reset for the next hour
    
    await async_write_json(ledger_file, daily_data)
    
    return {"status": "success", "snapshot_id": snapshot_id}

@router.post("/api/versioning/branch_take")
async def branch_experimental_take(payload: TakeBranchRequest):
    """
    Creates an isolated sandbox copy of a specific take. 
    Allows the user to destructively edit voxel data or apply new VLM styles 
    without altering the master Dailies ledger.
    """
    # 1. Locate the source file path by scanning the ledgers (Simplified for brevity)
    # In production, this would query a dedicated SQLite or robust JSON index
    project_path = WORKSPACE_DIR / payload.project_id
    dailies_dir = project_path / "Dailies"
    
    source_file_path = None
    # Simulate finding the take path...
    source_file_path = dailies_dir / "2026-05-25" / "Scene_01" / "Shot_01" / f"{payload.take_uid}.mp4"
    
    if not source_file_path or not source_file_path.exists():
        raise HTTPException(status_code=404, detail="Take media not found on disk.")

    # 2. Setup the Branch directory
    branch_dir = project_path / "Branches" / payload.branch_name
    await asyncio.to_thread(branch_dir.mkdir, parents=True, exist_ok=True)
    
    target_file_path = branch_dir / f"{payload.take_uid}_BRANCHED.mp4"
    
    # 3. Asynchronously copy the massive asset
    await async_copy_asset(source_file_path, target_file_path)
    
    return {
        "status": "branched",
        "sandbox_path": str(target_file_path),
        "message": f"Sandbox created for {payload.take_uid}."
    }