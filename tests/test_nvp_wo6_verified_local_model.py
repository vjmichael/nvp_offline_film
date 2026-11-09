"""WO6-07B real HTTP (mock *server*, not real GGUF) transport regressions.

The separate real-llama.cpp workflow is the ONLY real-model acceptance.
This checks identity/status/positive token proof and refused model spoofing.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import unittest

from backend.nvp_idea_pipeline import LocalModelUnavailable,LocalScriptModel
from backend.nvp_wo6_verified_local_model import (
    ProvenLocalModelWriter,FORMAT)
from tools.nvp_wo6_07b_real_gguf_smoke import checked_path


class Handler(BaseHTTPRequestHandler):
    reply=None
    requests=[]
    def log_message(self,*_):
        pass
    def do_POST(self):
        if self.path!="/v1/chat/completions":
            return self.send_error(404)
        raw=self.rfile.read(int(self.headers["Content-Length"]))
        Handler.requests.append(json.loads(raw))
        response=Handler.reply
        if response=="redirect":
            self.send_response(302)
            self.send_header("Location","https://example.com/steal")
            self.end_headers()
            return
        body=json.dumps(response).encode("utf8")
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def real_like_reply():
    return {
        "model":"local-tested-gguf",
        "choices":[{
            "index":0,"finish_reason":"stop",
            "message":{"role":"assistant","content":
                "Move the camera closer to the original actor, then review."},
        }],
        "usage":{"prompt_tokens":186,"completion_tokens":19,"total_tokens":205},
    }


class RealLoopbackProviderReceiptContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
    def setUp(self):
        Handler.reply=real_like_reply()
        Handler.requests=[]
        provider=LocalScriptModel(
            endpoint=f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions",
            model_name="local-tested-gguf")
        self.writer=ProvenLocalModelWriter(provider)

    def test_real_loopback_post_requires_identical_model_and_positive_tokens(self):
        result=self.writer.complete(
            "Review exactly one film shot","The original actor is walking.")
        self.assertIn("Move the camera",result)
        self.assertEqual(len(Handler.requests),1)
        self.assertEqual(Handler.requests[0]["model"],"local-tested-gguf")
        self.assertEqual(Handler.requests[0]["stream"],False)
        self.assertEqual(self.writer.completion_receipt["format"],FORMAT)
        self.assertEqual(
            self.writer.completion_receipt["provider_reported_completion_tokens"],19)
        self.assertTrue(
            self.writer.completion_receipt["provider_self_report_not_attestation"])
        self.assertFalse(
            self.writer.completion_receipt["model_weights_sha256_verified"])
        self.assertFalse(self.writer.completion_receipt["native_worker_authorized"])

    def test_host_selected_original_world_schema_is_delivered_to_real_loopback_http(self):
        schema={"type":"object","properties":{"params":{"type":"object"}},
                "required":["params"],"additionalProperties":False}
        Handler.reply={**real_like_reply(),
            "choices":[{"finish_reason":"stop",
                "message":{"content":'{"params":{}}'}}]}
        generated=self.writer.complete_world_candidate(
            "Return only JSON","Use approved original source buildings",schema)
        self.assertEqual(generated,'{"params":{}}')
        self.assertEqual(len(Handler.requests),1)
        self.assertEqual(Handler.requests[0]["response_format"],{
            "type":"json_schema",
            "json_schema":{"name":"nvp_original_world_candidate",
                           "strict":True,"schema":schema}})
        self.assertFalse(self.writer.completion_receipt[
            "model_weights_sha256_verified"])
        self.assertFalse(self.writer.completion_receipt["native_worker_authorized"])
        with self.assertRaises(ValueError):
            self.writer.complete_world_candidate(
                "System","User",{"huge":"x"*16000})

    def test_host_scoped_native_camera_json_schema_transport_never_grants_authority(self):
        schema={
            "type":"object","additionalProperties":False,
            "properties":{"technique":{"type":"string","enum":["dolly"]},
                          "nodes":{"type":"array","items":{
                              "type":"object"}}},
            "required":["technique","nodes"]}
        Handler.reply={**real_like_reply(),
            "choices":[{"finish_reason":"stop",
                "message":{"content":'{"technique":"dolly","nodes":[]}'}}]}
        text=self.writer.complete_camera_candidate(
            "Return strict native film camera JSON",
            "Source approved original actor, no OS approval",schema)
        self.assertEqual(text,'{"technique":"dolly","nodes":[]}')
        self.assertEqual(Handler.requests[-1]["response_format"],{
            "type":"json_schema","json_schema":{
                "name":"nvp_original_camera_rail",
                "strict":True,"schema":schema}})
        self.assertFalse(self.writer.completion_receipt[
            "native_worker_authorized"])
        self.assertFalse(self.writer.completion_receipt[
            "model_weights_sha256_verified"])
        with self.assertRaises(ValueError):
            self.writer.complete_camera_candidate(
                "System","User",{"huge":"y"*12000})

    def test_reject_spoofed_model_missing_usage_truncation_redirect_and_replay(self):
        variants=[
            dict(model="another-instance"),
            dict(usage={}),
            dict(choices=[{
                "finish_reason":"length",
                "message":{"content":"An incomplete response"},
            }]),
            dict(choices=[{"finish_reason":"stop",
                          "message":{"content":""}}]),
        ]
        for patch in variants:
            with self.subTest(patch=str(patch)):
                Handler.reply={**real_like_reply(),**patch}
                with self.assertRaises(LocalModelUnavailable):
                    self.writer.complete("Director role","Original actor")
                self.assertIsNone(self.writer.completion_receipt)
        Handler.reply="redirect"
        with self.assertRaises(LocalModelUnavailable):
            self.writer.complete("Director role","Original actor")
        self.assertIsNone(self.writer.completion_receipt)

    def test_deceptive_loopback_looking_urls_and_remote_host_refused(self):
        urls=[
            "http://127.0.0.1:8000@evil.example/v1/chat/completions",
            "http://127.0.0.1:8000/v1/chat/completions?redirect=1",
            "http://127.0.0.1:8000/api/execute",
            "https://127.0.0.1:8000/v1/chat/completions",
            "http://evil.example:8000/v1/chat/completions",
        ]
        for url in urls:
            with self.subTest(url=url),self.assertRaises(PermissionError):
                ProvenLocalModelWriter(
                    LocalScriptModel(endpoint=url,model_name="local-tested-gguf"))

    def test_acceptance_requires_real_gguf_and_explicit_local_consent(self):
        import tempfile
        from pathlib import Path
        from tools.nvp_wo6_07b_real_gguf_smoke import run_real_gguf_acceptance
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            invalid=root/"not_a_gguf.gguf"
            invalid.write_bytes(b"BAD!"+b"x"*(1024*1024))
            with self.assertRaises(PermissionError):
                run_real_gguf_acceptance(
                    model_path=str(invalid),server_path=str(invalid),
                    consent="")
            with self.assertRaises(RuntimeError):
                checked_path(invalid,model=True)


if __name__=="__main__":
    unittest.main()
