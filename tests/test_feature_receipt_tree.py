import unittest
from backend.nvp_feature_receipt_tree import ReceiptTree,output_header,check_output_header

class TreeTests(unittest.TestCase):
    def build(self,n=100,manifest='a'*64,mutate=None):
        t=ReceiptTree(manifest)
        for i in range(n):t.add(f'file_{i:08d}', 'c'*64 if i==mutate else 'b'*64)
        return t
    def test_streaming_large(self):
        t=self.build(30000);self.assertEqual(t.count,30000);self.assertLessEqual(len(t.peaks),15)
        self.assertEqual(t.finish(),self.build(30000).finish())
    def test_exact_order_count_and_source(self):
        t=self.build();r=t.finish()
        for other in [self.build(99),self.build(mutate=99),self.build(manifest='d'*64)]:self.assertNotEqual(r,other.finish())
    def test_legacy_and_new(self):
        files={'CPL.xml':'b'*64,'PKL.xml':'d'*64};t=ReceiptTree('a'*64)
        for name in sorted(files):t.add(name,files[name])
        h=output_header(files,'a'*64,'e'*64)
        self.assertEqual(h['receipt_tree_sha256'],t.finish())
        check_output_header(h,'e'*64,t);check_output_header({'file_sha256':'e'*64},'e'*64,t)
        for bad in [{**h,'receipt_tree_sha256':'0'*64},{**h,'tree_format':'bogus'},{'file_sha256':'0'*64},dict(h,unexpected=True)]:
            with self.assertRaises(PermissionError):check_output_header(bad,'e'*64,t)
    def test_duplicate_and_bad_input(self):
        t=ReceiptTree('a'*64)
        with self.assertRaises(ValueError):t.finish()
        t.add('a','b'*64)
        for name,sha in [('a','c'*64),('../x','c'*64),('z','notsha')]:
            with self.assertRaises(PermissionError):t.add(name,sha)
if __name__=='__main__':unittest.main()
