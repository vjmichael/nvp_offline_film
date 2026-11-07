"""DA-06: legacy execution must be denied before any handler is called."""
import asyncio
import json
import unittest

from backend.nvp_legacy_quarantine import LegacyMediaQuarantine,quarantined


class QuarantineTests(unittest.TestCase):
    def test_retired_routes_cannot_run_creators_or_external_code(self):
        base="/api/projects/Film001/production/scenes/Scene001"
        for method,path in (
            ("POST",base+"/sequence/shots"),
            ("POST",base+"/rig-motion/attach"),
            ("GET",base+"/sequence/package"),
            ("GET",base+"/blender-script"),
            ("GET",base+"/skinning/blender-script"),
            ("GET",base+"/world/blender-script"),
            ("POST","/api/projects/Film001/color-grading/grades"),
            ("GET","/api/projects/Film001/color-grading/sources/x/preview"),
        ):
            with self.subTest(method=method,path=path):
                self.assertTrue(quarantined(path,method))
        self.assertFalse(quarantined(base+"/sequence/history","GET"))
        self.assertFalse(quarantined(base+"/rig-motion/history","GET"))
        self.assertFalse(quarantined("/api/projects/Film001/film/native-color/Grade001","POST"))
        self.assertFalse(quarantined("/api/projects/Film001/film/native-time-shots/Timeline001","GET"))
        self.assertFalse(quarantined("/api/projects/Film001","GET"))

    def test_asgi_denial_happens_without_dispatching_legacy_work(self):
        calls=[]
        async def application(scope,receive,send):
            calls.append(scope)
            await send({"type":"http.response.start","status":200,"headers":[]})
            await send({"type":"http.response.body","body":b"ok"})
        app=LegacyMediaQuarantine(application)
        async def dispatch(method,path):
            messages=[]
            async def send(message):messages.append(message)
            async def receive():return {"type":"http.request","body":b""}
            await app({"type":"http","path":path,"method":method},receive,send)
            return messages
        gone=asyncio.run(dispatch("POST",
            "/api/projects/Film001/production/scenes/S/sequence/shots"))
        self.assertEqual(gone[0]["status"],410)
        self.assertEqual(json.loads(gone[1]["body"])["legacy_executor_started"],False)
        self.assertEqual(calls,[])
        ok=asyncio.run(dispatch("GET",
            "/api/projects/Film001/film/native-time-shots/New"))
        self.assertEqual(ok[0]["status"],200)
        self.assertEqual(len(calls),1)


if __name__=="__main__":
    unittest.main()
