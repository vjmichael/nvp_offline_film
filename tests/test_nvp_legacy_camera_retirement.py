"""DA-06: native still/proxy renderer must stay retired, not restored for CI."""
import unittest
from unittest.mock import patch

from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge


class RetiredNativeStillTests(unittest.TestCase):
    def test_native_still_entry_refuses_without_loading_worker(self):
        bridge=object.__new__(TrustedDesktopCameraBridge)
        with (patch.object(TrustedDesktopCameraBridge,"_native_window",
                           return_value=object()),
              patch.object(TrustedDesktopCameraBridge,"_get_host",
                           side_effect=AssertionError("Legacy worker started"))):
            caps=bridge.camera_render_capabilities()
            self.assertTrue(caps["legacy_render_retired"])
            self.assertFalse(caps["supports_approved_still"])
            self.assertFalse(caps["blender_discovered"])
            with self.assertRaisesRegex(PermissionError,"retired"):
                bridge.request_camera_still({"untrusted":"payload"})
            # No worker discovery, tickets, renderer or FFmpeg fallback.
if __name__=="__main__":
    unittest.main()
