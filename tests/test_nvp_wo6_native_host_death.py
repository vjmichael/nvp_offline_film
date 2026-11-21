"""Real Windows host death at the original native Take boundaries.

Run only on a disposable Windows acceptance VM. The pre-binding death case
intentionally leaves an unresolved AppContainer profile/ACL journal; it must
not be run on a production computer or followed by release certification.
No native worker, result, launch, Job, or kernel handle is mocked.
"""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from backend.nvp_film_index import FilmIndex
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_studio import Studio
from backend.nvp_worker_host_lease import WorkerHostLease
from backend.nvp_wo6_recovery import RetakeRecovery


def child_main(root, args, mode, marker):
    from backend import nvp_wo6_native_take_action as action
    index = FilmIndex(Studio(root / 'film.sqlite'))
    ledger = TaskLedger(root / 'runtime', sampler=lambda: ResourceSnapshot(1,32768,24000,0,()))
    def stop_here(evidence):
        temp = marker.with_suffix('.tmp')
        with temp.open('x',encoding='utf8') as f:
            json.dump(evidence,f); f.flush(); os.fsync(f.fileno())
        os.replace(temp,marker)
        time.sleep(120)
        raise RuntimeError('Parent failed to terminate crash fixture')
    if mode == 'before_binding':
        original = action.launch_contained
        def launch(*a,**kw):
            proc = original(*a,**kw)
            journal = proc._worker._original_journal
            if proc.poll() is not None or journal._record['state'] != 'RUNNING':
                raise RuntimeError('Original native Job not alive at crash boundary')
            stop_here({'worker_pid': journal._record['pid_diagnostic_only'],
                       'job_id': journal.token})
        guard = patch.object(action,'launch_contained',launch)
    elif mode == 'after_publication':
        original = TaskLedger.finish
        def finish(self,task,state,detail=''):
            if state == 'SUCCEEDED':
                row = index.read_revision(args['project_id'],args['new_take_id'],1)
                stop_here({'task_id': task,'take_sha256': row['document_sha256'],
                           'job_id': row['data']['protected_retake_execution']['original_process_journal_id']})
            return original(self,task,state,detail)
        guard = patch.object(TaskLedger,'finish',finish)
    else:
        raise ValueError('Unknown fixed public fixture crash boundary')
    with guard:
        action.execute_saved_retake(index,ledger,**args,confirm_native=lambda *_: True,live_gate=lambda _: True)
    raise RuntimeError('Crash boundary was not reached')


@unittest.skipUnless(os.name == 'nt','Actual Windows kernel required')
class NativeHostDeathTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('NVP_WO6_DISPOSABLE_CRASH_VM'),'1',
                         'Run only in the isolated disposable Windows crash-acceptance job')
        import test_nvp_wo6_native_take_action as fixture_module
        self.fixture = fixture_module.NativeTakeActionTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.root = Path(self.fixture.index.studio.db_path).parent
        self.args = self.fixture.args()
        self.marker = self.root / 'crash.ready.json'

    def _child(self,mode):
        repo = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(repo),str(repo/'tests'))))
        source = ('from pathlib import Path;from test_nvp_wo6_native_host_death import child_main;'
                  f'child_main(Path({str(self.root)!r}),{self.args!r},{mode!r},Path({str(self.marker)!r}))')
        child = subprocess.Popen([sys.executable,'-c',source],cwd=repo,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.addCleanup(self._dispose,child)
        deadline = time.monotonic()+90
        while not self.marker.exists() and child.poll() is None and time.monotonic()<deadline:
            time.sleep(.05)
        if not self.marker.exists():
            if child.poll() is None: child.kill()
            _,err = child.communicate(timeout=15)
            self.fail('Crash boundary not reached: '+err.decode('utf8','replace')[-3000:])
        self.assertIsNone(child.poll())
        with self.assertRaises(RuntimeError):
            with WorkerHostLease(self.fixture.ledger.root): pass
        return child,json.loads(self.marker.read_text('utf8'))

    @staticmethod
    def _dispose(child):
        if child.poll() is None:
            child.kill(); child.wait(timeout=15)
        child.stdout.close();child.stderr.close()

    def _kill(self,child):
        child.kill(); child.communicate(timeout=15)
        self.assertNotEqual(child.returncode,0)

    def _recover(self):
        ledger = TaskLedger(self.fixture.ledger.root,sampler=self.fixture.ledger.sampler)
        index = FilmIndex(Studio(self.root/'film.sqlite'))
        with WorkerHostLease(ledger.root) as lease:
            result = RetakeRecovery(ledger,lease).reconcile(index,self.args['project_id'])
        return ledger,index,result

    def test_after_publication_before_terminal_commit(self):
        child,evidence = self._child('after_publication')
        self._kill(child)
        ledger,index,result = self._recover()
        self.assertEqual(result,[(evidence['task_id'],'SUCCEEDED')])
        self.assertEqual(ledger.snapshot()['reservations']['ram_mb'],0)
        self.assertEqual(index.read_revision(self.args['project_id'],self.args['new_take_id'],1)['document_sha256'],evidence['take_sha256'])
        self.assertEqual(index.read_revision(self.args['project_id'],'Original',1)['document_sha256'],self.fixture.original['document_sha256'])
        self.assertEqual(self._recover()[2],[])
        print('WO6_NATIVE_AFTER_PUBLICATION_REOPENED_WITHOUT_REPLAY',flush=True)

    def test_before_binding_real_job_kill_and_unverified_cleanup_retention(self):
        child,evidence = self._child('before_binding')
        # Hold a genuine kernel HANDLE while the specific worker is alive.
        # A process-list lookup after the crash would not establish identity.
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        kernel.WaitForSingleObject.restype=ctypes.c_ulong
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        kernel.CloseHandle.restype=ctypes.c_int
        handle=kernel.OpenProcess(0x00100000|0x1000,False,evidence['worker_pid'])
        self.assertTrue(handle,'Cannot open exact live native worker handle')
        try:
            self.assertEqual(kernel.WaitForSingleObject(handle,0),258) # WAIT_TIMEOUT, live
            self._kill(child)
            self.assertEqual(kernel.WaitForSingleObject(handle,15000),0) # WAIT_OBJECT_0, exited
        finally:
            kernel.CloseHandle(handle)
        ledger,index,result = self._recover()
        self.assertEqual(len(result),1)
        self.assertEqual(result[0][1],'HELD_UNVERIFIED')
        self.assertEqual(ledger.snapshot()['reservations']['ram_mb'],4096)
        with self.assertRaises(KeyError):index.read_revision(self.args['project_id'],self.args['new_take_id'])
        self.assertEqual(index.read_revision(self.args['project_id'],'Original',1)['document_sha256'],self.fixture.original['document_sha256'])
        from backend.nvp_w1g_release_gate import release_process_journal_root
        original = json.loads((release_process_journal_root()/(evidence['job_id']+'.json')).read_text('utf8'))
        self.assertEqual(original['state'],'RUNNING')
        print('WO6_NATIVE_HOST_DEATH_WORKER_EXITED_RESERVATION_HELD_PROFILE_UNVERIFIED',flush=True)

if __name__=='__main__':unittest.main()
