"""WO4 LF02 actual native three-source-frame picture Reel→MXF→unwrap.

No codec mocks: independent interpreter per durable checkpoint, real approved
OpenJPEG + CineCert executables, real OpenUSD source Take, full 2K XYZ12
picture pixels, ordered immutable decision and all codestream SHAs reopened.
This validates file-spooled picture *MXF*, not a finished DCP or projector.
"""
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from test_nvp_wo3_native_delivery import WO3OriginalCinemaAuthoring
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_production_cinema import CinemaJournal
from backend.nvp_wo4_pcm_master import master_pcm24_candidate
from backend.nvp_wo4_master_qc import evaluate_master_candidates
from backend.nvp_wo4_mastering_decision import register_mastering_decision

NEEDED=("NVP_NATIVE_OPENJPEG","NVP_NATIVE_ASDCP_WRAP",
        "NVP_NATIVE_ASDCP_INFO","NVP_NATIVE_ASDCP_UNWRAP")


@unittest.skipUnless(all(os.environ.get(x) for x in NEEDED),
    "Exact reviewed native OpenJPEG/asdcplib binaries required")
class ActualFileBackedProductionReel(unittest.TestCase):
    def codec(self,env,product):
        p=Path(os.environ[env]).resolve(strict=True)
        return ApprovedCodecBinary(p,product=product,sha256=digest_file(p))

    def test_native_supervisor_frame_checkpoint_restart_mxf_and_full_unwrap(self):
        fixture=WO3OriginalCinemaAuthoring(
            "test_real_smpte_package_metadata_is_written_and_reopened")
        fixture.setUp()
        try:
            root=Path(fixture.tmp.name).resolve()
            journal=CinemaJournal(root/"production-journal")
            sources=[]
            images=[]
            for n,code in enumerate((128,500,1200)):
                pixels=(code.to_bytes(2,"big")*3)*(1998*1080)
                picture={
                    "format":"nvp.wo4.xyz12_master_candidate.v1",
                    "xyz12":pixels,"xyz12_sha256":sha256(pixels).hexdigest(),
                    "original_take_sha256":fixture.sha,
                    "profile":"2K_FLAT_24","width":1998,"height":1080,
                    "source_modified":False,"production_picture_accepted":False}
                images.append(picture)
                file=root/f"approved_frame_{n}.xyz12"
                file.write_bytes(pixels)
                sources.append(file)
            pcm=b"\x00\x00\x00\x10\x00\x00"*6000
            sound=master_pcm24_candidate(
                pcm,source_sha256=sha256(pcm).hexdigest(),
                original_take_sha256=fixture.sha,cinema_frames=3,
                channel_layout="stereo",creator_approved=True)
            qc=evaluate_master_candidates(images[0],sound)
            approved=register_mastering_decision(
                fixture.index,fixture.pid,take_id="FrozenFixture",
                take_revision=1,take_sha256=fixture.sha,
                picture=images[0],ordered_pictures=images,
                sound=sound,qc=qc,
                decision_id="ApprovedSpoolReel",approve=lambda _:True)
            self.assertEqual(approved["status"],"MASTERING_DECISION_RECORDED")
            job=journal.submit_reel(
                fixture.index,fixture.pid,
                mastering_decision_id="ApprovedSpoolReel",
                frame_sources=[str(x) for x in sources],
                openjpeg=self.codec("NVP_NATIVE_OPENJPEG","OpenJPEG-opj_compress"),
                wrapper=self.codec("NVP_NATIVE_ASDCP_WRAP","ASDCP-asdcp_wrap"),
                info=self.codec("NVP_NATIVE_ASDCP_INFO","ASDCP-asdcp_info"),
                approve=lambda scope:scope["source_take_sha256"]==fixture.sha)
            self.assertEqual(job["status"],"QUEUED")
            repo=Path(__file__).resolve().parents[1]
            for index in range(4):
                proc=subprocess.run([
                    sys.executable,"-m","backend.nvp_production_supervisor",
                    "once","--state-root",str(journal.root)],
                    cwd=str(repo),stdin=subprocess.DEVNULL,
                    capture_output=True,text=True,timeout=360,check=False)
                self.assertEqual(proc.returncode,0,proc.stderr[-900:])
                self.assertNotIn("REVIEW_REQUIRED",proc.stdout,proc.stdout[-900:])
                snap=journal.status(job["job_id"])
                if index<3:
                    self.assertEqual(snap["verified_segments"],index+1)
                else:
                    self.assertEqual(snap["state"],"OUTPUT_READY")
            reel=journal.reel(job["job_id"])
            spool=journal.spool(job["job_id"])
            track=spool/"picture.mxf"
            self.assertTrue(track.is_file())
            self.assertEqual(digest_file(track),reel["track_sha256"])
            self.assertEqual(journal.cinema_reconcile()["jobs"][0]["status"],
                             "RECONCILED")
            unwrap=self.codec("NVP_NATIVE_ASDCP_UNWRAP","ASDCP-asdcp_unwrap")
            with TemporaryDirectory(prefix="nvp-spool-unwrapped-") as td:
                where=Path(td)
                # The verified MXF is immutable input; child sees a private
                # same-volume copy rather than a source-owned hard link.
                import shutil
                shutil.copyfile(track,where/"picture.mxf")
                unwrap.run(["-d","3","picture.mxf","p_"],
                           cwd=where,timeout=3600)
                for i,expected in enumerate(sources):
                    file=where/f"p_{i:06d}.j2c"
                    source_codestream=spool/"frames"/f"{i:06d}.j2c"
                    self.assertTrue(file.is_file())
                    self.assertEqual(digest_file(file),
                                     digest_file(source_codestream))
            for file,expected in zip(sources,images):
                self.assertEqual(digest_file(file),expected["xyz12_sha256"])
            self.assertEqual(fixture.index.read_revision(
                fixture.pid,"FrozenFixture",1)["document_sha256"],fixture.sha)
            print("WO4_SUPERVISED_DISK_NATIVE_PICTURE_MXF:",{
                "job_id":job["job_id"],
                "frame_checkpoints":journal.status(job["job_id"])["verified_segments"],
                "picture_mxf_sha256":reel["track_sha256"],
                "full_native_unwrap_sha_verified":True,
                "whole_reel_in_ram":False,
                "production_dcp_accepted":False},flush=True)
        finally:
            fixture.tmp.cleanup()


if __name__=="__main__":
    unittest.main()
