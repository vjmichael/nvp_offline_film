"""WO2 measured cross-render comparison refuses fabricated parity."""
import unittest
from backend.nvp_wo2_renderer_comparison import compare_rendered_rgb

SHA="a"*64

class WO2ActualImageComparison(unittest.TestCase):
    def compare(self,left,right,**kw):
        return compare_rendered_rgb(
            native_rgb=left,independent_rgb=right,
            width=2,height=2,source_scene_sha256=SHA,
            native_receipt_sha256="b"*64,
            independent_receipt_sha256="c"*64,**kw)

    def test_real_rgb_planes_produce_measured_difference_without_fake_parity(self):
        image=bytes([20,40,60]*4)
        identical=self.compare(image,image)
        self.assertTrue(identical["within_requested_numeric_tolerance"])
        self.assertEqual(identical["mean_absolute_error"],0)
        self.assertFalse(identical["scene_linear_hydra_parity_proven"])
        self.assertFalse(identical["physical_display_calibrated"])
        other=bytes([255,40,60]*4)
        changed=self.compare(image,other)
        self.assertFalse(changed["within_requested_numeric_tolerance"])
        self.assertGreater(changed["root_mean_square_error"],0)
        self.assertEqual(changed["max_channel_error"],235)
        self.assertNotEqual(changed["native_image_rgb_sha256"],
                            changed["independent_image_rgb_sha256"])

    def test_refuses_missing_pixels_or_fake_receipts(self):
        image=bytes([20,40,60]*4)
        with self.assertRaises(ValueError):
            self.compare(image,b"")
        with self.assertRaises(ValueError):
            compare_rendered_rgb(
                native_rgb=image,independent_rgb=image,
                width=2,height=2,
                source_scene_sha256="not a SHA",
                native_receipt_sha256="b"*64,
                independent_receipt_sha256="c"*64)
        with self.assertRaises(ValueError):
            self.compare(image,image,max_mean_absolute_error=float("inf"))


if __name__=="__main__":
    unittest.main()
