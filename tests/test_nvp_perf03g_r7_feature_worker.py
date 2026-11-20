"""Generated-only protocol/real codec fixture; native Windows gate is distinct."""
import hashlib
import multiprocessing
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch

from backend import nvp_g07_feature_reels as reels
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g07_feature_native import installed_identity
from backend.nvp_g07_feature_finish import review,analyze_approved
from backend.nvp_g09d_finishing import G09DFinishing,DEFAULT_AUDIO
from backend.nvp_g07_review_reels import inspect
from tools import nvp_g07_feature_reel_worker as worker
from test_nvp_perf03g_r6_feature_reels import R6Base
from test_nvp_perf03g_r4_protected_output import Fixture


class R7Protocol(R6Base,unittest.TestCase):
    def setUp(self):self.seed()
    def raw(self):
        f=self.f
        def get(db,movie):
            approved=reels._current(f.service,db,f.pid,self.analysis)
            a=reels._assembly(f.service,db,f.pid,self.analysis,approved,0,12)
            return worker.request(a,0,12,self.analysis['gain_plan'])
        return f.service._run(f.pid,get)
    def test_real_child_protocol_and_exact_readback(self):
        raw=self.raw();payload=worker.MAGIC_IN+struct.pack('!Q',len(raw))+raw
        # PUBLIC synthetic fixture only, NOT a protected OS-worker launch.
        proc=subprocess.run([sys.executable,'-m','tools.nvp_g07_feature_reel_worker'],input=payload,capture_output=True,timeout=45,cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(proc.returncode,0,proc.stderr[:100]);self.assertEqual(proc.stderr,b'')
        p=len(worker.MAGIC_OUT);self.assertEqual(proc.stdout[:p],worker.MAGIC_OUT);self.assertEqual(proc.stdout[p:p+32],hashlib.sha256(raw).digest())
        count=struct.unpack('!Q',proc.stdout[p+32:p+40])[0];data=proc.stdout[p+40:];self.assertEqual(count,len(data))
        self.assertEqual(data,worker.process(raw))
        audit=inspect(data,12,expected_sha=hashlib.sha256(data).hexdigest());self.assertEqual(audit['audio_samples_per_channel'],24000)
        bad=subprocess.run([sys.executable,'-m','tools.nvp_g07_feature_reel_worker'],input=payload+b'!',capture_output=True,timeout=45,cwd=Path(__file__).resolve().parents[1]);self.assertNotEqual(bad.returncode,0);self.assertEqual(bad.stdout,b'')
    def test_no_uncontained_private_fallback(self):
        self.assertEqual(worker.installed_worker_entry(),3)
        with self.assertRaises(PermissionError):installed_identity()
        with self.assertRaises(PermissionError):reels.review_native_next(self.f.service,self.f.pid,self.analysis['receipt_sha256'])
        self.assertEqual(self.next()['action'],'render')
    def test_native_launch_failure_never_falls_back_to_host(self):
        f=self.f;identity={'role':'protected_feature_reel','executable_sha256':'a'*64,'os':'windows-appcontainer-job'}
        # Source-only authority tests; no OS custody is being simulated as a pass.
        with patch('backend.nvp_g07_feature_native.installed_identity',return_value=identity),patch('backend.nvp_g07_feature_native.render',side_effect=VaultError('Native launch refused')),patch.object(reels,'render_reel',side_effect=AssertionError('Forbidden fallback')):
            review=reels.review_native_next(f.service,f.pid,self.analysis['receipt_sha256'],frames_per_reel=90)
            with self.assertRaises(PermissionError):reels.execute_native_approved(f.service,f.pid,review)
            with self.assertRaises(PermissionError):reels.execute_native_approved(f.service,f.pid,{**review,'native_review_sha256':'b'*64},human_approved=True)
            self.assertEqual(self.next()['action'],'render')
            with self.assertRaises(VaultError):reels.execute_native_approved(f.service,f.pid,review,human_approved=True)
            self.assertEqual(self.next()['action'],'resume')
            self.assertEqual(self.next()['pending_attempt'],1)
            self.assertFalse(reels._location(f.folder,f.key,review['review']['job_id'],0,create=True).exists())
    def test_corrupt_stage_is_retained(self):
        f=self.f;first=self.next();target=reels._location(f.folder,f.key,first['job_id'],0,create=True);stage=target.parent/('.stage-'+target.name);stage.mkdir();body=stage/'body.nvpsealed';body.write_bytes(b'truncated')
        with self.assertRaises(VaultError):self.execute(first)
        self.assertEqual(body.read_bytes(),b'truncated');self.assertFalse(target.exists());self.assertEqual(self.next()['action'],'resume')
    def test_inspection_cancellation(self):
        calls=[];data=worker.process(self.raw())
        def stop():
            calls.append(1)
            if len(calls)==3:raise InterruptedError('cancel review')
        with self.assertRaises(InterruptedError):inspect(data,12,expected_sha=hashlib.sha256(data).hexdigest(),guard=stop)
        self.assertEqual(len(calls),3)


@unittest.skipUnless(os.name=='posix','POSIX abrupt-exit fixture')
class R7Stage(R6Base,unittest.TestCase):
    def test_abrupt_exit_before_promotion_and_exact_replay(self):
        self.seed();f=self.f;first=self.next()
        def child():
            def kill(stage,target):os._exit(72)
            with patch.object(reels,'atomic_publish_directory',side_effect=kill):self.execute(first)
        proc=multiprocessing.get_context('fork').Process(target=child);proc.start();proc.join(45)
        if proc.is_alive():proc.terminate();proc.join();self.fail('Bounded fixture timed out')
        self.assertEqual(proc.exitcode,72)
        target=reels._location(f.folder,f.key,first['job_id'],0);stage=target.parent/('.stage-'+target.name);body=stage/'body.nvpsealed';cipher=body.read_bytes();self.assertFalse(target.exists())
        pending=self.next();self.assertEqual(pending['action'],'resume');self.execute(pending)
        self.assertFalse(stage.exists());self.assertEqual((target/'body.nvpsealed').read_bytes(),cipher);self.assertEqual(self.next()['part'],1)


class R7Longer(R6Base,unittest.TestCase):
    def test_generated_31_5_seconds_four_reels(self):
        f=Fixture(self,count=16);self.f=f
        finish=G09DFinishing(f.studio,live=f.store,token=f.token)
        doc=finish.change(f.pid,0,'audio',{**DEFAULT_AUDIO,'fade_in_seconds':.25,'fade_out_seconds':.5});finish.approve(f.pid,doc['revision'])
        self.analysis=analyze_approved(f.service,f.pid,review(f.service,f.pid,2,f.digest),human_approved=True)
        self.assertEqual(self.analysis['sample_count'],1512000)
        def next():return reels.review_next(f.service,f.pid,self.analysis['receipt_sha256'],frames_per_reel=240)
        for end in (240,480,720,756):self.assertEqual(self.execute(next())['end_frame'],end)
        final=self.execute(next());self.assertEqual(final['reel_count'],4);self.assertEqual(final['frames'],756);self.assertEqual(final['pcm_sha256'],self.analysis['derived_pcm_sha256']);self.assertFalse(final['independent_worker_verified'])
        self.assertEqual(reels.verify_complete(f.service,f.pid,final['job_id']),final)
        self.backup()
