"""WO4 native file-backed DCP author: real SMPTE XML, fake MXF ESSENCE.

These are structural/negative tests ONLY: fake track bytes are intentional,
and therefore these do NOT establish actual CineCert/independent DCI approval.
A separate real codec pipeline test proves genuine native MXF.
"""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest

from backend.nvp_wo4_file_dcp import publish_file_backed_dcp
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure


class FileBackedPackage(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.out=self.root/"exports"
        self.out.mkdir()
        self.uid=str(uuid4())
        self.take="a"*64
        self.ids={name:str(uuid4()) for name in
                  ("picture","sound","cpl","pkl","assetmap","reel")}
        self.receipts={}
        for kind in ("picture","sound"):
            path=self.root/(kind+".mxf")
            path.write_bytes((b"UNVERIFIED_MXF_FIXTURE_"+kind.encode())*200)
            raw=path.read_bytes()
            self.receipts[kind]={
                "kind":kind,"asset_uuid":self.ids[kind],
                "source_take_sha256":self.take,
                "file_path":str(path),
                "file_sha256":sha256(raw).hexdigest(),
                "file_bytes":len(raw),"frame_count":3,"edit_rate":[24,1],
                "source_modified":False,"production_dcp_accepted":False,
                **({"profile":"2K_FLAT_24"} if kind=="picture" else {})
            }
        self.original={k:Path(x["file_path"]).read_bytes()
                       for k,x in self.receipts.items()}

    def publish(self,**kwargs):
        params=dict(job_id=self.uid,picture=self.receipts["picture"],
                    sound=self.receipts["sound"],title="Protected Film",
                    profile="2K_FLAT_24",frames=3,output_root=self.out,
                    ids=self.ids,check_cancel=lambda:False)
        params.update(kwargs)
        return publish_file_backed_dcp(**params)

    def test_structural_smpte_xml_pkl_and_asset_hashes_are_real(self):
        rec=self.publish()
        self.assertEqual(rec["status"],"STRUCTURAL_FILE_DCP_PUBLISHED")
        self.assertTrue(rec["whole_mxf_loaded_into_ram"] is False)
        folder=Path(rec["destination"])
        audit=inspect_dcp_structure(folder)
        self.assertEqual(audit["status"],"STRUCTURE_AND_SHA_VERIFIED")
        self.assertEqual(audit["reel_durations"],[3])
        self.assertEqual(audit["cpl_uuid"],self.ids["cpl"])
        self.assertFalse(audit["mxf_essence_verified"])
        self.assertFalse(audit["production_dcp_accepted"])
        self.assertEqual({x.name for x in folder.iterdir()},
            {"picture.mxf","sound.mxf","CPL.xml","PKL.xml",
             "ASSETMAP.xml","VOLINDEX.xml"})
        for kind in ("picture","sound"):
            self.assertEqual((folder/(kind+".mxf")).read_bytes(),
                             self.original[kind])
            self.assertEqual(Path(self.receipts[kind]["file_path"]).read_bytes(),
                             self.original[kind])
        self.assertFalse((self.out/(".nvp-wo4-dcp-stage-"+self.uid)).exists())

    def test_existing_dcp_and_originals_are_not_overwritten(self):
        self.publish()
        with self.assertRaises(FileExistsError):
            self.publish()
        for kind in self.original:
            self.assertEqual(
                Path(self.receipts[kind]["file_path"]).read_bytes(),
                self.original[kind])

    def test_failed_copy_keeps_stage_and_does_not_publish(self):
        calls=[0]
        def cancel():
            calls[0]+=1
            return calls[0]>=3
        with self.assertRaises(InterruptedError):
            self.publish(check_cancel=cancel)
        stage=self.out/(".nvp-wo4-dcp-stage-"+self.uid)
        self.assertTrue(stage.exists())
        self.assertFalse((self.out/("DCP_"+self.ids["cpl"])).exists())
        with self.assertRaises(FileExistsError):
            self.publish()
        self.assertTrue(stage.exists())

    def test_source_hash_mismatch_refuses_any_package(self):
        original=self.receipts["sound"]["file_sha256"]
        self.receipts["sound"]["file_sha256"]="0"*64
        with self.assertRaises(PermissionError):
            self.publish()
        self.assertEqual(list(self.out.iterdir()),[])
        self.receipts["sound"]["file_sha256"]=original

    def test_denied_or_changed_asset_identity_is_never_published(self):
        bad=dict(self.receipts["picture"])
        bad["asset_uuid"]=str(uuid4())
        with self.assertRaises(PermissionError):
            self.publish(picture=bad)
        self.assertEqual(list(self.out.iterdir()),[])


if __name__=="__main__":
    unittest.main()
