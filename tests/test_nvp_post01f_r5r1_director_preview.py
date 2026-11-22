"""Read-only director preview acceptance, synthetic protected store only."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import test_nvp_post01f_r5_encrypted_review as fixtures

class DirectorPreviewContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.R5EncryptedDerivedPicture.setUpClass()
    def setUp(self):
        fx=fixtures.R5EncryptedDerivedPicture('test_encrypted_pending_review_and_no_original_asset_mutation')
        fx.setUp()
        self.addCleanup(fx.doCleanups)
        self.fx=fx
        self.review=fx.review
        self.preview_ok=True
        self.review.authorize_preview=lambda scope,event:self.preview_ok
        fx.pub()
    def preview(self,session='active-session',event=b'authenticated-preview'):
        fx=self.fx
        return self.review.director_preview_bytes(fx.pid,session,fx.job,creator_event=event)
    def test_releases_only_authenticated_full_gcm_picture(self):
        result=self.preview()
        self.assertEqual(result['picture_bytes'],self.fx.movie.read_bytes())
        self.assertEqual(result['media_type'],'video/mp4')
        self.assertTrue(result['video_only'])
    def test_refuses_invalid_viewer_event_without_approval(self):
        self.preview_ok=False
        with self.assertRaises(PermissionError):self.preview(event=b'spoof')
    def test_refuses_locked_session_on_preview(self):
        with self.assertRaises(PermissionError):self.preview(session='expired')
    def test_refuses_tampered_media_before_returning_bytes(self):
        fx=self.fx
        target=fx.store._folder(fx.pid)/'derived_ltx'/fx.job/'picture.nvpsealed'
        data=bytearray(target.read_bytes());data[-1]^=1;target.write_bytes(data)
        with self.assertRaises(Exception):self.preview()
    def test_missing_preview_authority_does_not_fallback_to_approval(self):
        self.review.authorize_preview=None
        with self.assertRaises(PermissionError):self.preview()

if __name__=='__main__':unittest.main()
