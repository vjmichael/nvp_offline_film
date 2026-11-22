"""COLOR-01A negative tests. Native Blender and FFmpeg acceptance is separate."""
import struct
import tempfile
import unittest
from pathlib import Path

from backend.nvp_color_exr import exr_info, check_frame, PIXEL_PNG, PIXEL_EXR
from backend.nvp_presentation_pipeline import PresentationPipeline, ENGINE, PBR_ENGINE
from backend.nvp_studio import Studio


def exr_header(*, ptype=1, compressor=3, channels=("R","G","B","A"), version=2):
    def attr(name,typ,payload):
        return name.encode()+b"\0"+typ.encode()+b"\0"+struct.pack("<I",len(payload))+payload
    ch=b""
    for cname in channels:
        ch+=cname.encode()+b"\0"+struct.pack("<i",ptype)+b"\0"*4+struct.pack("<ii",1,1)
    ch+=b"\0"
    box=struct.pack("<4i",0,0,31,15)
    return (b"\x76\x2f\x31\x01"+struct.pack("<I",version)+
            attr("channels","chlist",ch)+
            attr("dataWindow","box2i",box)+
            attr("compression","compression",bytes([compressor]))+b"\0"+b"\0"*64)


class EXRSourceTests(unittest.TestCase):
    def test_valid_half_float_rgba_contract(self):
        info=exr_info(exr_header())
        self.assertEqual(info,{"width":32,"height":16,"channels":["A","B","G","R"],
                               "pixel_type":"HALF","compression":"ZIP"})
        self.assertEqual(check_frame(exr_header(),PIXEL_EXR,None)["media_type"],"image/x-exr")
        self.assertEqual(exr_info(exr_header(version=0x402)),info)  # Blender LONG_NAMES flag

    def test_reject_bad_exr_header_and_nonhalf_format(self):
        for blob in [b"",b"PNG",exr_header(ptype=2),
                     exr_header(channels=("R","G","B")),
                     exr_header(compressor=0),
                     exr_header(version=0x202),  # tiled must remain disallowed
                     exr_header(version=0x1002), # multipart must remain disallowed
                     exr_header()[:24],exr_header().replace(b"dataWindow",b"dataWindowX",1)]:
            with self.subTest(size=len(blob)),self.assertRaises(RuntimeError):
                exr_info(blob)

    def test_renderer_capabilities_distinguish_exr_from_png(self):
        a,b=PresentationPipeline.available_engines()
        self.assertEqual(a["engine"],ENGINE)
        self.assertEqual(a["pixel_contracts"],[PIXEL_PNG])
        self.assertEqual(b["engine"],PBR_ENGINE)
        self.assertEqual(b["pixel_contracts"],[PIXEL_PNG,PIXEL_EXR])

    def test_workbench_exr_rejected_before_render_or_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=Studio(Path(tmp)/"f.db")
            pid=st.create_project("Film","EXR")["id"]
            pipe=PresentationPipeline(st)
            with self.assertRaisesRegex(ValueError,"Cycles"):
                pipe.render(pid,"valid_take","frame01",Path(tmp)/"render",
                            engine=ENGINE,pixel_contract=PIXEL_EXR)
            self.assertFalse((Path(tmp)/"render").exists())

if __name__=="__main__":
    unittest.main()
