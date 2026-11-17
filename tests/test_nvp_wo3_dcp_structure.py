"""WO3-01: independent SMPTE metadata integrity, not fake DCP essence."""
import base64
from hashlib import sha1
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from xml.etree import ElementTree as ET

from backend.nvp_wo3_dcp_structure import (
    inspect_dcp_structure,NS_AM,NS_PKL,NS_CPL,_xml)


def field(root,ns,name,value):
    elem=ET.SubElement(root,"{"+ns+"}"+name)
    elem.text=str(value)
    return elem


def uid():
    return "urn:uuid:"+str(uuid.uuid4())


class SMPTEIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.ids={k:uid() for k in ("am","pkl","cpl","pic","snd")}
        self.files={
            "picture.mxf":b"NOT_REAL_MXF_PICTURE",
            "sound.mxf":b"NOT_REAL_MXF_SOUND",
        }
        # Structural XML test only: realistic references, intentionally
        # non-MXF picture/sound bytes MUST remain production-unaccepted.
        cpl=ET.Element("{"+NS_CPL+"}CompositionPlaylist")
        field(cpl,NS_CPL,"Id",self.ids["cpl"])
        reels=ET.SubElement(cpl,"{"+NS_CPL+"}ReelList")
        reel=ET.SubElement(reels,"{"+NS_CPL+"}Reel")
        field(reel,NS_CPL,"Id",uid())
        assets=ET.SubElement(reel,"{"+NS_CPL+"}AssetList")
        for tag,key in (("MainPicture","pic"),("MainSound","snd")):
            track=ET.SubElement(assets,"{"+NS_CPL+"}"+tag)
            field(track,NS_CPL,"Id",self.ids[key])
            field(track,NS_CPL,"EditRate","24 1")
            field(track,NS_CPL,"IntrinsicDuration",3)
            field(track,NS_CPL,"EntryPoint",0)
            field(track,NS_CPL,"Duration",3)
        self.files["CPL.xml"]=ET.tostring(
            cpl,encoding="utf-8",xml_declaration=True)
        pkl=ET.Element("{"+NS_PKL+"}PackingList")
        field(pkl,NS_PKL,"Id",self.ids["pkl"])
        listed=ET.SubElement(pkl,"{"+NS_PKL+"}AssetList")
        for key,name,mime in (
            ("pic","picture.mxf","application/mxf"),
            ("snd","sound.mxf","application/mxf"),
            ("cpl","CPL.xml","text/xml"),
        ):
            entry=ET.SubElement(listed,"{"+NS_PKL+"}Asset")
            field(entry,NS_PKL,"Id",self.ids[key])
            field(entry,NS_PKL,"Size",len(self.files[name]))
            field(entry,NS_PKL,"Type",mime)
            field(entry,NS_PKL,"Hash",base64.b64encode(
                sha1(self.files[name]).digest()).decode("ascii"))
        self.files["PKL.xml"]=ET.tostring(
            pkl,encoding="utf-8",xml_declaration=True)
        assetmap=ET.Element("{"+NS_AM+"}AssetMap")
        field(assetmap,NS_AM,"Id",self.ids["am"])
        field(assetmap,NS_AM,"VolumeCount",1)
        mapped=ET.SubElement(assetmap,"{"+NS_AM+"}AssetList")
        for key,name in (
            ("pkl","PKL.xml"),("cpl","CPL.xml"),
            ("pic","picture.mxf"),("snd","sound.mxf"),
        ):
            item=ET.SubElement(mapped,"{"+NS_AM+"}Asset")
            field(item,NS_AM,"Id",self.ids[key])
            if key=="pkl":
                field(item,NS_AM,"PackingList","true")
            chunks=ET.SubElement(item,"{"+NS_AM+"}ChunkList")
            chunk=ET.SubElement(chunks,"{"+NS_AM+"}Chunk")
            field(chunk,NS_AM,"Path",name)
            field(chunk,NS_AM,"VolumeIndex",1)
            field(chunk,NS_AM,"Offset",0)
            field(chunk,NS_AM,"Length",len(self.files[name]))
        self.files["ASSETMAP.xml"]=ET.tostring(
            assetmap,encoding="utf-8",xml_declaration=True)
        for name,data in self.files.items():
            (self.root/name).write_bytes(data)

    def test_real_metadata_and_all_file_digests_do_not_certify_dummy_mxf(self):
        report=inspect_dcp_structure(self.root)
        self.assertEqual(report["status"],"STRUCTURE_AND_SHA_VERIFIED")
        self.assertEqual(report["asset_count"],3)
        self.assertEqual(report["reel_count"],1)
        self.assertEqual({x["kind"] for x in report["tracks"]},
                         {"picture","sound"})
        self.assertTrue(report["metadata_and_asset_hashes_verified"])
        self.assertFalse(report["mxf_essence_verified"])
        self.assertFalse(report["jpeg2000_xyz12_verified"])
        self.assertFalse(report["independent_dci_compliance_verified"])
        self.assertFalse(report["production_dcp_accepted"])

    def test_bad_assetmap_chunk_length_fails_even_when_pkl_sha_matches(self):
        tree=ET.parse(self.root/"ASSETMAP.xml")
        chunk=tree.getroot().find(
            ".//{"+NS_AM+"}Chunk/{"+NS_AM+"}Length")
        chunk.text=str(int(chunk.text)+1)
        tree.write(self.root/"ASSETMAP.xml",encoding="utf-8")
        with self.assertRaises(ValueError):
            inspect_dcp_structure(self.root)

    def test_unequal_picture_sound_cpl_duration_fails(self):
        tree=ET.parse(self.root/"CPL.xml")
        picture=tree.getroot().find(
            ".//{"+NS_CPL+"}MainPicture/{"+NS_CPL+"}Duration")
        picture.text="2"
        tree.write(self.root/"CPL.xml",encoding="utf-8")
        # Rebind the CPL PKL hash to isolate duration validation.
        altered=(self.root/"CPL.xml").read_bytes()
        pkl=ET.parse(self.root/"PKL.xml")
        for asset in pkl.getroot().findall(
                ".//{"+NS_PKL+"}Asset"):
            if asset.find("{"+NS_PKL+"}Id").text==self.ids["cpl"]:
                asset.find("{"+NS_PKL+"}Size").text=str(len(altered))
                asset.find("{"+NS_PKL+"}Hash").text=base64.b64encode(
                    sha1(altered).digest()).decode("ascii")
        pkl.write(self.root/"PKL.xml",encoding="utf-8")
        # Update AssetMap's PKL and CPL chunk sizes as well.
        am=ET.parse(self.root/"ASSETMAP.xml")
        for asset in am.getroot().findall(".//{"+NS_AM+"}Asset"):
            uid_text=asset.find("{"+NS_AM+"}Id").text
            if uid_text in (self.ids["cpl"],self.ids["pkl"]):
                target="CPL.xml" if uid_text==self.ids["cpl"] else "PKL.xml"
                asset.find(".//{"+NS_AM+"}Length").text=str(
                    (self.root/target).stat().st_size)
        am.write(self.root/"ASSETMAP.xml",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"durations disagree"):
            inspect_dcp_structure(self.root)

    def test_corrupted_mxf_fails_before_any_acceptance(self):
        (self.root/"picture.mxf").write_bytes(b"CORRUPTED")
        with self.assertRaises(RuntimeError):
            inspect_dcp_structure(self.root)

    def test_symlinked_mxf_is_not_read(self):
        (self.root/"sound.mxf").unlink()
        try:
            (self.root/"sound.mxf").symlink_to(self.root/"picture.mxf")
        except OSError:
            self.skipTest("Native OS denies symlink creation")
        with self.assertRaises(PermissionError):
            inspect_dcp_structure(self.root)

    def test_malicious_dtd_fails_closed(self):
        (self.root/"CPL.xml").write_bytes(
            b'<!DOCTYPE x [<!ENTITY leak SYSTEM "file:///etc/passwd">]>'+
            self.files["CPL.xml"])
        with self.assertRaises(ValueError):
            _xml(self.root,"CPL.xml",NS_CPL,"CompositionPlaylist")
        # The complete DCP scanner must independently reject the modified
        # CPL by PKL hash even before it reaches XML/DTD inspection.
        with self.assertRaises(RuntimeError):
            inspect_dcp_structure(self.root)

    def test_unknown_pkl_asset_fails(self):
        contents=(self.root/"ASSETMAP.xml").read_bytes()
        (self.root/"ASSETMAP.xml").write_bytes(
            contents.replace(b"picture.mxf",b"missing.mxf"))
        with self.assertRaises(PermissionError):
            inspect_dcp_structure(self.root)


if __name__=="__main__":
    unittest.main()
