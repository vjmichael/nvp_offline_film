"""G03 installed-API contract: project locks deny reads, writes and replay.

These tests prove FastAPI access controls, NOT full filesystem encryption or
a physically installed user's OS-key protection.
"""
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from backend import nvp_api
from backend.nvp_studio import Studio
from backend.nvp_project_access import ProjectAccess

HEADERS = {"x-nvp-director": "1"}
SECRET = "A distinctly long movie passphrase 2026"
SCRIPT = "EXT. VALLEY - MORNING\n\nFog rises."


class ProjectAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = nvp_api.studio
        nvp_api.studio = Studio(Path(self.temp.name)/"film.sqlite3")
        self.client = TestClient(nvp_api.app)
        self.a = self.client.post("/api/projects", json={
            "title":"Valley", "idea":"A quiet nature documentary"}).json()
        self.b = self.client.post("/api/projects", json={
            "title":"Coast", "idea":"A different project"}).json()
        self.base = "/api/projects/" + self.a["id"]

    def tearDown(self):
        nvp_api.studio = self.original
        self.temp.cleanup()

    def protect(self):
        res=self.client.post(self.base + "/protect",
            json={"passphrase":SECRET},headers=HEADERS)
        self.assertEqual(res.status_code,200,res.text)

    def unlock(self):
        res=self.client.post(self.base + "/unlock",
            json={"passphrase":SECRET},headers=HEADERS)
        self.assertEqual(res.status_code,200,res.text)
        self.assertIn("httponly",res.headers["set-cookie"].lower())
        self.assertIn("samesite=strict",res.headers["set-cookie"].lower())
        return res

    def test_lock_persists_and_blocks_every_existing_project_route(self):
        self.protect()
        listing=self.client.get("/api/projects").json()
        row=next(x for x in listing if x["id"]==self.a["id"])
        self.assertTrue(row["locked"])
        self.assertFalse(row["unlocked"])
        self.assertNotIn("idea",row)
        self.assertNotIn("documentary",str(row))
        self.assertEqual(self.client.get(self.base).status_code,423)
        self.assertEqual(self.client.get(self.base+"/screenplay-history").status_code,423)
        self.assertEqual(self.client.get(self.base+"/production/assets").status_code,423)
        self.assertEqual(self.client.get(self.base+"/story-bible").status_code,423)
        self.assertEqual(self.client.get(self.base+"/film/camera-scenes").status_code,423)
        self.assertEqual(self.client.put(self.base+"/screenplay",json={
            "screenplay":SCRIPT,"expected_revision":0}).status_code,423)
        self.assertEqual(self.client.post(self.base+"/creative-drafts",
            json={"stage":"logline","content":"Untrusted write"}).status_code,423)
        self.assertEqual(self.client.get("/api/projects/"+self.b["id"]).status_code,200)

    def test_wrong_password_header_and_cross_project_token_denied(self):
        self.protect()
        self.assertEqual(self.client.post(self.base+"/unlock",json={
            "passphrase":SECRET}).status_code,403)
        self.assertEqual(self.client.post(self.base+"/unlock",json={
            "passphrase":"An incorrect long password"},headers=HEADERS).status_code,403)
        self.unlock()
        self.assertEqual(self.client.get(self.base).status_code,200)
        self.assertEqual(self.client.put(self.base+"/screenplay",json={
            "screenplay":SCRIPT,"expected_revision":0}).status_code,403)
        result=self.client.put(self.base+"/screenplay",json={
            "screenplay":SCRIPT,"expected_revision":0},headers=HEADERS)
        self.assertEqual(result.status_code,200,result.text)
        # Lock project B while the A token is held. A token cannot unlock B.
        self.assertEqual(self.client.post("/api/projects/"+self.b["id"]+"/protect",
            json={"passphrase":"Another long distinct passphrase"},headers=HEADERS).status_code,200)
        self.assertEqual(self.client.get("/api/projects/"+self.b["id"]).status_code,423)

    def test_relock_invalidates_cookie_and_reopen_requires_password(self):
        self.protect()
        self.unlock()
        self.assertEqual(self.client.get(self.base).status_code,200)
        self.assertEqual(self.client.post(self.base+"/lock",headers=HEADERS).status_code,200)
        self.assertEqual(self.client.get(self.base).status_code,423)
        self.unlock()
        self.assertEqual(self.client.get(self.base).status_code,200)
        # New server process shares DB but not volatile unlock sessions.
        fresh=ProjectAccess(nvp_api.studio.db_path)
        token=self.client.cookies.get("nvp_film_access")
        self.assertFalse(fresh.permitted(self.a["id"],token))

    def test_scrypt_verifier_not_plaintext_and_restart_preserves_lock(self):
        self.protect()
        db=nvp_api.studio._connection()
        with db as conn:
            row=conn.execute("SELECT salt,verifier FROM project_access_locks WHERE project_id=?",
                             (self.a["id"],)).fetchone()
        self.assertEqual(len(row["salt"]),16)
        self.assertEqual(len(row["verifier"]),32)
        self.assertNotIn(SECRET.encode(),bytes(row["verifier"]))
        fresh=ProjectAccess(nvp_api.studio.db_path)
        self.assertTrue(fresh.protected(self.a["id"]))

    def test_idle_expiry_and_repeated_wrong_password_delay(self):
        now=[1000.0]
        x=ProjectAccess(nvp_api.studio.db_path,clock=lambda:now[0],
                        wall_clock=lambda:now[0])
        x.protect(self.a["id"],SECRET)
        for _ in range(5):
            with self.assertRaises(PermissionError):
                x.unlock(self.a["id"],"Incorrect passphrase forever")
        with self.assertRaises(PermissionError):
            x.unlock(self.a["id"],SECRET)
        now[0]+=31.0
        tok=x.unlock(self.a["id"],SECRET)
        self.assertTrue(x.permitted(self.a["id"],tok))
        now[0]+=1201.0
        self.assertFalse(x.permitted(self.a["id"],tok))

    def test_failed_attempts_stay_blocked_across_restart(self):
        now=[2000.0]
        def instance():
            return ProjectAccess(nvp_api.studio.db_path,
                clock=lambda:now[0],wall_clock=lambda:now[0])
        original=instance()
        original.protect(self.a["id"],SECRET)
        for _ in range(4):
            with self.assertRaises(PermissionError):
                original.unlock(self.a["id"],"A wrong long test passphrase")
        restarted=instance()
        with self.assertRaises(PermissionError):
            restarted.unlock(self.a["id"],"A wrong long test passphrase")
        restarted_again=instance()
        with self.assertRaisesRegex(PermissionError,"Too many attempts"):
            restarted_again.unlock(self.a["id"],SECRET)
        now[0]+=31.0
        self.assertTrue(restarted_again.unlock(self.a["id"],SECRET))

    def test_every_registered_project_route_is_locked(self):
        import re
        from fastapi.routing import APIRoute
        self.protect()
        checked=0
        for route in nvp_api.app.routes:
            if not isinstance(route,APIRoute):
                continue
            if not route.path.startswith("/api/projects/{project_id}"):
                continue
            if route.path.endswith(("/unlock","/protect")):
                continue
            uri=route.path.replace("{project_id}",self.a["id"])
            uri=re.sub(r"\{[^{}]+\}","fixture",uri)
            for method in sorted(route.methods & {"GET","POST","PUT","PATCH","DELETE"}):
                result=self.client.request(method,uri,json={},headers=HEADERS)
                self.assertEqual(result.status_code,423,
                    f"{method} {route.path} bypassed project lock: {result.text[:120]}")
                checked+=1
        self.assertGreater(checked,90)

    def test_global_activity_does_not_leak_locked_project_titles(self):
        original=nvp_api.resource_activity
        class SecretLedger:
            def snapshot(self):
                return {"format":"nvp.system.resource_activity.v1",
                        "tasks":[{"title":"PrivateMovieSecretStoryTitle"}]}
        try:
            nvp_api.resource_activity=SecretLedger()
            self.protect()
            response=self.client.get("/api/system/activity")
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json()["redacted"])
            self.assertEqual(response.json()["tasks"],[])
            self.assertNotIn("PrivateMovieSecretStoryTitle",response.text)
            self.assertIsNone(response.json()["sample"])
        finally:
            nvp_api.resource_activity=original

    def test_unencrypted_project_files_are_truthfully_disclosed(self):
        flags=self.client.get("/api/status").json()["capabilities"]
        import sys
        self.assertEqual(flags["project_file_encryption"],
                         "new_windows_movies_only" if sys.platform=="win32"
                         else "not_available")
        self.protect()
        # Demonstrate the known release blocker rather than asserting
        # that an HTTP lock encrypted original SQLite data.
        with nvp_api.studio._connection() as db:
            idea=db.execute("SELECT idea FROM projects WHERE id=?",
                            (self.a["id"],)).fetchone()[0]
        self.assertEqual(idea,"A quiet nature documentary")

    def test_another_nvp_process_revokes_old_unlock_grants(self):
        first=ProjectAccess(nvp_api.studio.db_path)
        second=ProjectAccess(nvp_api.studio.db_path)
        first.protect(self.a["id"],SECRET)
        one=first.unlock(self.a["id"],SECRET)
        self.assertTrue(first.permitted(self.a["id"],one))
        # The second native host unlocks; old grants cannot survive even if
        # the first host process is still open with its in-memory token.
        two=second.unlock(self.a["id"],SECRET)
        self.assertFalse(first.permitted(self.a["id"],one))
        self.assertTrue(second.permitted(self.a["id"],two))
        second.lock(self.a["id"],two)
        self.assertFalse(second.permitted(self.a["id"],two))

    def test_unprotected_existing_user_journey_unchanged(self):
        self.assertEqual(self.client.get(self.base).status_code,200)
        self.assertEqual(self.client.put(self.base+"/screenplay",json={
            "screenplay":SCRIPT,"expected_revision":0}).status_code,200)
        listing=self.client.get("/api/projects").json()
        self.assertFalse(next(x for x in listing if x["id"]==self.a["id"])["locked"])


if __name__=="__main__":
    unittest.main()
