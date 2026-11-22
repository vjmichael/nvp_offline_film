import unittest
from unittest.mock import Mock
from backend.nvp_partitioned_delivery_bridge import verify_finite_selection,partitioned_provenance,FORMAT
from backend.nvp_bounded_review import object_window

class AudioBridgeTests(unittest.TestCase):
    def setUp(self):
        self.root='a'*64;self.take='b'*64;self.decision='c'*64;self.tick=1000
        self.receipt={'format':FORMAT,'status':'PARTITIONED_PCM24_CANDIDATE_PUBLISHED','manifest_sha256':self.root}
        self.data={'source_take_sha256':self.take,'film_start_tick':3000}
        self.candidate={'partitioned_manifest_sha256':self.root,'first_frame':3,'frame_count':4,'sample_rate':48000,'sample_width_bytes':3,'original_take_sha256':self.take}
        self.index=Mock();self.journal=Mock();self.select=Mock(return_value=self.candidate)
        self.index.read_revision.return_value={'kind':'presentation','document_sha256':self.decision,'data':self.data}
        self.journal.status_page.return_value={'project_id':'p','state':'OUTPUT_READY'}
        self.journal.reel.return_value={'decision_id':'d','decision_revision':1,'decision_sha256':self.decision,'take_sha256':self.take,'frame_count':4}
    def run_bridge(self,**kw):
        return verify_finite_selection(self.index,self.journal,'p','job',self.receipt,1,frame_ticks=self.tick,select=self.select,**kw)
    def test_exact_selection(self):
        self.assertEqual(self.run_bridge(),self.candidate)
        self.assertEqual(self.select.call_args.kwargs['expected_first_frame'],3)
        self.assertEqual(self.select.call_args.kwargs['expected_frame_count'],4)
        self.assertEqual(partitioned_provenance(self.candidate,self.data,4,1000)['first_sample'],6000)
        self.assertEqual(partitioned_provenance(self.candidate,self.data,4,1000)['sample_count'],8000)
    def test_wrong_project_before_read(self):
        self.journal.status_page.return_value['project_id']='q'
        with self.assertRaises(PermissionError):self.run_bridge()
        self.select.assert_not_called()
    def test_wrong_decision(self):
        self.index.read_revision.return_value['document_sha256']='0'*64
        with self.assertRaises(PermissionError):self.run_bridge()
        self.select.assert_not_called()
    def test_bad_clock(self):
        self.data['film_start_tick']=3001
        with self.assertRaises(PermissionError):self.run_bridge()
        self.select.assert_not_called()
    def test_wrong_partition(self):
        self.candidate['partitioned_manifest_sha256']='d'*64
        with self.assertRaises(PermissionError):self.run_bridge()
    def test_wrong_first_frame(self):
        self.candidate['first_frame']=4
        with self.assertRaises(PermissionError):self.run_bridge()
    def test_wrong_take(self):
        self.candidate['original_take_sha256']='d'*64
        with self.assertRaises(PermissionError):self.run_bridge()
    def test_cancel(self):
        with self.assertRaises(InterruptedError):self.run_bridge(cancelled=lambda:True)
        self.select.assert_not_called()
    def test_legacy(self):self.assertIsNone(partitioned_provenance({},self.data,4,self.tick))

class ReviewTests(unittest.TestCase):
    def test_large_index(self):
        class Index:
            def list_objects(self,*args,**kwargs):raise AssertionError('full catalog prohibited')
            def object_page(self,p,*,kind,after,limit):
                assert limit<=64 and p=='p' and kind=='edit'
                start=int(after)+1 if after else 0;stop=min(start+limit,10000)
                return {'items':[{'object_id':str(i)} for i in range(start,stop)],'next_after':str(stop-1) if stop<10000 else None}
        cursor=None;total=0
        while True:
            rows,cursor=object_window(Index(),'p','edit',after=cursor,limit=256)
            self.assertLessEqual(len(rows),256)
            for row in rows:self.assertEqual(row['object_id'],str(total));total+=1
            if cursor is None:break
        self.assertEqual(total,10000)
    def test_nonadvancing_page(self):
        idx=Mock();idx.object_page.return_value={'items':[],'next_after':'bad'}
        with self.assertRaises(RuntimeError):object_window(idx,'p','edit')
    def test_bound(self):
        with self.assertRaises(ValueError):object_window(Mock(),'p','edit',limit=257)

if __name__=='__main__':unittest.main()
