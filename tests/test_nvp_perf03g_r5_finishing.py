"""Actual generated PCM finishing, preserving single programme gain and clock."""
import hashlib
import unittest
from unittest.mock import patch

from backend.nvp_g07_feature_finish import review,analyze_approved,verify_index
from backend.nvp_g09d_finishing import G09DFinishing,DEFAULT_AUDIO,DEFAULT_COLOR
from backend.nvp_g09e_audio import finish_window,FilmMeter
from backend.nvp_g07_paged_media import delivery_plan,native_source_window
from backend.nvp_g08_native_avi import _audio_frame,TICKS_FRAME
from backend import nvp_g03_payloads as payloads
from test_nvp_perf03g_r4_protected_output import Fixture


class R5Finishing(unittest.TestCase):
    def setUp(self):self.f=Fixture(self)
    def _approved(self):
        f=self.f;finish=G09DFinishing(f.studio,live=f.store,token=f.token)
        self.assertFalse(finish.view(f.pid)['approved_for_current_film'])
        doc=finish.change(f.pid,0,'audio',{**DEFAULT_AUDIO,'fade_in_seconds':.25,'fade_out_seconds':.5})
        self.assertEqual(doc['current_film_source']['edit_sha256'],f.digest)
        finish.approve(f.pid,doc['revision']);return finish
    def test_measurement_is_continuous_not_per_reel_or_export(self):
        f=self.f
        for family in ('edl','take'):
            r=payloads.review(f.store,f.pid,f.token,family)
            payloads.migrate(f.store,f.pid,f.token,family,None,r['approval_digest'],human_approved=True)
        f.migrate();self._approved();expected=review(f.service,f.pid,2,f.digest)
        with self.assertRaises(PermissionError):analyze_approved(f.service,f.pid,expected)
        # Generated fixture is 7.5 seconds. Force 1s source windows to cross
        # original dissolve and chapter boundaries; actual pxr/PCM reads.
        with patch('backend.nvp_g07_feature_finish.FRAMES_PER_CHUNK',24):
            result=analyze_approved(f.service,f.pid,expected,human_approved=True)
        self.assertEqual(result['sample_count'],360000)
        self.assertFalse(result['derived_bytes_saved']);self.assertFalse(result['worker_verified']);self.assertFalse(result['final_movie_exported'])
        plan=delivery_plan(f.service,f.pid,2,f.digest)
        source=native_source_window(f.service,f.pid,2,f.digest,0,plan['frame_count']*TICKS_FRAME,plan_sha256=plan['plan_sha256'])
        # Independent unpartitioned source view, one-second DSP chunks.
        expected_src=hashlib.sha256();expected_derived=hashlib.sha256();meter=FilmMeter(duration_samples=360000)
        for sample in range(0,360000,48000):
            raw=_audio_frame(source,source['original_takes'],sample,min(48000,360000-sample));expected_src.update(raw);meter.feed(raw)
            expected_derived.update(finish_window(raw,result['gain_plan'],start_sample=sample,total_samples=360000))
        self.assertEqual(result['source_pcm_sha256'],expected_src.hexdigest());self.assertEqual(result['derived_pcm_sha256'],expected_derived.hexdigest());self.assertEqual(result['source_measurement'],meter.finish())
        f.editor._execute(f.pid,lambda db,movie:verify_index(db,f.pid,f.guard))
        from backend.nvp_g03_live_backup import create_backup,restore_copy
        backup=f.root/'finishing-backup';backup.mkdir();restored=f.root/'finishing-restored';restored.mkdir()
        create_backup(f.store,f.pid,f.token,backup,guard=f.guard,human_approved=True)
        restore_copy(f.store,f.pid,f.token,backup/('NVP-'+f.pid+'-backup'),restored,guard=f.guard,human_approved=True)
        with self.assertRaises(PermissionError):analyze_approved(f.service,f.pid,expected,human_approved=True)
    def test_changed_creative_approval_refused_and_no_receipt(self):
        f=self.f;finish=self._approved();before=review(f.service,f.pid,2,f.digest)
        finish.change(f.pid,1,'color',{**DEFAULT_COLOR,'exposure':.2})
        with self.assertRaises(PermissionError):analyze_approved(f.service,f.pid,before,human_approved=True)
        self.assertIsNone(f.editor._execute(f.pid,lambda db,movie:db.execute("SELECT name FROM sqlite_master WHERE name='g07_feature_finish_analysis'").fetchone()))
