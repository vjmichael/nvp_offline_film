"""R6 actual bounded generated picture/PCM, sealed journal and split-commit replay.
Portable fixture uses public test key; genuine Windows DPAPI variant separately gated.
"""
import os
import unittest
from unittest.mock import patch

from backend.nvp_g03_live_backup import create_backup, restore_copy
from backend.nvp_g03_live_store import LiveFilmStore
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g07_edit import G07Editor
from backend.nvp_g07_sections import EditorialSections
from backend.nvp_g07_feature_finish import review, analyze_approved
from backend.nvp_g09d_finishing import G09DFinishing, DEFAULT_AUDIO, DEFAULT_COLOR
from backend import nvp_g07_feature_reels as reels
from test_nvp_perf03g_r4_protected_output import Fixture
from test_nvp_perf03g_sections import SECRET


class R6Base:
    def seed(self,native=False):
        f=Fixture(self,native=native);self.f=f
        finish=G09DFinishing(f.studio,live=f.store,token=f.token)
        doc=finish.change(f.pid,0,'audio',{**DEFAULT_AUDIO,'fade_in_seconds':.25,'fade_out_seconds':.5})
        finish.approve(f.pid,doc['revision']);self.finish=finish
        self.analysis=analyze_approved(f.service,f.pid,review(f.service,f.pid,2,f.digest),human_approved=True)
    def next(self):return reels.review_next(self.f.service,self.f.pid,self.analysis['receipt_sha256'],frames_per_reel=90)
    def execute(self,reviewed=None,**kwargs):return reels.execute_approved(self.f.service,self.f.pid,reviewed or self.next(),human_approved=True,**kwargs)
    def run_all(self):
        first=self.next();self.assertEqual(first['window'],[0,90]);self.assertEqual(self.execute(first)['end_frame'],90)
        self.assertEqual(self.next()['window'],[90,180]);self.assertEqual(self.execute()['end_frame'],180)
        self.assertEqual(self.next()['action'],'finalize');done=self.execute();self.assertTrue(done['working_reels_complete']);self.assertFalse(done['independent_worker_verified']);self.assertFalse(done['final_movie_exported']);self.assertEqual(done['pcm_sha256'],self.analysis['derived_pcm_sha256']);self.assertEqual(done['samples'],360000)
        self.assertEqual(self.next()['action'],'complete')
        return done
    def backup(self):
        f=self.f;parent=f.root/'reel-backup';parent.mkdir();restored=f.root/'reel-restore';restored.mkdir()
        create_backup(f.store,f.pid,f.token,parent,guard=f.guard,human_approved=True)
        restore_copy(f.store,f.pid,f.token,parent/('NVP-'+f.pid+'-backup'),restored,guard=f.guard,human_approved=True)
        return restored


class R6Reels(R6Base,unittest.TestCase):
    def setUp(self):self.seed()
    def test_whole_working_movie_and_backup(self):
        done=self.run_all();f=self.f;restored=self.backup()
        store=LiveFilmStore(restored);store._keys[f.token]=(f.pid,f.key)
        service=EditorialSections(G07Editor(f.studio,live=store,token=f.token),access_guard=lambda:store._session(f.pid,f.token))
        result=reels.review_next(service,f.pid,self.analysis['receipt_sha256'],frames_per_reel=90)
        self.assertEqual(result['action'],'complete');self.assertEqual(result['job_id'],done['job_id'])
        self.assertEqual(reels.verify_complete(service,f.pid,done['job_id']),done)
        self.assertEqual(reels.open_verified_reel(service,f.pid,done['job_id'],0)[:4],b'RIFF')
        # Actual encrypted files, not merely journal metadata.
        target=reels._location(f.folder,f.key,done['job_id'],0)/'body.nvpsealed';data=target.read_bytes();self.assertNotEqual(data[:4],b'RIFF')
        target.write_bytes(data[:-1]+bytes([data[-1]^1]));parent=f.root/'bad-backup';parent.mkdir()
        with self.assertRaises(VaultError):create_backup(f.store,f.pid,f.token,parent,guard=f.guard,human_approved=True)
    def test_cancellation_and_explicit_resume(self):
        first=self.next();f=self.f
        with self.assertRaises(PermissionError):reels.execute_approved(f.service,f.pid,first)
        # Cancel the actual renderer after one frame using the host callback.
        original=reels.render_reel;inside=[False];checks=[0]
        def cancel():
            if not inside[0]:return False
            checks[0]+=1;return checks[0]>=2
        def mark(*a,**kw):
            inside[0]=True;return original(*a,**kw)
        with patch.object(reels,'render_reel',side_effect=mark):
            with self.assertRaises(InterruptedError):self.execute(first,cancel=cancel)
        self.assertEqual(checks[0],2)
        pending=self.next();self.assertEqual(pending['action'],'resume');self.assertEqual(pending['pending_attempt'],1)
        with self.assertRaises(PermissionError):self.execute(first)
        self.assertEqual(self.execute(pending)['end_frame'],90)
        self.assertEqual(self.next()['part'],1)
    def test_split_commit_replay_and_fresh_authority(self):
        f=self.f;first=self.next();publish=reels._publish
        def fail_after_publish(*args,**kwargs):
            publish(*args,**kwargs);raise InterruptedError('fault after encrypted directory promotion')
        with patch.object(reels,'_publish',side_effect=fail_after_publish):
            with self.assertRaises(InterruptedError):self.execute(first)
        target=reels._location(f.folder,f.key,first['job_id'],0)/'body.nvpsealed';original=target.read_bytes()
        pending=self.next();self.assertEqual(pending['action'],'resume')
        parent=f.root/'pending-backup';parent.mkdir()
        with self.assertRaises(VaultError):create_backup(f.store,f.pid,f.token,parent,guard=f.guard,human_approved=True)
        self.execute(pending);self.assertEqual(target.read_bytes(),original)
        self.assertEqual(self.next()['part'],1)
        self.finish.change(f.pid,1,'color',{**DEFAULT_COLOR,'exposure':.2})
        with self.assertRaises((PermissionError,ValueError)):self.next()
    def test_unindexed_storage_refused(self):
        f=self.f;root=f.folder/'feature-reels';root.mkdir();orphan=root/('a'*64);orphan.mkdir();(orphan/'body.nvpsealed').write_bytes(b'unreviewed')
        parent=f.root/'unreviewed-backup';parent.mkdir()
        with self.assertRaises(VaultError):create_backup(f.store,f.pid,f.token,parent,guard=f.guard,human_approved=True)

    def test_cross_project_and_stale_review_denied(self):
        f=self.f;expected=self.next()
        with self.assertRaises(PermissionError):reels.execute_approved(f.service,'different',expected,human_approved=True)
        tampered={**expected,'window':[0,1]}
        with self.assertRaises(PermissionError):self.execute(tampered)
        self.assertEqual(self.next(),expected)


@unittest.skipUnless(os.name=='nt','Windows native DPAPI required')
class R6Windows(R6Base,unittest.TestCase):
    def test_dpapi_completed_reels_reopen(self):
        self.seed(native=True);done=self.run_all();f=self.f;restored=self.backup()
        store=LiveFilmStore(restored);store.authorize(f.pid,SECRET,f.token)
        service=EditorialSections(G07Editor(f.studio,live=store,token=f.token),access_guard=lambda:store._session(f.pid,f.token))
        self.assertEqual(reels.review_next(service,f.pid,self.analysis['receipt_sha256'],frames_per_reel=90)['job_id'],done['job_id'])
