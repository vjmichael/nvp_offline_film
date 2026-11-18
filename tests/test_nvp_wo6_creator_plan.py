import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_story_bible import StoryBible
from backend.nvp_story_timeline import StoryTimeline
from backend.nvp_scene_mind import SceneMind
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_webview_ipc_surface import NativeWebviewIPCSurface
from backend.nvp_wo6_creator_planning_desktop import RECEIPT, digest


class Window:
    url = 'http://127.0.0.1:51213/'
    def __init__(self):
        self.prompts = []
        self.approve = False
        self.on_ask = lambda: None
    def get_current_url(self):
        return self.url
    def create_confirmation_dialog(self, title, text):
        self.prompts.append((title, text)); self.on_ask(); return self.approve


class CreatorPlanTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.studio=Studio(Path(tmp.name)/'studio.sqlite3')
        StoryBible(self.studio); StoryTimeline(self.studio); SceneMind(self.studio)
        self.pid=self.studio.create_project('Movie','Idea','INT. ROOM - DAY\nA person enters.')['id']
        self.index=FilmIndex(self.studio)
        self.scene=self.index.register_revision(self.pid,'Room','scene',{'name':'Room'},expected_revision=0)
        self.timeline=self.index.register_revision(self.pid,'Time','temporal',{'duration_tick':1},expected_revision=0)
        self.take=self.index.register_revision(self.pid,'TakeOne','take',{
            'format':'nvp.digital_take.openusd_temporal.v1','frozen':True,
            'scene_id':'Room','scene_revision':1,'scene_document_sha256':self.scene['document_sha256'],
            'timeline_id':'Time','timeline_revision':1,'timeline_document_sha256':self.timeline['document_sha256']
        },dependencies=[{'object_id':'Room','revision':1,'role':'scene'},{'object_id':'Time','revision':1,'role':'temporal'}])
        self.index.register_revision(self.pid,'Cut','edit',{'title':'Cut'},dependencies=[{'object_id':'TakeOne','revision':1,'role':'source_take'}])
        self.bridge=TrustedDesktopCameraBridge(self.index,origin='http://127.0.0.1:51213');self.addCleanup(self.bridge._close)
        self.win=Window();self.bridge._attach_window(self.win);self.api=NativeWebviewIPCSurface(self.bridge)
        self.request={'project_id':self.pid,'source_id':'TakeOne','source_revision':1,'source_sha256':self.take['document_sha256'],
                      'change_kind':'retake','intention':'Try a slower entrance','screenplay_scene_id':None}
    def preview(self):
        return self.api.wo6_plan_preview(self.request)
    def save(self, preview):
        return self.api.wo6_plan_save({'proposal':self.request,'preview_sha256':preview['preview_sha256']})
    def test_exact_preview_is_read_only_and_tracks_sources(self):
        before=self.index.list_objects(self.pid);p=self.preview()
        self.assertEqual(p['verified_take_metadata'][0]['object_id'],'TakeOne')
        self.assertEqual({r['object_id'] for r in p['indexed_source_lineage']},{'Room','Time','TakeOne'})
        self.assertEqual(p['indexed_downstream'][0]['object_id'],'Cut')
        self.assertIsNotNone(p['story_context']['canon_sha256'])
        self.assertFalse(p['native_media_reopened']);self.assertFalse(p['worker_authorized'])
        self.assertEqual(before,self.index.list_objects(self.pid));self.assertEqual(self.win.prompts,[])
    def test_deny_then_native_approve_and_reopen(self):
        p=self.preview(); self.assertEqual(self.save(p)['status'],'DENIED')
        self.assertEqual(len(self.index.list_objects(self.pid)),4)
        self.win.approve=True; saved=self.save(p);self.assertFalse(saved['worker_authorized'])
        name=saved['record']['object_id']; self.assertEqual(saved['record']['revision'],1)
        self.assertIn(p['preview_sha256'],self.win.prompts[-1][1])
        self.assertEqual(self.index.read_revision(self.pid,'TakeOne')['document_sha256'],self.take['document_sha256'])
        reopened=FilmIndex(Studio(self.studio.db_path)).read_revision(self.pid,name,1)
        self.assertEqual(reopened['data']['format'],RECEIPT)
        self.assertTrue(self.api.wo6_plan_read(self.pid,name)['data']['creator_confirmed_planning_only'])
        self.assertIn(name,[x['object_id'] for x in self.api.wo6_plan_catalog(self.pid)['saved_plans']])
    def test_reject_browser_authority_wrong_hash_and_other_project(self):
        p=self.preview()
        with self.assertRaises(ValueError): self.api.wo6_plan_save({'proposal':self.request,'preview_sha256':p['preview_sha256'],'approved':True})
        with self.assertRaises(PermissionError): self.api.wo6_plan_save({'proposal':self.request,'preview_sha256':'0'*64})
        other=self.studio.create_project('Other','Other')['id']
        with self.assertRaises(KeyError): self.api.wo6_plan_preview({**self.request,'project_id':other})
        self.assertEqual(self.win.prompts,[])
    def test_new_consumer_during_dialog_blocks_commit(self):
        p=self.preview(); self.win.approve=True
        self.win.on_ask=lambda:self.index.register_revision(self.pid,'CutTwo','edit',{'title':'Second'},dependencies=[{'object_id':'TakeOne','revision':1,'role':'source_take'}])
        with self.assertRaises(PermissionError): self.save(p)
        self.assertEqual(self.api.wo6_plan_catalog(self.pid)['saved_plans'],[])
    def test_revoked_origin_and_protected_lock_block(self):
        p=self.preview();self.win.approve=True;self.win.on_ask=lambda:setattr(self.win,'url','http://outside.example/')
        with self.assertRaises(PermissionError):self.save(p)
        self.win.url='http://127.0.0.1:51213/'
        self.bridge._project_lock_check=lambda:True
        with self.assertRaises(PermissionError): self.preview()
    def test_new_source_head_and_truncated_impact_denied(self):
        req={**self.request,'source_id':'Room','source_sha256':self.scene['document_sha256'],'change_kind':'revise_scene'}
        p=self.api.wo6_plan_preview(req); self.index.register_revision(self.pid,'Room','scene',{'name':'New'},expected_revision=1)
        with self.assertRaises(PermissionError): self.api.wo6_plan_save({'proposal':req,'preview_sha256':p['preview_sha256']})
        with patch('backend.nvp_wo6_creator_planning_desktop.LIMIT',2):
            p=self.preview();self.assertTrue(p['graph_truncated']);self.assertFalse(p['planning_approval_available'])
            with self.assertRaises(PermissionError):self.save(p)
    def test_approved_canon_change_during_dialog_requires_fresh_plan(self):
        bible=StoryBible(self.studio); ent=bible.create_entity(self.pid,'character','Director')
        fact=bible.propose_fact(self.pid,ent['id'],'occupation','Teacher')
        expected=bible.get_entity(self.pid,ent['id'])['revision']
        p=self.preview();self.win.approve=True
        self.win.on_ask=lambda:bible.decide_fact(self.pid,fact['id'],'accept',expected)
        with self.assertRaises(PermissionError):self.save(p)
        self.assertEqual(self.preview()['story_context']['approved_facts'],1)
        self.assertEqual(self.api.wo6_plan_catalog(self.pid)['saved_plans'],[])
    def test_screenplay_edit_during_dialog_requires_fresh_plan(self):
        p=self.preview();self.win.approve=True
        rev=self.studio.get_project(self.pid)['revision']
        self.win.on_ask=lambda:self.studio.save_screenplay(self.pid,'EXT. PARK - NIGHT\nRain.',rev)
        with self.assertRaises(PermissionError):self.save(p)
        self.assertEqual(self.api.wo6_plan_catalog(self.pid)['saved_plans'],[])
    def test_bad_take_dependency_is_not_claimed_verified(self):
        malformed=self.index.register_revision(self.pid,'Broken','take',{'format':'nvp.digital_take.openusd_temporal.v1','frozen':True})
        with self.assertRaises(PermissionError):self.api.wo6_plan_preview({**self.request,'source_id':'Broken','source_sha256':malformed['document_sha256']})

if __name__=='__main__':unittest.main()
