"""R2-R2-R1 exact source qualifier CRLF repair, not an installed peer."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('r2r2r1_qualifier',
    ROOT / 'scripts' / 'nvp_lu_01f_r2r2_qualification.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SOURCE_WORKTREE = (ROOT / module.NVP_PROTO_PATH).read_bytes()
if b'\r' in SOURCE_WORKTREE.replace(b'\r\n', b''):
    raise RuntimeError('Noncanonical source worktree for CRLF regression fixture')
ORIGINAL = SOURCE_WORKTREE.replace(b'\r\n', b'\n')


class ExactSourceCRLFQualification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        path = self.root / module.NVP_PROTO_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ORIGINAL)
        self.path = path

    def test_exact_lf_and_crlf_worktree_are_same_blob(self):
        module.require_exact_domain_source(self.root)
        self.path.write_bytes(ORIGINAL.replace(b'\n', b'\r\n'))
        module.require_exact_domain_source(self.root)

    def test_content_or_lone_carriage_return_cannot_be_normalized(self):
        for mutated in (ORIGINAL + b'// extra\n',
                        ORIGINAL.replace(b'syntax =', b'syntzx =', 1),
                        ORIGINAL.replace(b'\n', b'\r', 1)):
            with self.subTest(change=mutated[:30]):
                self.path.write_bytes(mutated)
                with self.assertRaises(RuntimeError):
                    module.require_exact_domain_source(self.root)

    @unittest.skipUnless(shutil.which('git'), 'Git executable unavailable')
    def test_reject_changed_committed_blob_even_if_worktree_restored(self):
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', module.NVP_PROTO_PATH], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Test',
                        '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'locked'], check=True)
        module.require_exact_domain_source(self.root)
        self.path.write_bytes(ORIGINAL.replace(b'\n', b'\r\n'))
        module.require_exact_domain_source(self.root)
        self.path.write_bytes(ORIGINAL + b'// malicious\n')
        subprocess.run(['git', '-C', str(self.root), 'add', module.NVP_PROTO_PATH], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Test',
                        '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'changed'], check=True)
        self.path.write_bytes(ORIGINAL)
        with self.assertRaisesRegex(RuntimeError, 'Git object was repinned'):
            module.require_exact_domain_source(self.root)


if __name__ == '__main__':
    unittest.main()
