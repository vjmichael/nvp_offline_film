"""WO2 hardware evidence must never equate device names with rendered pixels."""
import unittest
from backend.nvp_wo2_hardware_evidence import collect_windows_gpu_evidence


class WO2HardwareEvidence(unittest.TestCase):
    def test_native_adapter_enumeration_never_forges_render_pass(self):
        receipt=collect_windows_gpu_evidence()
        self.assertEqual(receipt["format"],
                         "nvp.wo2.windows_gpu_adapter_evidence.v1")
        self.assertFalse(receipt["hardware_gpu_frame_verified"])
        self.assertFalse(receipt["installed_webview2_pixel_readback_verified"])
        self.assertFalse(receipt["physical_display_calibrated"])
        self.assertFalse(receipt["render_delegate_hydra_parity_accepted"])
        self.assertIsInstance(receipt["adapters"],list)
        if receipt["platform"]!="Windows":
            self.assertEqual(receipt["status"],
                             "NATIVE_WINDOWS_HARDWARE_UNAVAILABLE")
        else:
            self.assertIn(receipt["status"],(
                "OS_ADAPTERS_ENUMERATED_UNVERIFIED",
                "NO_WINDOWS_DISPLAY_ADAPTERS"))


if __name__=="__main__":
    unittest.main()
