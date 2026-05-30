import json
import uuid
from pathlib import Path

# Mapping to your actual workspace paths
BACKEND_DIR = Path(__file__).parent
BIBLE_DIR = BACKEND_DIR / "nvp_bible"
PROJECTS_DIR = BACKEND_DIR / "nvp_projects"
ACTORS_FILE = BIBLE_DIR / "nvp_casting_ledger.json"

class NvpDatabase:
    ACTORS_FILE = ACTORS_FILE
    PROJECTS_DIR = PROJECTS_DIR

    @staticmethod
    def get_actor(actor_id: str) -> dict:
        if not ACTORS_FILE.exists(): return {}
        with open(ACTORS_FILE, "r") as f:
            return json.load(f).get(actor_id, {})

    @staticmethod
    def update_actor_look(actor_id: str, updates: dict):
        if not ACTORS_FILE.exists(): return {}
        with open(ACTORS_FILE, "r+") as f:
            registry = json.load(f)
            if actor_id in registry:
                registry[actor_id].update(updates)
                f.seek(0)
                json.dump(registry, f, indent=4)
                f.truncate()
        return registry.get(actor_id)

    @staticmethod
    def get_scene(scene_id: str) -> dict:
        scene_path = PROJECTS_DIR / f"{scene_id}.json"
        if scene_path.exists():
            with open(scene_path, "r") as f:
                return json.load(f)
        return None

    @staticmethod
    def clone_scene(source_scene_id: str, new_take_name: str = None) -> dict:
        source_scene = NvpDatabase.get_scene(source_scene_id)
        if not source_scene:
            source_scene = {
                "scene_id": source_scene_id,
                "location_ref": "default_environment",
                "actors": [],
                "props": [],
                "script_lines": []
            }

        new_scene_id = new_take_name or f"{source_scene_id}_clone_{uuid.uuid4().hex[:6]}"
        cloned_scene = source_scene.copy()
        cloned_scene["scene_id"] = new_scene_id
        cloned_scene["script_lines"] = [] 

        new_path = PROJECTS_DIR / f"{new_scene_id}.json"
        with open(new_path, "w") as f:
            json.dump(cloned_scene, f, indent=4)
            
        return cloned_scene
