"""W1-G mandatory original role semantics, not caller-supplied truth."""
from hashlib import sha256
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest

from backend.nvp_w1g_first_party_result_verifier import (
    ROLE_OPERATIONS,verify_bounded_first_party_role,expected_native_math_picture,
)


class FirstPartyIndependentNativeResultVerifier(unittest.TestCase):
    def build(self,root,role,inputs,outbytes):
        for name,data in inputs.items():
            (root/name).write_bytes(data)
        output,operation=ROLE_OPERATIONS[role]
        (root/output).write_bytes(outbytes)
        scope={
            "job_id":"w1g_test_verified","project_id":"sample",
            "role":role,"plan_sha256":"a"*64,
        }
        result={
            "format":"nvp.w1g.native_worker_result.v1",
            "job_id":scope["job_id"],"project_id":scope["project_id"],
            "role":role,"plan_sha256":scope["plan_sha256"],
            "output_name":output,"operation":operation,
            "output_sha256":sha256(outbytes).hexdigest(),
            "output_bytes":len(outbytes),
            "full_film_pipeline_accepted":False,
        }
        return scope,result

    def test_true_capture_pcm_audit_and_no_fake_success_receipt(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            pcm=struct.pack("<4h",0,1,-500,-32768)
            audit=("format=nvp.w1g.pcm_intake.v1\n"
                   "samples=4\npeak=32768\n"
                   f"source_sha256={sha256(pcm).hexdigest()}\n").encode()
            scope,result=self.build(root,"original_capture",
                {"source.pcm":pcm},audit)
            self.assertTrue(verify_bounded_first_party_role(scope,result,root))
            forged=audit.replace(b"peak=32768",b"peak=32767")
            (root/"capture.manifest").write_bytes(forged)
            result["output_sha256"]=sha256(forged).hexdigest()
            result["output_bytes"]=len(forged)
            with self.assertRaisesRegex(PermissionError,"actual original"):
                verify_bounded_first_party_role(scope,result,root)

    def test_actual_audio_gain_not_merely_matching_own_output_hash(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            pcm=struct.pack("<4h",0,-500,30000,-30000)
            expected=struct.pack("<4h",0,-1000,32767,-32768)
            scope,result=self.build(root,"audio",
                {"source.pcm":pcm,"gain.txt":b"2 1\n"},expected)
            self.assertTrue(verify_bounded_first_party_role(scope,result,root))
            forged=struct.pack("<4h",0,-1000,30000,-30000)
            (root/"mix.pcm").write_bytes(forged)
            result["output_sha256"]=sha256(forged).hexdigest()
            with self.assertRaisesRegex(PermissionError,"exact rational PCM gain"):
                verify_bounded_first_party_role(scope,result,root)

    def test_editorial_and_delivery_recompute_original_inputs(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            pcm=struct.pack("<5h",3,5,7,9,11)
            selected=pcm[2:8]
            scope,result=self.build(root,"editorial",{
                "source.pcm":pcm,"edit.txt":b"1 3"},selected)
            self.assertTrue(verify_bounded_first_party_role(scope,result,root))
            (root/"edit.txt").write_bytes(b"0 3")
            with self.assertRaisesRegex(PermissionError,"sample selection"):
                verify_bounded_first_party_role(scope,result,root)
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            pic=b"P6\n16 16\n255\n"+bytes(range(256))*3
            mix=struct.pack("<2h",2,-2)
            delivery=b"NVPW1G01"+struct.pack("<QQ",len(pic),len(mix))+pic+mix
            scope,result=self.build(root,"delivery",{
                "render.ppm":pic,"mix.pcm":mix},delivery)
            self.assertTrue(verify_bounded_first_party_role(scope,result,root))
            (root/"mix.pcm").write_bytes(struct.pack("<2h",1,1))
            with self.assertRaisesRegex(PermissionError,"original picture/PCM"):
                verify_bounded_first_party_role(scope,result,root)

    def test_picture_and_receipt_field_authority(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            image=expected_native_math_picture(16,16)
            scope,result=self.build(root,"scene_render",
                {"scene.txt":b"16 16\n"},image)
            self.assertTrue(verify_bounded_first_party_role(scope,result,root))
            forged=bytearray(image)
            forged[-1] ^= 1
            (root/"render.ppm").write_bytes(forged)
            result["output_sha256"]=sha256(forged).hexdigest()
            with self.assertRaisesRegex(PermissionError,"independently computed scene"):
                verify_bounded_first_party_role(scope,result,root)
            (root/"render.ppm").write_bytes(image)
            result["output_sha256"]=sha256(image).hexdigest()
            result["full_film_pipeline_accepted"]=True
            with self.assertRaisesRegex(PermissionError,"sealed authorized role"):
                verify_bounded_first_party_role(scope,result,root)
            result["full_film_pipeline_accepted"]=False
            result["role"]="audio"
            with self.assertRaisesRegex(PermissionError,"sealed authorized role"):
                verify_bounded_first_party_role(scope,result,root)


if __name__=="__main__":
    unittest.main()
