"""G03: genuine loopback Uvicorn cannot assume sys.stdout in --windowed EXE."""
import json
import sys
import unittest
import urllib.request
from unittest.mock import patch

from fastapi import FastAPI
from tools.nvp_desktop_alpha import serve


class InstalledWindowedServer(unittest.TestCase):
    def test_uvicorn_server_opens_with_none_stdout_stderr(self):
        app=FastAPI()
        @app.get("/health")
        def health():
            return {"state":"ready"}
        # Actually construct and start Uvicorn with both std streams
        # absent, as with the Windows --windowed PyInstaller executable.
        with patch.object(sys,"stdout",None),patch.object(sys,"stderr",None):
            server,worker,port,socket=serve(app)
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health",timeout=8) as resp:
                self.assertEqual(resp.status,200)
                self.assertEqual(json.load(resp),{"state":"ready"})
        finally:
            server.should_exit=True
            worker.join(timeout=12)
            socket.close()
            self.assertFalse(worker.is_alive())


if __name__=="__main__":
    unittest.main()
