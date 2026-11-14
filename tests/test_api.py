import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from backend import nvp_api
from backend.nvp_studio import Studio


class APITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = nvp_api.studio
        nvp_api.studio = Studio(Path(self.tmp.name) / "store.sqlite3")
        self.client = TestClient(nvp_api.app)

    def tearDown(self):
        nvp_api.studio = self.original
        self.tmp.cleanup()

    def test_full_user_journey_and_capability_truth(self):
        status = self.client.get("/api/status").json()
        self.assertEqual(status["capabilities"]["3d_renderer"], "not_connected")
        self.assertFalse(status["gpu_required"])
        project = self.client.post("/api/projects", json={"title": "My first movie", "idea": "A reunion"}).json()
        self.assertEqual(self.client.get("/api/projects").json()[0]["id"], project["id"])
        response = self.client.put(f"/api/projects/{project['id']}/screenplay", json={
            "expected_revision": 0, "screenplay": "INT. HOUSE - NIGHT\n\nMAYA\nI came back."})
        self.assertEqual(response.status_code, 200)
        scene = response.json()["scenes"][0]
        response = self.client.post(f"/api/projects/{project['id']}/scenes/{scene['id']}/shot-plan")
        shot = response.json()["scenes"][0]["shots"][0]
        self.assertEqual(shot["status"], "proposed")
        endpoint = f"/api/projects/{project['id']}/scenes/{scene['id']}/shots/{shot['shot_id']}"
        changed = self.client.put(endpoint, json={"framing": "close_up", "subject": "MAYA",
             "intent": "Show resolve", "notes": "Keep this!", "approved": True})
        self.assertEqual(changed.json()["scenes"][0]["shots"][0]["status"], "approved")
        self.client.post(f"/api/projects/{project['id']}/scenes/{scene['id']}/shot-plan")
        self.assertEqual(self.client.get(f"/api/projects/{project['id']}").json()["scenes"][0]["shots"][0]["notes"], "Keep this!")
        conflict = self.client.put(f"/api/projects/{project['id']}/screenplay", json={
            "expected_revision": 0, "screenplay": "EXT. FIELDS - DAY"})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.client.get("/api/projects/bogus").status_code, 404)


if __name__ == "__main__":
    unittest.main()
