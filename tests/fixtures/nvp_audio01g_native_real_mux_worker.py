"""CI-only AUDIO-01G worker executing genuine FFmpeg and FilmIndex writes.

Upstream B14/AUDIO-01E source validators are stubbed ONLY in this purpose-built
test script; the real production worker has no such override. FilmIndex, MOV,
media hashes, native subprocess containment and crash hook execute for real.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from backend.nvp_digital_capture import DigitalCapture
from backend.nvp_studio import Studio
from backend.nvp_audio01f_picture_sound import build_picture_sound_preview
from backend.nvp_audio01g_fault_matrix import crash_after


def main():
    if (os.environ.get("NVP_AUDIO01G_FAULT_TEST")!="enabled" or
        len(sys.argv)!=3 or sys.argv[1]!="--plan"):
        raise PermissionError("Fixture worker requires explicit isolated CI flag")
    file=Path(sys.argv[2])
    if file.is_symlink() or not file.is_file():
        raise RuntimeError("Missing or symlinked sealed fixture plan")
    p=json.loads(file.read_text("ascii"))
    if (p.get("format")!="nvp.audio01f.native_plan.v1" or
        p.get("final_master") is not False or
        p.get("director_approved") is not False):
        raise RuntimeError("Unsafe test mux plan")
    cap=DigitalCapture(Studio(p["studio_db_path"]))
    with (patch("backend.nvp_audio01f_picture_sound.verify_edited_technical_mov",
                return_value={"status":"VERIFIED_EDITED_TECHNICAL_MOV_CANDIDATE"}),
          patch("backend.nvp_audio01f_picture_sound.verify_published_wavs",
                return_value={"status":"VERIFIED_UNAPPROVED_INDEXED_WAV_PREVIEW"})):
        result=build_picture_sound_preview(cap,p["project_id"],p["candidate_id"],
            p["audio_id"],p["package"],p["conform_dir"],p["movie_dir"],
            p["audio_dir"],p["audio_plan"],p["audio_sources"],
            p["audio_chunks"],p["destination"],p["presentation_id"],
            ffmpeg=p["ffmpeg"],ffprobe=p["ffprobe"])
    if result["status"]!="VERIFIED_UNAPPROVED_PICTURE_SOUND_REVIEW":
        raise RuntimeError("Real mux was not verified")
    receipt={"format":"nvp.audio01f.native_worker_receipt.v1",
             "presentation_id":p["presentation_id"],
             "document_sha256":result["document_sha256"],
             "frames":result["frames"],
             "samples_per_channel":result["samples_per_channel"],
             "final_master":False}
    with (file.parent/"worker_receipt.json").open("xb") as out:
        out.write(json.dumps(receipt,sort_keys=True,separators=(",",":")).encode("ascii"))
        out.flush();os.fsync(out.fileno())
    crash_after("worker_receipt_fsynced")


if __name__=="__main__":
    main()
