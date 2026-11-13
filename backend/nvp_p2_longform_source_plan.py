"""P2: feature-length immutable original-source film schedule and chunk audit.

A long source cut is indexed by constant-size 24fps film-time chunks without
expanding/storing every source video frame. Publication requires an independent
creator approval. The schedule may be 30 minutes to 2 hours; the *render* is
NOT considered complete merely because a schedule exists. Reconciliation
independently reopens each actual P1-F picture+PCM chunk and its SHA receipts.

No FFmpeg, artificial film footage, permission minting or unlimited background
worker is introduced. Original film master remains separately unauthorized.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_p1d_editorial_continuity import NativeEditorialContinuity
from backend.nvp_p1f_sustained_delivery import (
    NativeSustainedPictureSound,MAX_CHUNK_FRAMES,FRAME_TICKS)
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_temporal_ledger import TICKS_PER_SECOND,_int

FORMAT="nvp.p2.original_film_longform_source_schedule.v1"
MAX_TOTAL_FRAMES=2*60*60*24
MAX_CHUNKS=12000
MAX_PAGE=64
LONGFORM_FRAMES=30*60*24


def _canon(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _sequence(segments):
    """Yield bounded original-time chunk references in immutable cut order."""
    chunk=0
    cursor=0
    for segment in segments:
        first=segment["timeline_start_tick"]
        end=segment["timeline_end_tick"]
        source=segment["source_in_tick"]
        if (first!=cursor or first%FRAME_TICKS or end%FRAME_TICKS or
            source%FRAME_TICKS or segment["source_out_tick"]%FRAME_TICKS or
            end-first != segment["source_out_tick"]-source):
            raise RuntimeError("Feature-length source has a gap or requires hidden retiming")
        i=first//FRAME_TICKS
        stop=end//FRAME_TICKS
        while i<stop:
            n=min(MAX_CHUNK_FRAMES,stop-i)
            if chunk>=MAX_CHUNKS:
                raise ValueError("Long-form film exceeds bounded source chunk budget")
            yield {"index":chunk,"chunk_id":"P2FilmChunk"+str(chunk).zfill(6),
                   "first_frame":i,"frame_count":n,
                   "segment_id":segment["segment_id"],
                   "source_take_id":segment["source_take_id"],
                   "source_take_sha256":segment["source_take_document_sha256"],
                   "source_shot_id":segment["source_shot_id"],
                   "source_shot_sha256":segment["source_shot_document_sha256"],
                   "source_start_tick":str(
                       source+(i-first//FRAME_TICKS)*FRAME_TICKS)}
            chunk+=1
            i+=n
        cursor=end


class NativeLongformFilmPlan:
    def __init__(self,assembly:SlateSequenceAssembly,
                 continuity:NativeEditorialContinuity,*,verify_creator_action):
        if (not isinstance(assembly,SlateSequenceAssembly) or
            not isinstance(continuity,NativeEditorialContinuity) or
            assembly.index is not continuity.index or
            not callable(verify_creator_action)):
            raise TypeError("Native original editorial and creator longform approval required")
        self.assembly=assembly
        self.continuity=continuity
        self.index=assembly.index
        self.approve=verify_creator_action

    def _source(self,project_id,continuity_id,revision):
        record=self.continuity.open(project_id,continuity_id,revision)
        doc=record["data"]
        if doc["review_status"]!="READY_FOR_SEPARATE_EXPORT_AUTHORIZATION":
            raise PermissionError("Original director continuity review remains incomplete")
        edit=self.assembly.open_edit(project_id,doc["edit_id"],doc["edit_revision"])
        return record,edit

    def _prepare(self,project_id,continuity_id,revision,listener_path,camera_path):
        record,edit=self._source(project_id,continuity_id,revision)
        if (type(listener_path) is not str or
            not listener_path.startswith("/World/") or len(listener_path)>240 or
            type(camera_path) is not str or
            not camera_path.startswith("/World/") or len(camera_path)>240):
            raise ValueError("Longform source schedule requires exact authored listener and camera")
        duration=edit["data"]["duration_tick"]
        if duration%FRAME_TICKS:
            raise ValueError("Longform film cannot silently round the source cut")
        frames=duration//FRAME_TICKS
        if not 1<=frames<=MAX_TOTAL_FRAMES:
            raise ValueError("Longform schedule must remain inside 2-hour source ceiling")
        digest=hashlib.sha256()
        count=0
        for chunk in _sequence(edit["data"]["segments"]):
            digest.update(_canon(chunk)+b"\n")
            count+=1
        if not count or count>MAX_CHUNKS:
            raise ValueError("Feature original source requires bounded chunk count")
        return {"format":FORMAT,"continuity_id":continuity_id,
                "continuity_revision":revision,
                "continuity_document_sha256":record["document_sha256"],
                "edit_id":edit["object_id"],"edit_revision":edit["revision"],
                "edit_document_sha256":edit["document_sha256"],
                "listener_path":listener_path,"camera_path":camera_path,
                "duration_tick":str(duration),"total_frames":frames,
                "total_chunks":count,
                "chunk_manifest_sha256":digest.hexdigest(),
                "is_thirty_minute_longform":frames>=LONGFORM_FRAMES,
                "source_frames_rendered":0,
                "original_source_modified":False,
                "final_film_master_approved":False,
                "publication_is_only_a_source_plan":True}

    def publish(self,project_id,plan_id,*,continuity_id,
                continuity_revision,listener_path,camera_path,creator_event,
                expected_revision=0):
        _require_pid(project_id)
        _id(plan_id,"longform source plan")
        _id(continuity_id,"director-edited source")
        _int(expected_revision,"expected source plan revision")
        document=self._prepare(project_id,continuity_id,continuity_revision,
                               listener_path,camera_path)
        if expected_revision:
            old=self.open(project_id,plan_id,expected_revision)
            if old["data"]["edit_document_sha256"]!=document["edit_document_sha256"]:
                raise RuntimeError("Longform source changes require a new plan identity")
        intent={"operation":"nvp.p2.authorize_original_longform_source_plan.v1",
                "project_id":project_id,"plan_id":plan_id,
                "expected_revision":expected_revision,
                "continuity_sha256":document["continuity_document_sha256"],
                "edit_sha256":document["edit_document_sha256"],
                "chunk_manifest_sha256":document["chunk_manifest_sha256"],
                "duration_tick":document["duration_tick"],
                "is_thirty_minute_longform":document["is_thirty_minute_longform"],
                "film_master_approved":False}
        if self.approve(creator_event,dict(intent)) is not True:
            raise PermissionError("Creator did not approve exact longform source schedule")
        if self._prepare(project_id,continuity_id,continuity_revision,
                         listener_path,camera_path)!=document:
            raise RuntimeError("Approved original longform source changed")
        # Use a FilmIndex source revision; old schedules and all historic
        # freezes remain independently verifiable after new editorial work.
        return self.index.register_revision(
            project_id,plan_id,"presentation",document,
            expected_revision=expected_revision,
            dependencies=[
                {"object_id":continuity_id,"revision":continuity_revision,
                 "role":"presentation"},
                {"object_id":document["edit_id"],
                 "revision":document["edit_revision"],
                 "role":"presentation"},
            ])

    def open(self,project_id,plan_id,revision):
        record=self.index.read_revision(project_id,plan_id,revision)
        doc=record["data"]
        if (record["kind"]!="presentation" or doc.get("format")!=FORMAT or
            doc.get("final_film_master_approved") is not False or
            doc.get("publication_is_only_a_source_plan") is not True or
            doc.get("source_frames_rendered")!=0):
            raise RuntimeError("Not a source-only longform film plan")
        current=self._prepare(
            project_id,doc["continuity_id"],doc["continuity_revision"],
            doc["listener_path"],doc["camera_path"])
        if current!=doc:
            raise RuntimeError("Longform original edit or chunk list was modified")
        return record

    def page(self,project_id,plan_id,revision,*,first_index,limit=32):
        record=self.open(project_id,plan_id,revision)
        start=_int(first_index,"first longform reel chunk")
        n=_int(limit,"bounded longform page size",minimum=1,maximum=MAX_PAGE)
        if start>=record["data"]["total_chunks"]:
            raise ValueError("Longform chunk cursor beyond original source schedule")
        doc=record["data"]
        edit=self.assembly.open_edit(project_id,doc["edit_id"],doc["edit_revision"])
        chunks=[]
        for entry in _sequence(edit["data"]["segments"]):
            if entry["index"]<start:continue
            chunks.append(entry)
            if len(chunks)==n:break
        return {"format":FORMAT,"plan_sha256":record["document_sha256"],
                "start_index":start,"chunks":chunks,
                "next_index":start+len(chunks) if
                    start+len(chunks)<doc["total_chunks"] else None,
                "full_film_picture_sound_delivered":False,
                "install_authorized":False}

    def reconcile_page(self,project_id,plan_id,revision,*,output_parent,
                       first_index,limit=32):
        """Never count a frame unless its original picture+PCM hashes reopen."""
        page=self.page(project_id,plan_id,revision,
                       first_index=first_index,limit=limit)
        doc=self.open(project_id,plan_id,revision)["data"]
        parent=Path(output_parent)
        if parent.is_symlink() or not parent.is_dir():
            raise RuntimeError("Original source derivative parent is unavailable")
        verifier=NativeSustainedPictureSound(
            self.assembly,self.continuity,
            native_creator_approval=lambda *_:False,
            render_png=lambda **_:None)
        verified=[]
        missing=[]
        for entry in page["chunks"]:
            candidate=parent/("P1F_"+entry["chunk_id"])
            if not candidate.exists():
                missing.append(entry["chunk_id"])
                continue
            if candidate.is_symlink():
                raise RuntimeError("Longform derived chunk path replaced with symlink")
            proof=verifier.verify_chunk(project_id,candidate)
            expected={
                "first_frame":entry["first_frame"],
                "frame_count":entry["frame_count"],
                "source_take_sha256":entry["source_take_sha256"]}
            if any(proof.get(k)!=v for k,v in expected.items()):
                raise RuntimeError("Longform completed chunk cannot be attributed to this source reel")
            # The original P1-F plan must also belong to THIS exact
            # director/source edit plan and prescribed scene camera.
            manifest=json.loads((candidate/"manifest.json").read_bytes())
            plan=manifest["plan"]
            if (plan["continuity_document_sha256"]!=doc["continuity_document_sha256"] or
                plan["edit_document_sha256"]!=doc["edit_document_sha256"] or
                plan["listener_path"]!=doc["listener_path"] or
                plan["camera_path"]!=doc["camera_path"] or
                plan["source_shot_sha256"]!=entry["source_shot_sha256"] or
                plan["source_start_tick"]!=entry["source_start_tick"]):
                raise RuntimeError("Completed chunk belongs to another source film or optical setup")
            verified.append({"chunk_id":entry["chunk_id"],
                             "manifest_sha256":proof["manifest_sha256"],
                             "frames":entry["frame_count"]})
        return {"format":FORMAT,"plan_sha256":page["plan_sha256"],
                "page_start_index":first_index,
                "verified_chunks":verified,"missing_chunks":missing,
                "verified_frames":sum(v["frames"] for v in verified),
                "full_film_master_approved":False,
                "auto_resumed_worker":False}

    def reconcile_all(self,project_id,plan_id,revision,*,output_parent):
        doc=self.open(project_id,plan_id,revision)["data"]
        count=0
        frames=0
        digest=hashlib.sha256()
        for start in range(0,doc["total_chunks"],MAX_PAGE):
            result=self.reconcile_page(
                project_id,plan_id,revision,output_parent=output_parent,
                first_index=start,limit=MAX_PAGE)
            if result["missing_chunks"]:
                return {"format":FORMAT,"status":"INCOMPLETE_ORIGINAL_SOURCE_DERIVATIVES",
                        "verified_chunks":count,"verified_frames":frames,
                        "first_missing_chunk":result["missing_chunks"][0],
                        "original_source_mutated":False,
                        "master_approved":False}
            for row in result["verified_chunks"]:
                digest.update(_canon(row)+b"\n")
                count+=1
                frames+=row["frames"]
        if count!=doc["total_chunks"] or frames!=doc["total_frames"]:
            raise RuntimeError("A longform film cannot pass without every original source frame")
        return {"format":FORMAT,
                "status":"ALL_TECHNICAL_PICTURE_PCM_DERIVATIVES_VERIFIED_NOT_MASTER",
                "verified_chunks":count,"verified_frames":frames,
                "completed_manifest_chain_sha256":digest.hexdigest(),
                "original_source_mutated":False,"master_approved":False,
                "feature_artistry_accepted":False,
                "physical_creator_accepted":False}
