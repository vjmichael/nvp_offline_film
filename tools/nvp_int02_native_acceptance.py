"""INT-02C independent EXACT-HEAD native Cycles source/film acceptance audit.

READ-ONLY with respect to original FilmIndex takes and committed edits.
Requires a real installed Blender, an actual 30-second NVP edited output,
720 existing Cycles worker journal/output receipts, and full original PCM.
No synthetic frame/fixture can satisfy this audit by a manifest alone.

This is automated native artifact verification, never owner-operated
physical color, sound, encryption or W1-F sustained approval.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex, _require_pid, _id
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_int02_edited_film import verify_edited_film
from backend.nvp_blender_worker import BlenderWorkerSupervisor, sha_file
from backend.nvp_final_2d_native import _file_sha256

FORMAT="nvp.int02.cycles.30s.native_acceptance.v1"
EXPECTED_PICTURES=720


def worker_id(project_id,presentation_id,take_sha,source_tick,shot_sha):
    value=(project_id+"|"+presentation_id+"|"+
           take_sha+"|"+str(source_tick)+"|"+str(shot_sha)).encode("utf8")
    return "int02_"+sha256(value).hexdigest()[:40]


def inspect_real_native_edit(index,project_id,edit_id,edit_revision,package,
                             supervisor,*,require_all_cycles=True):
    if not isinstance(index,FilmIndex) or not isinstance(
            supervisor,BlenderWorkerSupervisor):
        raise TypeError("Real original FilmIndex and native Blender worker journal required")
    _require_pid(project_id)
    _id(edit_id,"committed native editorial film")
    slate=DigitalSlateBranches(index,verify_editor_action=lambda *_:False)
    assembly=SlateSequenceAssembly(slate,verify_editor_action=lambda *_:False)
    delivery=Path(package)
    verified=verify_edited_film(
        assembly,project_id,edit_id,edit_revision,delivery)
    manifest=delivery/"manifest.json"
    doc=json.loads(manifest.read_text("utf8"))
    rows=doc["pictures"]
    if (len(rows)!=EXPECTED_PICTURES or
        doc.get("picture_dimensions")!=[1920,1080] or
        doc.get("export_is_plaintext_derivative") is not True):
        raise RuntimeError("Native accepted film requires all 720 Full-HD source moments")
    checked=0
    black_gaps=0
    sources=[]
    for item in rows:
        if item["camera_path"] is None:
            # Original camera timeline explicitly supplies a blank interval.
            black_gaps+=1
            continue
        seg=next((e for e in doc["segments"]
                  if e["segment_id"]==item["segment_id"]),None)
        if seg is None or item["source_take_sha256"]!=seg["source_take_sha256"]:
            raise RuntimeError("Native Cycles picture has no committed original Take")
        shot_sha=seg["source_shot_sha256"]
        original_tick=int(item["source_tick"])
        ident=worker_id(project_id,doc["presentation_id"],
                        seg["source_take_sha256"],original_tick,shot_sha)
        received=supervisor.verify_completed(ident)
        if received["state"]!="SUCCEEDED":
            raise RuntimeError("Native Cycles picture has no verified supervised worker")
        directory=supervisor.root/ident
        plan_path=directory/"plan.json"
        audit_path=directory/"audit.json"
        image_path=directory/"frame.png"
        if any(p.is_symlink() or not p.is_file() for p in (
                plan_path,audit_path,image_path)):
            raise RuntimeError("Native Cycles proof file missing or linked")
        plan=json.loads(plan_path.read_text("utf8"))
        audit=json.loads(audit_path.read_text("utf8"))
        if (plan.get("format")!="nvp.int02.cycles.frame_plan.v1" or
            plan.get("source_tick")!=original_tick or
            plan.get("camera_path")!=item["camera_path"] or
            plan.get("renderer")!="CYCLES" or
            plan.get("width")!=1920 or plan.get("height")!=1080 or
            audit.get("format")!="nvp.int02.cycles.native_frame.v1" or
            audit.get("passed") is not True or
            audit.get("render_engine")!="CYCLES" or
            audit.get("cycles_samples",0)<64 or
            audit.get("source_usd_sha256")!=plan["usd_sha256"] or
            audit.get("native_frame_sha256")!=item["sha256"] or
            _file_sha256(image_path)!=item["sha256"] or
            received["outputs"]["frame.png"]["sha256"]!=item["sha256"] or
            received["outputs"]["audit.json"]["sha256"]!=_file_sha256(audit_path)):
            raise RuntimeError("Edited frame does not match independently verified Cycles output")
        sources.append(sha256((ident+plan["usd_sha256"]+
                               item["sha256"]).encode("ascii")).hexdigest())
        checked+=1
    if require_all_cycles and checked==0:
        raise RuntimeError("Black-only output is not an accepted production film")
    output={
        "format":FORMAT,
        "status":"NATIVE_CYCLES_EDITED_30S_AUTOMATED_ARTIFACTS_VERIFIED",
        "project_id":project_id,"edit_id":edit_id,
        "edit_revision":edit_revision,
        "committed_edit_sha256":verified["edit_sha256"],
        "manifest_sha256":verified["manifest_sha256"],
        "total_picture_samples":len(rows),
        "supervised_cycles_pictures_verified":checked,
        "original_camera_blank_samples":black_gaps,
        "source_pcm_samples_verified":verified["original_pcm_samples"],
        "worker_provenance_sha256":sha256(
            "".join(sources).encode("ascii")).hexdigest(),
        "no_ffmpeg":True,
        "original_film_modified":False,
        "physical_owner_accepted":False,
        "encrypted_original_staging_verified":False,
        "production_color_sound_accepted":False,
        "W1F_sustained_production_accepted":False,
    }
    if checked+black_gaps!=EXPECTED_PICTURES:
        raise RuntimeError("Unexpected gap in actual native film output")
    return output


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--studio-sqlite",required=True,type=Path)
    parser.add_argument("--project",required=True)
    parser.add_argument("--edit",required=True)
    parser.add_argument("--revision",required=True,type=int)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--worker-workspace",required=True,type=Path)
    parser.add_argument("--blender",required=True,type=Path)
    parser.add_argument("--receipt",type=Path)
    args=parser.parse_args(argv)
    if not args.studio_sqlite.is_file() or args.studio_sqlite.is_symlink():
        raise RuntimeError("Original film SQLite database must already exist")
    if not args.blender.is_file() or args.blender.is_symlink():
        raise RuntimeError("Real installed Blender executable required")
    from backend.nvp_int02_cycles_renderer import _blender_version
    worker=BlenderWorkerSupervisor(
        args.worker_workspace,
        blender_executable=args.blender,
        blender_sha256=sha_file(args.blender),
        blender_version=_blender_version(args.blender))
    original=FilmIndex(Studio(args.studio_sqlite))
    report=inspect_real_native_edit(
        original,args.project,args.edit,args.revision,args.output,worker)
    serialized=json.dumps(report,sort_keys=True,indent=2)+"\n"
    if args.receipt:
        if args.receipt.exists() or args.receipt.is_symlink():
            raise RuntimeError("Cannot overwrite a native acceptance receipt")
        with args.receipt.open("x",encoding="utf8") as f:
            f.write(serialized)
    print(serialized)


if __name__=="__main__":
    main()
