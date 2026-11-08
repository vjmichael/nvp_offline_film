"""FILM03-06: real source-derived ActorID gait worker via NVP Blender supervisor.

The host reopens an actual frozen OpenUSD Take, its complete StoryBible
ActorID cast, real source meshes, original 3D transforms and the latest
director-approved character motion profile before stage. Blender only
receives an approved SHA-bound packet. The returned .blend and real Cycles
PNG are unapproved new-motion candidates, never a rewritten original Take.
"""
from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import json
import math
import shutil

from backend.nvp_film03_actor_identity_core import ActorIdentityCore, canonical, digest
from backend.nvp_blender_worker import BlenderWorkerSupervisor, BlenderOperation, sha_file
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_production_bible_actors import ProductionBibleActors
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

PACKET_FORMAT="nvp.film03.actor_animation_packet.v1"
AUDIT_FORMAT="nvp.film03.blender_actor_motion_native_receipt.v1"
CANDIDATE_FORMAT="nvp.film03.unapproved_actor_motion_blend.v1"
PRESETS={"steady","lopsided_roll","uneven_step"}
FPS=24
TICK=TICKS_PER_SECOND//FPS
MAX_FRAMES=24


def gait(preset,n):
    if preset=="steady":return 0.0,0.0
    if preset=="lopsided_roll":
        return 0.10*math.sin(n*math.pi/2)+0.05*(n%3==2),0.075*math.sin(n*math.pi/3)
    if preset=="uneven_step":
        return (0.13 if n%4 in (1,2) else 0), (0.05 if n%2 else -0.05)
    raise PermissionError("Unsupported reviewed ActorID animation gait")


