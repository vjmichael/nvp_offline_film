"""Actual journal/ledger recovery via desktop IPC; authority/window are doubles.
Real systemd authority and cold reboot are covered by the installed SEC-06
fixture. These tests do not claim real GTK or a privileged kernel execution.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

from backend.nvp_audio01e3_native_host import NativeAudioHost
from backend.nvp_audio01d_chunked_recovery import RATE, run_chunked_preview
from backend.nvp_film_index import FilmIndex
from backend.nvp_linux_desktop_audio_recovery import ManagedAudioRecoveryControls
from backend.nvp_linux_service_recovery import SystemdRecoveryAuthority, digest
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_studio import Studio
from backend.nvp_webview_ipc_surface import NativeWebviewIPCSurface


class Window:
    url = 'http://127.0.0.1:7777/'
    response = True
    after_dialog = None
    prompts = 0
    def get_current_url(self): return self.url
    def create_confirmation_dialog(self, title, message):
        self.prompts += 1
        if self.after_dialog: self.after_dialog()
        return self.response


@unittest.skipUnless(sys.platform == 'linux', 'Linux service recovery')
class DesktopAudioRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root/'voice.wav'
        self.n = 2*RATE
        with wave.open(str(self.src), 'wb') as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE)
            w.writeframes(struct.pack('<hh', 1200, -1200)*self.n)
        self.plan = {'stems': [{'stem_id': 'voice', 'kind': 'dialogue', 'clips': [
            {'out_start': 0, 'out_end': self.n, 'source_start': 0, 'fade_in': 0,
             'fade_out': 0, 'gain_milli': 1000}]}]}
        self.ledger = TaskLedger(self.root/'ledger', sampler=lambda: ResourceSnapshot(0,16000,12000,0.,tuple()))
        self.authority = SystemdRecoveryAuthority('nvp-desktop@creator.service')
        self.start = {'invocation': 'a'*32, 'unit': self.authority.unit}
        self.current = self.start
        self.stop = {'start_sha256': digest(self.start), 'prior_subtree_empty': True}
        self.stop_available = True
        def stopped(invocation, sha):
            if (not self.stop_available or self.current == self.start or invocation != self.start['invocation'] or sha != digest(self.start)):
                raise PermissionError('No authenticated predecessor in this test')
            return self.stop
        a=patch.object(SystemdRecoveryAuthority,'current',side_effect=lambda:self.current);a.start();self.addCleanup(a.stop)
        a=patch.object(SystemdRecoveryAuthority,'stopped',side_effect=stopped);a.start();self.addCleanup(a.stop)
        self.old = NativeAudioHost(self.ledger,self.root/'native',verify_creator_action=lambda event,scope:event=='old-creator',systemd_recovery=self.authority)
        self.window=Window();self.locked=False
        self.bridge=TrustedDesktopCameraBridge(FilmIndex(Studio(self.root/'studio.sqlite3')),origin='http://127.0.0.1:7777', project_lock_check=lambda:self.locked)
        self.addCleanup(self.bridge._close)
        self.bridge._attach_window(self.window)
        self.api=NativeWebviewIPCSurface(self.bridge)

    def admission(self, name, *, output=False, prelaunch=False):
        dest=self.root/name
        job=self.old.stage_and_approve(self.plan,{'voice':self.src},self.n,dest,'old-creator')['job_id']
        self.assertEqual(self.old._claim_next()['task_id'],job)
        if not prelaunch:
            self.old.journal.transition(job,0,'running','admitted')
            self.old._mark_launch_intent(job)
        if output:run_chunked_preview(self.plan,{'voice':self.src},self.n,dest,max_new_chunks=1)
        return job,dest

    def reopen(self):
        self.current={'invocation':'b'*32,'unit':self.authority.unit}
        self.bridge._attach_audio_recovery(self.ledger,self.root/'native',self.authority)
        return self.api.audio_recovery_catalog()

    def test_unmanaged_window_exposes_no_authority(self):
        self.assertEqual(self.api.audio_recovery_catalog(),{'available':False,'items':[],'held':0,'more':False,'next_page':None})
        with self.assertRaises(PermissionError):self.api.audio_recovery_act('a'*48,'recover')

    def test_real_checkpoint_reconciliation_no_automatic_restart(self):
        job,dest=self.admission('mix',output=True)
        before={p.name:p.read_bytes() for p in dest.iterdir() if p.suffix=='.pcm'}
        result=self.reopen();self.assertEqual(len(result['items']),1)
        self.assertEqual(set(result['items'][0]),{'selection','can_abandon','can_recover'})
        self.assertNotIn(str(self.root),json.dumps(result));self.assertNotIn(job,json.dumps(result))
        token=result['items'][0]['selection']
        self.assertFalse(result['items'][0]['can_abandon'])
        self.assertEqual(self.api.audio_recovery_act(token,'recover'),{'status':'RECOVERED'})
        self.assertEqual(self.old.journal.read(job)['state'],'reconciled')
        self.assertEqual(self.ledger.get_task(job)['state'],'INTERRUPTED')
        self.assertEqual(before,{p.name:p.read_bytes() for p in dest.iterdir() if p.suffix=='.pcm'})
        self.assertEqual(self.window.prompts,1)
        with self.assertRaises(PermissionError):self.api.audio_recovery_act(token,'recover')
        self.assertFalse(self.api.audio_recovery_catalog()['items'])

    def test_real_abandonment_requires_new_native_confirmation(self):
        job,dest=self.admission('missing')
        token=self.reopen()['items'][0];self.assertTrue(token['can_abandon'])
        self.window.response=False
        self.assertEqual(self.api.audio_recovery_act(token['selection'],'abandon'),{'status':'CANCELLED'})
        self.assertEqual(self.ledger.get_task(job)['state'],'ACTIVE')
        self.assertFalse(dest.exists())
        self.window.response=True
        token=self.api.audio_recovery_catalog()['items'][0]['selection']
        self.assertEqual(self.api.audio_recovery_act(token,'abandon'),{'status':'ENDED'})
        self.assertEqual(self.ledger.get_task(job)['reserved'],0)
        self.assertEqual(self.old.journal.read(job)['state'],'failed')
        self.assertFalse(dest.exists())
        with self.ledger._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM audio_native_abandonments').fetchone(),(1,))
            self.assertEqual(db.execute('SELECT count(*) FROM audio_native_staging_leases').fetchone(),(0,))

    def test_never_started_reservation_close(self):
        job,dest=self.admission('never',prelaunch=True)
        token=self.reopen()['items'][0];self.assertFalse(token['can_abandon'])
        self.assertEqual(self.api.audio_recovery_act(token['selection'],'recover'),{'status':'CLOSED'})
        self.assertFalse(dest.exists());self.assertEqual(self.ledger.get_task(job)['reserved'],0)

    def test_unknown_origin_locked_and_changed_during_dialog(self):
        job,_=self.admission('missing');token=self.reopen()['items'][0]['selection']
        self.window.url='http://127.0.0.1:7777/postproduction.html'
        with self.assertRaises(PermissionError):self.api.audio_recovery_act(token,'abandon')
        self.window.url='http://127.0.0.1:7777/'
        self.locked=True
        with self.assertRaises(PermissionError):self.api.audio_recovery_catalog()
        self.locked=False
        token=self.api.audio_recovery_catalog()['items'][0]['selection']
        self.window.after_dialog=lambda:setattr(self.window,'url','https://example.invalid/')
        with self.assertRaises(PermissionError):self.api.audio_recovery_act(token,'abandon')
        self.assertEqual(self.ledger.get_task(job)['state'],'ACTIVE')

    def test_no_stop_foreign_owner_raw_job_and_current_generation(self):
        job,_=self.admission('missing')
        self.bridge._attach_audio_recovery(self.ledger,self.root/'native',self.authority)
        self.assertFalse(self.api.audio_recovery_catalog()['items'])
        self.current={'invocation':'b'*32,'unit':self.authority.unit};self.stop_available=False
        self.assertEqual(self.api.audio_recovery_catalog()['held'],1)
        self.stop_available=True
        with self.assertRaises(PermissionError):self.api.audio_recovery_act(job,'abandon')
        foreign=ManagedAudioRecoveryControls(self.ledger,self.root/'othernative',self.authority,lambda:self.window)
        self.addCleanup(foreign.close)
        self.assertFalse(foreign.catalog()['items'])
        token=self.api.audio_recovery_catalog()['items'][0]['selection']
        self.api.audio_recovery_catalog() # old token must be invalidated
        with self.assertRaises(PermissionError):self.api.audio_recovery_act(token,'recover')
        self.bridge._audio_recovery.close()
        with self.assertRaises(PermissionError):self.api.audio_recovery_catalog()
        self.assertEqual(self.ledger.get_task(job)['state'],'ACTIVE')

    def test_bounded_opaque_pagination(self):
        self.admission('first',prelaunch=True);self.admission('second',prelaunch=True)
        self.current={'invocation':'b'*32,'unit':self.authority.unit}
        self.bridge._attach_audio_recovery(self.ledger,self.root/'native',self.authority)
        with patch('backend.nvp_linux_desktop_audio_recovery._PAGE',1):
            first=self.api.audio_recovery_catalog();self.assertTrue(first['more']);self.assertEqual(len(first['items']),1)
            second=self.api.audio_recovery_catalog(first['next_page']);self.assertFalse(second['more']);self.assertEqual(len(second['items']),1)
            with self.assertRaises(PermissionError):self.api.audio_recovery_catalog(first['next_page'])
            with self.assertRaises(PermissionError):self.api.audio_recovery_act(first['items'][0]['selection'],'recover')

    def test_tamper_of_sealed_job_after_catalog_refused(self):
        job,_=self.admission('missing');token=self.reopen()['items'][0]['selection']
        with self.ledger._db() as db:
            db.execute("UPDATE authorized_task_specs SET spec_json='{}' WHERE task_id=?",(job,))
        with self.assertRaises(PermissionError):self.api.audio_recovery_act(token,'abandon')
        self.assertEqual(self.ledger.get_task(job)['state'],'ACTIVE');self.assertEqual(self.window.prompts,0)
