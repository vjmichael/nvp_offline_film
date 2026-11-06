"""INDEX-TIME-09: actual Film Time assembly -> temporary synchronized A/V proxy.

Only the host-approved OS-contained worker may call execute(). Original
external source files are READ ONLY and stay the source of truth. This module
calculates a sealed, revision-scoped preview edit decision and composes a
bounded 24fps review proxy with 48kHz stereo AAC; output is NEVER a conform,
an accepted master, nor a mutation of source, Slate or authored Film Time.

Original timestamp decisions and cut/gap order use saved VFR FilmIndex
source PTS, not nominal source FPS. The proxy's 24fps picture sampling and
AAC latency are explicitly preview-only (not frame-exact source conform).
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from backend.nvp_index_time05_desktop_read import FilmTimeDesktopRead
from backend.nvp_film_index import FilmIndex, _sha
from backend.nvp_temporal_ledger import TICKS_PER_SECOND,MAX_TICK
from backend.nvp_source_window_decode import _read_sources
from backend.nvp_native_frame_index import stamp
from backend.nvp_studio import Studio

FORMAT="nvp.index_time09.av_proxy_plan.v1"
RECEIPT_FORMAT="nvp.index_time09.av_proxy_receipt.v1"
RATE=48000
FPS=24
MAX_SECONDS=1200
MAX_PARTS=48
MAX_BYTES=160*1024*1024
MAX_SOURCE_PATHS=32
MAX_DIM=(960,540)
DRIFT_SECONDS=Fraction(1,20)  # review tolerance: 50 ms
TICK_PER_SAMPLE=TICKS_PER_SECOND//RATE

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")

def _decimal(value):
    with localcontext() as c:
        c.prec=38
        return format(Decimal(value.numerator)/Decimal(value.denominator),".12f")

def _seconds(tick):
    return _decimal(Fraction(tick,TICKS_PER_SECOND))

def _from_pts(pts,num,den):
    return _decimal(Fraction(pts*num,den))

def _run(args,timeout=180):
    result=subprocess.run(args,stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    if result.returncode:
        raise RuntimeError("Bounded native media operation failed: "+
                           result.stderr.decode("utf8","replace")[-1200:])
    return result.stdout

def _probe(source,ffprobe):
    response=_run([str(ffprobe),"-v","error","-show_streams",
                  "-of","json",str(source)],timeout=60)
    streams=json.loads(response)["streams"]
    has_video=any(x.get("codec_type")=="video" for x in streams)
    if not has_video:raise RuntimeError("Original source has no actual video stream")
    return any(x.get("codec_type")=="audio" for x in streams)

def _head(reader,pid,edit_id,revision,sha):
    _sha(sha)
    current=reader.index.read_revision(pid,edit_id)
    prior=reader.index.read_revision(pid,edit_id,revision)
    if (current["revision"]!=revision or
        current["document_sha256"]!=sha or
        prior["document_sha256"]!=sha):
        raise RuntimeError("Original editorial assembly changed before review")
    if reader._publisher.verify_revision(
        pid,edit_id,revision)["edit_document_sha256"]!=sha:
        raise RuntimeError("Original Film Time clip manifest changed")
    return prior

def plan(studio,reader,project_id,edit_id,revision,sha,start_tick,*,ffprobe):
    """Plan a continuous A/V review proxy for at most 20 Film Time minutes.

    The plan binds every source PTS interval and held Film Time interval,
    pre-existing source file path *only inside native host memory*, source
    stamp, project, original media SHA and exact edit head revision.
    """
    if type(start_tick) is not int or not 0<=start_tick<=MAX_TICK:
        raise ValueError("Exact authored Film Time position required")
    reader._seek_resolver()
    record=_head(reader,project_id,edit_id,revision,sha)
    duration=record["data"]["duration_tick"]
    if start_tick>=duration:raise ValueError("Review playhead is at end of assembly")
    limit=min(start_tick+MAX_SECONDS*TICKS_PER_SECOND,duration)
    if limit<=start_tick:raise ValueError("Empty continuous film review")
    rows=[];after=-1
    while len(rows)<record["data"]["clip_count"]:
        # The public browser reader intentionally omits private asset SHA,
        # source timebase and media PTS needed to compose a trustworthy A/V
        # proxy. Use the verified native publisher's full clip rows instead.
        page=reader._publisher.clips(project_id,edit_id,revision,
                                    after_ordinal=after,limit=100)
        if (page["edit_document_sha256"]!=sha or not page["clips"]):
            raise RuntimeError("Incomplete original source clip manifest")
        rows.extend(page["clips"])
        after=rows[-1]["ordinal"]
    if len(rows)!=record["data"]["clip_count"]:
        raise RuntimeError("Immutable original assembly clip count changed")
    pieces=[]
    cursor=start_tick
    sources={}
    for row in rows:
        left=int(row["film_start_tick"]);right=int(row["film_end_tick"])
        if right<=cursor:continue
        if left>=limit:break
        if len(pieces)>=MAX_PARTS:break
        if left>cursor:
            gap=min(left,limit)-cursor
            if gap>0:
                pieces.append({"kind":"gap","duration_tick":gap})
                cursor+=gap
        if cursor>=limit or len(pieces)>=MAX_PARTS:break
        if right<=cursor:continue
        source_first=int(row["source_in_pts"])
        source_last=int(row["source_out_pts"])
        film_first=left;film_last=right
        if cursor>left:
            first=reader.seek(project_id,edit_id,revision,
                              expected_edit_sha256=sha,tick=cursor)
            if first["status"]!="INDEXED_SOURCE_FRAME_SELECTED" or (
                first["clip_ordinal"]!=row["ordinal"]):
                raise RuntimeError("Original source start could not map to PTS")
            source_first=int(first["source_pts"])
            film_first=int(first["frame_film_start_tick"])
            if film_first<cursor:
                # Preserve the selection's fractional held frame by using
                # the actual source boundary; report snapped start openly.
                if pieces:raise RuntimeError("Non-increasing source PTS near clip cut")
                cursor=film_first
        if right>limit:
            last=reader.seek(project_id,edit_id,revision,
                             expected_edit_sha256=sha,tick=limit-1)
            if (last["status"]!="INDEXED_SOURCE_FRAME_SELECTED" or
                last["clip_ordinal"]!=row["ordinal"]):
                raise RuntimeError("Original source end could not map to PTS")
            source_last=int(last["next_source_pts"])
            film_last=int(last["frame_film_end_tick"])
        if film_last<=film_first or source_last<=source_first:
            raise RuntimeError("Original source interval collapsed")
        sid=row["source_id"]
        if sid not in sources:
            if len(sources)>=MAX_SOURCE_PATHS:
                raise ValueError("Too many original source recordings for one review")
            source=reader.index.read_revision(
                project_id,sid,row["source_revision"])
            if (source["document_sha256"]!=row["source_document_sha256"] or
                source["data"]["content_sha256"]!=row["source_sha256"]):
                raise RuntimeError("Original asset identity changed")
            path=_read_sources(studio,project_id,sid)
            if path.is_symlink() or not path.is_file():
                raise RuntimeError("Source footage unavailable without a local file")
            sources[sid]={
                "path":str(path),"stamp":stamp(path),
                "content_sha256":row["source_sha256"],
                "source_revision":row["source_revision"],
                "source_document_sha256":row["source_document_sha256"],
                "has_audio":_probe(path,ffprobe),
            }
        src=sources[sid]
        if (src["source_revision"]!=row["source_revision"] or
            src["content_sha256"]!=row["source_sha256"]):
            raise RuntimeError("Different versions of one source ID require separate review")
        piece={
            "kind":"source","source_id":sid,
            "source_revision":row["source_revision"],
            "source_document_sha256":row["source_document_sha256"],
            "film_start_tick":film_first,
            "duration_tick":film_last-film_first,
            "source_start_pts":source_first,"source_end_pts":source_last,
            "time_base_num":row["time_base_num"],
            "time_base_den":row["time_base_den"],
            "has_audio":src["has_audio"],
        }
        pieces.append(piece)
        cursor=film_last
    if not pieces:raise RuntimeError("Nothing visible occurs after selected playhead")
    if not any(p["kind"]=="source" for p in pieces):
        raise RuntimeError("No original camera footage within bounded review window")
    # Output CFR frames/audio samples are a derived review representation,
    # never a claim that the original source was constant-frame-rate.
    output_frames=0
    for item in pieces:
        frame_count=(
            item["duration_tick"]*FPS+TICKS_PER_SECOND//2
        )//TICKS_PER_SECOND
        if frame_count<=0:
            raise RuntimeError("Edit contains a sub-frame interval not previewable at 24fps")
        item["review_frames"]=frame_count
        output_frames+=frame_count
    if output_frames>MAX_SECONDS*FPS+MAX_PARTS:
        raise RuntimeError("Native audio/video proxy exceeds bounded 20-minute review")
    return {
        "format":FORMAT,"project_id":project_id,
        "edit_id":edit_id,"edit_revision":revision,
        "edit_document_sha256":sha,
        "requested_start_tick":start_tick,
        "actual_start_tick":start_tick if pieces[0]["kind"]=="gap" else (
            pieces[0]["film_start_tick"]),
        "review_duration_tick":sum(p["duration_tick"] for p in pieces),
        "expected_review_frames":output_frames,
        "fps":FPS,"sample_rate":RATE,"channels":2,
        "sources":sources,"parts":pieces,
        "original_sources_modified":False,
        "output_is_unapproved_proxy":True,
        "master_approved":False,
    }

def _graph(pl):
    args=[]
    video=[]
    audio=[]
    for i,item in enumerate(pl["parts"]):
        n=item["review_frames"]
        if item["kind"]=="gap":
            video.append(
                f"color=c=black:s=640x360:r=24,trim=end_frame={n},"
                f"setpts=N/(24*TB),format=yuv420p[v{i}]")
            audio.append(
                f"anullsrc=r=48000:cl=stereo,atrim=end_sample={n*2000},"
                f"asetpts=N/SR/TB[a{i}]")
            continue
        src=pl["sources"][item["source_id"]]
        ix=len(args)
        args.append(src["path"])
        begin=_from_pts(item["source_start_pts"],
                        item["time_base_num"],item["time_base_den"])
        end=_from_pts(item["source_end_pts"],
                      item["time_base_num"],item["time_base_den"])
        video.append(
            f"[{ix}:v:0]trim=start={begin}:end={end},"
            f"setpts=PTS-STARTPTS,fps=24,"
            f"scale=640:360:force_original_aspect_ratio=decrease,"
            f"pad=640:360:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"tpad=stop_mode=clone:stop_duration=2,"
            f"trim=end_frame={n},setpts=N/(24*TB),format=yuv420p[v{i}]")
        if item["has_audio"]:
            audio.append(
                f"[{ix}:a:0]aresample=48000:async=1:first_pts=0,"
                f"atrim=start={begin}:end={end},asetpts=PTS-STARTPTS,"
                f"aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo,"
                f"apad,atrim=end_sample={n*2000},"
                f"asetpts=N/SR/TB[a{i}]")
        else:
            audio.append(
                f"anullsrc=r=48000:cl=stereo,atrim=end_sample={n*2000},"
                f"asetpts=N/SR/TB[a{i}]")
    chain=";".join(video+audio+[
        "".join(f"[v{i}][a{i}]" for i in range(len(pl["parts"])))+
        f"concat=n={len(pl['parts'])}:v=1:a=1[v][a]"
    ])
    return args,chain

def verify(destination,plan,ffprobe):
    """Independent mux/PTS/sample-clock and source custodian check."""
    dest=Path(destination)
    movie=dest/"source_review.mp4"
    receipt=dest/"review_receipt.json"
    if (dest.is_symlink() or movie.is_symlink() or receipt.is_symlink() or
        not movie.is_file() or not receipt.is_file() or
        movie.stat().st_size<256 or movie.stat().st_size>MAX_BYTES or
        receipt.stat().st_size>65536):
        raise RuntimeError("Untrusted or unbounded A/V review derivative")
    raw=receipt.read_bytes()
    document=json.loads(raw)
    if (raw!=canonical(document) or
        document.get("format")!=RECEIPT_FORMAT or
        document.get("plan_sha256")!=sha256(canonical(plan)).hexdigest() or
        document.get("media_sha256")!=_sha_file(movie) or
        document.get("size_bytes")!=movie.stat().st_size or
        document.get("master_approved") is not False or
        document.get("original_modified") is not False):
        raise RuntimeError("Synchronized preview media/receipt was altered")
    from backend.nvp_source_window_decode import _sha_file
    info=json.loads(_run([
        str(ffprobe),"-v","error","-show_streams","-show_format",
        "-of","json",str(movie)],timeout=90))
    streams=info["streams"]
    video=[s for s in streams if s.get("codec_type")=="video"]
    audio=[s for s in streams if s.get("codec_type")=="audio"]
    if (len(video)!=1 or len(audio)!=1 or
        video[0].get("codec_name")!="h264" or
        video[0].get("r_frame_rate")!="24/1" or
        int(video[0].get("nb_frames",0))!=plan["expected_review_frames"] or
        audio[0].get("codec_name")!="aac" or
        int(audio[0].get("sample_rate",0))!=RATE or
        int(audio[0].get("channels",0))!=2):
        raise RuntimeError("Preview stream codec/rate/sound contract changed")
    expected=Fraction(plan["expected_review_frames"],FPS)
    vduration=Fraction(str(video[0]["duration"]))
    aduration=Fraction(str(audio[0]["duration"]))
    if (abs(vduration-expected)>DRIFT_SECONDS or
        abs(aduration-expected)>DRIFT_SECONDS or
        abs(aduration-vduration)>DRIFT_SECONDS):
        raise RuntimeError("Native A/V sync drift exceeds 50 ms technical preview bound")
    return {
        "format":RECEIPT_FORMAT,
        "status":"VERIFIED_UNAPPROVED_AV_REVIEW",
        "project_id":plan["project_id"],
        "edit_id":plan["edit_id"],
        "edit_revision":plan["edit_revision"],
        "edit_document_sha256":plan["edit_document_sha256"],
        "media_sha256":document["media_sha256"],
        "size_bytes":document["size_bytes"],
        "duration_seconds":_decimal(expected),
        "video_frames":plan["expected_review_frames"],
        "sample_rate":RATE,"channels":2,
        "av_drift_ms":str(float(abs(aduration-vduration))*1000),
        "source_integrity":"STAMP_UNVERIFIED_REVIEW_ONLY",
        "original_modified":False,"master_approved":False,
    }

def execute(studio_path,plan,destination,ffmpeg,ffprobe,*,timeout=1200):
    """Invoke only INSIDE a host-approved, OS-contained native worker."""
    from backend.nvp_source_media_inventory import SourceMediaInventory
    from backend.nvp_external_media_catalog import ExternalMediaCatalog
    from backend.nvp_source_film_bridge import SourceFilmBridge
    from backend.nvp_native_frame_index import NVPFrameIndex
    from backend.nvp_film_time_editorial import FilmTimeEditorialPublisher
    if plan.get("format")!=FORMAT:
        raise ValueError("Not an approved native Film Time A/V plan")
    base=Path(studio_path)
    src=Studio(base)
    ffmpeg=Path(ffmpeg);ffprobe=Path(ffprobe)
    if any(not p.is_absolute() or p.is_symlink() or not p.is_file()
           for p in (ffmpeg,ffprobe)):
        raise RuntimeError("Pinned FFmpeg/FFprobe media tools are unavailable")
    catalog=ExternalMediaCatalog(src)
    publisher=FilmTimeEditorialPublisher(
        FilmIndex(src),SourceFilmBridge(FilmIndex(src),SourceMediaInventory(catalog)),
        NVPFrameIndex(base.parent/".native-source-review"/"indexes",ffprobe=ffprobe))
    reader=FilmTimeDesktopRead(src,ffprobe_path=ffprobe,
                              index_root=base.parent/".native-source-review"/"indexes")
    current=_head(reader,plan["project_id"],plan["edit_id"],
                  plan["edit_revision"],plan["edit_document_sha256"])
    if current["document_sha256"]!=plan["edit_document_sha256"]:
        raise RuntimeError("Current original editorial source changed")
    checked=globals()["plan"](
        src,reader,plan["project_id"],plan["edit_id"],
        plan["edit_revision"],plan["edit_document_sha256"],
        plan["requested_start_tick"],ffprobe=ffprobe)
    if checked!=plan:
        raise RuntimeError("Sealed source/audio timeline changed before decode")
    dest=Path(destination)
    if (not dest.is_absolute() or dest.is_symlink() or dest.exists() or
        not dest.parent.is_dir() or dest.parent.is_symlink()):
        raise RuntimeError("A/V proxy destination must be new under trusted host")
    dest.mkdir(parents=True,mode=0o700)
    try:
        for source in plan["sources"].values():
            path=Path(source["path"])
            if stamp(path)!=source["stamp"]:
                raise RuntimeError("Frozen source stamp changed before review")
        inputs,graph=_graph(plan)
        command=[str(ffmpeg),"-hide_banner","-v","error","-nostdin","-xerror",
                 "-y"]
        for path in inputs:command+=["-i",path]
        command+=["-filter_complex",graph,
                  "-map","[v]","-map","[a]",
                  "-c:v","libx264","-preset","veryfast","-crf","31",
                  "-c:a","aac","-b:a","128k",
                  "-ar","48000","-ac","2",
                  "-movflags","+faststart",
                  "-max_muxing_queue_size","512",
                  str(dest/"source_review.mp4")]
        _run(command,timeout=timeout)
        for source in plan["sources"].values():
            if stamp(Path(source["path"]))!=source["stamp"]:
                raise RuntimeError("Frozen source stamp changed during native A/V decode")
        if (globals()["plan"](
                src,reader,plan["project_id"],plan["edit_id"],
                plan["edit_revision"],plan["edit_document_sha256"],
                plan["requested_start_tick"],ffprobe=ffprobe)!=plan):
            raise RuntimeError("Saved Film Time assembly changed during proxy decode")
        media=dest/"source_review.mp4"
        if not media.is_file() or media.stat().st_size>MAX_BYTES:
            raise RuntimeError("Bounded A/V proxy exceeded 160 MiB")
        from backend.nvp_source_window_decode import _sha_file
        receipt={
            "format":RECEIPT_FORMAT,
            "plan_sha256":sha256(canonical(plan)).hexdigest(),
            "media_sha256":_sha_file(media),
            "size_bytes":media.stat().st_size,
            "original_modified":False,"master_approved":False,
        }
        with (dest/"review_receipt.json").open("xb") as out:
            out.write(canonical(receipt))
            out.flush()
            os.fsync(out.fileno())
        return verify(dest,plan,ffprobe)
    except BaseException:
        # Partial output is not a published/verified source review.
        # Native host owns cancellation and post-crash OS reconciliation.
        raise
