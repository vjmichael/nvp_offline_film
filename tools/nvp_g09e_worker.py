#!/usr/bin/env python3
"""Fixed G09-E independently custodied long-film analyze/render/verify/finalize.

The host supplies only a reviewed project/job/owned-index, never a shell,
untrusted script, network URL, codec or arbitrary source/output path. All
film source and approved creative directions are reopened from SQLite and
compared with the human-approved job's exact source identity.

Each process owns at most one actual 10s AVI at once. A final package is a
manifest of already independently verified, restart-stable reel receipts.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from backend.nvp_g09e_chunk import (
    chunk_bounds,source_digests,check_assembly,iter_source_pcm,render_reel,
    inspect_reel,MAX_CHUNK_BYTES,MAX_CHUNKS,MAX_FRAMES,FORMAT,_canonical)
from backend.nvp_g09e_audio import FilmMeter,plan_gain
from backend.nvp_g08_native_avi import TICKS_FRAME,verify_movie
from backend.nvp_g09d_interchange import _parse_verified

MAX_RECEIPT=128*1024
MAX_MANIFEST=2*1024*1024
MAX_ALL_BYTES=32*1024*1024*1024
TICKS_PER_SAMPLE=TICKS_FRAME//2000

def _owned(args):
    from backend.nvp_g06_filming import HEX
    if not HEX.fullmatch(args.project) or not HEX.fullmatch(args.job):
        raise ValueError("A trusted original project and work order are required")
    if getattr(args,"index",-1)<-1 or args.index>=MAX_CHUNKS:
        raise ValueError("Worker reel index is outside the approved film")
    db=Path(args.db).resolve(strict=True)
    root=db.parent/"nvp_g09e_exports"
    directory=root/args.project/args.job
    # The existing host exclusively creates directories and validates
    # status before launching this fixed worker; never follow a path link.
    for p in (db.parent,root,root/args.project,directory):
        if p.is_symlink() or not p.is_dir() or p.resolve()!=p:
            raise RuntimeError("The film export worker has an unsafe destination")
    return db,directory

def _job(dbpath,pid,jobid):
    from backend.nvp_studio import Studio
    studio=Studio(dbpath)
    with studio._connection() as db:
        row=db.execute("""SELECT * FROM g09e_jobs WHERE id=? AND project_id=?""",
            (jobid,pid)).fetchone()
        if row is None:raise RuntimeError("A reviewed long-film job no longer exists")
        record=dict(row)
        parts=[dict(row) for row in db.execute("""SELECT * FROM g09e_chunks
            WHERE project_id=? AND job_id=? ORDER BY chunk_index""",
            (pid,jobid))]
    source=json.loads(record["source_json"])
    if (type(source) is not dict or len(source)!=5 or
        record["total_frames"]>MAX_FRAMES or
        record["total_chunks"]>MAX_CHUNKS or
        record["total_chunks"]!=(record["total_frames"]+239)//240):
        raise RuntimeError("The long-film source manifest is invalid")
    if sha256(_canonical(source)).hexdigest()!=record["source_sha256"]:
        raise RuntimeError("The creative source manifest was changed")
    return record,parts,source

def _read_json(path,limit=MAX_RECEIPT):
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=limit:
        raise RuntimeError("A fixed native worker receipt is missing")
    return json.loads(path.read_text(encoding="utf8"))

def _write_owned(directory,name,value):
    raw=_canonical(value)
    limit=MAX_MANIFEST if name=="candidate-manifest.json" else MAX_RECEIPT
    if len(raw)>limit:
        raise ValueError("The native worker result is too large")
    final=directory/name
    if final.is_symlink():
        raise RuntimeError("Untrusted worker output path")
    temp=directory/("."+name+"."+uuid.uuid4().hex+".partial")
    with open(temp,"xb") as output:
        output.write(raw);output.flush();os.fsync(output.fileno())
    if final.exists():
        # Retrying an interrupted worker may NOT silently replace
        # a different receipt. The host reconciles before fresh starts.
        temp.unlink()
        raise RuntimeError("A prior native result already occupies the destination")
    os.link(temp,final,follow_symlinks=False)
    temp.unlink()

def _load_window(dbpath,record,source,start,end):
    from backend.nvp_studio import Studio
    from backend.nvp_g07_edit import G07Editor
    studio=Studio(dbpath)
    assembly=G07Editor(studio).native_assembly(
        record["project_id"],record["edit_revision"],
        window=(start*TICKS_FRAME,end*TICKS_FRAME))
    check_assembly(assembly,record["total_frames"],start,end,source)
    return assembly

def _analysis(args,dbpath,directory,record,source):
    duration=record["total_frames"]*2000
    meter=FilmMeter(duration_samples=duration)
    for index in range(record["total_chunks"]):
        start,end=chunk_bounds(record["total_frames"],index)
        assembly=_load_window(dbpath,record,source,start,end)
        for sample,raw in iter_source_pcm(assembly,start,end):
            meter.feed(raw)
        if (index+1)%4==0 or index+1==record["total_chunks"]:
            _write_progress(directory,{
                "status":"analyzing","job_id":record["id"],
                "source_sha256":record["source_sha256"],
                "analyzed_chunks":index+1,
                "total_chunks":record["total_chunks"]})
    measured=meter.finish()
    from backend.nvp_g09d_finishing import G09DFinishing
    # The source window already returns the approved final finishing
    # choice with all SHA checks. Capture it once from the first window.
    first=_load_window(dbpath,record,source,*chunk_bounds(
        record["total_frames"],0))
    finishing=first.get("approved_finishing")
    plan=plan_gain(measured,finishing)
    report={"format":"nvp.g09e.analysis.v1","source_sha256":record["source_sha256"],
        "total_frames":record["total_frames"],
        "measured":measured,"sound_plan":plan,
        "sound_plan_sha256":sha256(_canonical(plan)).hexdigest(),
        "original_pcm_unmodified":True,
        "target_is_only_predicted_before_output_recheck":True}
    _write_owned(directory,"analysis-result.json",report)

def _write_progress(directory,value):
    raw=_canonical(value)
    target=directory/"progress.json"
    temp=directory/(".progress."+uuid.uuid4().hex)
    with open(temp,"xb") as out:
        out.write(raw);out.flush();os.fsync(out.fileno())
    os.replace(temp,target)

def _render(args,dbpath,directory,record,source):
    if not 0<=args.index<record["total_chunks"]:
        raise ValueError("Choose a reviewed film reel")
    analysis=json.loads(record["analysis_json"])
    if (analysis["source_sha256"]!=record["source_sha256"] or
        sha256(_canonical(analysis["sound_plan"])).hexdigest()!=
        analysis["sound_plan_sha256"]):
        raise RuntimeError("The film-wide mastering plan changed")
    start,end=chunk_bounds(record["total_frames"],args.index)
    assembly=_load_window(dbpath,record,source,start,end)
    name=f"reel-{args.index:05d}"
    file=directory/(name+".partial.avi")
    if file.is_symlink() or file.exists():
        raise RuntimeError("An unverified reel already exists")
    last=[-1]
    def progress(done,total):
        if last[0]==done:return
        last[0]=done
        _write_progress(directory,{"job_id":record["id"],
            "status":"rendering","index":args.index,
            "frames_in_reel":total,"frames_completed":done})
    with open(file,"xb") as sink:
        receipt=render_reel(assembly,start,end,
            analysis["sound_plan"],sink,progress=progress)
        sink.flush();os.fsync(sink.fileno())
    receipt.update({
        "index":args.index,"job_id":record["id"],
        "source_sha256":record["source_sha256"],
        "file_sha256":sha256(file.read_bytes()).hexdigest(),
        "source_verified":True})
    _write_owned(directory,name+".render.json",receipt)

def _verify(args,dbpath,directory,record,source):
    if not 0<=args.index<record["total_chunks"]:
        raise ValueError("Choose a reviewed film reel")
    start,end=chunk_bounds(record["total_frames"],args.index)
    name=f"reel-{args.index:05d}"
    receipt=_read_json(directory/(name+".render.json"))
    if (receipt["job_id"]!=record["id"] or
        receipt["index"]!=args.index or
        receipt["source_sha256"]!=record["source_sha256"] or
        receipt["source_digests"]!=source or
        receipt["start_frame"]!=start or
        receipt["end_frame"]!=end or
        receipt["sound_plan_sha256"]!=
            sha256(_canonical(json.loads(
                record["analysis_json"])["sound_plan"])).hexdigest()):
        raise RuntimeError("Native reel did not preserve its source authority")
    result=inspect_reel(directory/(name+".partial.avi"),end-start,
        expected_sha=receipt["file_sha256"])
    if result["audio_samples_per_channel"]!=2000*(end-start):
        raise RuntimeError("Rendered picture and audio are not clock-aligned")
    _write_owned(directory,name+".verify.json",{
        "format":"nvp.g09e.reel_verified.v1",
        "job_id":record["id"],"index":args.index,
        "source_sha256":record["source_sha256"],
        "file_sha256":result["sha256"],
        "frames":end-start,
        "audio_samples":2000*(end-start),
        "verified":True,"ffmpeg_used":False,
        "independent_worker_reopened":True})

def _finalize(args,dbpath,directory,record,source):
    if not record["analysis_json"]:
        raise RuntimeError("Film-wide sound analysis was not completed")
    analysis=json.loads(record["analysis_json"])
    meter=FilmMeter(duration_samples=record["total_frames"]*2000)
    parts=_job(dbpath,record["project_id"],record["id"])[1]
    if len(parts)!=record["total_chunks"] or any(
        p["state"]!="completed" for p in parts):
        raise RuntimeError("The film contains unverified or missing reels")
    directory_bytes=0
    manifest_parts=[]
    for index,part in enumerate(parts):
        if part["chunk_index"]!=index:raise RuntimeError("The film has a reel gap")
        start,end=chunk_bounds(record["total_frames"],index)
        path=directory/(f"reel-{index:05d}.avi")
        if path.is_symlink() or not path.is_file() or (
                path.stat().st_size>MAX_CHUNK_BYTES):
            raise RuntimeError("A completed film reel is missing or unsafe")
        raw=path.read_bytes()
        actual_sha=sha256(raw).hexdigest()
        if actual_sha!=part["sha256"]:
            raise RuntimeError("A previously checked film reel was changed")
        verified=verify_movie(raw,end-start,expected_sha=part["sha256"])
        frames,pcm=_parse_verified(raw)
        if len(frames)!=(end-start) or len(pcm)!=(end-start)*8000:
            raise RuntimeError("A film reel lost audio/video continuity")
        for offset in range(0,len(pcm),48000*4):
            meter.feed(pcm[offset:offset+48000*4])
        directory_bytes+=len(raw)
        if directory_bytes>MAX_ALL_BYTES:
            raise ValueError("The long film exceeds its 32GiB delivery quota")
        manifest_parts.append({
            "index":index,"path":path.name,
            "sha256":actual_sha,
            "start_frame":start,"end_frame":end,
            "start_tick":start*TICKS_FRAME,
            "end_tick":end*TICKS_FRAME,
            "start_sample":start*2000,"end_sample":end*2000,
            "bytes":len(raw),"format":"MJPEG/PCM16 AVI",
            "independent_reel_verified":True})
        _write_progress(directory,{
            "status":"finalizing","job_id":record["id"],
            "verified_chunks":index+1,"total_chunks":record["total_chunks"]})
    measured=meter.finish()
    plan=analysis["sound_plan"]
    target=plan["target_integrated_lufs"]
    if measured["sample_peak_abs"]>32767*10**(
            plan["peak_ceiling_dbfs"]/20)+1:
        raise RuntimeError("Complete film mastered sound exceeds approved sample peak")
    reached=(
        target is not None and
        measured["integrated_lufs"] is not None and
        abs(measured["integrated_lufs"]-target)<=1.)
    if plan["intention"]!="working" and not reached:
        raise RuntimeError("The finished film did not achieve its director-approved sound level")
    manifest={"format":FORMAT,"job_id":record["id"],
        "source_sha256":record["source_sha256"],
        "source_digests":source,
        "original_frozen_takes_preserved":True,
        "human_director_confirmation_required":True,
        "film_time_ticks_per_second":7056000000,
        "total_frames":record["total_frames"],
        "duration_seconds":record["total_frames"]/24,
        "frame_rate":24,"sample_rate":48000,"channels":2,
        "original_source_not_re_encoded":True,
        "derived_reels_format":"640x360_MJPEG_PCM16_AVI",
        "reel_count":len(manifest_parts),
        "total_reel_bytes":directory_bytes,
        "film_sound_measurement":measured,
        "director_sound_target_reached":reached,
        "source_analysis_sha256":sha256(
            _canonical(analysis)).hexdigest(),
        "reels":manifest_parts,
        "not_a_single_gapless_media_file":True,
        "not_a_professional_master_or_DCP":True,
        "physical_windows_installed_acceptance":False}
    if len(_canonical(manifest))>MAX_MANIFEST:
        raise ValueError("The final film index exceeds its 2 MiB budget")
    _write_owned(directory,"candidate-manifest.json",manifest)

def main(argv=None):
    arguments=list(sys.argv[1:] if argv is None else argv)
    if arguments==["--selfcheck"]:
        # Installer-only dependency and dispatch check; no movie, project,
        # native source, worker authority or finished-film claim.
        from backend.nvp_g09f_runtime import runtime_report
        from backend.nvp_g09e_audio import FilmMeter,RATE
        report=runtime_report()
        if not report["native_long_film_modules_available"]:
            return 2
        if FilmMeter(duration_samples=RATE*(10*60+1)).engine != "scipy-accelerated-biquad":
            return 2
        return 0
    parser=argparse.ArgumentParser(description="Fixed NVP film reel worker")
    parser.add_argument("action",choices=("analyze","render","verify","finalize"))
    parser.add_argument("--db",required=True)
    parser.add_argument("--project",required=True)
    parser.add_argument("--job",required=True)
    parser.add_argument("--index",type=int,default=-1)
    args=parser.parse_args(arguments)
    try:
        db,directory=_owned(args)
        record,parts,source=_job(db,args.project,args.job)
        if args.action=="analyze":_analysis(args,db,directory,record,source)
        elif args.action=="render":_render(args,db,directory,record,source)
        elif args.action=="verify":_verify(args,db,directory,record,source)
        else:_finalize(args,db,directory,record,source)
        return 0
    except BaseException as error:
        if sys.stderr is not None:
            print("NVP film reel worker did not complete: "+type(error).__name__,
                  file=sys.stderr)
        return 1

if __name__=="__main__":raise SystemExit(main())
