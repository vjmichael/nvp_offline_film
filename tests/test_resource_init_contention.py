"""NVP B4: real multi-process SQLite WAL/schema first-open race regression."""
from __future__ import annotations

import multiprocessing as mp
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_resource_guard import AdmissionRequest,ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


def sample():
    return ResourceSnapshot(1,32768,18000,0,())


def initializer_worker(root,index,barrier,result):
    try:
        barrier.wait(timeout=20)
        ledger=TaskLedger(root,sampler=sample)
        result.put(("ok",index,ledger.snapshot()["reservations"]["ram_mb"]))
    except BaseException as exc:
        result.put(("error",index,type(exc).__name__+": "+str(exc)))


class ConcurrentSchemaInitializationTests(unittest.TestCase):
    def test_six_simultaneous_new_profile_connections_do_not_lock(self):
        with TemporaryDirectory() as root:
            ctx=mp.get_context("spawn")
            barrier=ctx.Barrier(6)
            results=ctx.Queue()
            procs=[ctx.Process(target=initializer_worker,
                               args=(root,i,barrier,results)) for i in range(6)]
            for child in procs:child.start()
            try:
                observed=[results.get(timeout=30) for _ in range(6)]
                for child in procs:child.join(timeout=20)
                self.assertTrue(all(c.exitcode==0 for c in procs))
                self.assertTrue(all(entry[0]=="ok" for entry in observed),observed)
                ledger=TaskLedger(root,sampler=sample)
                with ledger._db() as db:
                    names={row[0] for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'")}
                    self.assertTrue({"tasks","task_events","task_schedule"}.issubset(names))
                    self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0],"wal")
            finally:
                for child in procs:
                    if child.is_alive():
                        child.kill()
                        child.join(timeout=5)
                results.close()
                results.join_thread()

    def test_schema_reopen_preserves_active_reservations(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            admitted=ledger.admit(AdmissionRequest(
                "before_restart","ai_loading","Model admitted",4096))
            self.assertTrue(admitted["admitted"])
            reopened=TaskLedger(root,sampler=sample)
            self.assertEqual(reopened.get_task("before_restart")["state"],"ACTIVE")
            self.assertEqual(reopened.snapshot()["reservations"]["ram_mb"],4096)
            # Only a verified real worker cleanup may release this, not init.


if __name__=="__main__":
    unittest.main()
