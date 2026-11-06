"""AUDIO-01K.3 actual DCP-o-matic + DcpDoctor native acceptance.

This test is intentionally opt-in for machines with the real, installed
cinema tools: a fake MKF/XML fixture can never satisfy native acceptance.
Previous NVP final AV approval is a controlled fixture; the actual DCP encode,
MXF/JPEG2000 production, strict independent QC, Job Object/process containment,
FilmIndex candidate and restart verification are all real.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from backend.nvp_audio01k3_native_host import NativeAudio01K3Host
from backend.nvp_audio01k_distribution import FORMAT as DIST_FORMAT
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_resource_ledger import TaskLedger

TOOLS=("dcpomatic2_create","dcpomatic2_cli","dcpdoctor","ffmpeg","ffprobe")


def native_tools_available():
    return all(shutil.which(item) for item in TOOLS)


class AuthorizedDistribution:
    """Test fixture only: real NVP upstream authorization tested in AUDIO-01K."""
    def __init__(self,cap):
        self.cap=cap

    def verify(self,pid,distribution_id,destination,*args,**kwargs):
        record=self.cap.index.read_revision(pid,distribution_id,1)
        movie=Path(destination)/"feature_master.mov"
        if hashlib.sha256(movie.read_bytes()).hexdigest()!=record["data"]["delivered_movie_sha256"]:
            raise RuntimeError("Fixture approved MOV changed")
        return {"status":"VERIFIED_MEZZANINE_DISTRIBUTION"}


def ledger(root):
    return TaskLedger(root/"ledger",sampler=lambda:ResourceSnapshot(
        0,16384,15000,0,tuple()))


def setup(root):
    cap=DigitalCapture(Studio(root/"studio.sqlite3"))
    pid=cap.studio.create_project("DCP real JPEG2000 24fps",
                                  "Native cinema integration acceptance")["id"]
    source=root/"mezzanine"
    source.mkdir()
    mov=source/"feature_master.mov"
    subprocess.run(["ffmpeg","-nostdin","-hide_banner","-v","error","-xerror",
        "-f","lavfi","-i","testsrc2=size=128x72:rate=24:duration=1",
        "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=1",
        "-frames:v","24","-c:v","prores_ks","-profile:v","3",
        "-pix_fmt","yuv422p10le","-c:a","pcm_s24le",
        "-ar","48000","-ac","2","-f","mov",str(mov)],check=True,timeout=120)
    sha=hashlib.sha256(mov.read_bytes()).hexdigest()
    cap.index.register_revision(pid,"mezzanine","master",{
        "format":DIST_FORMAT,"status":"verified_mezzanine_distribution",
        "delivered_movie_sha256":sha,"frames":24,"dcp_delivered":False
    },expected_revision=0,dependencies=[])
    return cap,pid,source


class NativeDCPAcceptance(unittest.TestCase):
    def test_real_smpte_2k_assets_and_restart(self):
        missing=[tool for tool in TOOLS if shutil.which(tool) is None]
        self.assertFalse(missing,"Real cinema tool dependencies missing: "+", ".join(missing))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cap,pid,mezzanine=setup(root)
            host=NativeAudio01K3Host(
                cap,ledger(root),root/"dcphost",
                distribution_host=AuthorizedDistribution(cap),
                verify_creator_action=lambda *_:True,strict_linux_tree=False)
            queued=host.stage(pid,"mezzanine",mezzanine,
                root,root,root,"cinema_candidate",root/"SMPTE_DCP",
                "NVP_Real_Cinema_Test","creator_authorizes_DCP",
                ram_mb=4096,duration_s=7200)
            self.assertEqual(queued["state"],"QUEUED")
            outcome=host.run_next(timeout_seconds=3600)
            self.assertEqual(outcome["state"],"SUCCEEDED")
            self.assertFalse(outcome["dcp_delivered"])
            output=root/"SMPTE_DCP"
            self.assertTrue((output/"ASSETMAP.xml").is_file())
            self.assertTrue(any(p.suffix.lower()==".mxf" for p in output.iterdir()))
            reopen=NativeAudio01K3Host(
                DigitalCapture(Studio(root/"studio.sqlite3")),
                ledger(root),root/"dcphost",
                distribution_host=AuthorizedDistribution(
                    DigitalCapture(Studio(root/"studio.sqlite3"))),
                verify_creator_action=lambda *_:False,strict_linux_tree=False)
            proof=reopen.verify_candidate(pid,"cinema_candidate",queued["job_id"])
            self.assertTrue(proof["independent_validator_passed"])
            self.assertFalse(proof["dcp_delivered"])
            self.assertFalse(reopen.recover_completed(queued["job_id"])["rerendered"])
            artifact_root=os.environ.get("NVP_AUDIO01K3_ARTIFACT_DIR")
            if artifact_root:
                artifact=Path(artifact_root)
                if artifact.exists() or artifact.is_symlink():
                    raise RuntimeError("Real DCP artifact destination must be absent")
                artifact.mkdir(parents=True,mode=0o700)
                shutil.copytree(output,artifact/"SMPTE_DCP")
                for name in ("dcpdoctor_stdout.txt","dcpdoctor_stderr.txt",
                             "worker_receipt.json","plan.json"):
                    src=root/"dcphost"/queued["job_id"]/name
                    if src.is_file():
                        shutil.copy2(src,artifact/name)
            doc=reopen.capture.index.read_revision(pid,"cinema_candidate",1)
            self.assertEqual(doc["kind"],"presentation")
            self.assertEqual(doc["data"]["status"],
                             "independently_validated_dcp_candidate")
            # After successful DCP QC, altered MXF contents must fail.
            essence=next(p for p in output.iterdir() if p.suffix.lower()==".mxf")
            with essence.open("ab") as file:
                file.write(b"tamper")
            with self.assertRaises(RuntimeError):
                reopen.verify_candidate(pid,"cinema_candidate",queued["job_id"])


if __name__=="__main__":
    unittest.main()
