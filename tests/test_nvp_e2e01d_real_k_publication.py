"""E2E-01D: real AUDIO-01K media copy and SQLite publication crash matrix.

No fake MOV or mock storage: a real FFmpeg ProRes/PCM24 film is copied,
fsynced, renamed and indexed by production publish_mezzanine, with os._exit
in a distinct process for each filesystem/SQLite boundary. The only fixture
shortcut is the explicitly synthetic verify_native_master callback; these
tests DO NOT establish creator approval or native AUDIO-01J worker custody.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from backend.nvp_audio01k_fault_matrix import BOUNDARIES
from backend.nvp_audio01k_distribution import (
    publish_mezzanine,verify_mezzanine)
from backend.nvp_audio01j_final_av import FORMAT as AV_FORMAT
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio


def run(argv,*,env=None,timeout=120):
    process=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,check=False,timeout=timeout,env=env)
    if process.returncode:
        raise RuntimeError("Native media setup failed: "+
                           process.stderr.decode("utf8","replace")[-1500:])


def make_mov(root):
    import shutil
    ffmpeg=shutil.which("ffmpeg")
    ffprobe=shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("Real FFmpeg and FFprobe mandatory for K publication crash gate")
    film=root/"final_picture_sound.mov"
    run([ffmpeg,"-hide_banner","-nostdin","-loglevel","error","-xerror","-y",
         "-f","lavfi","-i","testsrc2=size=128x72:rate=24:duration=0.5",
         "-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=0.5",
         "-map","0:v","-map","1:a","-c:v","prores_ks","-profile:v","3",
         "-pix_fmt","yuv422p10le","-c:a","pcm_s24le","-ar","48000",
         "-ac","2","-frames:v","12",str(film)])
    run([ffprobe,"-v","error","-show_entries","stream=codec_name",
         "-of","default=noprint_wrappers=1",str(film)])
    return film


def source_proof():
    return {"status":"VERIFIED_FINAL_AV_MASTER","final_master":True}


def _native_child_environment():
    # Running a test by filename adds tests/ to sys.path, not repository root.
    # Inherit a pinned source root for actual hard-kill Python child processes,
    # whether launched from unittest, pytest, or a Windows packaged runner.
    env=os.environ.copy()
    repo=str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"]=os.pathsep.join(filter(None,(repo,env.get("PYTHONPATH",""))))
    return env


def subprocess_publish(root,mode="copy"):
    studio=Studio(root/"studio.sqlite3")
    project=(root/"project_id").read_text("ascii")
    capture=DigitalCapture(studio)
    if mode=="host":
        from backend.nvp_resource_ledger import TaskLedger
        from backend.nvp_audio01k_native_host import NativeAudio01KHost
        class VerifiedAVFixture:
            def verify_published(self,*_args,**_kwargs):
                return source_proof()
        host=NativeAudio01KHost(
            capture,TaskLedger(root/"resource_ledger"),
            av_host=VerifiedAVFixture(),
            verify_creator_action=lambda *_args:True)
        host.publish(project,"approved_movie","mezzanine",
                     root/"original",root/"original",root/"original",
                     root/"distribution","technical-creator-event-fixture")
    else:
        publish_mezzanine(capture,project,"approved_movie","mezzanine",
            root/"original",root/"distribution",verify_native_master=source_proof)


class NativeKCrashIO(unittest.TestCase):
    def test_native_host_creator_event_crashes_preserve_one_time_approval(self):
        from backend.nvp_resource_ledger import TaskLedger
        from backend.nvp_audio01k_native_host import NativeAudio01KHost
        import shutil
        for point in ("creator_event_reserved","creator_event_published"):
            with self.subTest(point=point):
                with tempfile.TemporaryDirectory(prefix="nvp-k-host-crash-") as tmp:
                    root=Path(tmp)
                    origin=root/"original"
                    origin.mkdir()
                    movie=make_mov(origin)
                    digest=hashlib.sha256(movie.read_bytes()).hexdigest()
                    studio=Studio(root/"studio.sqlite3")
                    pid=studio.create_project("Real K host event crash","")["id"]
                    (root/"project_id").write_text(pid,"ascii")
                    capture=DigitalCapture(studio)
                    capture.index.register_revision(pid,"approved_movie","master",{
                        "format":AV_FORMAT,"director_approved":True,
                        "final_master":True,"dcp_delivered":False,
                        "rendered_mov_sha256":digest,"frames":12})
                    env=_native_child_environment()
                    env["NVP_AUDIO01K_FAULT_TEST"]="enabled"
                    env["NVP_AUDIO01K_CRASH_AFTER"]=point
                    child=subprocess.run([sys.executable,
                        str(Path(__file__).resolve()),"--child",str(root),"host"],
                        cwd=Path(__file__).resolve().parents[1],
                        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,timeout=90,env=env)
                    self.assertEqual(child.returncode,98,
                        child.stderr.decode("utf8","replace"))
                    ledger=TaskLedger(root/"resource_ledger")
                    with ledger._db() as db:
                        events=db.execute("""SELECT status,document_sha
                            FROM native_audio01k_events WHERE project_id=?""",
                            (pid,)).fetchall()
                    self.assertEqual(len(events),1)
                    self.assertEqual(events[0][0],
                        "RESERVED" if point=="creator_event_reserved" else "PUBLISHED")
                    reopened=DigitalCapture(Studio(root/"studio.sqlite3"))
                    if point=="creator_event_reserved":
                        self.assertIsNone(events[0][1])
                        with self.assertRaises(KeyError):
                            reopened.index.read_revision(pid,"mezzanine",1)
                    else:
                        record=reopened.index.read_revision(pid,"mezzanine",1)
                        self.assertEqual(events[0][1],record["document_sha256"])
                        self.assertTrue((root/"distribution"/"feature_master.mov").is_file())
                    class VerifiedAVFixture:
                        def verify_published(self,*_args,**_kwargs):
                            return source_proof()
                    host=NativeAudio01KHost(reopened,ledger,
                        av_host=VerifiedAVFixture(),
                        verify_creator_action=lambda *_args:True)
                    with self.assertRaises(PermissionError):
                        host.publish(pid,"approved_movie","mezzanine",
                            origin,origin,origin,root/"distribution",
                            "technical-creator-event-fixture")

    def test_all_real_copy_fsync_rename_and_filmindex_boundaries(self):
        for point in BOUNDARIES:
            if point in ("creator_event_reserved","creator_event_published"):
                continue   # Those are host-authorization checks, a separate gate.
            with self.subTest(checkpoint=point):
                with tempfile.TemporaryDirectory(prefix="nvp-k-crash-") as tmp:
                    root=Path(tmp)
                    origin=root/"original"
                    origin.mkdir()
                    movie=make_mov(origin)
                    raw=movie.read_bytes()
                    digest=hashlib.sha256(raw).hexdigest()
                    studio=Studio(root/"studio.sqlite3")
                    project=studio.create_project("Crash-tested real MOV","")["id"]
                    (root/"project_id").write_text(project,"ascii")
                    capture=DigitalCapture(studio)
                    capture.index.register_revision(project,"approved_movie",
                        "master",{
                            "format":AV_FORMAT,
                            "director_approved":True,
                            "final_master":True,
                            "dcp_delivered":False,
                            "rendered_mov_sha256":digest,
                            "frames":12
                        })
                    env=_native_child_environment()
                    for k in ("NVP_AUDIO01K_FAULT_TEST",
                              "NVP_AUDIO01K_CRASH_AFTER"):
                        env.pop(k,None)
                    env["NVP_AUDIO01K_FAULT_TEST"]="enabled"
                    env["NVP_AUDIO01K_CRASH_AFTER"]=point
                    worker=subprocess.run([sys.executable,
                        str(Path(__file__).resolve()),"--child",str(root)],
                        cwd=Path(__file__).resolve().parents[1],
                        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,timeout=90,env=env,check=False)
                    self.assertEqual(worker.returncode,98,
                                     worker.stderr.decode("utf8","replace"))
                    reopened=DigitalCapture(Studio(root/"studio.sqlite3"))
                    self.assertEqual((origin/"final_picture_sound.mov").read_bytes(),
                                     raw,"Original approved candidate was modified")
                    published=(root/"distribution")
                    staged=root/".distribution.audio01k.stage"
                    promoted=point in ("directory_promoted","filmindex_registered")
                    indexed=point=="filmindex_registered"
                    self.assertEqual(published.is_dir(),promoted)
                    self.assertEqual(staged.is_dir(),not promoted)
                    try:
                        record=reopened.index.read_revision(
                            project,"mezzanine",1)
                    except KeyError:
                        record=None
                    self.assertEqual(record is not None,indexed)
                    if indexed:
                        result=verify_mezzanine(reopened,project,
                            "mezzanine",published,
                            verify_native_master=source_proof)
                        self.assertEqual(result["status"],
                                         "VERIFIED_MEZZANINE_DISTRIBUTION")
                        self.assertFalse(result["dcp_delivered"])
                    else:
                        with self.assertRaises((KeyError,RuntimeError)):
                            verify_mezzanine(reopened,project,"mezzanine",
                                published,verify_native_master=source_proof)
                    # Even if the final directory was renamed, no
                    # FilmIndex record means it cannot be claimed delivered.
                    if promoted:
                        self.assertEqual((published/"feature_master.mov").read_bytes(),
                                         raw)


if __name__=="__main__":
    if len(sys.argv)>=3 and sys.argv[1]=="--child":
        subprocess_publish(Path(sys.argv[2]),
                           "host" if len(sys.argv)>3 and sys.argv[3]=="host"
                           else "copy")
    else:
        unittest.main()
