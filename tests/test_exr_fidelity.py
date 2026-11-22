"""B9 OpenEXR header parser tests; synthetic headers are NOT render evidence."""
from __future__ import annotations

import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_exr_fidelity import inspect_exr_header


def attribute(name,kind,payload):
    return name.encode()+b"\0"+kind.encode()+b"\0"+struct.pack("<I",len(payload))+payload


def minimal_exr(*,width=160,height=90,channel_type=2,omit=None):
    channels=b"".join(c.encode()+b"\0"+
         struct.pack("<iB3xii",channel_type,0,1,1) for c in "RGBA")+b"\0"
    attrs=[
      ("channels","chlist",channels),
      ("compression","compression",b"\3"),
      ("dataWindow","box2i",struct.pack("<iiii",0,0,width-1,height-1)),
      ("displayWindow","box2i",struct.pack("<iiii",0,0,width-1,height-1)),
      ("lineOrder","lineOrder",b"\0"),
      ("pixelAspectRatio","float",struct.pack("<f",1.)),
      ("screenWindowCenter","v2f",struct.pack("<ff",0.,0.)),
      ("screenWindowWidth","float",struct.pack("<f",1.)),
    ]
    return (bytes.fromhex("762f3101")+struct.pack("<I",2)+
            b"".join(attribute(*e) for e in attrs if e[0]!=omit)+
            b"\0"+b"\0"*128)


class NativeOpenEXRHeaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.p=Path(self.tmp.name)/"frame_000001.exr"

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_standard_layout_requires_32bit_float_all_rgba_channels(self):
        self.p.write_bytes(minimal_exr())
        actual=inspect_exr_header(self.p,width=160,height=90)
        self.assertTrue(actual["rgba_float32"])
        self.assertEqual(actual["channel_names"],["A","B","G","R"])
        self.assertEqual(actual["width"],160)
        self.assertEqual(actual["compression_code"],3)

    def test_16bit_half_exr_must_never_claim_32bit_float(self):
        self.p.write_bytes(minimal_exr(channel_type=1))
        with self.assertRaisesRegex(RuntimeError,"32-bit"):
            inspect_exr_header(self.p,width=160,height=90)

    def test_wrong_real_frame_dimensions_refuse(self):
        self.p.write_bytes(minimal_exr())
        with self.assertRaisesRegex(RuntimeError,"dimensions"):
            inspect_exr_header(self.p,width=161,height=90)

    def test_missing_required_channel_attribute_refuses(self):
        self.p.write_bytes(minimal_exr(omit="channels"))
        with self.assertRaisesRegex(RuntimeError,"channels"):
            inspect_exr_header(self.p,width=160,height=90)

    def test_corrupt_magic_or_non_exr_never_proves_native_float(self):
        self.p.write_bytes(b"EXR"+b"\0"*200)
        with self.assertRaisesRegex(RuntimeError,"OpenEXR"):
            inspect_exr_header(self.p,width=160,height=90)

    def test_symlinked_exr_is_not_accepted(self):
        self.p.write_bytes(minimal_exr())
        link=Path(self.tmp.name)/"escape.exr"
        try:
            link.symlink_to(self.p)
        except (OSError,NotImplementedError):
            self.skipTest("Windows lacks symlink privilege")
        with self.assertRaisesRegex(RuntimeError,"symlinked"):
            inspect_exr_header(link,width=160,height=90)

    def test_truncated_or_multipart_exr_refused(self):
        self.p.write_bytes(bytes.fromhex("762f3101")+struct.pack("<I",2|0x1000)+b"\0"*200)
        with self.assertRaisesRegex(RuntimeError,"multipart|flags"):
            inspect_exr_header(self.p,width=160,height=90)


if __name__=="__main__":
    unittest.main()
