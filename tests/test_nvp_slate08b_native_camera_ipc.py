"""DA-06 regression: retired SLATE-08B external still/proxy bridge is fail-closed.

Historical pre-retirement camera delivery tests remain in Git history.
The active native OpenUSD viewer does not issue still-render jobs.
"""
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_project_access import ProjectAccess


class Window:
    def __init__(self, url="http://127.0.0.1:7777/"):
        self.url = url
        self.questions = 0
    def get_current_url(self):
        return self.url
    def create_confirmation_dialog(self, *args):
        self.questions += 1
        return True


class CinemaDependencyIsolation(unittest.TestCase):
    def test_camera_metadata_imports_need_no_numerical_runtime(self):
        import subprocess
        import sys
        code = r"""
import importlib.abc
import sys
class BlockNumerics(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('numpy', 'scipy'):
            raise ModuleNotFoundError('numeric runtime intentionally absent', name=fullname)
sys.meta_path.insert(0, BlockNumerics())
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge
from backend.nvp_wo4_xyz12_master import FORMAT
from backend.nvp_dci_dual_decode import compare_xyz12
from backend.nvp_dci_surround import validate_layout, route_block
from backend.nvp_dci_color_reference import REVISION
assert FORMAT and REVISION and TrustedDesktopCameraBridge
assert validate_layout('5.1', ['L','R','C','LFE','Ls','Rs']) == 6
for operation in (lambda: compare_xyz12(bytes(6),bytes(6)),
                  lambda: route_block(bytes(18),'5.1',['L','R','C','LFE','Ls','Rs'])):
    try:
        operation()
    except ModuleNotFoundError as exc:
        assert exc.name == 'numpy'
    else:
        raise AssertionError('Numeric work executed without required runtime')
assert 'numpy' not in sys.modules and 'scipy' not in sys.modules
"""
        # -S avoids environment-specific sitecustomize preloading NumPy.
        code = "import sys\nsys.path[:] = " + repr(sys.path) + "\n" + code
        result = subprocess.run([sys.executable, '-S', '-c', code], capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class RetiredCameraContract(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.index = FilmIndex(Studio(Path(self.temp.name) / 'studio.sqlite3'))
        self.window = Window()
        self.created_hosts = []
        def factory(callback):
            self.created_hosts.append(callback)
            raise AssertionError("Retired renderer host must never be created")
        self.bridge = TrustedDesktopCameraBridge(
            self.index, origin="http://127.0.0.1:7777", host_factory=factory)
        self.bridge._attach_window(self.window)
        self.addCleanup(self.bridge._close)

    def test_capabilities_advertise_retirement(self):
        capabilities = self.bridge.camera_render_capabilities()
        self.assertTrue(capabilities["legacy_render_retired"])
        self.assertTrue(capabilities["native_data_first_scene"])
        self.assertFalse(capabilities["supports_approved_still"])
        self.assertFalse(capabilities["blender_discovered"])
        self.assertFalse(capabilities["supports_cancel"])

    def test_every_still_request_is_denied_before_host_or_consent(self):
        for payload in ({}, None, {"source_tick": 0}, {"source_tick": True}):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(PermissionError, "retired"):
                    self.bridge.request_camera_still(payload)
        self.assertEqual(self.created_hosts, [])
        self.assertEqual(self.window.questions, 0)

    def test_retired_poll_and_cancel_cannot_recover_forged_old_ticket(self):
        self.bridge._tickets["historical_ticket"] = {
            "project_id": "f" * 32, "job_id": "legacy_job"}
        for operation in (self.bridge.poll_camera_still,
                          self.bridge.cancel_camera_still):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(PermissionError, "retired"):
                    operation("historical_ticket")
        self.assertEqual(self.created_hosts, [])
        self.assertEqual(self.window.questions, 0)

    def test_untrusted_origin_is_rejected(self):
        self.window.url = "https://outside.example/"
        with self.assertRaises(PermissionError):
            self.bridge.camera_render_capabilities()
        with self.assertRaises(PermissionError):
            self.bridge.request_camera_still({})
        self.assertEqual(self.created_hosts, [])

    def test_native_bridge_refuses_protected_movie_data(self):
        protected=self.index.studio.create_project("Secret film","Hidden scene")
        lock=ProjectAccess(self.index.studio.db_path)
        self.assertFalse(lock.any_protected())
        restricted=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:7777",
            host_factory=lambda *_: self.fail("Worker cannot run"),
            project_lock_check=lock.any_protected)
        restricted._attach_window(self.window)
        self.addCleanup(restricted._close)
        self.assertTrue(restricted.camera_render_capabilities()["native_window"])
        lock.protect(protected["id"],"A long original protected movie passphrase")
        for action in (
            lambda:restricted.plan02c_catalog(protected["id"]),
            lambda:restricted.data_av_catalog(protected["id"]),
            lambda:restricted.data_av_capture_catalog(protected["id"]),
            lambda:restricted.data_av_audio_window("guessed",0,10),
            lambda:restricted.camera_render_capabilities(),
        ):
            with self.subTest(action=action):
                with self.assertRaisesRegex(PermissionError,"protected"):
                    action()
        self.assertEqual(restricted.data_av_stop("old")["status"],"STOPPED")
        denied=restricted.data_av_capture_cancel()
        self.assertFalse(denied["terminal_verified"])
        self.assertFalse(denied["source_exposed"])

    def test_closed_window_cannot_restart_renderer(self):
        self.bridge._close()
        with self.assertRaises(PermissionError):
            self.bridge.request_camera_still({})
        self.assertEqual(self.created_hosts, [])


if __name__ == "__main__":
    unittest.main()
