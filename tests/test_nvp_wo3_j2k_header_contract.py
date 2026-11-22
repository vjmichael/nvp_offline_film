"""Original pure WO3 header test, extracted from historical native-delivery.
The original mixed suite must also be restored when codecs are integrated.
Synthetic marker bytes do not establish native decoder or DCI acceptance.
"""
import stat
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.nvp_wo3_j2k_audit import inspect_j2k_header
from backend.nvp_wo3_dcp_structure import _asset_file, _child, NS_AM

def synthetic_header(*,width=1998,height=1080,bits=12,progression=4,rsiz=3):
    # Real JPEG2000 marker byte grammar but NOT a real encoded picture.
    siz=(struct.pack(">HH8IH",47,rsiz,width,height,0,0,
                     width,height,0,0,3)+
         bytes([bits-1,1,1])*3)
    cod=b"\x00"+bytes([progression])+b"\x00\x01"+bytes([0,5,4,4,0,0])
    return (b"\xff\x4f\xff\x51"+siz+b"\xff\x52"+
            struct.pack(">H",len(cod)+2)+cod+
            b"\xff\x90\x00\x0a"+b"\x00"*24)


class HistoricalWO3HeaderAndPathContract(unittest.TestCase):
    def test_j2k_marker_header_only_never_claims_actual_decode(self):
        header=inspect_j2k_header(synthetic_header(),"2K_FLAT_24")
        self.assertEqual(header["components"][0]["precision"],12)
        self.assertFalse(header["full_codestream_decoded"])
        self.assertFalse(header["dci_compliant"])
        for raw in (
            synthetic_header(bits=8),
            synthetic_header(progression=0),
            synthetic_header(rsiz=0),
            synthetic_header(width=2048),
            b"\x00"*120,
        ):
            with self.subTest(blob=raw[:10]):
                with self.assertRaises(ValueError):
                    inspect_j2k_header(raw,"2K_FLAT_24")

    def test_windows_device_names_and_reparse_entries_are_not_read(self):
        for name in ("CON.xml","NUL.mxf","COM1.xml","LPT9.mxf","bad."):
            with self.subTest(name=name),self.assertRaises(PermissionError):
                _asset_file(Path("."),name)
        with patch.object(Path,"lstat",return_value=SimpleNamespace(
                st_mode=stat.S_IFREG,st_file_attributes=0x400)):
            with self.assertRaises(PermissionError):
                _asset_file(Path("."),"picture.mxf")

    def test_duplicate_xml_singleton_refused(self):
        from xml.etree import ElementTree as ET
        root=ET.Element("root")
        for _ in range(2):
            ET.SubElement(root,"{"+NS_AM+"}VolumeCount").text="1"
        with self.assertRaisesRegex(ValueError,"Duplicate singleton"):
            _child(root,"VolumeCount",NS_AM)


if __name__=="__main__":
    unittest.main()
