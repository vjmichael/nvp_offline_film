"""W1-F native Windows: genuine isolated frozen one-frame private reel acceptance.

CI synthetic source ONLY. Never unlocks a human film, never pretends a model
approved a worker, and never claims 30-180 minute physical creator acceptance.
The actual kernel AppContainer/Job, pipes, end-to-end MJPEG/PCM decoder,
AES-GCM sealed output, restart, original immutability and worker receipt are
not mocked. Exact fixed child role is the installed NVP.exe itself.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import secrets
import sys
import tempfile

from backend.nvp_g03_live_store import LiveFilmStore
from backend.nvp_g03_windows_appcontainer import _api
from backend.nvp_g08_native_avi import TICKS_FRAME,verify_movie
from backend.nvp_g09e_chunk import REQUIRED_DIGESTS,source_digests
from backend.nvp_g09e_audio import plan_gain
from backend.nvp_g09e_sealed_worker import ProtectedSealedReelWorker

USDA=(b'#usda 1.0\n'
      b'(\n    defaultPrim = "World"\n)\n'
      b'def Xform "World" {\n}\n')


def _fixture(usd):
    original_sha=sha256(usd).hexdigest()
    digests={name:sha256(("w1f-synthetic-"+name).encode("ascii")).hexdigest()
             for name in REQUIRED_DIGESTS}
    take={"original_usd":usd,"performance_usd":usd,
          "original_sha256":original_sha,"performance_sha256":original_sha,
          "audio":[],"stage_objects":[],"stage_setting":{"daylight":"day"}}
    assembly={
        "format":"nvp.g07.non_destructive_edit.v1",
        "source_media_modified":False,
        "duration_tick":TICKS_FRAME,
        "window":[0,TICKS_FRAME],
        "source_payload_budget_bytes":len(usd)*2,
        "original_takes":{"synthetic-take":take},
        "segments":[{
            "take_id":"synthetic-take","start_tick":0,"end_tick":TICKS_FRAME,
            "source_in_tick":0,"source_out_tick":TICKS_FRAME,
            "camera":{"position":[0.,0.,5.],"look_at":[0.,0.,0.],
                      "focal_mm":35.},
            "grade":{"exposure":0.,"saturation":1.,"warmth":0.,"contrast":1.},
            "audio":[],"transition":{"kind":"cut","duration_tick":0}
        }],
        "master_gain":1.0,"production_looks":{},
        "actor_performances":{},"acoustic_looks":{},
        "approved_finishing":None,**digests}
    measured={"sample_count":2000,"sample_peak_abs":0,
        "integrated_lufs":None,"meter_engine":"synthetic-ci-no-live-sound",
        "gated_400ms_blocks":0,"true_peak_measured":False,
        "physical_multichannel_cinema_certified":False}
    return assembly,plan_gain(measured,None)


def run():
    if (sys.platform!="win32" or
        os.environ.get("GITHUB_ACTIONS")!="true" or
        os.environ.get("NVP_W1F_TEST_APPROVAL")!="CI_SOURCE_ONLY"):
        raise RuntimeError("Only an explicit ephemeral Windows CI source smoke may run")
    if not getattr(sys,"frozen",False):
        raise RuntimeError("This acceptance requires a real installed frozen NVP.exe")
    _api()  # Must have the real kernel security APIs.
    with tempfile.TemporaryDirectory(prefix="nvp-w1f-sealed-reel-") as temp:
        root=Path(temp)/"w1f-encrypted-originals"
        host=LiveFilmStore(root)
        pid=secrets.token_hex(16)
        passwd="W1-F CI original SHA and encrypted private reel acceptance"
        token="w1f-installed-"+secrets.token_urlsafe(32)
        host.create(pid,"Synthetic W1-F only","", "",passwd)
        host.authorize(pid,passwd,token)
        original_name="originals/w1f-public-synthetic-world.usda"
        witness=host.put_original(pid,token,original_name,USDA,
                                  "model/vnd.usda")
        if witness["sha256"]!=sha256(USDA).hexdigest():
            raise RuntimeError("Original scene was not sealed correctly")
        loaded=host.get_original(pid,token,original_name)
        assembly,plan=_fixture(loaded)
        job=secrets.token_hex(16)
        ticket=secrets.token_urlsafe(32)
        granted={ticket}
        def review(review_pid,review_job,index,binding,provided):
            if not (review_pid==pid and review_job==job and index==0 and
                    provided in granted and len(binding)==64):
                return False
            granted.remove(provided)
            return True
        def attestor(review_pid,review_job,index,binding):
            # Only a preflight. The actual protected worker supervisor MUST
            # independently launch a Windows AppContainer and inspect Job,
            # ACL/profile teardown before publication.
            if not (review_pid==pid and review_job==job and index==0 and
                    len(binding)==64):
                return False
            _api()
            return True
        result=ProtectedSealedReelWorker(host,
            review_authority=review,
            os_isolation_attestor=attestor).render(
                pid,token,job,0,1,assembly,plan,ticket)
        if (not result["encrypted_output"] or
            not result["os_process_tree_closed"] or
            not result["independent_audio_picture_verified"] or
            result["index"]!=0 or result["end_frame"]!=1 or granted):
            raise RuntimeError("One real protected film frame lacked OS custody")
        original=host.get_original(pid,token,original_name)
        if original!=USDA:
            raise RuntimeError("Native private worker mutated original OpenUSD")
        movie=host.get_original(pid,token,result["output_name"])
        if sha256(movie).hexdigest()!=result["sha256"]:
            raise RuntimeError("Sealed working reel diverged after publication")
        checked=verify_movie(movie,1,expected_sha=result["sha256"])
        if checked["frames"]!=1 or checked["audio_samples_per_channel"]!=2000:
            raise RuntimeError("Native picture/audio clock changed during worker run")
        receipts=host.protected_worker_runs(pid,token)
        if not any(x["state"]=="SUCCEEDED" and
                   x["output_sha256"]==result["sha256"] for x in receipts):
            raise RuntimeError("Original worker execution journal lacks success")
        for item in root.rglob("*"):
            if item.is_file():
                raw=item.read_bytes()
                if raw.startswith((b"RIFF",b"#usda")):
                    raise RuntimeError("Protected source or reel leaked plaintext file")
        host.revoke(pid)
        opened=LiveFilmStore(root)
        fresh="w1f-reopen-"+secrets.token_urlsafe(32)
        opened.authorize(pid,passwd,fresh)
        if (opened.get_original(pid,fresh,original_name)!=USDA or
            sha256(opened.get_original(
                pid,fresh,result["output_name"])).hexdigest()!=result["sha256"]):
            raise RuntimeError("Native encrypted reel did not survive restart")
    print("W1F_REAL_INSTALLED_APPCONTAINER_ONE_FRAME_PCM2000_AESGCM_REOPEN_PASS")
    return 0


if __name__=="__main__":
    raise SystemExit(run())
