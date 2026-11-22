"""Actual SQLite and lease tests; synthetic original Job receipt only on portable lanes."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.nvp_approved_tasks import ApprovedTaskBindings
from backend.nvp_film_index import FilmIndex
from backend.nvp_resource_guard import AdmissionRequest, ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_wo6_recovery import FORMAT, RECEIPT, RetakeRecovery, _digest
from backend.nvp_worker_host_lease import WorkerHostLease


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.index = FilmIndex(Studio(self.root / 'film.sqlite'))
        self.pid = self.index.studio.create_project('Movie', 'Idea')['id']
        self.ledger = TaskLedger(self.root / 'runtime', sampler=lambda: ResourceSnapshot(1, 32768, 24000, 0, ()))
        self.owner = 'wo6take_' + self.pid
        self.bindings = ApprovedTaskBindings(self.ledger, approval_check=lambda *_: True)
        self.job = 'nvpjob_' + '1'*32
        self.journals = self.root / 'jobs'; self.journals.mkdir()
        self.patch = patch('backend.nvp_w1g_release_gate.release_process_journal_root', return_value=self.journals)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.counter = 0

    def make_job(self, **changes):
        row = dict(format='nvp.w1g.original_windows_job_journal.v1', job_id=self.job,
                   command_sha256='b'*64, state='TREE_REAPED_VERIFIED',
                   process_tree_custody_verified=True, worker_exit_verified=True)
        row.update(changes)
        (self.journals / (self.job+'.json')).write_text(json.dumps(row), encoding='utf8')

    def setup_task(self, recovery, phase='PREPARED', original_sha=None):
        self.counter += 1
        task = 'wo6take_' + str(self.counter)
        scope = dict(project_id=self.pid, new_take_id='NewTake'+str(self.counter),
                     scope_sha256='a'*64, plan_id='Plan', plan_document_sha256='c'*64,
                     original_take_id='Original', original_take_sha256=original_sha or 'd'*64,
                     scene_sha256='e'*64, timeline_sha256='f'*64)
        execution = dict(command_sha256='b'*64, worker_sha256='1'*64, input_sha256='2'*64)
        spec = dict(format=FORMAT, kind='compositing', project_id=self.pid,
                    owner_key=self.owner, task_id=task, native_approval_id='Grant',
                    scope=scope, execution=execution, ram_mb=4096, expires_at=0)
        self.bindings.enqueue(AdmissionRequest(task,'compositing','Take',4096),
                              owner_key=self.owner,lane='standard',approval_id='Grant',document=spec)
        if phase=='QUEUED': return task,spec
        self.assertTrue(self.bindings.claim_next(owner_key=self.owner,expected_task_id=task)['admitted'])
        if phase=='LEGACY': return task,spec
        recovery.prepare(task,spec)
        if phase=='PREPARED': return task,spec
        recovery.launch_intent(task)
        if phase=='LAUNCH_INTENT': return task,spec
        recovery.running(task,self.job)
        if phase=='RUNNING': return task,spec
        self.make_job(); recovery.custody_closed(task,self.job)
        return task,spec

    @contextmanager
    def recovery(self):
        with WorkerHostLease(self.ledger.root) as lease:
            yield RetakeRecovery(self.ledger,lease)

    def test_never_started_queue_cancel_and_prepared_release(self):
        with self.recovery() as r:
            first,_=self.setup_task(r,'QUEUED')
            self.assertEqual(r.reconcile(self.index,self.pid),[(first,'CANCELLED')])
            second,_=self.setup_task(r,'PREPARED')
            self.assertEqual(r.reconcile(self.index,self.pid),[(second,'INTERRUPTED')])
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)

    def test_durable_cancel_before_launch_fences_and_releases(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'PREPARED')
            self.assertTrue(r.request_cancel(task))
            self.assertTrue(r.cancelled(task))
            with self.assertRaises(PermissionError):r.launch_intent(task)
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'CANCELLED')])
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)

    def test_durable_cancel_running_retains_until_cleanup(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'RUNNING')
            self.assertTrue(r.request_cancel(task))
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])
            self.make_job();r.custody_closed(task,self.job)
            with self.assertRaises(PermissionError):r.publication_pending(task,{'receipt':True})
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'CANCELLED')])
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)

    def test_publication_fence_rejects_late_cancel(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'CUSTODY_CLOSED')
            r.publication_pending(task,{'receipt':True})
            self.assertFalse(r.request_cancel(task))
            self.assertFalse(r.cancelled(task))
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'INTERRUPTED')])

    def test_missing_legacy_lifecycle_holds(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'LEGACY')
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],4096)

    def test_launch_intent_and_running_hold_even_with_tree_receipt(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'LAUNCH_INTENT')
            self.make_job()
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])
            r.running(task,self.job)
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],4096)

    def test_verified_closed_with_no_publication_releases(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'CUSTODY_CLOSED')
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'INTERRUPTED')])
            self.assertEqual(r.reconcile(self.index,self.pid),[])
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)

    def test_tampered_job_receipt_holds(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'CUSTODY_CLOSED')
            for change in (dict(command_sha256='3'*64),dict(state='RUNNING'),dict(worker_exit_verified=False)):
                self.make_job(**change)
                self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])
                self.assertEqual(self.ledger.get_task(task)['state'],'ACTIVE')

    def test_recovery_requires_live_kernel_lease(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'PREPARED')
            with self.assertRaises(RuntimeError):
                with WorkerHostLease(self.ledger.root): pass
        with self.assertRaises(PermissionError):r.reconcile(self.index,self.pid)
        self.assertEqual(self.ledger.get_task(task)['state'],'ACTIVE')

    def test_durable_spec_tamper_holds(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'PREPARED')
            with self.ledger._db() as db:
                db.execute('UPDATE authorized_task_specs SET spec_sha256=? WHERE task_id=?', ('9'*64,task))
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])

    def test_contradictory_published_take_holds(self):
        with self.recovery() as r:
            task,spec=self.setup_task(r,'CUSTODY_CLOSED')
            self.index.register_revision(self.pid,spec['scope']['new_take_id'],'take',{'wrong':True})
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])
            r.publication_pending(task,{'wrong':True})
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])

    def test_exact_committed_take_recovery_requires_both_reopens(self):
        with self.recovery() as r:
            original=self.index.register_revision(self.pid,'Original','take',{'sample_digest_sha256':'9'*64})
            task,spec=self.setup_task(r,'CUSTODY_CLOSED',original_sha=original['document_sha256'])
            scope=spec['scope']
            # Actual SQLite original and Take; native verifier is synthetic here.
            receipt=dict(format=RECEIPT,project_id=self.pid,task_id=task,
                         spec_sha256=_digest(spec),scope_sha256=scope['scope_sha256'],
                         plan_id=scope['plan_id'],plan_document_sha256=scope['plan_document_sha256'],
                         original_take_id=scope['original_take_id'],original_take_sha256=scope['original_take_sha256'],
                         new_take_id=scope['new_take_id'],scene_sha256=scope['scene_sha256'],
                         timeline_sha256=scope['timeline_sha256'],original_process_journal_id=self.job,
                         process_tree_custody_verified=True,sample_digest_sha256='9'*64,**spec['execution'])
            r.publication_pending(task,receipt)
            row=self.index.register_revision(self.pid,scope['new_take_id'],'take',
                {'protected_retake_execution':receipt,'sample_digest_sha256':'9'*64})
            # No claim of actual OpenUSD here: exercise the durable verification
            # consumer with a deliberately synthetic verifier result.
            with patch('backend.nvp_openusd_take.OpenUSDTakeCapture') as capture:
                capture.return_value.verify_take.side_effect=[
                    {'status':'VERIFIED_FROZEN_DATA_TAKE','take_document_sha256':row['document_sha256']},
                    {'status':'VERIFIED_FROZEN_DATA_TAKE','take_document_sha256':scope['original_take_sha256']}]
                self.assertEqual(r.reconcile(self.index,self.pid),[(task,'SUCCEEDED')])
                self.assertEqual(capture.return_value.verify_take.call_count,2)
            self.assertEqual(r.reconcile(self.index,self.pid),[])
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],0)

    def test_missing_take_blob_is_not_unused_identity(self):
        with self.recovery() as r:
            task,spec=self.setup_task(r,'CUSTODY_CLOSED')
            self.index.register_revision(self.pid,spec['scope']['new_take_id'],'take',{'wrong':True})
            with patch.object(self.index,'get_blob',side_effect=KeyError('Blob missing')):
                self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])
        self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],4096)

    def test_missing_after_take_verified_holds(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'CUSTODY_CLOSED')
            r.publication_pending(task,{'test':True}); r.take_verified(task,{'test':True})
            self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])

    def test_real_host_death_retains_uncertain_native_reservation(self):
        with self.recovery() as r:
            task,_=self.setup_task(r,'PREPARED')
        ready=self.root/'ready'
        code=('import time;from pathlib import Path;'
              'from backend.nvp_resource_ledger import TaskLedger;'
              'from backend.nvp_worker_host_lease import WorkerHostLease;'
              'from backend.nvp_wo6_recovery import RetakeRecovery;'
              f'l=TaskLedger({str(self.ledger.root)!r});'
              'lease=WorkerHostLease(l.root);lease.__enter__();'
              f'RetakeRecovery(l,lease).launch_intent({task!r});'
              f'Path({str(ready)!r}).write_text("ready");time.sleep(60)')
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        child=subprocess.Popen([sys.executable,'-c',code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            until=time.monotonic()+15
            while not ready.exists() and child.poll() is None and time.monotonic()<until:time.sleep(.02)
            self.assertTrue(ready.exists(),'Real owner did not reach durable launch intent')
            with self.assertRaises(RuntimeError):
                with self.recovery():pass
            child.kill();child.communicate(timeout=15)
            self.assertNotEqual(child.returncode,0)
            self.ledger=TaskLedger(self.ledger.root,sampler=self.ledger.sampler)
            with self.recovery() as r:
                self.assertEqual(r.reconcile(self.index,self.pid),[(task,'HELD_UNVERIFIED')])
            self.assertEqual(self.ledger.snapshot()['reservations']['ram_mb'],4096)
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=15)
            child.stdout.close();child.stderr.close()

if __name__=='__main__': unittest.main()
