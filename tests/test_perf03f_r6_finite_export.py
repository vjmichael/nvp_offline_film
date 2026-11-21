"""R6 finite whole-feature bridge, real FilmIndex, fixture reel metadata.

Real structural DCP publication test uses synthetic MXF bytes and substitutes
Windows storage admission on Linux. NOT native codec, EFS or installed proof.
"""
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from backend.nvp_film_index import FilmIndex,MAX_DEPENDENCIES
from backend.nvp_studio import Studio
from backend import nvp_feature_sections as sections
from backend.nvp_wo4_resource_budget import MAX_REELS
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend import nvp_wo4_multireel as mult
from backend import nvp_wo4_pcm_stream as pcm
from backend import nvp_wo4_file_dcp as dcp
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure

T=TICKS_PER_SECOND//24
P='2K_FLAT_24'

def ref_from(record):
    return {'object_id':record['object_id'],'revision':record['revision'],'sha256':record['document_sha256']}

class FiniteExportIntegration(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.db=self.root/'film.sqlite3'
        self.studio=Studio(self.db);self.index=FilmIndex(self.studio)
        self.pid=self.studio.create_project('Original production','Fixture')['id']
        self.other=self.studio.create_project('Other production','Fixture')['id']
        self.reels={}
    def leaf(self,i,counts=(3,3)):
        jobs=[]
        for j,n in enumerate(counts):
            uid=f'job-{i}-{j}';jobs.append(uid)
            self.reels[uid]={'project_id':self.pid,'job_id':uid,'profile':P,'state':'DCP_INDEXED','frame_count':n,'receipt_sha256':'a'*64}
        return ref_from(self.index.register_revision(self.pid,f'Leaf{i}','edit',{'format':sections.LEAF,
            'ordered_reel_job_ids':jobs,'start_tick':0,'end_tick':sum(counts)*T}))
    def group(self,name,children):
        return ref_from(sections.register(self.index,self.pid,name,children,frame_ticks=T,approve=lambda _:True))
    def plan(self,source,**kw):
        args=dict(frame_ticks=T,profile=P,reel_budget=min(MAX_REELS,MAX_DEPENDENCIES-1),read_reel=self.reels.__getitem__);args.update(kw)
        return sections.finite_export_plan(self.index,self.pid,source,**args)
    def register(self,source,**kw):
        args=dict(frame_ticks=T,profile=P,reel_budget=min(MAX_REELS,MAX_DEPENDENCIES-1),read_reel=self.reels.__getitem__,approve=lambda _:True);args.update(kw)
        return sections.register_finite_export(self.index,self.pid,'FinalAssembly',source,**args)
    def test_actual_index_nested_assembly_survives_reopen(self):
        a=self.group('GroupA',[self.leaf(0),self.leaf(1)])
        b=self.group('GroupB',[self.leaf(2),self.leaf(3)])
        root=self.group('Root',[a,b]);approved=[]
        reg=self.register(root,approve=lambda scope:approved.append(scope) or True)
        self.assertFalse(approved[0]['authorizes_output'])
        self.assertEqual(reg['dependencies'],[{'object_id':'Root','revision':1,'role':'presentation'}])
        self.index=FilmIndex(Studio(self.db))
        saved=self.index.read_revision(self.pid,'FinalAssembly',1)
        self.assertEqual(saved['data'],self.plan(root));self.assertEqual(len(saved['data']['ordered_reel_job_ids']),8)
        self.assertEqual(saved['data']['end_tick'],24*T)
        self.assertEqual(saved['document_sha256'],reg['document_sha256'])
    def test_project_scope_and_wrong_reel_timing(self):
        root=self.group('Root',[self.leaf(0),self.leaf(1)])
        self.reels['job-1-0']['project_id']=self.other
        with self.assertRaises(PermissionError):self.plan(root)
        self.reels['job-1-0']['project_id']=self.pid;self.reels['job-1-0']['frame_count']=4
        with self.assertRaises(PermissionError):self.plan(root)
        self.reels['job-1-0']['frame_count']=3;self.reels['job-1-0']['profile']='4K_FLAT_24'
        with self.assertRaises(PermissionError):self.plan(root)
    def test_repeated_source_across_nested_groups(self):
        shared=self.leaf(0);a=self.group('GroupA',[shared,self.leaf(1)]);b=self.group('GroupB',[shared,self.leaf(2)])
        with self.assertRaises(PermissionError):self.plan(self.group('Root',[a,b]))
    def test_budget_rejects_before_reading_reel(self):
        root=self.group('Root',[self.leaf(0),self.leaf(1)])
        with self.assertRaises(ValueError):self.plan(root,reel_budget=3,read_reel=lambda _:self.fail('must not read reel'))
    def test_refusal_and_cancellation_no_assembly(self):
        root=self.group('Root',[self.leaf(0),self.leaf(1)])
        self.assertEqual(self.register(root,approve=lambda _:False),{'status':'DENIED'})
        with self.assertRaises(InterruptedError):self.register(root,cancelled=lambda:True)
        self.assertEqual(self.index.history(self.pid,'FinalAssembly'),[])
    def test_changed_source_timing_during_consent(self):
        root=self.group('Root',[self.leaf(0),self.leaf(1)])
        def approve(_):self.reels['job-0-0']['frame_count']=4;return True
        with self.assertRaises(PermissionError):self.register(root,approve=approve)
        self.assertEqual(self.index.history(self.pid,'FinalAssembly'),[])
    def test_changed_indexed_receipt_during_consent(self):
        root=self.group('Root',[self.leaf(0),self.leaf(1)])
        def approve(_):
            self.reels['job-0-0']['receipt_sha256']='f'*64
            return True
        with self.assertRaises(PermissionError):self.register(root,approve=approve)
        self.assertEqual(self.index.history(self.pid,'FinalAssembly'),[])
    def test_approved_ordered_receipts_remain_bound(self):
        root=self.group('Root',[self.leaf(0),self.leaf(1)])
        self.reels['job-0-1']['receipt_sha256']='b'*64
        self.reels['job-1-0']['receipt_sha256']='c'*64
        reg=self.register(root)
        data=self.index.read_revision(self.pid,'FinalAssembly',reg['revision'])['data']
        self.assertEqual(data['hierarchical_reel_receipt_sha256'],['a'*64,'b'*64,'c'*64,'a'*64])
        self.reels['job-1-0']['receipt_sha256']='e'*64
        self.assertNotEqual(data,self.plan(root))
    def test_corrupted_pinned_child_blob(self):
        a=self.leaf(0);root=self.group('Root',[a,self.leaf(1)])
        self.index._blob_path(self.pid,a['sha256']).write_bytes(b'corrupted immutable source')
        with self.assertRaises(RuntimeError):self.plan(root)
    def test_native_structure_publisher_one_continuous_package(self):
        root=self.group('Root',[self.leaf(0,(3,4)),self.leaf(1,(5,6))]);r=self.register(root)
        data=self.index.read_revision(self.pid,'FinalAssembly',1)['data'];jobs=data['ordered_reel_job_ids']
        reels=[];authority=[];start=0;original={};output=self.root/'exports';output.mkdir()
        for i,uid in enumerate(jobs):
            frames=self.reels[uid]['frame_count']; source=sha256(uid.encode()).hexdigest()
            part={'start_tick':start,'end_tick':start+frames*T,'frames':frames,'reel_uuid':str(uuid4())};start=part['end_tick']
            authority.append({'source_take_sha256':source,'mastering_decision_sha256':'b'*64,'indexed_receipt_sha256':'a'*64})
            for kind in ('picture','sound'):
                path=self.root/f'{kind}-{i}.mxf';raw=(f'FAKE-{i}-{kind}-STRUCTURAL'.encode())*100;path.write_bytes(raw);original[path]=raw
                part[kind]={'file_path':str(path),'file_sha256':sha256(raw).hexdigest(),'file_bytes':len(raw),'asset_uuid':str(uuid4()),'kind':kind,'source_take_sha256':source,'frame_count':frames,'edit_rate':[24,1],'source_modified':False,'production_dcp_accepted':False,**({'profile':P} if kind=='picture' else {})}
            reels.append(part)
        def local_guard(path,*,directory=False):
            p=Path(path)
            if not p.is_absolute() or any(x.is_symlink() for x in (p,*p.parents)):raise PermissionError('fixture link')
            st=p.stat()
            if not (stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)):raise PermissionError('fixture type')
            return st.st_dev,st.st_ino
        def export_root(path):
            p=Path(path);return p.resolve(strict=True),local_guard(p,directory=True)
        ids={k:str(uuid4()) for k in ('cpl','pkl','assetmap')}
        args=dict(reels=reels,ids=ids,title='Hierarchy structural fixture',profile=P,output_root=output,
            check_cancel=lambda:False,approve=lambda _:True,source_take_sha256=authority[0]['source_take_sha256'],
            mastering_decision_sha256=authority[0]['mastering_decision_sha256'],source_reel_authority=authority,feature_assembly_sha256=r['document_sha256'])
        with ExitStack() as stack:
            for module in (pcm,dcp,mult):stack.enter_context(patch.object(module,'_protected_path',local_guard))
            for module in (dcp,mult):stack.enter_context(patch.object(module,'_export_root',export_root))
            result=mult.publish_multireel_dcp(**args)
            with self.assertRaises(FileExistsError):mult.publish_multireel_dcp(**args)
        report=inspect_dcp_structure(result['destination'])
        self.assertEqual(report['status'],'STRUCTURE_AND_SHA_VERIFIED');self.assertEqual(report['reel_durations'],[3,4,5,6])
        self.assertEqual(result['total_frames'],18);self.assertEqual(result['feature_assembly_sha256'],r['document_sha256'])
        self.assertFalse(result['production_dcp_accepted']);self.assertEqual(len(list(output.iterdir())),1)
        for path,raw in original.items():self.assertEqual(path.read_bytes(),raw)

if __name__=='__main__':unittest.main()
