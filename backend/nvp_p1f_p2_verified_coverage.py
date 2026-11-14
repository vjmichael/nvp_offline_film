"""P1-F/P2 independently verified multi-reel coverage; never a movie master.

Every entry is an actual committed original Cycles PNG/48k WAV *segment*,
not a planned reel count. The entire source film cannot be claimed ready
unless EVERY frame and audio sample is present in exact order and independently
reopened against the original FilmIndex plan and its real worker receipts.
No video/audio codec, film file, master approval or model-generated images.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
import time

from backend.nvp_p1f_picture_audio_delivery import (
    P1FVerifiedSegmentDelivery,FORMAT as SEGMENT_FORMAT)
from backend.nvp_p1f_p2_reel_plan import P1FReelPlan
from backend.nvp_film_index import _require_pid,_id

FORMAT="nvp.p1f.p2.verified_multi_reel_coverage.v1"
FPS=24
PCM_PER_FRAME=2000


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()


class P1FVerifiedFilmCoverage:
    def __init__(self,delivery:P1FVerifiedSegmentDelivery):
        if not isinstance(delivery,P1FVerifiedSegmentDelivery):
            raise TypeError("Only original PNG/WAV independently verified segments accepted")
        self.delivery=delivery
        self.plans=P1FReelPlan(delivery.journal.index)
        self.db=delivery.journal.renderer.supervisor.root/"p1f_film_coverage.sqlite3"
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS verified_segments (
                    project_id TEXT NOT NULL,plan_id TEXT NOT NULL,
                    plan_sha256 TEXT NOT NULL,batch_id TEXT NOT NULL,
                    first_frame INTEGER NOT NULL,frame_count INTEGER NOT NULL,
                    source_manifest_sha256 TEXT NOT NULL,
                    first_source_take_sha256 TEXT NOT NULL,
                    last_source_take_sha256 TEXT NOT NULL,
                    committed_ns INTEGER NOT NULL,
                    PRIMARY KEY(project_id,plan_id,batch_id),
                    UNIQUE(project_id,plan_id,first_frame)
                );
            """)

    @contextmanager
    def _connect(self):
        con=sqlite3.connect(self.db,timeout=15,isolation_level=None)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("PRAGMA busy_timeout=15000")
            yield con
        finally:
            con.close()

    def register(self,project_id,plan_id,batch_id):
        _require_pid(project_id);_id(plan_id,"original production plan")
        # A planned-only batch or interrupted native worker cannot register.
        current=self.delivery.verify_delivered(batch_id)
        if (current.get("format")!=SEGMENT_FORMAT or
                current["project_id"]!=project_id or
                current["plan_id"]!=plan_id or
                current["final_master_approved"] is not False or
                current["whole_film_delivered"] is not False):
            raise RuntimeError("No independently verified original segment identity")
        plan=self.plans.read(project_id,plan_id)
        if current["plan_document_sha256"]!=plan["document_sha256"]:
            raise RuntimeError("Segment source manifest differs from original film plan")
        frames=current["frames"]
        first=frames[0]["global_frame"]
        count=len(frames)
        if (count!=current["frame_count"] or
                count*PCM_PER_FRAME!=current["audio_sample_count_per_channel"] or
                first<0 or first+count>plan["data"]["frame_count"] or
                [f["global_frame"] for f in frames]!=list(range(first,first+count))):
            raise RuntimeError("Source audio/picture interval is incomplete or disordered")
        for frame in frames:
            index=frame["global_frame"]
            reel_index=index//240
            reel_first=plan["data"]["reels"][reel_index]["first_frame"]
            actual=self.plans.picture_instant(
                project_id,plan_id,reel_index,index-reel_first)
            if (frame["original_take_sha256"]!=actual["source_take_sha256"] or
                    frame["source_tick"]!=actual["source_tick"] or
                    frame["output_tick"]!=actual["output_tick"] or
                    frame["camera_path"]!=actual["source_camera"]):
                raise RuntimeError("New segment contains an altered original camera/Take")
        source_sha=_digest(current)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT 1 FROM verified_segments
                    WHERE project_id=? AND plan_id=? AND
                          first_frame<? AND first_frame+frame_count>?""",
                    (project_id,plan_id,first+count,first)).fetchone()
            if row is not None:
                raise RuntimeError("Original film frames overlap an existing verified segment")
            if db.execute("""SELECT 1 FROM verified_segments WHERE project_id=?
                 AND plan_id=? AND batch_id=?""",(project_id,plan_id,batch_id)).fetchone():
                raise RuntimeError("Original batch registration cannot replay")
            db.execute("""INSERT INTO verified_segments VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (project_id,plan_id,plan["document_sha256"],batch_id,
                        first,count,source_sha,frames[0]["original_take_sha256"],
                        frames[-1]["original_take_sha256"],time.time_ns()))
            db.commit()
        return {"status":"SEGMENT_REGISTERED_NOT_FILM",
                "batch_id":batch_id,"first_frame":first,"frame_count":count,
                "plan_document_sha256":plan["document_sha256"],
                "portable_film_created":False}

    def verify_coverage(self,project_id,plan_id):
        """Independently reopen every registered source segment and compare clocks."""
        _require_pid(project_id);_id(plan_id,"original production plan")
        plan=self.plans.read(project_id,plan_id)
        with self._connect() as db:
            rows=db.execute("""SELECT plan_sha256,batch_id,first_frame,
                 frame_count,source_manifest_sha256,
                 first_source_take_sha256,last_source_take_sha256
                 FROM verified_segments WHERE project_id=? AND plan_id=?
                 ORDER BY first_frame,batch_id""",(project_id,plan_id)).fetchall()
        cursor=0;segments=0;broken=[]
        for plan_sha,batch,first,count,manifest_sha,first_take,last_take in rows:
            if first!=cursor:
                broken.append({"gap_or_overlap_at":cursor,"next_frame":first})
                break
            if plan_sha!=plan["document_sha256"]:
                raise RuntimeError("Original FilmIndex plan identity changed")
            current=self.delivery.verify_delivered(batch)
            if (current["project_id"]!=project_id or
                    current["plan_id"]!=plan_id or
                    current["plan_document_sha256"]!=plan_sha or
                    _digest(current)!=manifest_sha or
                    current["frame_count"]!=count or
                    current["frames"][0]["global_frame"]!=first or
                    current["frames"][-1]["global_frame"]!=first+count-1 or
                    current["frames"][0]["original_take_sha256"]!=first_take or
                    current["frames"][-1]["original_take_sha256"]!=last_take):
                raise RuntimeError("Rendered source coverage differs from independent audio/picture proof")
            cursor+=count;segments+=1
        total=plan["data"]["frame_count"]
        if cursor>total:
            raise RuntimeError("Verified source coverage exceeds planned film")
        return {
            "format":FORMAT,"status":(
                "ALL_ORIGINAL_FRAMES_VERIFIED_NOT_MASTER"
                if not broken and cursor==total
                else "PARTIAL_SOURCE_COVERAGE_NOT_FILM"),
            "project_id":project_id,"plan_id":plan_id,
            "plan_document_sha256":plan["document_sha256"],
            "verified_segments":segments,
            "verified_frames":cursor,"required_frames":total,
            "verified_pcm_samples_per_channel":cursor*PCM_PER_FRAME,
            "required_pcm_samples_per_channel":plan["data"]["sample_count"],
            "missing_frames":total-cursor,
            "gap_or_overlap":broken,
            "all_source_frames_verified":not broken and cursor==total,
            "portable_film_created":False,
            "audio_mastered":False,
            "final_film_authorized":False,
        }
