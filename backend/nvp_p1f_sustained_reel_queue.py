"""P1-F/P2 finite cross-reel ORIGINAL-source work planner, no hidden execution.

Read the independently verified production coverage and propose only the
next missing contiguous source-frame window, ending before the next reel
boundary. A separate creator action must authorize the exact review hash
and each original frame must still obtain fresh one-use worker custody.
No automatic retries of interrupted/invalidated receipts; no automatic
full 30min/3h rendering and no completed-film claims.
"""
from __future__ import annotations

from hashlib import sha256
import json

from backend.nvp_film_index import _require_pid,_id
from backend.nvp_p1f_multishot_reel import P1FDurableShotReels
from backend.nvp_p1f_picture_audio_delivery import P1FVerifiedSegmentDelivery
from backend.nvp_p1f_p2_verified_coverage import P1FVerifiedFilmCoverage
from backend.nvp_p1f_p2_reel_plan import P1FReelPlan

FORMAT="nvp.p1f.sustained.verified_source_work_review.v1"
MAX_BATCH=240


def _digest(obj):
    return sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()


class P1FReviewedReelQueue:
    def __init__(self,journal:P1FDurableShotReels):
        if not isinstance(journal,P1FDurableShotReels):
            raise TypeError("Sustained source queue requires canonical durable host journal")
        self.journal=journal
        self.coverage=P1FVerifiedFilmCoverage(P1FVerifiedSegmentDelivery(journal))
        self.plans=P1FReelPlan(journal.index)

    def review_next(self,pid,plan_id,*,max_frames=MAX_BATCH):
        _require_pid(pid);_id(plan_id,"original movie source plan")
        if type(max_frames) is not int or not 1<=max_frames<=MAX_BATCH:
            raise ValueError("One bounded native approval cannot exceed a 240-frame reel")
        original=self.plans.read(pid,plan_id)
        coverage=self.coverage.verify_coverage(pid,plan_id)
        if original["document_sha256"]!=coverage["plan_document_sha256"]:
            raise RuntimeError("Verified picture/audio coverage no longer matches original edit")
        if coverage["gap_or_overlap"]:
            raise RuntimeError("Discontinuous film coverage needs independent manual reconciliation")
        cursor=coverage["verified_frames"]
        total=original["data"]["frame_count"]
        if cursor==total:
            return {
                "format":FORMAT,"status":"ALL_SOURCE_FRAMES_VERIFIED_NOT_MASTER",
                "project_id":pid,"plan_id":plan_id,
                "plan_document_sha256":original["document_sha256"],
                "frame_count":0,"verified_source_frames":cursor,
                "film_master_created":False,"worker_authorized":False,
            }
        if cursor>total:
            raise RuntimeError("Source coverage count exceeds original film duration")
        reels=original["data"]["reels"]
        matches=[(i,reel) for i,reel in enumerate(reels)
                 if reel["first_frame"]<=cursor<
                    reel["first_frame"]+reel["frame_count"]]
        if len(matches)!=1:
            raise RuntimeError("Original film cursor has no unique source reel")
        reel_index,reel=matches[0]
        offset=cursor-reel["first_frame"]
        length=min(max_frames,reel["frame_count"]-offset)
        if length<1:
            raise RuntimeError("No native source frame in reviewed reel")
        start=self.plans.picture_instant(pid,plan_id,reel_index,offset)
        end=self.plans.picture_instant(pid,plan_id,reel_index,offset+length-1)
        review={
            "format":FORMAT,
            "status":"REVIEW_REQUIRED_NOT_AUTHORIZED",
            "project_id":pid,"plan_id":plan_id,
            "plan_document_sha256":original["document_sha256"],
            "verified_source_frames":cursor,"total_source_frames":total,
            "reel_index":reel_index,"first_frame_offset":offset,
            "frame_count":length,
            "first_original_take_sha256":start["source_take_sha256"],
            "last_original_take_sha256":end["source_take_sha256"],
            "first_original_camera_path":start["source_camera"],
            "last_original_camera_path":end["source_camera"],
            "source_start_tick":start["source_tick"],
            "source_end_tick":end["source_tick"],
            "output_start_tick":start["output_tick"],
            "output_end_tick":end["output_tick"],
            "worker_authorized":False,
            "all_source_frames_rendered":False,
            "film_master_created":False,
        }
        return {**review,"review_sha256":_digest(review)}

    def reserve_next(self,pid,plan_id,batch_id,*,expected_review_sha256,
                     creator_event,max_frames=MAX_BATCH):
        _require_pid(pid);_id(plan_id,"original movie source plan")
        if (type(expected_review_sha256) is not str or
                len(expected_review_sha256)!=64 or
                any(c not in "0123456789abcdef" for c in expected_review_sha256)):
            raise ValueError("Sustained production requires exact reviewed source hash")
        fresh=self.review_next(pid,plan_id,max_frames=max_frames)
        if (fresh.get("status")!="REVIEW_REQUIRED_NOT_AUTHORIZED" or
                fresh["review_sha256"]!=expected_review_sha256):
            raise RuntimeError("Source coverage/reel changed; fresh human review required")
        # This call alone never renders. The durable journal revalidates all
        # per-frame original Takes under its own BEGIN IMMEDIATE admission
        # lock, and prevents another ID from overlapping active/accepted work.
        receipt=self.journal.create_batch(
            pid,plan_id,batch_id,
            reel_index=fresh["reel_index"],
            first_frame_offset=fresh["first_frame_offset"],
            frame_count=fresh["frame_count"],
            creator_event=creator_event)
        return {**receipt,
                "status":"BOUNDED_SOURCE_BATCH_PLANNED_ONLY",
                "source_review_sha256":expected_review_sha256,
                "ready_to_auto_render":False,
                "whole_film_delivered":False}
