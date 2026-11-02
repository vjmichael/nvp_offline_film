"""Local model API integration regressions (mock server, no GGUF inference)."""
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import nvp_api
from backend.nvp_model_service import discover_models, model_family, configured_endpoint
from backend.nvp_studio import Studio


class LocalServer(BaseHTTPRequestHandler):
    received = None
    redirect = False

    def log_message(self, fmt, *args):
        pass

    def respond(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/v1/models":
            return self.send_error(404)
        if LocalServer.redirect:
            self.send_response(302)
            self.send_header("Location", "https://example.com/")
            return self.end_headers()
        self.respond({"data": [{"id": "gemma-4-31b-Q4.gguf"},
                               {"id": "qwen3.8-27b-Q4.gguf"},
                               {"id": "qwen3.6-35b-a3b-Q4.gguf"}]})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self.send_error(404)
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        LocalServer.received = data
        self.respond({"choices": [{"message": {"content":
            "INT. STUDIO - NIGHT\n\nAMY\nLet's begin."}, "finish_reason": "stop"}]})


class WriterRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LocalServer)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1/chat/completions"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=3)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = nvp_api.studio
        nvp_api.studio = Studio(self.tmp.name + "/nvp.db")
        self.project = nvp_api.studio.create_project("Test film", "A missing friend returns")
        self.api = TestClient(nvp_api.app)
        self.environment = patch.dict(os.environ, {"NVP_LLM_URL": self.url})
        self.environment.start()
        LocalServer.redirect = False
        LocalServer.received = None

    def tearDown(self):
        self.environment.stop()
        nvp_api.studio = self.original
        self.tmp.cleanup()

    def test_discovers_three_model_ids(self):
        result = self.api.get("/api/creative/models").json()
        self.assertEqual(result["state"], "available")
        self.assertEqual(len(result["models"]), 3)
        self.assertIn("not yet verified", result["message"])
        self.assertEqual(model_family(result["models"][0]["id"]), "Gemma 4 31B")

    def test_selected_model_routes_and_preserves_script(self):
        response = self.api.post(
            f"/api/projects/{self.project['id']}/creative-drafts/generate",
            json={"model_id": "qwen3.8-27b-Q4.gguf", "stage": "screenplay",
                  "instructions": "A tense opening"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(LocalServer.received["model"], "qwen3.8-27b-Q4.gguf")
        self.assertEqual(response.json()["status"], "proposed")
        self.assertEqual(nvp_api.studio.get_project(self.project["id"])["screenplay"], "")

    def test_unknown_model_refused(self):
        response = self.api.post(f"/api/projects/{self.project['id']}/creative-drafts/generate",
                                 json={"model_id": "unknown-cloud-writer", "stage": "logline"})
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(LocalServer.received)

    def test_direct_local_port_without_env(self):
        with patch.dict(os.environ, {"NVP_LLM_URL": ""}):
            port = self.server.server_port
            self.assertEqual(discover_models(port)["state"], "available")
            self.assertEqual(configured_endpoint(port), self.url)
            response = self.api.post(
                f"/api/projects/{self.project['id']}/creative-drafts/generate",
                json={"model_id": "qwen3.6-35b-a3b-Q4.gguf", "model_port": port, "stage": "logline"})
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(LocalServer.received["model"], "qwen3.6-35b-a3b-Q4.gguf")
        with self.assertRaises(ValueError):
            configured_endpoint(1)

    def test_redirect_refused(self):
        LocalServer.redirect = True
        self.assertEqual(discover_models()["state"], "unavailable")

    def test_no_server_configured(self):
        with patch.dict(os.environ, {"NVP_LLM_URL": ""}):
            self.assertEqual(discover_models()["state"], "not_configured")

    def test_remote_endpoint_rejected(self):
        with patch.dict(os.environ, {"NVP_LLM_URL": "https://example.com/v1/chat/completions"}):
            self.assertEqual(discover_models()["state"], "invalid_configuration")


if __name__ == "__main__":
    unittest.main()
