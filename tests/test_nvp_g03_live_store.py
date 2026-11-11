"""G03-E1 exact native encrypted *live* Windows film storage acceptance.

Real Windows DPAPI and AES-GCM are mandatory; non-Windows tests assert
unavailability instead of substituting fake encryption. No fake cryptographic
engine may turn a source-only test into a physical Windows acceptance claim.
"""
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_g03_live_store import LiveFilmStore, LiveFilmError
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_studio import Studio
from fastapi.testclient import TestClient
from backend import nvp_api

PID="ab"*16
PASSPHRASE="G03-encrypted-live-movie-test-passphrase-2026"
SOURCE=b"#usda 1.0\n\ndef Xform \"DIRECTOR_ORIGINAL_SOURCE_MARKER\" {}\n"
SCREENPLAY="EXT. SECRET VALLEY - NIGHT\n\nThe moon rises over the water."
UPDATED="INT. SECRET KITCHEN - EVENING\n\nA clock chimes."


@unittest.skipUnless(sys.platform=="win32", "Requires actual Windows DPAPI, not a mock")
class LiveFilmStoreWindows(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="nvp-g03-live-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"secured"
        self.grants=set()
        self.store=LiveFilmStore(self.root,
                                 grant_checker=lambda pid,t:(pid,t) in self.grants)
        self.store.create(PID,"Secret Film","PRIVATE IDEA MARKER",SCREENPLAY,PASSPHRASE)
        self.token="host-authorized-token-"+("x"*32)
        self.grants.add((PID,self.token))
        self.store.authorize(PID,PASSPHRASE,self.token)

    def leaked(self):
        all_bytes=b"".join(f.read_bytes() for f in self.root.rglob("*") if f.is_file())
        for forbidden in (b"PRIVATE IDEA MARKER",b"SECRET VALLEY",
                          b"DIRECTOR_ORIGINAL_SOURCE_MARKER"):
            self.assertNotIn(forbidden,all_bytes)
        self.assertFalse(list(self.root.rglob("*.sqlite3")))
        self.assertFalse(list(self.root.rglob("*.db")))
        self.assertFalse(list(self.root.rglob("*-wal")))
        self.assertFalse(list(self.root.rglob("*-shm")))
        self.assertFalse(list(self.root.rglob("*.usda")))
        self.assertFalse(list(self.root.rglob("*.pcm")))

    def test_encrypted_live_sqlite_revisions_and_real_restart(self):
        self.assertIn("SECRET VALLEY",self.store.read(PID,self.token)["screenplay"])
        changed=self.store.save_screenplay(PID,self.token,UPDATED,0)
        self.assertEqual(changed["revision"],1)
        self.assertIn("SECRET KITCHEN",changed["screenplay"])
        self.leaked()
        # Simulated native host exit: the new process must re-prove the
        # Windows account and passphrase; no key/session is stored in SQLite.
        fresh=LiveFilmStore(self.root,grant_checker=lambda pid,t:(pid,t) in self.grants)
        with self.assertRaises(LiveFilmError):
            fresh.read(PID,self.token)
        with self.assertRaises(VaultError):
            fresh.authorize(PID,"Wrong passphrase for this movie",self.token)
        fresh.authorize(PID,PASSPHRASE,self.token)
        self.assertEqual(fresh.read(PID,self.token)["screenplay"],UPDATED)
        self.assertEqual(len(fresh.recovery_candidates(PID,self.token)),2)

    def test_human_reviewed_recovery_preserves_immutable_originals(self):
        self.store.put_original(PID,self.token,"scene/source.usda",SOURCE)
        self.store.save_screenplay(PID,self.token,UPDATED,0)
        self.assertEqual(self.store.read(PID,self.token)["revision"],1)
        with self.assertRaisesRegex(LiveFilmError,"Director-approved"):
            self.store.recover_screenplay(PID,self.token,0,1)
        restored=self.store.recover_screenplay(
            PID,self.token,0,1,human_approved=True)
        self.assertEqual(restored["revision"],2)
        self.assertEqual(restored["screenplay"],SCREENPLAY)
        self.assertEqual(self.store.get_original(PID,self.token,"scene/source.usda"),
                         SOURCE)
        receipts=self.store.recovery_receipts(PID,self.token)
        self.assertEqual(len(receipts),1)
        self.assertEqual(receipts[0]["selected_commit_sequence"],0)
        self.assertEqual(receipts[0]["resulting_revision"],2)
        self.leaked()

    def test_original_data_encrypted_and_worker_authority_one_use(self):
        src=self.store.put_original(PID,self.token,"scene/original.usda",SOURCE,
                                    "model/vnd.usda")
        self.assertEqual(src["sha256"],hashlib.sha256(SOURCE).hexdigest())
        self.assertEqual(self.store.get_original(PID,self.token,"scene/original.usda"),SOURCE)
        self.leaked()
        with self.assertRaisesRegex(LiveFilmError,"Human-approved"):
            self.store.worker_grant(PID,self.token,"scene/original.usda",
                                    "read_original")
        lease=self.store.worker_grant(PID,self.token,"scene/original.usda",
                                    "read_original",human_approved=True)
        self.assertEqual(self.store.worker_execute(PID,lease,"read_original",
                                                   "scene/original.usda"),SOURCE)
        with self.assertRaisesRegex(LiveFilmError,"replayed"):
            self.store.worker_execute(PID,lease,"read_original","scene/original.usda")
        receipt=self.store.worker_grant(PID,self.token,"scene/actor.pcm",
                                       "write_original",human_approved=True)
        write=self.store.worker_execute(PID,receipt,"write_original",
                                        "scene/actor.pcm",data=b"\x01\x02\x03")
        self.assertTrue(write["encrypted"])
        self.assertEqual(self.store.get_original(PID,self.token,"scene/actor.pcm"),
                         b"\x01\x02\x03")
        receipts=self.store.worker_receipts(PID,self.token)
        self.assertEqual(len(receipts),2)
        self.assertEqual({r["operation"] for r in receipts},
                         {"read_original","write_original"})
        self.leaked()

    def test_lock_revokes_all_native_keys_and_grants(self):
        lease=self.store.worker_grant(PID,self.token,"scene/a.usda",
                                      "write_original",human_approved=True)
        self.grants.clear()
        with self.assertRaisesRegex(LiveFilmError,"permission"):
            self.store.worker_execute(PID,lease,"write_original",
                                      "scene/a.usda",data=SOURCE)
        self.assertEqual(list((self.root/PID/"assets").glob("*.nvpsealed")),[])
        with self.assertRaises(LiveFilmError):
            self.store.read(PID,self.token)

    def test_durable_head_crash_keeps_previous_sqlite_and_next_update_works(self):
        from backend import nvp_g03_live_store as module
        original=module.LiveFilmStore._publish_head
        calls=[0]
        def power_cut(folder,record):
            calls[0]+=1
            if calls[0]==1:
                raise OSError("simulated power interruption before HEAD commit")
            return original(folder,record)
        with patch.object(module.LiveFilmStore,"_publish_head",side_effect=power_cut):
            with self.assertRaisesRegex(OSError,"power interruption"):
                self.store.save_screenplay(PID,self.token,UPDATED,0)
        self.assertEqual(self.store.read(PID,self.token)["revision"],0)
        self.assertEqual(self.store.save_screenplay(PID,self.token,UPDATED,0)["revision"],1)
        self.assertGreaterEqual(len(list((self.root/PID/"revisions").glob("*.nvpsealed"))),3)
        self.leaked()

    def test_authenticated_original_rejects_tampered_ciphertext(self):
        self.store.put_original(PID,self.token,"scene/original.usda",SOURCE)
        path=next((self.root/PID/"assets").glob("*.nvpsealed"))
        data=bytearray(path.read_bytes())
        data[-1] ^= 0x01
        path.write_bytes(data)
        with self.assertRaises(VaultError):
            self.store.get_original(PID,self.token,"scene/original.usda")
        self.leaked()

    def test_two_process_writers_cannot_replace_committed_film_revision(self):
        import threading
        second=LiveFilmStore(self.root,grant_checker=lambda pid,t:(pid,t) in self.grants)
        second.authorize(PID,PASSPHRASE,self.token)
        outcomes=[]
        barrier=threading.Barrier(2)
        def commit(store,source):
            barrier.wait(timeout=5)
            try:
                result=store.save_screenplay(PID,self.token,source,0)
                outcomes.append(("ok",result["revision"]))
            except LiveFilmError as error:
                outcomes.append(("denied",str(error)))
        a=threading.Thread(target=commit,args=(self.store,UPDATED))
        b=threading.Thread(target=commit,args=(second,SCREENPLAY+"\nAnother line."))
        a.start();b.start()
        a.join(timeout=25);b.join(timeout=25)
        self.assertFalse(a.is_alive() or b.is_alive())
        self.assertEqual(sum(x[0]=="ok" for x in outcomes),1,outcomes)
        self.assertEqual(sum(x[0]=="denied" for x in outcomes),1,outcomes)
        self.assertEqual(self.store.read(PID,self.token)["revision"],1)
        self.leaked()

    def test_corrupt_head_never_silently_rolls_back_private_history(self):
        self.store.save_screenplay(PID,self.token,UPDATED,0)
        head=self.root/PID/"HEAD.json"
        raw=bytearray(head.read_bytes())
        raw[-1] ^= 0x01
        head.write_bytes(raw)
        with self.assertRaises((LiveFilmError,ValueError)):
            self.store.read(PID,self.token)

    def test_asset_after_ciphertext_before_sqlite_commit_can_resume(self):
        from backend import nvp_g03_live_store as module
        first=module.LiveFilmStore._seal_db
        def fail_after_asset(folder,pid,key,raw,seq):
            if seq>0:raise OSError("injected durable commit fault")
            return first(folder,pid,key,raw,seq)
        with patch.object(module.LiveFilmStore,"_seal_db",side_effect=fail_after_asset):
            with self.assertRaises(OSError):
                self.store.put_original(PID,self.token,"scene/source.usda",SOURCE)
        self.assertEqual(self.store.read(PID,self.token)["source_assets"],[])
        self.store.put_original(PID,self.token,"scene/source.usda",SOURCE)
        self.assertEqual(self.store.get_original(PID,self.token,"scene/source.usda"),SOURCE)
        self.leaked()


@unittest.skipUnless(sys.platform=="win32", "Requires real Windows DPAPI")
class LiveFilmAPIWindows(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="nvp-g03-live-api-")
        self.addCleanup(self.temp.cleanup)
        self.prior=nvp_api.studio
        nvp_api.studio=Studio(Path(self.temp.name)/"public-catalog.sqlite3")
        self.client=TestClient(nvp_api.app)
        self.headers={"x-nvp-director":"1"}

    def tearDown(self):
        nvp_api.studio=self.prior

    def test_new_live_movie_never_stores_script_in_shared_sqlite(self):
        r=self.client.post("/api/projects/encrypted",headers=self.headers,json={
            "title":"Protected Windows Film","idea":"PRIVATE IDEA MARKER",
            "screenplay":SCREENPLAY,"passphrase":PASSPHRASE})
        self.assertEqual(r.status_code,201,r.text)
        movie=r.json()
        self.assertTrue(movie["encrypted"])
        pid=movie["id"]
        listing=self.client.get("/api/projects").json()
        self.assertTrue(next(p for p in listing if p["id"]==pid)["encrypted"])
        with nvp_api.studio._connection() as db:
            stub=db.execute("SELECT idea,screenplay,title FROM projects WHERE id=?",
                            (pid,)).fetchone()
        self.assertEqual(stub["idea"],"")
        self.assertEqual(stub["screenplay"],"")
        public_db=nvp_api.studio.db_path.read_bytes()
        self.assertNotIn(b"PRIVATE IDEA MARKER",public_db)
        self.assertNotIn(b"SECRET VALLEY",public_db)
        self.assertEqual(self.client.get("/api/projects/"+pid).status_code,403)
        self.assertEqual(self.client.get("/api/projects/"+pid+"/story-bible").status_code,403)
        self.assertEqual(self.client.get("/api/projects/"+pid+"/live").status_code,200)
        changed=self.client.put("/api/projects/"+pid+"/live/screenplay",
                                headers=self.headers,json={
                                "screenplay":UPDATED,"expected_revision":0})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(changed.json()["revision"],1)
        self.assertEqual(self.client.post("/api/projects/"+pid+"/lock",
                                         headers=self.headers).status_code,200)
        self.assertEqual(self.client.get("/api/projects/"+pid+"/live").status_code,423)
        wrong=self.client.post("/api/projects/"+pid+"/unlock",headers=self.headers,
                               json={"passphrase":"This is a definitely wrong password"})
        self.assertEqual(wrong.status_code,403)
        unlocked=self.client.post("/api/projects/"+pid+"/unlock",headers=self.headers,
                                  json={"passphrase":PASSPHRASE})
        self.assertEqual(unlocked.status_code,200,unlocked.text)
        self.assertEqual(self.client.get("/api/projects/"+pid+"/live").json()["screenplay"],UPDATED)
        # Re-create host lock/key managers without changing underlying SQLite.
        nvp_api._film_access=None
        nvp_api._live_films=None
        self.assertEqual(self.client.get("/api/projects/"+pid+"/live").status_code,423)
        self.assertEqual(self.client.post("/api/projects/"+pid+"/unlock",
                           headers=self.headers,json={"passphrase":PASSPHRASE}).status_code,200)
        self.assertEqual(self.client.get("/api/projects/"+pid+"/live").json()["revision"],1)
        self.assertFalse(list(Path(self.temp.name).rglob("*.usda")))


class LiveFilmNonWindows(unittest.TestCase):
    @unittest.skipIf(sys.platform=="win32","Real Windows tests above")
    def test_explicit_no_fake_dpapi_and_no_plaintext_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            from backend.nvp_g03_live_store import LiveFilmStore
            store=LiveFilmStore(Path(tmp)/"vault")
            with self.assertRaisesRegex(VaultError,"Windows user-scoped DPAPI"):
                store.create(PID,"Film","PRIVATE IDEA MARKER",SCREENPLAY,PASSPHRASE)
            self.assertNotIn(b"PRIVATE IDEA MARKER",
                b"".join(p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()))


if __name__=="__main__":
    unittest.main()
