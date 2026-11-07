"""WO4-02 ST 428-1 deterministic coding, black/white and denial gates."""
from hashlib import sha256
import struct
import unittest
from unittest.mock import patch
from backend.nvp_wo4_xyz12_master import encode_linear_rgb_d65_to_xyz12

PROFILE="2K_FLAT_24"

def pixels(values):
    return b"".join(struct.pack("<fff",*v) for v in values)

class XYZ12Tests(unittest.TestCase):
    def encode(self,data,**kw):
        args=dict(profile=PROFILE,source_sha256=sha256(data).hexdigest(),
                  original_take_sha256="a"*64,creator_approved=True)
        args.update(kw)
        with patch("backend.nvp_wo4_xyz12_master.PROFILES",
                   {PROFILE:(len(data)//12,1,24)}):
            return encode_linear_rgb_d65_to_xyz12(data,**args)

    def test_source_black_neutral_and_white_are_not_8bit_rgb(self):
        original=pixels([(0.,0.,0.),(.18,.18,.18),(1.,1.,1.)])
        candidate=self.encode(original)
        self.assertEqual(candidate["xyz12"][:6],b"\x00"*6)
        values=[int.from_bytes(candidate["xyz12"][i:i+2],"big")
                for i in range(12,18,2)]
        # D65 reference white is NOT the DCI projector white.
        self.assertTrue(3500<values[0]<4095)
        self.assertTrue(3500<values[1]<4095)
        self.assertTrue(3500<values[2]<=4095)
        self.assertEqual(original,pixels([(0.,0.,0.),(.18,.18,.18),(1.,1.,1.)]))
        self.assertFalse(candidate["independently_calibrated"])
        self.assertFalse(candidate["production_picture_accepted"])

    def test_no_implicit_clipping_or_tonemapping(self):
        for rgb in [(1.01,0.,0.),(-.001,0.,0.),(float("nan"),0.,0.),
                    (float("inf"),0.,0.)]:
            with self.subTest(rgb=rgb):
                with self.assertRaises(ValueError):
                    self.encode(pixels([rgb]))

    def test_source_hash_and_creator_approval_enforced(self):
        data=pixels([(.1,.2,.3)])
        with self.assertRaises(PermissionError):
            self.encode(data,source_sha256="0"*64)
        with self.assertRaises(PermissionError):
            self.encode(data,creator_approved=False)
        with self.assertRaises(ValueError):
            self.encode(data,output_white_intent="DCI_PROJECTOR_AUTO_ADAPT")

    def test_deterministic_distinct_colors_and_xyz_sha(self):
        data=pixels([(.5,.0,.0),(.0,.5,.0),(.0,.0,.5)])
        one=self.encode(data)
        two=self.encode(data)
        self.assertEqual(one["xyz12_sha256"],two["xyz12_sha256"])
        self.assertEqual(sha256(one["xyz12"]).hexdigest(),one["xyz12_sha256"])
        self.assertNotEqual(one["xyz12"][:6],one["xyz12"][6:12])

if __name__=="__main__":
    unittest.main()
