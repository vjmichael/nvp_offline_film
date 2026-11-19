"""Portable SQLite/FilmIndex source geometry fixtures, not native USD renders."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_openusd_take import FORMAT as TAKE_FORMAT
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_paged_catalog import SlatePagedCatalog
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_slate_hierarchy import SlateHierarchy
from backend.nvp_slate_navigation import SlateNavigation
from backend.nvp_slate08_desktop_read import FilmCameraReadBridge


def ref(row):
    return {k:row[k] for k in ('object_id','revision','document_sha256')}


class SectionsTest(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'film.sqlite';self.studio=Studio(self.path)
        self.pid=self.studio.create_project('Fixture','')['id'];self.index=FilmIndex(self.studio)
        self.approvals=[]
        def approve(event,scope):
            self.approvals.append(scope);return event=='yes'
        self.h=SlateHierarchy(self.index,approve=approve);self.b=SlateNavigation(self.index)

    def graph(self,n):
        sid=f'scene{n}';take=f'take{n}'
        # Metadata fixture only: no native Take capture or USD evaluation.
        self.index.register_revision(self.pid,take,'take',{'format':TAKE_FORMAT,'frozen':True,'scene_id':sid,'duration_tick':T})
        node={'branch_id':'original','kind':'performance','parent_id':None,'fork_tick':None,'group_id':'group','primary':True,
              'take_id':take,'source_start_tick':0,'source_end_tick':T,'shot_id':None,'shot_revision':None,
              'slate':{'scene':str(n),'setup':'A','shot':'Wide','camera':'A','take_number':1,'wild':False,'script_revision':'v1','notes':''}}
        graph=DigitalSlateBranches(self.index,verify_editor_action=lambda *_:False)
        return graph.publish_graph(self.pid,f'graph{n}',scene_id=sid,scene_label=str(n),nodes=[node]),graph,node

    def group(self,ident,children,*,family='takes',event='yes'):
        return self.h.publish(self.pid,ident,family=family,title='Section '+ident,children=[ref(c) for c in children],creator_event=event)

    def page(self,row,family,**kw):
        return self.b.page(self.pid,row['object_id'],row['revision'],digest=row['document_sha256'],family=family,**kw)

    def test_nested_catalog_pages_original_branch_ids_and_reopen(self):
        a,_,_=self.graph(1);b,_,_=self.graph(2)
        group=self.group('group_a',[a,b]);root=self.group('root',[group]);
        self.assertEqual(self.approvals[-1]['operation'],'nvp.slate.publish_hierarchy.v1')
        top=self.page(root,'takes');self.assertEqual(top['items'][0]['object_id'],'group_a')
        page=self.page(group,'takes',limit=1);self.assertEqual(page['items'][0]['label'],'1');self.assertEqual(page['next_first'],1)
        page=self.page(group,'takes',first=1,limit=1);self.assertEqual(page['items'][0]['label'],'2');self.assertIsNone(page['next_first'])
        for graph in (a,b):
            page=self.page(graph,'takes');self.assertEqual(page['items'][0]['branch_id'],'original');self.assertFalse(page['source_modified'])
        reopened=SlateHierarchy(FilmIndex(Studio(self.path)),approve=lambda *_:False)
        self.assertEqual(reopened.open(self.pid,'root',1)['document_sha256'],root['document_sha256'])

    def test_paged_catalog_leaf_uses_existing_page_source(self):
        a,_,node=self.graph(1)
        catalog=SlatePagedCatalog(self.index,verify_catalog_action=lambda *_:True)
        cat=catalog.publish(self.pid,'catalog',scene_id='scene1',scene_label='1',records=[{**node,'semantic':{}}],capture_event='yes')
        group=self.group('root',[cat]);self.assertEqual(self.page(group,'takes')['items'][0]['object_id'],'catalog')
        self.assertEqual(self.page(cat,'takes')['items'][0]['branch_id'],'original')

    def test_edit_group_exact_offsets_and_original_cut_preserved(self):
        edits=[]
        for n in (1,2):
            graph,slate,_=self.graph(n)
            engine=SlateSequenceAssembly(slate,verify_editor_action=lambda *_:True)
            edits.append(engine.commit(self.pid,f'cut{n}',graph_id=graph['object_id'],graph_revision=1,
                segments=[{'segment_id':'shot','branch_id':'original','source_in_tick':0,'source_out_tick':T}],editor_event='yes'))
        root=self.group('editroot',edits,family='edit')
        page=self.page(root,'edit',first=1,limit=1);self.assertEqual((page['items'][0]['start_tick'],page['items'][0]['end_tick']),(str(T),str(2*T)))
        self.assertEqual(self.page(edits[1],'edit')['items'][0]['take'],'take2')
        self.assertEqual(self.index.read_revision(self.pid,'cut1',1)['document_sha256'],edits[0]['document_sha256'])
        self.assertFalse(self.h.open(self.pid,'editroot',1)['data']['render_approved'])

    def test_refusal_duplicate_depth_scope_and_exact_digest(self):
        leaf,_,_=self.graph(1)
        with self.assertRaises(PermissionError):self.group('denied',[leaf],event='no')
        with self.assertRaises(KeyError):self.index.read_revision(self.pid,'denied')
        with self.assertRaises(ValueError):self.group('duplicate',[leaf,leaf])
        a=self.group('a',[leaf]);b=self.group('b',[a]);c=self.group('c',[b])
        with self.assertRaises(ValueError):self.group('d',[c])
        with self.assertRaises(ValueError):self.group('graph1',[leaf])
        with self.assertRaises(PermissionError):self.b.page(self.pid,'a',1,digest='b'*64,family='takes')
        other=self.studio.create_project('Other','')['id']
        with self.assertRaises(KeyError):self.b.page(other,'a',1,digest=a['document_sha256'],family='takes')
        doc=self.index.read_revision(self.pid,'a',1)['data'];doc['children'][0]['item_count']+=1
        forged=self.index.register_revision(self.pid,'forged','presentation',doc,dependencies=[{'object_id':'graph1','revision':1,'role':'presentation'}])
        with self.assertRaises(RuntimeError):self.page(forged,'takes')

    def test_scene_keyset_no_full_list_and_camera_continuation(self):
        for n in range(270):
            self.index.register_revision(self.pid,f'scene{n:04}','scene',{'native_schema_version':1,'prim_roles':{'/World/Cam':'camera'} if n>=260 else {}})
        with patch.object(self.index,'list_objects',side_effect=AssertionError('Unbounded listing')):
            directory=self.b.directory(self.pid,family='scenes',limit=32)
            self.assertEqual(len(directory['items']),32);self.assertEqual(directory['next_after'],'scene0031')
            selected=self.b.directory(self.pid,family='scenes',after='scene0259',limit=32)
            self.assertEqual(len(selected['items']),10);self.assertIsNone(selected['next_after'])
            bridge=FilmCameraReadBridge(self.index);first=bridge.scenes(self.pid)
            self.assertEqual(first['scenes'],[]);self.assertEqual(first['next_after'],'scene0255')
            second=bridge.scenes(self.pid,after=first['next_after']);self.assertEqual(len(second['scenes']),10);self.assertFalse(second['usd_loaded']);self.assertIsNone(second['next_after'])
        with self.assertRaises(ValueError):self.b.directory(self.pid,family='scenes',limit=65)

    def test_existing_p1de_approved_leaf_and_hierarchy_navigation(self):
        from backend import nvp_p1de_edit_audio as conform
        def bind(index,pid,segments):
            return [{**s,"scene_sha256":"c"*64,"timeline_sha256":"d"*64} for s in segments],sum(s["out_tick"]-s["in_tick"] for s in segments),[]
        with patch.object(conform,"_bound_segments",side_effect=bind):
            leaf=conform.P1DEConform(self.index,approve_edit=lambda *_:True).publish(self.pid,"source_edit",
                [{"take_id":"original","take_sha256":"a"*64,"in_tick":0,"out_tick":T,"listener_path":"/World/Camera","audio":[]}],creator_event="yes")
            self.assertEqual(self.page(leaf,"edit")["items"][0]["end_tick"],str(T))
        # Exact prior root shape, source conform verification stubbed only for
        # this archive test; real P1DE root read is covered by native CI fixture.
        doc={"format":"nvp.p1de.source_edit_manifest.v2","source_modified":False,"flattened_soundtrack":False,
            "picture_rendered":False,"master_approved":False,"duration_tick":T,
            "children":[{"edit_id":"source_edit","revision":1,"document_sha256":leaf["document_sha256"],"start_tick":0,"end_tick":T,"depth":0}]}
        root=self.index.register_revision(self.pid,"source_root","edit",doc,dependencies=[{"object_id":"source_edit","revision":1,"role":"timeline"}])
        with patch.object(conform.P1DEConform,"read",return_value=self.index.read_revision(self.pid,"source_root",1)) as verified:
            page=self.page(root,"edit")
            self.assertEqual(page["items"][0]["document_sha256"],leaf["document_sha256"])
            verified.assert_called_once_with(self.pid,"source_root",1)

    def test_native_host_authoring_requires_window_consent_and_live_scope(self):
        from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
        from backend.nvp_webview_ipc_surface import NativeWebviewIPCSurface
        leaf,_,_=self.graph(1)
        class Window:
            url='http://127.0.0.1:7777/'
            allowed=False
            count=0
            def get_current_url(self):return self.url
            def create_confirmation_dialog(self,*_):self.count+=1;return self.allowed
        window=Window();host=TrustedDesktopCameraBridge(self.index,origin='http://127.0.0.1:7777');host._attach_window(window);self.addCleanup(host._close)
        api=NativeWebviewIPCSurface(host);request={'project_id':self.pid,'family':'takes','title':'Act I','children':[ref(leaf)]}
        with self.assertRaises(PermissionError):api.slate_publish_section(request)
        window.allowed=True
        with self.assertRaises(ValueError):api.slate_publish_section({**request,'approved':True})
        self.assertEqual(window.count,1)
        receipt=api.slate_publish_section(request);self.assertFalse(receipt['render_approved'])
        self.assertEqual(self.b.page(self.pid,receipt['object_id'],1,digest=receipt['document_sha256'],family='takes')['items'][0]['object_id'],leaf['object_id'])
        window.url='http://127.0.0.1:8888/'
        with self.assertRaises(PermissionError):api.slate_publish_section(request)
        window.url='http://127.0.0.1:7777/'
        def revoke(*_):window.url='http://127.0.0.1:8888/';return True
        window.create_confirmation_dialog=revoke
        before=self.index.object_page(self.pid,kind='presentation')['items']
        with self.assertRaises(PermissionError):api.slate_publish_section(request)
        self.assertEqual(self.index.object_page(self.pid,kind='presentation')['items'],before)

    def test_directory_limit_even_when_unrelated_rows_hide_results(self):
        for i in range(33):self.index.register_revision(self.pid,f'aaa{i:03}','presentation',{'format':'not-a-catalog'})
        leaf,_,_=self.graph(1)
        first=self.b.directory(self.pid,family='takes');self.assertEqual(first['items'],[]);self.assertIsNotNone(first['next_after'])
        next_page=self.b.directory(self.pid,family='takes',after=first['next_after']);self.assertEqual(next_page['items'][0]['object_id'],leaf['object_id'])

if __name__=='__main__':unittest.main()
