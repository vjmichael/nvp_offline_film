"""Portable G03 nonce ledger protocol tests; synthetic live store fixture only."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import test_nvp_post01f_r5_encrypted_review as fixtures

class NonceLedgerContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.R5EncryptedDerivedPicture.setUpClass()
        with __import__('unittest').mock.patch.dict(sys.modules,fixtures.FAKES):
            import importlib.util
            p=pathlib.Path(__file__).resolve().parents[1]/'backend/nvp_post01f_g03_nonce_ledger.py'
            spec=importlib.util.spec_from_file_location('r5r1_nonce_under_fake_store',p)
            cls.module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.module)
    def setUp(self):
        fx=fixtures.R5EncryptedDerivedPicture('test_encrypted_pending_review_and_no_original_asset_mutation')
        fx.setUp();self.fx=fx;self.addCleanup(fx.doCleanups)
        self.ledger=self.module.G03ScmNonceLedger(fx.store,project_id=fx.pid,
                                                  session_token='active-session')
    def test_nonce_spent_once_in_existing_encrypted_head(self):
        fx=self.fx
        self.assertTrue(self.ledger(fx.job,'f'*32,'a'*64))
        self.assertFalse(self.ledger(fx.job,'f'*32,'a'*64))
    def test_independent_nonces_are_separately_spent(self):
        job=self.fx.job
        self.assertTrue(self.ledger(job,'f'*32,'a'*64))
        self.assertTrue(self.ledger(job,'e'*32,'a'*64))
    def test_denies_changed_project_and_locked_session(self):
        ledger=self.module.G03ScmNonceLedger(self.fx.store,
             project_id=self.fx.pid,session_token='expired')
        with self.assertRaises(PermissionError):ledger(self.fx.job,'f'*32,'a'*64)
    def test_denies_noncanonical_ids_without_mutation(self):
        for args in ((self.fx.job,'x'*32,'a'*64),('../other','f'*32,'a'*64),
                     (self.fx.job,'f'*32,'00'),(self.fx.job,True,'a'*64)):
            with self.subTest(args=args),self.assertRaises(PermissionError):
                self.ledger(*args)
    def test_spend_is_durable_across_new_host_ledger_object(self):
        self.assertTrue(self.ledger(self.fx.job,'f'*32,'a'*64))
        fresh=self.module.G03ScmNonceLedger(self.fx.store,project_id=self.fx.pid,
                                              session_token='active-session')
        self.assertFalse(fresh(self.fx.job,'f'*32,'a'*64))

if __name__=='__main__':unittest.main()