class ReviewedActorAnimationHost:
    def __init__(self,index,supervisor,*,verify_creator_action):
        if (not isinstance(index,FilmIndex) or
                not isinstance(supervisor,BlenderWorkerSupervisor) or
                not callable(verify_creator_action)):
            raise TypeError("Real FilmIndex + existing Blender supervisor + director authorization required")
        self.index=index
        self.worker=supervisor
        self.approve=verify_creator_action

    def plan(self,pid,actor_id,*,profile_revision,take_id,
             first_frame_in_take=0,frame_count=8):
        _require_pid(pid)
        _id(take_id,"frozen original OpenUSD source Take")
        _id(actor_id,"canonical ActorID")
        if (type(first_frame_in_take) is not int or first_frame_in_take<0
                or type(frame_count) is not int or
                not 2<=frame_count<=MAX_FRAMES):
            raise ValueError("A bounded source Take animation frame window is required")
        identity=ActorIdentityCore(
            self.index,verify_creator_action=lambda *_:False).current(pid,actor_id)
        current=identity["current"]
        if (not current or current["profile_revision"]!=profile_revision or
                identity["profile_voice_cast_stale"]):
            raise PermissionError("Not the latest authorized ActorID profile and VoiceID")
        profile=current["profile"]
        preset=profile["movement"].get("gait_preset","unconfigured")
        if preset not in PRESETS:
            raise PermissionError("Character movement is prose only; director must configure a typed gait preset")
        cast=ProductionBibleActors(
            self.index.studio).require_complete_cast(pid,take_id)
        prims=[prim for prim,aid in cast["actor_id_by_prim"].items() if aid==actor_id]
        if len(prims)!=1:
            raise PermissionError("ActorID must have one original cast prim in selected source Take")
        take=self.index.read_revision(pid,take_id,1)
        if take["document_sha256"]!=cast["take_sha256"] or take["kind"]!="take":
            raise PermissionError("Original Take changed before gait worker staging")
        if (first_frame_in_take+frame_count)*TICK>take["data"]["duration_tick"]:
            raise PermissionError("Actor animation would cross the source Take duration")
        original=FrozenSceneAV(
            self.index,pid,take_id,
            expected_take_sha256=take["document_sha256"],
            listener_path="/World/Camera")
        reg=OpenUSDAssetRegistry(self.index)
        frames=[]
        assets={}
        try:
            for n in range(frame_count):
                frame_no=first_frame_in_take+n
                snap=original.snapshot(frame_no*TICK)
                if (snap["scene_document_sha256"]!=take["data"]["scene_document_sha256"] or
                        snap["timeline_document_sha256"]!=take["data"]["timeline_document_sha256"]):
                    raise PermissionError("Original scene or temporal source changed")
                paths={obj["path"]:obj for obj in snap["objects"]}
                if (not {"/World/Camera","/World/PracticalLight"}<=set(paths) or
                        not set(cast["actor_id_by_prim"])<=set(paths)):
                    raise PermissionError("Source camera, light or actor prim missing")
                if n and set(paths)!=set(frames[0]["world_matrices"]):
                    raise PermissionError("Original actor/asset set changed inside same Take")
                for obj in snap["objects"]:
                    if obj["semantic_role"] in ("actor","prop"):
                        asset=obj["asset"]
                        if not isinstance(asset,dict) or asset["asset_revision"]!=1:
                            raise PermissionError("No real source asset for selected actor scene")
                        if obj["path"] not in assets:
                            record,_=reg.open(pid,asset["asset_id"],1)
                            if record["kind"]!="asset" or record["data"].get("shape") not in (
                                    "mesh","cube","sphere"):
                                raise PermissionError("Unsupported original USD actor source geometry")
                            assets[obj["path"]]={
                                "asset_id":asset["asset_id"],
                                "source_document_sha256":record["document_sha256"],
                                "source_data":record["data"],
                            }
                    elif obj["semantic_role"] not in ("camera","light"):
                        raise PermissionError("Unexpected original scene semantic role")
                frames.append({
                    "frame_in_take":frame_no,
                    "source_snapshot_sha256":snap["snapshot_sha256"],
                    "source_take_sha256":take["document_sha256"],
                    "world_matrices":{
                        p:obj["world_matrix"] for p,obj in paths.items()
                    },
                })
        finally:
            original.close()
        if set(assets)!=set(frames[0]["world_matrices"])-{
                "/World/Camera","/World/PracticalLight"}:
            raise PermissionError("Missing original source geometry")
        source={
            "project_id":pid,"actor_id":actor_id,
            "actor_prim_path":prims[0],
            "voice_id":identity["current_voice_id"],
            "profile_revision":profile_revision,
            "profile_sha256":current["document_sha256"],
            "profile":profile,
            "source_take_id":take_id,
            "source_take_sha256":take["document_sha256"],
            "source_scene_sha256":take["data"]["scene_document_sha256"],
            "source_timeline_sha256":take["data"]["timeline_document_sha256"],
            "cast_actor_id_by_prim":cast["actor_id_by_prim"],
            "gait_preset":preset,"fps":FPS,
            "first_frame_in_take":first_frame_in_take,
            "assets":assets,"frames":frames,
            "original_take_remains_immutable":True,
            "director_animation_acceptance":False,
        }
        return {"format":PACKET_FORMAT,"source":source,
                "source_sha256":digest(source)}

    def run(self,pid,actor_id,*,take_id,profile_revision,job_id,
            creator_event,first_frame_in_take=0,frame_count=8):
        _id(job_id,"ActorID native animation job")
        if len(job_id)>48:
            raise ValueError("Native animation job exceeds FilmIndex candidate ID bounds")
        packet=self.plan(pid,actor_id,take_id=take_id,
                         profile_revision=profile_revision,
                         first_frame_in_take=first_frame_in_take,
                         frame_count=frame_count)
        src=packet["source"]
        code=Path(__file__).resolve().parents[1]/"tools"/"nvp_film03_actor_animation_worker.py"
        if code.is_symlink() or not code.is_file():
            raise PermissionError("Reviewed fixed Blender gait adapter is not installed")
        scope={
            "operation":"film03_run_source_locked_actor_animation",
            "project_id":pid,"actor_id":actor_id,
            "voice_id":src["voice_id"],
            "profile_sha256":src["profile_sha256"],
            "source_take_id":take_id,
            "source_take_sha256":src["source_take_sha256"],
            "source_packet_sha256":packet["source_sha256"],
            "gait_preset":src["gait_preset"],
            "script_sha256":sha_file(code),
            "blender_binary_sha256":self.worker.binary_sha256,
            "job_id":job_id,
        }
        if not self.approve(creator_event,scope):
            raise PermissionError("Trusted creator did not approve original ActorID gait worker")
        # Stage only after exact native approval; the supervisor independently
        # checks all inputs and script again both before/after Blender runs.
        job=self.worker.root/job_id
        if job.exists() or job.is_symlink():
            raise RuntimeError("ActorID motion job already staged; never overwrite")
        job.mkdir(mode=0o700)
        for name,content in (
            ("trusted_gait.py",code.read_bytes()),
            ("source.json",canonical(packet)),
        ):
            target=job/name
            with target.open("xb") as out:
                out.write(content)
        op=BlenderOperation(
            job_id=job_id,script="trusted_gait.py",
            script_sha256=sha_file(job/"trusted_gait.py"),
            inputs={"source.json":sha_file(job/"source.json")},
            outputs={"scene.blend":"blend","preview.png":"png",
                     "audit.json":"json_audit"},
            arguments={"--manifest":"source.json","--output":"scene.blend",
                       "--audit":"audit.json","--preview":"preview.png"},
            timeout_seconds=600,memory_limit_mb=4096,
            gpu_memory_mb=0,require_linux_cgroup_v2=False,
        )
        # This is THE existing native Blender worker, not a new renderer.
        # Its journal, native containment, resource admission, cancellation,
        # output auditing and recovery gates apply.
        result=self.worker.run(op)
        if result["state"]!="SUCCEEDED":
            return {"state":result["state"],"worker_result":result,
                    "published_as_approved_take":False}
        self.worker.verify_completed(job_id)
        native=json.loads((job/"audit.json").read_text("utf8"))
        trace=native.get("generated_keyframes",[])
        if (native.get("format")!=AUDIT_FORMAT or native.get("passed") is not True
                or native.get("actor_id")!=actor_id or
                native.get("actor_prim_path")!=src["actor_prim_path"] or
                native.get("source_take_sha256")!=src["source_take_sha256"] or
                native.get("profile_sha256")!=src["profile_sha256"] or
                native.get("source_packet_sha256")!=packet["source_sha256"] or
                native.get("gait_preset")!=src["gait_preset"] or
                native.get("frame_count")!=frame_count or
                len(trace)!=frame_count or
                native.get("all_other_actors_source_transforms_unchanged") is not True or
                native.get("original_frozen_take_modified") is not False or
                native.get("source_human_director_review_pending") is not True or
                native.get("blend_sha256")!=sha_file(job/"scene.blend") or
                native.get("preview_png_sha256")!=sha_file(job/"preview.png")):
            raise PermissionError("Native Blender ActorID/source/gait audit invalid")
        for i,(row,origin) in enumerate(zip(trace,src["frames"])):
            dz,angle=gait(src["gait_preset"],i)
            if (row.get("frame_in_take")!=origin["frame_in_take"] or
                    row.get("source_snapshot_sha256")!=
                    origin["source_snapshot_sha256"] or
                    row.get("gait_lift_m")!=round(dz,8) or
                    row.get("gait_tilt_radians")!=round(angle,8) or
                    row.get("other_actors_motion_source_unchanged") is not True):
                raise PermissionError("Real Blender gait frame/ActorID deviated from approved Take")
        # Source may have changed during 3D execution. Reopening original
        # 8 source frames assures exact FilmIndex/ActorID provenance.
        if self.plan(pid,actor_id,take_id=take_id,
                     profile_revision=profile_revision,
                     first_frame_in_take=first_frame_in_take,
                     frame_count=frame_count)!=packet:
            raise PermissionError("Actor identity, original scene or mesh changed mid-render")
        # FilmIndex stores a durable, content-addressed copy of the real
        # Blender output; never point to a mutable temp output as a film Take.
        media=self.index.put_media_file(pid,job/"scene.blend",
            media_type="application/octet-stream",max_bytes=64*1024*1024)
        png=self.index.put_blob(pid,(job/"preview.png").read_bytes(),
                                media_type="image/png")
        if media["sha256"]!=native["blend_sha256"] or png!=native["preview_png_sha256"]:
            raise RuntimeError("Indexed ActorID motion media differs from supervised output")
        candidate_id="ActorMotionCandidate_"+job_id
        candidate={
            "format":CANDIDATE_FORMAT,"actor_id":actor_id,
            "voice_id":src["voice_id"],"source_take_id":take_id,
            "source_take_sha256":src["source_take_sha256"],
            "source_profile_sha256":src["profile_sha256"],
            "original_source_packet_sha256":packet["source_sha256"],
            "reviewed_blender_binary_sha256":self.worker.binary_sha256,
            "reviewed_blender_script_sha256":op.script_sha256,
            "gait_preset":src["gait_preset"],
            "frame_count":frame_count,
            "blender_media_sha256":media["sha256"],
            "preview_png_blob_sha256":png,
            "native_audit_sha256":sha_file(job/"audit.json"),
            "source_authoritative_no_old_take_rewritten":True,
            "animation_rendered_by_real_blender":True,
            "candidate_director_approved":False,
            "source_film_editorial_updated":False,
        }
        def guard(db):
            row=db.execute(
                """SELECT document_sha256 FROM nvp_bible_actor_identity_profiles
                   WHERE project_id=? AND actor_id=?
                   ORDER BY profile_revision DESC LIMIT 1""",
                (pid,actor_id)).fetchone()
            if not row or row[0]!=src["profile_sha256"]:
                raise RuntimeError("ActorID changed during durable animation candidate commit")
        self.index.register_revision(pid,candidate_id,"asset",candidate,
                                     expected_revision=0,precommit_guard=guard)
        return {
            "format":AUDIT_FORMAT,"job_id":job_id,"actor_id":actor_id,
            "voice_id":src["voice_id"],"source_take_sha256":src["source_take_sha256"],
            "profile_sha256":src["profile_sha256"],
            "gait_preset":src["gait_preset"],
            "frame_count":frame_count,
            "native_blender_receipt":native,
            "candidate_id":candidate_id,
            "blender_media_sha256":media["sha256"],
            "preview_png_sha256":png,
            "actual_native_Blender_completed":True,
            "creator_film_approval":False,
            "original_take_unchanged":True,
        }

    def verify(self,pid,job_id):
        _id(job_id,"source actor motion job")
        status=self.worker.verify_completed(job_id)
        doc=self.index.read_revision(pid,"ActorMotionCandidate_"+job_id,1)
        if doc["kind"]!="asset" or doc["data"].get("format")!=CANDIDATE_FORMAT:
            raise PermissionError("No valid canonical ActorID motion candidate")
        data=doc["data"]
        if (self.index.verify_media_file(
                pid,data["blender_media_sha256"],
                media_type="application/octet-stream") is None or
                self.index.get_blob(pid,data["preview_png_blob_sha256"])[:8]!=
                b"\x89PNG\r\n\x1a\n" or
                sha_file(self.worker.root/job_id/"audit.json")!=
                   data["native_audit_sha256"]):
            raise RuntimeError("Original actor animated blend or preview failed restart audit")
        return {"status":"VERIFIED_UNAPPROVED","actor_id":data["actor_id"],
                "candidate_id":"ActorMotionCandidate_"+job_id,
                "original_take_sha256":data["source_take_sha256"],
                "worker":status,"production_approved":False}
