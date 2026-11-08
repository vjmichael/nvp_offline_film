"""STACK-02C3B1 trusted priority scheduling, no unsafe worker dispatch."""
import multiprocessing as mp
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_resource_guard import AdmissionRequest,ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger


def sample(available=20000):
    return ResourceSnapshot(1,32768,available,0,())


def competing_claim(root,barrier,output):
    try:
        ledger=TaskLedger(root,sampler=sample)
        barrier.wait(timeout=15)
        result=ledger.claim_next(owner_key="blender_host")
        output.put((result["task_id"],result["admitted"]) if result else (None,None))
    except BaseException as error:
        output.put(("ERROR",str(error)))


class PrioritySchedulerTests(unittest.TestCase):
    def req(self,key,ram=2048):
        return AdmissionRequest(key,"blender",key,ram)

    def test_enqueue_never_starts_or_reserves(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            ledger.enqueue(self.req("queued_one"),owner_key="blender_host")
            self.assertEqual(ledger.get_task("queued_one")["state"],"QUEUED")
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_priority_and_fifo(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            for key,lane in (("bg","background"),("normal","standard"),
                             ("fast1","interactive"),("fast2","interactive")):
                ledger.enqueue(self.req(key),owner_key="blender_host",lane=lane)
            claimed=[ledger.claim_next(owner_key="blender_host")["task_id"] for _ in range(4)]
            self.assertEqual(claimed,["fast1","fast2","normal","bg"])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],8192)
            self.assertIsNone(ledger.claim_next(owner_key="blender_host"))

    def test_head_of_line_blocked_without_lower_priority_bypass(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=lambda:sample(10000))
            ledger.enqueue(self.req("expensive",6000),owner_key="producer",lane="interactive")
            ledger.enqueue(self.req("cheap",1024),owner_key="producer",lane="background")
            result=ledger.claim_next(owner_key="producer")
            self.assertEqual(result["task_id"],"expensive")
            self.assertFalse(result["admitted"])
            self.assertEqual(ledger.get_task("cheap")["state"],"QUEUED")
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)

    def test_exact_dispatch_notice_cannot_claim_unrelated_priority_head(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            ledger.enqueue(self.req("slow"),owner_key="producer",lane="background")
            ledger.enqueue(self.req("urgent"),owner_key="producer",lane="interactive")
            rejected=ledger.claim_next(
                owner_key="producer",expected_task_id="slow")
            self.assertEqual(rejected["state"],"NOT_CLAIMED")
            self.assertFalse(rejected["admitted"])
            self.assertEqual(ledger.get_task("slow")["state"],"QUEUED")
            self.assertEqual(ledger.get_task("urgent")["state"],"QUEUED")
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            chosen=ledger.claim_next(
                owner_key="producer",expected_task_id="urgent")
            self.assertTrue(chosen["admitted"])
            self.assertEqual(chosen["task_id"],"urgent")
            next_=ledger.claim_next(
                owner_key="producer",expected_task_id="slow")
            self.assertTrue(next_["admitted"])
            self.assertEqual(next_["task_id"],"slow")

    def test_cancelled_notice_does_not_start_another_native_task(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            ledger.enqueue(self.req("cancelled"),owner_key="producer")
            ledger.enqueue(self.req("survivor"),owner_key="producer")
            ledger.cancel_queued("cancelled",owner_key="producer")
            result=ledger.claim_next(
                owner_key="producer",expected_task_id="cancelled")
            self.assertEqual(result["state"],"NOT_CLAIMED")
            self.assertFalse(result["admitted"])
            self.assertEqual(ledger.get_task("survivor")["state"],"QUEUED")
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            other=ledger.claim_next(
                owner_key="producer",expected_task_id="survivor")
            self.assertTrue(other["admitted"])
            self.assertEqual(other["task_id"],"survivor")

    def test_exact_approved_binding_notice_checks_same_head_and_policy(self):
        from backend.nvp_approved_tasks import ApprovedTaskBindings
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            seen=[]
            def policy(approval_id,digest,document):
                seen.append(document["task_id"])
                return True
            binding=ApprovedTaskBindings(ledger,approval_check=policy)
            for task,lane in (("first","interactive"),("second","standard")):
                binding.enqueue(
                    self.req(task),owner_key="producer",lane=lane,
                    approval_id="director_"+task,
                    document={"task_id":task,"kind":"blender"})
            denied=binding.claim_next(
                owner_key="producer",expected_task_id="second")
            self.assertEqual(denied["state"],"NOT_CLAIMED")
            self.assertFalse(denied["admitted"])
            self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],0)
            first=binding.claim_next(
                owner_key="producer",expected_task_id="first")
            self.assertEqual(first["task_id"],"first")
            self.assertTrue(first["admitted"])
            second=binding.claim_next(
                owner_key="producer",expected_task_id="second")
            self.assertEqual(second["task_id"],"second")
            self.assertTrue(second["admitted"])
            self.assertIn("first",seen)
            self.assertIn("second",seen)

    def test_wrong_producer_cannot_claim_or_cancel(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            ledger.enqueue(self.req("owned"),owner_key="producer")
            self.assertIsNone(ledger.claim_next(owner_key="intruder"))
            with self.assertRaises(PermissionError):
                ledger.cancel_queued("owned",owner_key="intruder")
            self.assertEqual(ledger.cancel_queued("owned",owner_key="producer")["state"],"CANCELLED")
            self.assertIsNone(ledger.claim_next(owner_key="producer"))

    def test_active_cannot_cancel_or_fabricate_cleanup(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            ledger.enqueue(self.req("running"),owner_key="producer")
            self.assertTrue(ledger.claim_next(owner_key="producer")["admitted"])
            with self.assertRaises(RuntimeError):
                ledger.cancel_queued("running",owner_key="producer")
            self.assertEqual(TaskLedger(root,sampler=sample).snapshot()["reservations"]["ram_mb"],2048)

    def test_invalid_lane_and_duplicate_id_refused(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            with self.assertRaises(ValueError):
                ledger.enqueue(self.req("one"),owner_key="not/valid")
            with self.assertRaises(ValueError):
                ledger.enqueue(self.req("one"),owner_key="producer",lane="urgent")
            ledger.enqueue(self.req("one"),owner_key="producer")
            with self.assertRaises(RuntimeError):
                ledger.enqueue(self.req("one"),owner_key="producer")

    def test_reservation_blocks_until_verified_finish(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=lambda:sample(12000))
            for key in ("a","b"):
                ledger.enqueue(self.req(key,4000),owner_key="producer")
            self.assertTrue(ledger.claim_next(owner_key="producer")["admitted"])
            self.assertFalse(ledger.claim_next(owner_key="producer")["admitted"])
            ledger.finish("a","INTERRUPTED","Verified contained OS cleanup")
            self.assertTrue(ledger.claim_next(owner_key="producer")["admitted"])

    def test_ui_reports_lane_and_no_fake_progress(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            ledger.enqueue(self.req("interactive_job"),owner_key="producer",lane="interactive")
            row=ledger.snapshot()["tasks"][0]
            self.assertEqual(row["queue_lane"],"interactive")
            self.assertIsNone(row["completed_fraction"])

    def test_two_real_processes_cannot_double_claim(self):
        with TemporaryDirectory() as root:
            ledger=TaskLedger(root,sampler=sample)
            ledger.enqueue(self.req("one"),owner_key="blender_host")
            ctx=mp.get_context("spawn")
            barrier=ctx.Barrier(2)
            output=ctx.Queue()
            processes=[ctx.Process(target=competing_claim,args=(root,barrier,output)) for _ in range(2)]
            for p in processes:p.start()
            try:
                results=[output.get(timeout=25) for _ in range(2)]
                for p in processes:
                    p.join(timeout=15)
                    self.assertEqual(p.exitcode,0)
                self.assertEqual(results.count(("one",True)),1,results)
                self.assertEqual(results.count((None,None)),1,results)
                self.assertEqual(ledger.snapshot()["reservations"]["ram_mb"],2048)
            finally:
                for p in processes:
                    if p.is_alive():p.kill();p.join(timeout=5)
                output.close();output.join_thread()


if __name__=="__main__":
    unittest.main()
