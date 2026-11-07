"""WO4 real 4K native OpenJPEG/CineCert file-spool acceptance.

Three actual 4096x1716 XYZ12 4K frames, no full reel in Python RAM.
This is a 4K codec/spool pilot, NOT a 3-hour installed throughput test.
"""
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import unittest

from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_wo4_picture_spool import (
    encode_disk_xyz12,wrap_disk_j2k_picture)


@unittest.skipUnless(
    all(os.environ.get(x) for x in (
        "NVP_NATIVE_OPENJPEG","NVP_NATIVE_ASDCP_WRAP",
        "NVP_NATIVE_ASDCP_INFO","NVP_NATIVE_ASDCP_UNWRAP")),
    "Pinned real 4K OpenJPEG/CineCert tools required")
class Native4KPicturePilot(unittest.TestCase):
    def codec(self,env,product):
        file=Path(os.environ[env]).resolve(strict=True)
        return ApprovedCodecBinary(file,product=product,sha256=digest_file(file))

    def test_three_distinct_full_4k_frames_spool_and_native_mxf(self):
        with TemporaryDirectory(prefix="nvp-wo4-4k-") as temp:
            root=Path(temp).resolve()
            frames=root/"frames"
            frames.mkdir()
            for i,code in enumerate((20,1000,3000)):
                raw=root/f"original_xyz12_{i}.raw"
                pixel=code.to_bytes(2,"big")*3
                source=sha256()
                remaining=4096*1716
                with raw.open("xb") as out:
                    while remaining:
                        pixels=min(remaining,8192)
                        chunk=pixel*pixels
                        out.write(chunk)
                        source.update(chunk)
                        remaining-=pixels
                work=root/f"work_{i}"
                work.mkdir()
                receipt=encode_disk_xyz12(
                    self.codec("NVP_NATIVE_OPENJPEG","OpenJPEG-opj_compress"),
                    profile="4K_SCOPE_24",source_path=str(raw),
                    source_sha256=source.hexdigest(),
                    private_work=work,check_cancel=lambda:False,
                    timeout=900)
                self.assertEqual(receipt["status"],"ENCODED_J2K_STAGE_VERIFIED")
                self.assertFalse(receipt["input"]["whole_reel_loaded_into_ram"])
                file=frames/f"{i:06d}.j2c"
                os.link(work/"frame.j2c",file)
                self.assertEqual(digest_file(file),receipt["codestream_sha256"])
                self.assertEqual(digest_file(raw),source.hexdigest())
            stage=root/"mxf-stage"
            stage.mkdir()
            picture=wrap_disk_j2k_picture(
                self.codec("NVP_NATIVE_ASDCP_WRAP","ASDCP-asdcp_wrap"),
                self.codec("NVP_NATIVE_ASDCP_INFO","ASDCP-asdcp_info"),
                frames_dir=frames,stage_dir=stage,frame_count=3,
                profile="4K_SCOPE_24",asset_uuid=str(uuid4()),
                check_cancel=lambda:False,timeout=900)
            self.assertEqual(picture["status"],
                             "NATIVE_PICTURE_MXF_STAGE_VERIFIED")
            self.assertEqual(picture["frame_count"],3)
            self.assertFalse(picture["whole_mxf_loaded_into_ram"])
            self.assertEqual(digest_file(stage/"picture.mxf"),
                             picture["file_sha256"])
            # Real MXF info/readback is exercised above. The 2K path has
            # a full independent decoder, while 4K cinema ingest remains
            # a distinct acceptance gate.
            self.assertFalse(picture["independent_dci_validator_passed"])
            print("WO4_NATIVE_4K_PILOT",{
                "real_4k_frames":3,"picture_mxf_sha256":picture["file_sha256"],
                "all_sources_preserved":True,
                "whole_movie_loaded_into_ram":False},flush=True)


if __name__=="__main__":
    unittest.main()
