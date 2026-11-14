"""USD-FILM-01F: render ORIGINAL world-composed Digital Takes via existing Blender.

First film-world-to-pixels handoff. It reopens two independent immutable 01E
world Takes and their source scenes, evaluates exact native Film Time, freezes
only a DERIVED one-frame USD working snapshot, and dispatches reviewed
Blender scripts through existing journaled, contained BlenderWorkerSupervisor.

This first pass supports verified untextured USD geometry/camera/light with
original authored geometry. Unresolved external textures, lack of actual
actor mesh, unverified camera, mismatched Take, or failed independent Blender
reopen fail CLOSED. A single-frame source snapshot is not a moving-actor
sequence, mastered audio or photoreal human film.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import shutil

from backend.nvp_blender_worker import (
    BlenderOperation, BlenderWorkerSupervisor, sha_file)
from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_usd_film01e_world_take import (
    OpenUSDWorldTakeCapture, _canonical, FORMAT as TAKE_FORMAT)
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film01d_shot_working_set import _camera_native

PACKET_FORMAT = "nvp.usd_film01f.original_world_cycles_packet.v1"
AUDIT_FORMAT = "nvp.usd_film01f.native_cycles_original_world_frame.v1"
SCRIPT = "nvp_usd_film01f_blender_worker.py"
REOPEN_SCRIPT = "nvp_usd_film01f_blender_reopen.py"
MAX_RENDER_STAGE = 64 * 1024 * 1024
FRAME = "frame.png"
BLEND = "scene.blend"
AUDIT = "audit.json"
USD = "source.usda"
MANIFEST = "source.json"


def _snapshot_usd(index: FilmIndex, pid: str, take_id: str, tick: int,
                  job: Path):
    from pxr import Sdf, Usd, UsdGeom
    capture = OpenUSDWorldTakeCapture(
        index, verify_creator_action=lambda *_: False)
    proof = capture.verify_take(pid, take_id)
    if proof["status"] != "VERIFIED_ORIGINAL_WORLD_SOURCE_DATA_TAKE":
        raise PermissionError("Original world Take failed independent verification")
    original = index.read_revision(pid, take_id, 1)
    data = original["data"]
    if data["format"] != TAKE_FORMAT or tick not in data["checkpoint_ticks"]:
        raise PermissionError("No selected original source camera checkpoint")
    expected = capture.sample(pid, take_id, tick=tick)
    shot = index.read_revision(
        pid, data["camera_shot_id"], data["camera_shot_revision"])["data"]
    with OpenUSDWorldComposer(index).open(
            pid, data["world_id"], data["world_revision"]) as world:
        world.load(shot["director_required_sets"])
        # Director look changes are non-authoritative session opinions.
        with Usd.EditContext(world.stage,world.stage.GetSessionLayer()):
            for name, choice in shot["director_looks"].items():
                world.switch_variant(name, choice)
        camera_path, camera_pos = _camera_native(
            world, shot["camera_set"], shot["camera_prim_path"], [tick])
        if (camera_path != expected["original_camera_path"] or
            any(abs(a-b)>1e-6 for a,b in zip(
                camera_pos[0],expected["original_camera_position_m"]))):
            raise PermissionError("Source-authoritative native film camera changed")
        world_actors = []
        for member in data["canonical_original_actors"]:
            if member["set"] not in shot["director_required_sets"]:
                continue
            original_path=member["composed_actor_prim"]
            prim=world.stage.GetPrimAtPath(original_path)
            if not prim or not prim.IsDefined():
                raise RuntimeError("Original world actor prim is not in render stage")
            # Mesh and authored geometric primitives must be real descendants
            # of the ActorID's source prim, never rendered placeholders.
            rendered=[]
            for found in Usd.PrimRange(prim):
                if (found.IsA(UsdGeom.Mesh) or found.IsA(UsdGeom.Cube) or
                    found.IsA(UsdGeom.Sphere) or found.IsA(UsdGeom.Cylinder) or
                    found.IsA(UsdGeom.Cone)):
                    rendered.append(str(found.GetPath()))
            if not rendered:
                raise RuntimeError(
                    "An original ActorID has no authored renderable USD geometry")
            world_actors.append({
                "actor_id":member["actor_id"],
                "source_prim":original_path,
                "geometry_prims":rendered,
                "historical_voice_id":member["voice_id"],
            })
        if not world_actors:
            raise RuntimeError("Original film frame has no verifiable geometric actor")
        # Flatten ALL ACTUALLY LOADED original source USD layers in memory.
        # No asset folder, mesh topology, actor identity or story is authored
        # by this exporter. The derived stage is used only for this render.
        flat=world.stage.Flatten(addSourceFileComment=False)
        frozen=Usd.Stage.Open(flat)
        source=Usd.TimeCode(float(tick))
        for prim in frozen.TraverseAll():
            for attr in prim.GetAttributes():
                if attr.GetTypeName()==Sdf.ValueTypeNames.Asset:
                    original_asset=attr.Get()
                    if original_asset is not None and original_asset.path:
                        # MaterialX image resolution for arbitrarily staged
                        # renderer profiles requires an audited file bundle.
                        # Never silently drop an image or contact the network.
                        raise PermissionError(
                            "01F initial Blender handoff refuses unstaged external texture")
                keys=attr.GetTimeSamples()
                if not keys:
                    continue
                observed=attr.Get(source)
                if observed is None:
                    raise RuntimeError("Original animated USD value missing at checkpoint")
                for key in keys:
                    if not attr.ClearAtTime(Usd.TimeCode(key)):
                        raise RuntimeError("Cannot isolate original film-time USD sample")
                if not attr.Set(observed):
                    raise RuntimeError("Cannot freeze evaluated original USD attribute")
        frozen.SetStartTimeCode(1.)
        frozen.SetEndTimeCode(1.)
        frozen.SetTimeCodesPerSecond(24.)
        frozen.SetFramesPerSecond(24.)
        stagefile=job/USD
        if not frozen.Export(str(stagefile)):
            raise RuntimeError("Native frozen original USD export failed")
        size=stagefile.stat().st_size
        if not 100<size<=MAX_RENDER_STAGE:
            raise RuntimeError("Original shot render stage is outside checked size")
        reopened=Usd.Stage.Open(str(stagefile),load=Usd.Stage.LoadAll)
        if not reopened or not reopened.GetPrimAtPath(camera_path).IsA(UsdGeom.Camera):
            raise RuntimeError("Independent native USD snapshot lacks original camera")
        for actor in world_actors:
            for p in actor["geometry_prims"]:
                if not reopened.GetPrimAtPath(p).IsDefined():
                    raise RuntimeError("Native flattened USD actor source vanished")
        return {
            "project_id":pid,
            "original_world_take_id":take_id,
            "original_world_take_sha256":original["document_sha256"],
            "original_world_sha256":data["world_document_sha256"],
            "original_camera_shot_sha256":data["camera_shot_document_sha256"],
            "original_camera_path":camera_path,
            "original_camera_position_m":camera_pos[0],
            "original_film_tick":tick,
            "actor_sources":world_actors,
            "original_pcm_source_count":len(data["original_timeline_audio_sources"]),
            "original_selected_dialogue_count":len(data["original_selected_dialogue"]),
            "original_sound_not_mixed":True,
            "source_usd_file":USD,
            "source_usd_sha256":sha_file(stagefile),
            "native_source_usd_size_bytes":size,
            "source_world_take_checkpoint_sha256":data["checkpoint_digest_sha256"],
            "blender_profile":"cycles_cpu_320x180_12samples_v1",
            "not_a_final_approved_film":True,
        }


class ReviewedWorldTakeCyclesHost:
    def __init__(self, index:FilmIndex, supervisor:BlenderWorkerSupervisor,
                 *, verify_director_action):
        if (not isinstance(index,FilmIndex) or
            not isinstance(supervisor,BlenderWorkerSupervisor) or
            not callable(verify_director_action)):
            raise TypeError("Use verified NVP FilmIndex and the existing Blender supervisor")
        self.index=index
        self.supervisor=supervisor
        self.authorize=verify_director_action

    def stage(self, pid, take_id, *, tick, job_id):
        _id(take_id,"original world Take")
        _id(job_id,"original film Blender job")
        if type(tick) is not int or tick<0 or len(job_id)>64:
            raise ValueError("Source tick or approved job identity invalid")
        job=self.supervisor.root/job_id
        if job.exists() or job.is_symlink():
            raise FileExistsError("World Take render job already exists")
        job.mkdir(mode=0o700)
        try:
            original=_snapshot_usd(self.index,pid,take_id,tick,job)
            packet={
                "format":PACKET_FORMAT, "source":original,
                "source_sha256":sha256(_canonical(original)).hexdigest()}
            (job/MANIFEST).write_bytes(_canonical(packet))
            script=Path(__file__).resolve().parents[1]/"tools"/SCRIPT
            if script.is_symlink() or not script.is_file():
                raise RuntimeError("Reviewed original world Blender worker unavailable")
            (job/SCRIPT).write_bytes(script.read_bytes())
            op=BlenderOperation(
                job_id=job_id, script=SCRIPT,
                script_sha256=sha_file(job/SCRIPT),
                inputs={USD:sha_file(job/USD),
                        MANIFEST:sha_file(job/MANIFEST)},
                outputs={BLEND:"blend",FRAME:"png",AUDIT:"json_audit"},
                arguments={"--manifest":MANIFEST,
                           "--output":BLEND,
                           "--preview":FRAME,
                           "--audit":AUDIT},
                memory_limit_mb=8192,timeout_seconds=600,
                gpu_memory_mb=0,require_linux_cgroup_v2=True,require_private_isolation=True)
            self.supervisor._validate(op)
            return {"packet":packet,"operation":op,"job_dir":job}
        except Exception:
            # Failed predispatch artifacts aren't approved source. Delete
            # only the newly created job folder.
            shutil.rmtree(job)
            raise

    def render_pair(self,pid,requests,*,director_event):
        if (type(requests) is not list or len(requests)!=2 or
            any(type(x) is not dict or set(x)!={"take_id","tick","job_id"}
                for x in requests) or
            requests[0]["take_id"]==requests[1]["take_id"] or
            requests[0]["job_id"]==requests[1]["job_id"]):
            raise ValueError("Two distinct original world Takes and jobs required")
        prepared=[]
        for q in requests:
            prepared.append(self.stage(pid,q["take_id"],
                 tick=q["tick"],job_id=q["job_id"]))
        first,second=(x["packet"]["source"] for x in prepared)
        if (first["original_world_sha256"]!=second["original_world_sha256"] or
            first["original_camera_shot_sha256"]==
                second["original_camera_shot_sha256"]):
            raise PermissionError("Two distinct original shots must share one frozen world")
        scope={
            "operation":"nvp.render.usd_film01f_world_take_pair.v1",
            "project_id":pid,
            "world_sha256":first["original_world_sha256"],
            "take_shas":[first["original_world_take_sha256"],
                         second["original_world_take_sha256"]],
            "camera_shot_shas":[first["original_camera_shot_sha256"],
                                second["original_camera_shot_sha256"]],
            "source_usd_shas":[first["source_usd_sha256"],
                               second["source_usd_sha256"]],
            "source_ticks":[first["original_film_tick"],second["original_film_tick"]],
        }
        if self.authorize(director_event,scope) is not True:
            raise PermissionError("Director did not approve exact original two-shot render")
        completed=[]
        for staged in prepared:
            src=staged["packet"]["source"]
            current=self.index.read_revision(pid,src["original_world_take_id"],1)
            if current["document_sha256"]!=src["original_world_take_sha256"]:
                raise PermissionError("Original Take changed during render handoff")
            state=self.supervisor.run(staged["operation"])
            if state["state"]!="SUCCEEDED":
                raise RuntimeError("Original Blender shot failed: "+str(state["state"]))
            self.supervisor.verify_completed(staged["operation"].job_id)
            job=staged["job_dir"]
            audit=json.loads((job/AUDIT).read_text("utf8"))
            if (audit.get("format")!=AUDIT_FORMAT or
                audit.get("passed") is not True or
                audit.get("original_world_take_sha256")!=
                    src["original_world_take_sha256"] or
                audit.get("source_usd_sha256")!=src["source_usd_sha256"] or
                audit.get("source_packet_sha256")!=
                    staged["packet"]["source_sha256"] or
                audit.get("rendered_png_sha256")!=sha_file(job/FRAME) or
                audit.get("saved_blend_sha256")!=sha_file(job/BLEND) or
                audit.get("actual_native_cycles_image") is not True):
                raise RuntimeError("Native Blender picture does not match frozen world Take")
            # Independent second Blender process must reopen saved .blend,
            # validate source world/Take/ActorID/camera tags and geometry,
            # and produce a separate journaled proof. No Blender process
            # result is accepted merely from the first worker's JSON.
            secondary_id=staged["operation"].job_id+"_reopen"
            if len(secondary_id)>80:
                raise ValueError("Native Blender reopen ID exceeds bounded journal")
            folder=self.supervisor.root/secondary_id
            if folder.exists() or folder.is_symlink():
                raise RuntimeError("Independent Blender reopen job already exists")
            folder.mkdir(mode=0o700)
            shutil.copyfile(job/BLEND,folder/BLEND)
            reopen_source={
                "source":src,"source_blend_sha256":sha_file(folder/BLEND)}
            (folder/MANIFEST).write_bytes(_canonical(reopen_source))
            script=Path(__file__).resolve().parents[1]/"tools"/REOPEN_SCRIPT
            if script.is_symlink() or not script.is_file():
                raise RuntimeError("Reviewed independent Blender reopener unavailable")
            (folder/REOPEN_SCRIPT).write_bytes(script.read_bytes())
            check_op=BlenderOperation(
                job_id=secondary_id,scene=BLEND,
                script=REOPEN_SCRIPT,
                script_sha256=sha_file(folder/REOPEN_SCRIPT),
                inputs={BLEND:sha_file(folder/BLEND),
                        MANIFEST:sha_file(folder/MANIFEST)},
                outputs={AUDIT:"json_audit"},
                arguments={"--manifest":MANIFEST,"--audit":AUDIT},
                memory_limit_mb=8192,timeout_seconds=600,
                require_linux_cgroup_v2=True,require_private_isolation=True)
            outcome=self.supervisor.run(check_op)
            if outcome["state"]!="SUCCEEDED":
                raise RuntimeError("Independent original Blender reopen failed")
            self.supervisor.verify_completed(secondary_id)
            proof=json.loads((folder/AUDIT).read_text("utf8"))
            if (proof.get("passed") is not True or
                proof.get("format")!=
                  "nvp.usd_film01f.independent_cycles_scene_reopen.v1" or
                proof.get("source_blend_sha256")!=sha_file(job/BLEND) or
                proof.get("original_take_sha256")!=
                  src["original_world_take_sha256"] or
                proof.get("source_usd_sha256")!=src["source_usd_sha256"] or
                proof.get("actor_count")!=len(src["actor_sources"]) or
                proof.get("real_saved_usd_actor_objects_reopened") is not True):
                raise RuntimeError("Independent Blender .blend evidence differs from world Take")
            from backend.nvp_usd_film01f_original_audio import (
                render_original_source_stems)
            original_sound=render_original_source_stems(
                self.index,pid,src["original_world_take_id"],
                job/"original_audio")
            if (not original_sound["actual_original_pcm_readback_verified"] or
                original_sound["world_take_sha256"] !=
                    src["original_world_take_sha256"] or
                original_sound["final_picture_sound_mux_verified"] is not False):
                raise RuntimeError("Audio source stems cannot be bound to rendered original Take")
            completed.append({
                "job_dir":job,"source":src,"audit":audit,
                "independent_reopen_audit":proof,"independent_reopen_dir":folder,
                "original_audio_source_receipt":original_sound})
        return {
            "state":"RENDERED_TWO_UNAPPROVED_WORLD_SHOT_FRAMES",
            "world_sha256":first["original_world_sha256"],
            "shots":completed,
            "original_source_takes_unchanged":all(
                self.index.read_revision(
                    pid,s["source"]["original_world_take_id"],1)[
                        "document_sha256"]==s["source"]["original_world_take_sha256"]
                for s in completed),
            "independent_blender_reopen_verified":True,
            "original_source_audio_events_not_mixed":True,
            "final_audio_mix_verified":False,
            "human_photorealism_accepted":False,
            "finished_film_approved":False,
        }
