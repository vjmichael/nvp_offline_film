import json
import logging
from pathlib import Path
from langchain_community.chat_models import ChatOllama

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

class ProductionBibleManager:
    def __init__(self, bible_dir="./nvp_bible"):
        self.bible_dir = Path(bible_dir)
        self.casting_ledger = self._load_json("nvp_casting_ledger.json")
        self.environment_registry = self._load_json("nvp_environment_registry.json")

    def _load_json(self, filename):
        try:
            with open(self.bible_dir / filename, 'r') as f: return json.load(f)
        except FileNotFoundError: return {}

    def get_actor_fingerprint(self, actor_id):
        actor_data = self.casting_ledger.get(actor_id)
        if not actor_data or "height_cm" not in actor_data.get("physical_metrics", {}):
            raise RuntimeError(f"FATAL: Missing actor {actor_id} or height_cm metric.")
        return actor_data

    def get_set_bounds(self, set_id):
        return self.environment_registry.get(set_id, {}).get("spatial_bounds", {})

nvp_bible = ProductionBibleManager()
director_llm = ChatOllama(model="llama3:70b", temperature=0.1, format="json")
worker_llm = ChatOllama(model="qwen3.1:32b", temperature=0.0)
