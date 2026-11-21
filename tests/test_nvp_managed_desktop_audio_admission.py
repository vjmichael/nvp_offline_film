"""Local source/ledger tests; the dialog/service are doubles, not GUI evidence."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from backend.nvp_audio01e3_native_host import NativeAudioHost
from backend.nvp_film_index import FilmIndex
from backend.nvp_imported_audio import FORMAT
from backend.nvp_linux_service_recovery import SystemdRecoveryAuthority
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_studio import Studio
from backend.nvp_webview_ipc_surface import NativeWebviewIPCSurface


class Window:
    url = 'http://127.0.0.1:7777/'
    answer = False
    calls = 0
    after = None

    def get_current_url(self):
        return self.url

    def create_confirmation_dialog(self, title, message):
        self.calls += 1
        if self.after:
            self.after()
        return self.answer


class ProjectAudioAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.index = FilmIndex(Studio(self.root / 'studio.sqlite3'))
        self.pid = self.index.studio.create_project('First movie', '')['id']
        self.other = self.index.studio.create_project('Other movie', '')['id']
        self.path = self.root / 'voice.wav'
        with wave.open(str(self.path), 'wb') as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
            w.writeframes(struct.pack('<hh', 100, -100) * 48000)
        self.original = self.path.read_bytes()
        blob = self.index.put_media_file(self.pid, self.path, media_type='audio/wav')
        record = {'format': FORMAT, 'original_codec': 'wav', 'source_media_sha256': blob['sha256'],
                  'source_media_type': 'audio/wav', 'source_bytes': len(self.original),
                  'native_sample_rate': 48000, 'native_channels': 2, 'native_frame_count': 48000,
                  'converted_soundtrack': False}
        self.index.register_revision(self.pid, 'Voice', 'audio', record, expected_revision=0)
        self.ledger = TaskLedger(self.root / 'ledger', sampler=lambda: ResourceSnapshot(0,16000,0,0.,tuple()))
        self.authority = SystemdRecoveryAuthority('nvp-desktop@creator.service')
        a = patch.object(SystemdRecoveryAuthority, 'current', return_value={'invocation':'a'*32,'unit':self.authority.unit})
        a.start(); self.addCleanup(a.stop)
        self.window = Window()
        self.locked = False
        self.bridge = TrustedDesktopCameraBridge(self.index, origin='http://127.0.0.1:7777', project_lock_check=lambda: self.locked)
        self.bridge._attach_window(self.window)
        self.bridge._attach_audio_recovery(self.ledger, self.root/'native', self.authority)
        self.addCleanup(self.bridge._close)
        self.api = NativeWebviewIPCSurface(self.bridge)

    def jobs(self):
        with self.ledger._db() as db:
            return db.execute('SELECT id,state,reserved FROM tasks').fetchall()

    def test_catalog_project_bound_and_refusal_never_queues(self):
        self.assertEqual(self.api.audio_preview_catalog(self.pid)['items'], [{'source_id':'Voice','revision':1}])
        self.assertEqual(self.api.audio_preview_catalog(self.other)['items'], [])
        with self.assertRaises(PermissionError):
            self.api.audio_preview_start(self.other, 'Voice', 1)
        self.assertEqual(self.window.calls, 0)
        self.assertEqual(self.api.audio_preview_start(self.pid, 'Voice', 1), {'status':'CANCELLED'})
        self.assertEqual(self.jobs(), [])
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_resource_denial_closes_exact_queue_no_worker(self):
        self.window.answer = True
        self.assertEqual(self.api.audio_preview_start(self.pid, 'Voice', 1), {'status':'REVIEW_REQUIRED'})
        self.assertEqual(self.window.calls, 1)
        job,state,reserved = self.jobs()[0]
        self.assertEqual((state,reserved),('CANCELLED',0))
        host = self.bridge._audio_recovery._host
        row = host.journal.read(job)
        self.assertEqual(row['state'], 'failed')
        self.assertEqual(row['spec']['project_source']['project_id'], self.pid)
        self.assertEqual(row['spec']['project_source']['source_id'], 'Voice')
        self.assertEqual(row['spec']['project_source']['media_sha256'], hashlib.sha256(self.original).hexdigest())
        self.assertFalse(Path(row['spec']['directory']).exists())
        self.assertEqual(host.close_unclaimed_project_preview(job), {'state':'CANCELLED','worker_started':False})
        with self.ledger._db() as db:
            for table in ('audio_native_staging_leases','audio_native_service_bindings','audio_native_os_stop_receipts'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone(), (0,))

    def test_decline_changed_origin_and_cancel_during_dialog(self):
        self.window.answer = True
        self.window.after = lambda: self.api.audio_preview_cancel(self.pid)
        self.assertEqual(self.api.audio_preview_start(self.pid,'Voice',1),{'status':'CANCELLED'})
        self.assertFalse(self.jobs())
        self.window.after = lambda: setattr(self.window,'url','https://example.invalid/')
        self.assertEqual(self.api.audio_preview_start(self.pid,'Voice',1),{'status':'CANCELLED'})
        self.assertFalse(self.jobs())

    def test_locked_movie_no_admission(self):
        self.locked = True
        with self.assertRaises(PermissionError): self.api.audio_preview_catalog(self.pid)
        with self.assertRaises(PermissionError): self.api.audio_preview_start(self.pid,'Voice',1)
        self.assertEqual(self.window.calls,0)

    def test_split_queue_closure_replay(self):
        self.window.answer = True
        with patch('backend.nvp_audio01e3_native_journal.AudioJobJournal.transition', side_effect=RuntimeError('interruption')):
            with self.assertRaises(PermissionError):
                self.api.audio_preview_start(self.pid,'Voice',1)
        job,state,reserved = self.jobs()[0]
        self.assertEqual((state,reserved),('CANCELLED',0))
        host = self.bridge._audio_recovery._host
        self.assertEqual(host.journal.read(job)['state'],'approved')
        self.assertEqual(host.close_unclaimed_project_preview(job)['state'],'CANCELLED')
        self.assertEqual(host.journal.read(job)['state'],'failed')
        with self.ledger._db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM audio_native_staging_leases').fetchone(),(0,))
