"""Real WebView2 startup preflight contracts; never synthesize GUI success.

The GUI itself must still be separately accepted on interactive Windows.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from tools.nvp_desktop_alpha import (
    _webview_profile_dir, _windows_session_id,
)


class WebView2NativeProfileTests(unittest.TestCase):
    def test_explicit_writable_isolated_profile(self):
        with tempfile.TemporaryDirectory(prefix="nvp-webview2-") as tmp:
            home=Path(tmp)
            result=Path(_webview_profile_dir(home))
            self.assertEqual(result,home/"WebView2Profile")
            self.assertTrue(result.is_dir())
            self.assertFalse(list(result.glob(".nvp-write-probe-*")))
            self.assertEqual(Path(_webview_profile_dir(home)),result)

    def test_unwritable_profile_node_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="nvp-webview2-") as tmp:
            root=Path(tmp)
            (root/"WebView2Profile").write_bytes(b"not a directory")
            with self.assertRaises((OSError, RuntimeError)):
                _webview_profile_dir(root)

    def test_symlink_profile_is_never_followed(self):
        with tempfile.TemporaryDirectory(prefix="nvp-webview2-") as tmp:
            root=Path(tmp)
            target=root/"elsewhere"
            target.mkdir()
            try:
                (root/"WebView2Profile").symlink_to(target,target_is_directory=True)
            except (OSError,NotImplementedError):
                self.skipTest("Creating directory symlinks not permitted by OS")
            with self.assertRaises(PermissionError):
                _webview_profile_dir(root)

    def test_native_session_is_real_os_observation(self):
        sid=_windows_session_id()
        if __import__("os").name=="nt":
            self.assertIsInstance(sid,int)
            self.assertGreaterEqual(sid,0)
        else:
            self.assertIsNone(sid)


if __name__=="__main__":
    unittest.main()
