"""WO6-B foundation: exact notice and sealed owner admission on real SQLite."""
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.nvp_resource_guard import AdmissionRequest, ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_approved_tasks import ApprovedTaskBindings


class ExactDispatch(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.ledger = TaskLedger(temp.name, sampler=lambda: ResourceSnapshot(1,32768,24000,0,()))
        self.approved = set()
        self.bound = ApprovedTaskBindings(self.ledger, approval_check=lambda a,d,s: (a, s['task_id']) in self.approved)

    def queue(self, name, lane='standard', owner='creator_take'):
        approval = 'grant_'+name
        self.approved.add((approval,name))
        self.bound.enqueue(AdmissionRequest(name,'compositing',name,1024), owner_key=owner,
                           lane=lane,approval_id=approval,document={'task_id':name,'kind':'compositing'})

    def test_out_of_order_notice_does_not_start_different_task(self):
        self.queue('a'); self.queue('b','interactive')
        result = self.bound.claim_next(owner_key='creator_take',expected_task_id='a')
        self.assertEqual(result['state'],'NOT_CLAIMED')
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)
        self.assertTrue(self.bound.claim_next(owner_key='creator_take',expected_task_id='b')['admitted'])
        self.assertEqual(self.ledger.get_task('a')['state'],'QUEUED')

    def test_cancelled_notice_never_claims_next(self):
        self.queue('a'); self.queue('b')
        self.ledger.cancel_queued('a',owner_key='creator_take')
        self.assertFalse(self.bound.claim_next(owner_key='creator_take',expected_task_id='a')['admitted'])
        self.assertEqual(self.ledger.get_task('b')['state'],'QUEUED')
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)

    def test_priority_change_between_preflight_and_claim_is_fenced(self):
        self.queue('a')
        original = self.ledger.claim_next
        def changed(**kwargs):
            self.queue('b','interactive')
            return original(**kwargs)
        with patch.object(self.ledger,'claim_next',side_effect=changed):
            result = self.bound.claim_next(owner_key='creator_take')
        self.assertEqual(result['task_id'],'a')
        self.assertEqual(result['state'],'NOT_CLAIMED')
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)

    def test_stale_owner_and_revoked_grant_do_not_reserve(self):
        self.queue('a')
        self.assertIsNone(self.bound.claim_next(owner_key='another',expected_task_id='a'))
        self.approved.clear()
        with self.assertRaises(PermissionError):
            self.bound.claim_next(owner_key='creator_take',expected_task_id='a')
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)

    def test_bad_notice_refused_even_on_empty_queue(self):
        for method in (self.ledger.claim_next,self.bound.claim_next):
            for notice in ('../a',True,'', 'a'*81):
                with self.subTest(notice=notice),self.assertRaises(ValueError):
                    method(owner_key='creator_take',expected_task_id=notice)

    def test_exact_ledger_gate_cannot_bypass_priority(self):
        self.queue('a'); self.queue('b','interactive')
        result = self.ledger.claim_next(owner_key='creator_take',expected_task_id='a')
        self.assertEqual(result['state'],'NOT_CLAIMED')
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)


if __name__ == '__main__':
    unittest.main()
