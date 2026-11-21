"""Exact LTX native creator signoff source invariants, not installed acceptance."""
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tools/nvp_post01f_windows_ltx_creator_signoff.cpp'
SCM=ROOT/'tools/nvp_post01f_windows_scm_ltx_broker.cpp'

class NativeLtxConsent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=SOURCE.read_text(encoding='utf8')
        cls.scm=SCM.read_text(encoding='utf8')
    def test_exact_shared_cms_signature_and_verifier(self):
        for marker in ('nvp_post01f_creator::Scope s{',
                       'nvp_post01f_creator::message(s)',
                       'nvp_post01f_creator::verify(s,output,pin)',
                       'CryptSignMessage(&para,TRUE,1',
                       'SignerCertificateSha256'):
            with self.subTest(marker=marker):self.assertIn(marker,self.source)
        self.assertIn('nvp_post01f_creator::verify(approved,approval_file,creator_cert)',
                      self.scm)
    def test_explicit_native_creator_consent_not_batch(self):
        for marker in ('MessageBoxW(','MB_YESNO','MB_DEFBUTTON2',
                       'response==IDYES','required(argc==1',
                       'NVP_POST01F_CREATOR_SIGNOFF_DENIED'):
            self.assertIn(marker,self.source)
        for forbidden in ('--accept','--yes','--approve','NVP_PUBLIC_SYNTHETIC_CI'):
            self.assertNotIn(forbidden,self.source)
    def test_fixed_efs_and_one_creation(self):
        for marker in ('L"CreatorApprovals"','L".p7s"',
                       'FILE_IS_ENCRYPTED','CREATE_NEW',
                       'FlushFileBuffers(h)','!fs::is_symlink(root)'):
            self.assertIn(marker,self.source)
        self.assertIn('L"CreatorApprovals"',self.scm)
        self.assertIn('SHGetKnownFolderPath(FOLDERID_ProgramData',self.source)
        self.assertNotIn('GetEnvironmentVariableW',self.source)
    def test_admin_pinned_exact_scope_and_expiry(self):
        for marker in ('ApprovedLtxPicture','CreatorTrust','KEY_WOW64_64KEY',
                       'field(L"PendingId")','field(L"ModelStackSha256")',
                       'field(L"ReceiptNonce")','field(L"CreatorExpiresUtc")',
                       'expiry<=now+900'):
            self.assertIn(marker,self.source)
        self.assertNotIn('subprocess',self.source)
    def test_windows_runner_resets_expected_refusal_exit_only_after_checks(self):
        workflow=(ROOT/'.github/workflows/nvp-post01f-r5r1-scm-cng-negative.yml').read_text(encoding='utf8')
        begin=workflow.index('      - name: Compile native LTX creator CMS signoff')
        end=workflow.index('      - name: Prove direct CLI and unapproved SCM start',begin)
        step=workflow[begin:end]
        unattended=step.index("if ($LASTEXITCODE -ne 91) { throw 'Unattended native creator signoff was not denied' }")
        unapproved=step.index("if ($LASTEXITCODE -ne 91) { throw 'Creator signoff without protected HKLM source was not denied' }")
        marker=step.index("Write-Host 'NVP_POST01F_NATIVE_CREATOR_WITHOUT_TRUST_DENIED'")
        reset=step.index('$global:LASTEXITCODE = 0')
        self.assertTrue(unattended < unapproved < marker < reset)
        self.assertEqual(step.count('$global:LASTEXITCODE = 0'),1)
        self.assertIn('Get-FileHash $exe -Algorithm SHA256',step)
        self.assertIn('NVP_POST01F_REAL_WINDOWS_SCM_MISSING_GRANT_DENIED',workflow)

    def test_creator_does_not_approve_film_or_change_audio(self):
        self.assertIn('Original Takes and sound remain unchanged',self.source)
        self.assertIn('requires your separate review',self.source)
        self.assertNotIn('StartServiceW(',self.source)
        self.assertNotIn('CreateProcessW(',self.source)

if __name__=='__main__':unittest.main()
