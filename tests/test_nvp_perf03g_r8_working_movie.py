"""Portable HTTP/controller doubles, plus genuine generated host-media rendering.
These cases do not establish installed Windows worker custody or human consent.
"""
import hashlib
import io
import threading
import time
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.nvp_g07_recovery_dialog import NativeRecoveryDialog
from backend.nvp_g07_section_routes import mount_section_routes
from backend.nvp_g07_feature_finish import review, analyze_approved
from backend.nvp_g09d_finishing import G09DFinishing, DEFAULT_AUDIO
from backend import nvp_g07_feature_reels as reels
from test_nvp_perf03g_r4_protected_output import Fixture
from test_nvp_perf03g_r6_feature_reels import R6Base

IDENTITY={'role':'protected_feature_reel','executable_sha256':'a'*64,'os':'windows-appcontainer-job'}
ORIGIN='http://127.0.0.1:8765'

def finish(f):
    svc=G09DFinishing(f.studio,live=f.store,token=f.token)
    doc=svc.change(f.pid,0,'audio',{**DEFAULT_AUDIO,'fade_in_seconds':.25,'fade_out_seconds':.5});svc.approve(f.pid,doc['revision'])

class Window:
    def __init__(self,pid):self.url=ORIGIN+'/postproduction.html?project='+pid+'&encrypted=1';self.choices=[];self.prompts=[]
    def get_current_url(self):return self.url
    def create_file_dialog(self,*args,**kwargs):raise AssertionError('Unrequested file dialog')
    def create_confirmation_dialog(self,*args):self.prompts.append(args);return self.choices.pop(0)

