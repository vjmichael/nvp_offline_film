import requests
import logging

class UE5RemoteConnector:
    def __init__(self, host="127.0.0.1", port=3001):
        self.base_url = f"http://{host}:{port}"
        
    def push_camera_payload(self, set_path: str, camera_name: str, payload: dict) -> bool:
        logging.info(f"Pushing payload to {set_path}:{camera_name}")
        return True
