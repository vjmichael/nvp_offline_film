"""E2E-01D: verify a real creator-approved film from persisted NVP custody.

This is deliberately NOT a fixture builder: it cannot synthesize grants,
project approvals, FilmIndex records, native worker-stop witnesses, AV streams,
or distribution receipts. Missing materials fail closed. A separately
uploaded production fixture must be an original NVP workspace, not a mock.

Usage:
 python -m tools.nvp_e2e01d_verify_approved_film --manifest fixture.json

Manifest absolute file/dir paths:
 studio_db, ledger_root, audio_host_root, av_host_root,
 project_id, picture_lock_id, audio_delivery_id, final_av_id,
 distribution_id, b12_package_dir, b14_conform_dir, b14_movie_dir,
 audio_dir, final_av_dir, distribution_dir

The manifest is only a set of paths/IDs; it carries NO authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

from backend.nvp_studio import Studio
from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_audio01i_native_host import NativeAudio01IHost
from backend.nvp_audio01j_native_host import NativeAudio01JHost
from backend.nvp_audio01k_native_host import NativeAudio01KHost
from backend.nvp_audio01j_picture_lock import validate_picture_lock
from backend.nvp_b14_edited_movie import verify_edited_technical_mov
from backend.nvp_e2e01c_finishing import NativeFinishingHandoff

KEYS=(
    "studio_db","ledger_root","audio_host_root","av_host_root",
    "project_id","picture_lock_id","audio_delivery_id","final_av_id",
    "distribution_id","b12_package_dir","b14_conform_dir",
    "b14_movie_dir","audio_dir","final_av_dir","distribution_dir"
)


def verify_document(document,*,ffmpeg="ffmpeg",ffprobe="ffprobe"):
    if not isinstance(document,dict) or any(
            not isinstance(document.get(key),str) or not document[key]
            for key in KEYS):
        raise ValueError("Missing actual FilmIndex/native source path or identity")
    for name in ("studio_db","b12_package_dir","b14_conform_dir",
                 "b14_movie_dir","audio_dir","final_av_dir","distribution_dir"):
        path=Path(document[name])
        if (not path.is_absolute() or path.is_symlink()
            or not path.exists() or
            (not path.is_file() if name=="studio_db" else not path.is_dir())):
            raise RuntimeError("Missing/unsafe immutable production fixture: "+name)
    for name in ("ledger_root","audio_host_root","av_host_root"):
        path=Path(document[name])
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise RuntimeError("Original native custody directory required: "+name)
    for name in ("ffmpeg","ffprobe"):
        binary=shutil.which(ffmpeg if name=="ffmpeg" else ffprobe)
        if binary is None:
            raise RuntimeError("Real binary missing: "+name)
    capture=DigitalCapture(Studio(document["studio_db"]))
    ledger=TaskLedger(document["ledger_root"])
    # Reopened hosts must NOT be allowed to issue new creator events here.
    deny_new_approvals=lambda *_:False
    audio=NativeAudio01IHost(
        capture,ledger,document["audio_host_root"],
        verify_creator_action=deny_new_approvals)
    av=NativeAudio01JHost(
        capture,ledger,document["av_host_root"],
        verify_creator_action=deny_new_approvals,audio_host=audio)
    distribution=NativeAudio01KHost(
        capture,ledger,av_host=av,verify_creator_action=deny_new_approvals)
    project=document["project_id"]
    lock_id=document["picture_lock_id"]
    lock,picture=validate_picture_lock(capture,project,lock_id)
    picture_id=lock["data"]["source_picture_id"]
    technical=verify_edited_technical_mov(
        capture,project,picture_id,
        Path(document["b12_package_dir"]),
        Path(document["b14_conform_dir"]),
        Path(document["b14_movie_dir"]),
        ffmpeg=ffmpeg,ffprobe=ffprobe)
    if technical.get("status")!="VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE":
        raise RuntimeError("Full frozen-origin picture and color lineage failed")
    sound=audio.verify_delivery(
        project,document["audio_delivery_id"],document["audio_dir"],
        ffmpeg=ffmpeg,ffprobe=ffprobe)
    if sound.get("status")!="VERIFIED_FINAL_AUDIO":
        raise RuntimeError("Creator-approved PCM24 audio missing")
    video=av.verify_published(
        project,document["final_av_id"],document["final_av_dir"],
        document["b14_movie_dir"],document["audio_dir"],
        ffmpeg=ffmpeg,ffprobe=ffprobe)
    if video.get("status")!="VERIFIED_FINAL_AV_MASTER":
        raise RuntimeError("No authorized native AV worker and final master")
    picture_frames=technical.get("frames")
    movie_frames=video.get("frames")
    if (type(picture_frames) is not int or picture_frames<=0
        or type(movie_frames) is not int or movie_frames!=picture_frames):
        raise RuntimeError("Complete approved film picture/AV frame clock mismatch")
    mezzanine=distribution.verify(
        project,document["distribution_id"],document["distribution_dir"],
        document["final_av_dir"],document["b14_movie_dir"],document["audio_dir"],
        ffmpeg=ffmpeg,ffprobe=ffprobe)
    if mezzanine.get("status")!="VERIFIED_MEZZANINE_DISTRIBUTION":
        raise RuntimeError("Source-bound mezzanine custody failed")
    source=capture.index.read_revision(project,document["final_av_id"],1)
    delivery=capture.index.read_revision(project,document["distribution_id"],1)
    if (source["data"].get("picture_lock_id")!=lock_id
        or source["data"].get("audio_delivery_id")!=document["audio_delivery_id"]
        or source["data"].get("dcp_delivered") is not False
        or delivery["data"].get("export_id")!=document["final_av_id"]
        or delivery["data"].get("dcp_delivered") is not False):
        raise RuntimeError("Cross-chain final film identity or cinema claim mismatch")
    # Prevent a false all-green report if unfinished AV workers still hold
    # safety budgets. Existing unrelated production tasks may be active;
    # this script explicitly does not free or terminate those tasks.
    return {
        "status":"VERIFIED_APPROVED_NATIVE_FILM",
        "project_id":project,
        "picture_lock_id":lock_id,
        "picture_sha256":picture["document_sha256"],
        "master_sha256":source["document_sha256"],
        "distribution_sha256":delivery["document_sha256"],
        "picture_frames":technical.get("frames"),
        "av_frames":video.get("frames"),
        "dcp_delivered":False,
        "no_new_creator_approval_granted":True,
        "native_audio_status":sound["status"],
        "native_av_status":video["status"],
        "native_distribution_status":mezzanine["status"],
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--ffmpeg",default="ffmpeg")
    parser.add_argument("--ffprobe",default="ffprobe")
    parser.add_argument("--report",type=Path)
    args=parser.parse_args(argv)
    if args.manifest.is_symlink() or not args.manifest.is_file():
        raise SystemExit("No original production film fixture manifest")
    doc=json.loads(args.manifest.read_text("utf8"))
    report=verify_document(doc,ffmpeg=args.ffmpeg,ffprobe=args.ffprobe)
    serialized=json.dumps(report,indent=2,sort_keys=True)+"\n"
    if args.report:
        if args.report.is_symlink() or args.report.exists():
            raise SystemExit("Refusing overwrite of original verification report")
        with args.report.open("x",encoding="utf8") as out:
            out.write(serialized)
    print(serialized,end="")


if __name__=="__main__":
    main()