class R8Controller(unittest.TestCase):
    def setUp(self):
        self.f=f=Fixture(self,count=6);finish(f)
        self.window=Window(f.pid);self.dialog=NativeRecoveryDialog(self.window,ORIGIN)
        self.app=FastAPI();self.app.state.nvp_editorial_recovery_dialog=self.dialog
        class Access:
            def permitted(_,pid,token):return pid==f.pid and token==f.token
        mount_section_routes(self.app,lambda:f.studio,lambda:f.store,lambda:Access(),'test_session')
        self.client=TestClient(self.app,base_url=ORIGIN,headers={'origin':ORIGIN,'sec-fetch-site':'same-origin','x-nvp-director':'1'},cookies={'test_session':f.token})
        self.base=f'/api/projects/{f.pid}/live/edit/sections';self.enterContext(patch('backend.nvp_g07_feature_native.installed_identity',return_value=IDENTITY))
    def step(self,op):return self.client.post(self.base+'/feature-step',json={'revision':2,'digest':self.f.digest,'operation_id':op})
    def prepare(self):
        self.window.choices.append(True);result=self.step('5'*32);self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['state'],'prepared')
    def test_prepare_refusal_and_exact_scope(self):
        self.window.choices.append(False);result=self.step('1'*32);self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['state'],'refused');self.assertEqual(len(self.window.prompts),1)
        self.assertEqual(self.step('1'*32).status_code,403)
        bad=self.client.post(self.base+'/feature-step',json={'revision':2,'digest':'f'*64,'operation_id':'2'*32});self.assertNotEqual(bad.status_code,200);self.assertEqual(len(self.window.prompts),1)
        bad=self.client.post(self.base+'/feature-step',json={'revision':2,'digest':self.f.digest,'operation_id':'3'*32,'human_approved':True});self.assertEqual(bad.status_code,422)
        self.prepare();self.window.choices.append(False);result=self.step('4'*32);self.assertEqual(result.json()['state'],'refused');self.assertIn('remaining',self.window.prompts[-1][1])
    def test_cancel_is_nonblocking_and_session_scoped_then_resume(self):
        self.prepare();self.window.choices.append(True);op='2'*32;started=threading.Event();released=threading.Event();result={}
        def blocking(assembly,start,end,plan,identity,guard,**kw):
            if kw.get('started'):kw['started']()
            started.set();deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                try:guard()
                except InterruptedError:released.set();raise
                time.sleep(.01)
            raise AssertionError('Stop did not reach renderer')
        def run():result['response']=self.step(op)
        with patch('backend.nvp_g07_feature_native.render',side_effect=blocking):
            thread=threading.Thread(target=run,daemon=True);thread.start()
            try:
                self.assertTrue(started.wait(15),'Controller never reached renderer')
                status=self.client.post(self.base+'/feature-status',json={'operation_id':op});self.assertTrue(status.json()['active'])
                wrong=self.client.post(self.base+'/feature-stop',json={'operation_id':'f'*32});self.assertFalse(wrong.json()['stop_requested'])
                wrong=self.client.post(self.base+'/feature-stop',json={'operation_id':op},headers={'origin':'http://invalid.test'});self.assertEqual(wrong.status_code,403)
                with TestClient(self.app,base_url=ORIGIN,headers={'origin':ORIGIN,'sec-fetch-site':'same-origin','x-nvp-director':'1'},cookies={'test_session':'wrong'}) as other:
                    self.assertEqual(other.post(self.base+'/feature-stop',json={'operation_id':op}).status_code,423)
                before=time.monotonic();stopped=self.client.post(self.base+'/feature-stop',json={'operation_id':op});self.assertTrue(stopped.json()['stop_requested']);self.assertLess(time.monotonic()-before,2)
                self.assertTrue(released.wait(5));thread.join(15);self.assertFalse(thread.is_alive());self.assertEqual(result['response'].json()['state'],'stopped')
            finally:
                if thread.is_alive():self.dialog.close();thread.join(20)
        self.assertFalse(self.client.post(self.base+'/feature-status',json={'operation_id':op}).json()['active'])
        # A fresh window/host controller discovers the durable analysis/cursor.
        self.dialog.close();self.assertTrue(self.dialog.wait_feature_closed())
        self.dialog=NativeRecoveryDialog(self.window,ORIGIN);self.app.state.nvp_editorial_recovery_dialog=self.dialog
        def public_media(assembly,start,end,plan,identity,guard,**kw):
            if kw.get('started'):kw['started']()
            data=io.BytesIO();reels.render_reel(assembly,start,end,plan,data,cancel=lambda:(guard(),False)[1]);raw=data.getvalue()
            return raw,{'identity':IDENTITY,'request_sha256':'c'*64,'media_sha256':hashlib.sha256(raw).hexdigest(),'job_and_profile_cleanup_verified':True}
        self.window.choices.append(True);prior=len(self.window.prompts)
        with patch('backend.nvp_g07_feature_native.render',side_effect=public_media) as render:
            resumed=self.step('3'*32);self.assertEqual(resumed.status_code,200,resumed.text);body=resumed.json();self.assertEqual(body['state'],'complete');self.assertEqual(body['saved_frames'],276);self.assertEqual(render.call_count,2)
        self.assertEqual(len(self.window.prompts),prior+1)
        with patch('backend.nvp_g07_feature_native.render',side_effect=AssertionError('Re-render of completed movie')):
            self.assertEqual(self.step('4'*32).json()['state'],'complete')
        self.assertEqual(len(self.window.prompts),prior+1)
    def test_unsupported_runtime_does_not_prompt_or_fallback(self):
        with patch('backend.nvp_g07_feature_native.installed_identity',side_effect=PermissionError('Unavailable')):
            self.assertEqual(self.step('1'*32).status_code,403)
        self.assertFalse(self.window.prompts)

class R8Extended(R6Base,unittest.TestCase):
    def test_generated_63_5_seconds_seven_reels(self):
        f=Fixture(self,count=32);self.f=f;finish(f)
        self.analysis=analyze_approved(f.service,f.pid,review(f.service,f.pid,2,f.digest),human_approved=True)
        self.assertEqual(self.analysis['sample_count'],3048000)
        def next():return reels.review_next(f.service,f.pid,self.analysis['receipt_sha256'],frames_per_reel=240)
        for end in (240,480,720,960,1200,1440,1524):self.assertEqual(self.execute(next())['end_frame'],end)
        final=self.execute(next());self.assertEqual(final['reel_count'],7);self.assertEqual(final['frames'],1524);self.assertEqual(final['pcm_sha256'],self.analysis['derived_pcm_sha256']);self.assertFalse(final['independent_worker_verified']);self.assertEqual(reels.verify_complete(f.service,f.pid,final['job_id']),final);self.backup()
