"""P2: feature-length immutable original-source film schedule and chunk audit.

A long source cut is indexed by constant-size 24fps film-time chunks without
expanding/storing every source video frame. Publication requires an independent
creator approval. The schedule uses exact bounded chunk identities; the *render* is
NOT considered complete merely because a schedule exists. Reconciliation
independently reopens each actual P1-F picture+PCM chunk and its SHA receipts.

No FFmpeg, artificial film footage, permission minting or unlimited background
worker is introduced. Original film master remains separately unauthorized.
"""
from __future__ import annotations

from backend.nvp_performance_probe import measured, span, observe_windows_job

import hashlib
import json
from pathlib import Path

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_p1d_editorial_continuity import NativeEditorialContinuity
from backend.nvp_p1f_sustained_delivery import (
    NativeSustainedPictureSound,MAX_CHUNK_FRAMES,FRAME_TICKS)
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_temporal_ledger import TICKS_PER_SECOND,_int
from backend.nvp_longfilm_schedule import ChunkSchedule,MAX_TOTAL_FRAMES,MAX_CHUNKS,MAX_PAGE

FORMAT="nvp.p2.original_film_longform_source_schedule.v1"
LONGFORM_FRAMES=30*60*24


def _canon(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True,allow_nan=False).encode("ascii")


