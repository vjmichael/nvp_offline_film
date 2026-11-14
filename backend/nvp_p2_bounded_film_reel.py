"""P2 bounded one-use creator reel grants: never background auto-resume.

A trusted host authorizes up to 8 exact original picture+PCM chunks at once.
Each P1-F child grant is consumed once. Already published original chunks are
independently reverified. Crash survivors may be rechecked on the next human
request; no stale grant can be replayed. No film-master or install authority.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from backend.nvp_film_index import _id,_require_pid
from backend.nvp_p1f_sustained_delivery import NativeSustainedPictureSound
from backend.nvp_p2_longform_source_plan import NativeLongformFilmPlan

FORMAT="nvp.p2.bounded_source_film_reel_grant.v1"
MAX_REEL_CHUNKS=8


def _sha(value):
    return hashlib.sha256(json.dumps(
        value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False).encode("ascii")).hexdigest()


class NativeFilmReelBatch:
    def __init__(self,planner:NativeLongformFilmPlan,*,native_creator_approval,
                 render_png,cancelled=lambda:False,progress=lambda **_:None):
        if (not isinstance(planner,NativeLongformFilmPlan) or
            not callable(native_creator_approval) or not callable(render_png)
            or not callable(cancelled) or not callable(progress)):
            raise TypeError("Original P2 planner and trusted bounded native renderer required")
        self.planner=planner
        self.approve=native_creator_approval
        self.renderer=render_png
        self.cancelled=cancelled
        self.progress=progress

    def _prepare(self,project_id,plan_id,revision,*,first_index,limit,
                 output_parent,actor_mix_id,actor_mix_revision):
        _require_pid(project_id)
        _id(plan_id,"original source film plan")
        if (type(first_index) is not int or first_index<0 or
            type(limit) is not int or not 1<=limit<=MAX_REEL_CHUNKS):
            raise ValueError("A native reel grant covers 1 to 8 original film chunks")
        if (actor_mix_id is None)!=(actor_mix_revision is None):
            raise ValueError("Original actor bus needs exact source revision")
        parent=Path(output_parent)
        if parent.is_symlink() or not parent.is_dir():
            raise RuntimeError("Native derivative root is not a trusted plain directory")
        parent=parent.resolve()
        film=self.planner.open(project_id,plan_id,revision)
        data=film["data"]
        page=self.planner.page(project_id,plan_id,revision,
                               first_index=first_index,limit=limit)
        verifier=NativeSustainedPictureSound(
            self.planner.assembly,self.planner.continuity,
            native_creator_approval=lambda *_:False,
            render_png=lambda **_:None)
        intents=[]
        for chunk in page["chunks"]:
            source=verifier.preflight(
                project_id,data["continuity_id"],data["continuity_revision"],
                first_frame=chunk["first_frame"],frame_count=chunk["frame_count"],
                listener_path=data["listener_path"],camera_path=data["camera_path"],
                actor_mix_id=actor_mix_id,actor_mix_revision=actor_mix_revision)
            if (source["source_take_id"]!=chunk["source_take_id"] or
                source["source_take_sha256"]!=chunk["source_take_sha256"] or
                source["source_start_tick"]!=chunk["source_start_tick"] or
                source["source_shot_sha256"]!=chunk["source_shot_sha256"]):
                raise RuntimeError("Requested reel chunk differs from its source-authorized cut")
            child={
                "operation":"nvp.p1f.authorize_original_finite_chunk.v1",
                "project_id":project_id,"chunk_id":chunk["chunk_id"],
                "plan_sha256":_sha(source),
                "output_directory":str(parent/("P1F_"+chunk["chunk_id"])),
                "frames":chunk["frame_count"],
                "full_film_master_approved":False,
                "source_mutation_allowed":False,
            }
            if (parent/("P1F_"+chunk["chunk_id"])).is_symlink():
                raise RuntimeError("Original film derivative target was replaced with a symlink")
            intents.append({"chunk":chunk,"intent":child,
                            "existed":(parent/("P1F_"+chunk["chunk_id"])).exists()})
        if not intents:raise ValueError("Native original source reel is empty")
        grant={
            "format":FORMAT,"project_id":project_id,
            "source_plan_id":plan_id,"source_plan_revision":revision,
            "source_plan_sha256":film["document_sha256"],
            "first_index":first_index,"chunk_count":len(intents),
            "total_frames":sum(x["chunk"]["frame_count"] for x in intents),
            "source_chunk_intents_sha256":_sha([x["intent"] for x in intents]),
            "output_parent":str(parent),"actor_mix_id":actor_mix_id,
            "actor_mix_revision":actor_mix_revision,
            "film_master_approved":False,"automatic_replay_allowed":False,
        }
        return grant,intents,data,parent

    def preflight(self,project_id,plan_id,revision,*,first_index,limit,
                  output_parent,actor_mix_id=None,actor_mix_revision=None):
        return self._prepare(project_id,plan_id,revision,first_index=first_index,
            limit=limit,output_parent=output_parent,actor_mix_id=actor_mix_id,
            actor_mix_revision=actor_mix_revision)[0]

    def render(self,project_id,plan_id,revision,*,first_index,limit,
               output_parent,actor_mix_id=None,actor_mix_revision=None):
        grant,items,source,parent=self._prepare(
            project_id,plan_id,revision,first_index=first_index,limit=limit,
            output_parent=output_parent,actor_mix_id=actor_mix_id,
            actor_mix_revision=actor_mix_revision)
        if self.cancelled():
            raise InterruptedError("Source reel cancelled before human authorization")
        if self.approve(dict(grant)) is not True:
            raise PermissionError("Creator refused exact finite source reel")
        renewed,review,_,_=self._prepare(
            project_id,plan_id,revision,first_index=first_index,limit=limit,
            output_parent=parent,actor_mix_id=actor_mix_id,
            actor_mix_revision=actor_mix_revision)
        if renewed!=grant or review!=items:
            raise RuntimeError("Original reel or approved output slots changed during native consent")
        unused={x["chunk"]["chunk_id"]:x["intent"] for x in items}
        def one_use_child(intent):
            if type(intent) is not dict:return False
            expected=unused.pop(intent.get("chunk_id"),None)
            return expected is not None and intent==expected
        writer=NativeSustainedPictureSound(
            self.planner.assembly,self.planner.continuity,
            native_creator_approval=one_use_child,
            render_png=self.renderer,cancelled=self.cancelled)
        verified=[]
        reused=[]
        for i,row in enumerate(items):
            if self.cancelled():
                raise InterruptedError("Creator cancelled; verified earlier reels remain on disk")
            chunk=row["chunk"]
            ident=chunk["chunk_id"]
            path=parent/("P1F_"+ident)
            if path.exists():
                receipt=writer.verify_chunk(project_id,path)
                if (receipt["plan_sha256"]!=row["intent"]["plan_sha256"] or
                    receipt["first_frame"]!=chunk["first_frame"] or
                    receipt["frame_count"]!=chunk["frame_count"]):
                    raise RuntimeError("Existing original reel derivative is not the requested source")
                unused.pop(ident,None)
                reused.append(ident)
            else:
                receipt=writer.export_chunk(
                    project_id,source["continuity_id"],
                    source["continuity_revision"],ident,parent,
                    first_frame=chunk["first_frame"],
                    frame_count=chunk["frame_count"],
                    listener_path=source["listener_path"],
                    camera_path=source["camera_path"],
                    actor_mix_id=actor_mix_id,
                    actor_mix_revision=actor_mix_revision)
                if receipt["plan_sha256"]!=row["intent"]["plan_sha256"]:
                    raise RuntimeError("P1-F output differs from its native parent one-use grant")
            verified.append({"chunk_id":ident,
                             "manifest_sha256":receipt["manifest_sha256"],
                             "frames":chunk["frame_count"]})
            self.progress(stage="SOURCE_REEL_CHUNK_VERIFIED",
                          completed=len(verified),planned=len(items))
        if unused:
            raise RuntimeError("Unconsumed reel child grants cannot be reported as accepted")
        return {"format":FORMAT,"status":"BOUNDED_REEL_PICTURE_PCM_VERIFIED",
                "source_plan_sha256":grant["source_plan_sha256"],
                "source_chunk_intents_sha256":grant["source_chunk_intents_sha256"],
                "verified_chunks":verified,"reused_verified_chunks":reused,
                "verified_frame_count":sum(x["frames"] for x in verified),
                "all_film_rendered":False,"film_master_approved":False,
                "original_source_modified":False,"auto_restarted_worker":False}