def _sequence(segments):
    """Preserve the original canonical v1 chunk sequence."""
    yield from ChunkSchedule(segments).entries()


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
        return self._prepare_schedule(project_id,continuity_id,revision,
                                      listener_path,camera_path)[0]

    @measured("reel.plan")
    def _prepare_schedule(self,project_id,continuity_id,revision,listener_path,camera_path,*,
                          cancelled=lambda:False):
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
            raise ValueError("Longform schedule exceeds exact source address range")
        schedule=ChunkSchedule(edit["data"]["segments"])
        if schedule.total_frames!=frames:
            raise RuntimeError("Original schedule does not cover the exact edit duration")
        digest=schedule.digest(cancelled=cancelled)
        count=schedule.total_chunks
        return {"format":FORMAT,"continuity_id":continuity_id,
                "continuity_revision":revision,
                "continuity_document_sha256":record["document_sha256"],
                "edit_id":edit["object_id"],"edit_revision":edit["revision"],
                "edit_document_sha256":edit["document_sha256"],
                "listener_path":listener_path,"camera_path":camera_path,
                "duration_tick":str(duration),"total_frames":frames,
                "total_chunks":count,
                "chunk_manifest_sha256":digest,
                "is_thirty_minute_longform":frames>=LONGFORM_FRAMES,
                "source_frames_rendered":0,
                "original_source_modified":False,
                "final_film_master_approved":False,
                "publication_is_only_a_source_plan":True},schedule

    @measured("reel.publish")
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
        return self._open_schedule(project_id,plan_id,revision)[0]

    def _open_schedule(self,project_id,plan_id,revision,*,cancelled=lambda:False):
        if cancelled():
            raise InterruptedError("Creator cancelled original schedule validation")
        record=self.index.read_revision(project_id,plan_id,revision)
        doc=record["data"]
        if (record["kind"]!="presentation" or doc.get("format")!=FORMAT or
            doc.get("final_film_master_approved") is not False or
            doc.get("publication_is_only_a_source_plan") is not True or
            doc.get("source_frames_rendered")!=0):
            raise RuntimeError("Not a source-only longform film plan")
        current,schedule=self._prepare_schedule(
            project_id,doc["continuity_id"],doc["continuity_revision"],
            doc["listener_path"],doc["camera_path"],cancelled=cancelled)
        if current!=doc:
            raise RuntimeError("Longform original edit or chunk list was modified")
        return record,schedule

    def page(self,project_id,plan_id,revision,*,first_index,limit=32):
        record,schedule=self._open_schedule(project_id,plan_id,revision)
        return self._page(record,schedule,first_index,limit)

    @staticmethod
    def _page(record,schedule,first_index,limit):
        start=_int(first_index,"first longform reel chunk")
        n=_int(limit,"bounded longform page size",minimum=1,maximum=MAX_PAGE)
        doc=record["data"]
        chunks=schedule.page(start,n)
        return {"format":FORMAT,"plan_sha256":record["document_sha256"],
                "start_index":start,"chunks":chunks,
                "next_index":start+len(chunks) if
                    start+len(chunks)<doc["total_chunks"] else None,
                "full_film_picture_sound_delivered":False,
                "install_authorized":False}

    def reconcile_page(self,project_id,plan_id,revision,*,output_parent,
                       first_index,limit=32,require_protected_worker=False,
                       native_worker_verifier=None,cancelled=lambda:False):
        """Never count a frame unless its original picture+PCM hashes reopen."""
        if not callable(cancelled):
            raise TypeError("Reconciliation cancellation must come from trusted host")
        record,schedule=self._open_schedule(project_id,plan_id,revision,cancelled=cancelled)
        return self._reconcile_verified_page(project_id,record,schedule,
            output_parent=output_parent,first_index=first_index,limit=limit,
            require_protected_worker=require_protected_worker,
            native_worker_verifier=native_worker_verifier,cancelled=cancelled)

    def _reconcile_verified_page(self,project_id,record,schedule,*,output_parent,
                                 first_index,limit,require_protected_worker,
                                 native_worker_verifier,cancelled):
        page=self._page(record,schedule,first_index,limit)
        doc=record["data"]
        parent=Path(output_parent)
        if parent.is_symlink() or not parent.is_dir():
            raise RuntimeError("Original source derivative parent is unavailable")
        verifier=NativeSustainedPictureSound(
            self.assembly,self.continuity,
            native_creator_approval=lambda *_:False,
            render_png=lambda **_:None,
            require_protected_worker=require_protected_worker,
            native_worker_verifier=native_worker_verifier)
        if not callable(cancelled):
            raise TypeError("Reconciliation cancellation must come from trusted host")
        verified=[]
        missing=[]
        for entry in page["chunks"]:
            if cancelled():
                raise InterruptedError("Creator cancelled independent source reel audit")
            candidate=parent/("P1F_"+entry["chunk_id"])
            if candidate.is_symlink():
                raise RuntimeError("Longform derived chunk path replaced with symlink")
            if not candidate.exists():
                missing.append(entry["chunk_id"])
                continue
            proof=verifier.verify_chunk(project_id,candidate)
            expected={
                "chunk_id":entry["chunk_id"],
                "first_frame":entry["first_frame"],
                "frame_count":entry["frame_count"],
                "source_take_id":entry["source_take_id"],
                "source_take_sha256":entry["source_take_sha256"],
                "source_shot_id":entry["source_shot_id"],
                "source_shot_sha256":entry["source_shot_sha256"],
                "source_start_tick":entry["source_start_tick"],
                "audio_samples":entry["frame_count"] * 2000}
            if any(proof.get(k)!=v for k,v in expected.items()):
                raise RuntimeError("Longform completed chunk cannot be attributed to this source reel")
            # The original P1-F plan must also belong to THIS exact
            # director/source edit plan and prescribed scene camera.
            if (proof["continuity_document_sha256"]!=doc["continuity_document_sha256"] or
                proof["source_edit_sha256"]!=doc["edit_document_sha256"] or
                proof["listener_path"]!=doc["listener_path"] or
                proof["camera_path"]!=doc["camera_path"]):
                raise RuntimeError("Completed chunk belongs to another source film or optical setup")
            if (require_protected_worker and
                    proof.get("protected_worker_independently_reopened") is not True):
                raise RuntimeError("Unreopened native Blender frame cannot count toward a film")
            verified.append({"chunk_id":entry["chunk_id"],
                             "first_frame":entry["first_frame"],
                             "manifest_sha256":proof["manifest_sha256"],
                             "audio_sha256":proof["audio_sha256"],
                             "frames":entry["frame_count"],
                             "audio_samples":proof["audio_samples"],
                             "protected_worker_independently_reopened":
                                 proof["protected_worker_independently_reopened"]})
        return {"format":FORMAT,"plan_sha256":page["plan_sha256"],
                "page_start_index":first_index,
                "verified_chunks":verified,"missing_chunks":missing,
                "verified_frames":sum(v["frames"] for v in verified),
                "all_protected_workers_independently_reopened":
                    bool(require_protected_worker and
                         not missing and
                         all(x["protected_worker_independently_reopened"]
                             for x in verified)),
                "full_film_master_approved":False,
                "auto_resumed_worker":False}

    @measured("reel.analysis")
    def reconcile_all(self,project_id,plan_id,revision,*,output_parent,
                      require_protected_worker=False,native_worker_verifier=None,
                      cancelled=lambda:False,progress=lambda **_:None):
        if not callable(cancelled) or not callable(progress):
            raise TypeError("Native full-film audit requires host cancellation and progress")
        record,schedule=self._open_schedule(project_id,plan_id,revision,cancelled=cancelled)
        doc=record["data"]
        count=0
        frames=0
        samples=0
        digest=hashlib.sha256()
        for start in range(0,doc["total_chunks"],MAX_PAGE):
            if cancelled():
                raise InterruptedError("Creator cancelled full original source audit")
            result=self._reconcile_verified_page(
                project_id,record,schedule,output_parent=output_parent,
                first_index=start,limit=MAX_PAGE,
                require_protected_worker=require_protected_worker,
                native_worker_verifier=native_worker_verifier,
                cancelled=cancelled)
            if result["missing_chunks"]:
                return {"format":FORMAT,"status":"INCOMPLETE_ORIGINAL_SOURCE_DERIVATIVES",
                        "verified_chunks":count,"verified_frames":frames,
                        "first_missing_chunk":result["missing_chunks"][0],
                        "original_source_mutated":False,
                        "master_approved":False}
            for row in result["verified_chunks"]:
                digest.update(_canon(row)+b"\n")
                if (row["first_frame"] != frames or
                    row["audio_samples"] != row["frames"] * 2000):
                    raise RuntimeError("Original reel picture/audio clock has a gap or overlap")
                count+=1
                frames+=row["frames"]
                samples+=row["audio_samples"]
            progress(stage="REOPENED_ORIGINAL_SOURCE_REELS",
                     completed=count,planned=doc["total_chunks"],
                     frames=frames,pcm_samples=samples)
        # Revalidate the immutable source at the end, never trust a prior-session cache.
        reopened,_=self._open_schedule(project_id,plan_id,revision,cancelled=cancelled)
        if reopened["document_sha256"]!=record["document_sha256"]:
            raise RuntimeError("Original longform plan changed during independent audit")
        if (count!=doc["total_chunks"] or frames!=doc["total_frames"] or
            samples!=doc["total_frames"]*2000):
            raise RuntimeError("A longform film cannot pass without every original source frame")
        return {"format":FORMAT,
                "status":"ALL_TECHNICAL_PICTURE_PCM_DERIVATIVES_VERIFIED_NOT_MASTER",
                "verified_chunks":count,"verified_frames":frames,
                "verified_audio_samples_48khz":samples,
                "verified_30_minute_original_film":(
                    require_protected_worker and
                    frames >= LONGFORM_FRAMES and doc["is_thirty_minute_longform"]),
                "protected_workers_independently_reopened":
                    bool(require_protected_worker),
                "completed_manifest_chain_sha256":digest.hexdigest(),
                "original_source_mutated":False,"master_approved":False,
                "feature_artistry_accepted":False,
                "physical_creator_accepted":False}
