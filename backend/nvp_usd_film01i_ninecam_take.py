"""USD-FILM-01I: one immutable actor performance, nine ORIGINAL native cameras.

A nine-camera *source rig* does not create nine Takes or generate a renderer
image. Each camera reads the same original 01E world Take, its ActorIDs,
original scene Take, original timeline audio and original Film Time. Camera
metadata is authored in the immutable native scene, not supplied by a worker.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film01e_world_take import (
    OpenUSDWorldTakeCapture, FORMAT as WORLD_TAKE_FORMAT)
from backend.nvp_usd_film01d_shot_working_set import FilmWorldShotPlanner
from backend.nvp_openusd_scene import MAX_USD_EXACT_TICK

FORMAT = "nvp.usd_film01i.source_one_performance_nine_camera_bank.v1"
FRAMES_PER_CAMERA = 720
FPS = 24
DURATION_TICKS = 30 * T
ANGLES = ("A", "B", "C")
FRAMINGS = ("wide", "medium", "close")
GRID = tuple((a, f) for a in ANGLES for f in FRAMINGS)
NATIVE_CAMERA_SAMPLE_TICKS = (0, 10 * T, 20 * T, 29 * T)


def _canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(doc):
    return sha256(_canonical(doc)).hexdigest()


def _performance_source(world_take):
    """Independent of camera: original world/scene/actors/PCM/voice decisions."""
    return {
        "world_document_sha256": world_take["world_document_sha256"],
        "scene_takes": world_take["original_scene_takes"],
        "actors": world_take["canonical_original_actors"],
        "original_pcm_events": world_take["original_timeline_audio_sources"],
        "original_dialogue_selections": world_take["original_selected_dialogue"],
        "original_scene_checkpoint_digest": [
            x["original_sample_digest_sha256"]
            for x in world_take["original_scene_takes"]],
    }


def _native_cameras(index, pid, world_take, entries):
    from pxr import Usd, UsdGeom
    from backend.nvp_openusd_native_schemas import MM_PER_CAMERA_UNIT
    with OpenUSDWorldComposer(index).open(
            pid, world_take["world_id"], world_take["world_revision"]) as world:
        set_name = world_take["original_scene_takes"][0]["set"]
        world.load([set_name])
        cameras = []
        for angle, framing, shot_record in entries:
            shot = shot_record["data"]
            if (shot["camera_set"] != set_name or
                shot["director_required_sets"] != [set_name] or
                shot["director_looks"] or
                shot["world_document_sha256"] !=
                    world_take["world_document_sha256"] or
                tuple(shot["camera_sample_ticks"]) != NATIVE_CAMERA_SAMPLE_TICKS):
                raise PermissionError(
                    "Nine camera plan must share the exact original unmodified world")
            path = shot["native_composed_camera_path"]
            prim = world.stage.GetPrimAtPath(path)
            camera = UsdGeom.Camera(prim)
            if not camera or not prim.IsDefined():
                raise RuntimeError("Native original camera source missing")
            focal = float(camera.GetFocalLengthAttr().Get()) * MM_PER_CAMERA_UNIT
            rotation_attr = prim.GetAttribute("xformOp:rotateXYZ")
            if not rotation_attr or not rotation_attr.HasAuthoredValue():
                raise PermissionError("Nine-camera film requires original authored direction")
            rot = [float(x) for x in rotation_attr.Get()]
            if len(rot) != 3 or not all(math.isfinite(x) for x in rot):
                raise PermissionError("Original native camera orientation invalid")
            positions = []
            for tick in NATIVE_CAMERA_SAMPLE_TICKS:
                matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
                    Usd.TimeCode(float(tick)))
                xyz = matrix.ExtractTranslation()
                pos = [float(xyz[i]) for i in range(3)]
                if not all(math.isfinite(x) for x in pos):
                    raise RuntimeError("Nonfinite native film camera position")
                positions.append(pos)
            if positions != shot["original_camera_positions_m"]:
                raise PermissionError("Camera coordinates changed from source-locked shot")
            cameras.append({
                "angle":angle, "framing":framing,
                "camera_shot_id":shot_record["object_id"],
                "camera_shot_revision":shot_record["revision"],
                "camera_shot_sha256":shot_record["document_sha256"],
                "camera_prim":shot["camera_prim_path"],
                "native_composed_camera_path":path,
                "source_camera_scene_sha256":shot["source_camera_scene_sha256"],
                "focal_length_mm":round(focal, 6),
                "rotation_euler_deg":rot,
                "source_world_positions_m":positions,
            })
    # Actual source lens families must read wide -> medium -> close. Native
    # view direction must differ between A/B/C; no label-only camera rigs.
    for i, angle in enumerate(ANGLES):
        group = cameras[i*3:i*3+3]
        focal = [x["focal_length_mm"] for x in group]
        if not (8 <= focal[0] < focal[1] < focal[2] <= 300):
            raise ValueError("Wide/medium/close lens must widen-to-tighten natively")
        direction = [x["rotation_euler_deg"] for x in group]
        if any(max(abs(a-b) for a,b in zip(direction[0],x))>0.01
               for x in direction[1:]):
            raise ValueError("A camera angle's three framings must share direction")
    directions = [cameras[i*3]["rotation_euler_deg"] for i in range(3)]
    if any(max(abs(a-b) for a,b in zip(directions[i],directions[j]))<5
           for i in range(3) for j in range(i+1,3)):
        raise ValueError("Three film angles need genuinely different native orientations")
    if len({c["native_composed_camera_path"] for c in cameras}) != 9:
        raise ValueError("Nine cameras must be nine different native USD prims")
    if len({tuple(c["source_world_positions_m"][0]) for c in cameras}) != 9:
        raise ValueError("Distinct camera positions required for actual coverage")
    return cameras


class OriginalNineCameraFilmSet:
    def __init__(self, index: FilmIndex, *, verify_creator_action):
        if not isinstance(index, FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Original FilmIndex and host-authenticated action required")
        self.index = index
        self._approve = verify_creator_action

    def _prepare(self, pid, world_take_id, camera_shots):
        _require_pid(pid)
        _id(world_take_id, "original frozen film performance")
        if (type(camera_shots) is not list or len(camera_shots) != 9 or
            any(type(x) is not dict or set(x) != {
                "angle", "framing", "shot_id", "shot_revision"
            } for x in camera_shots) or
            tuple((x["angle"], x["framing"]) for x in camera_shots) != GRID):
            raise ValueError("A/B/C x wide/medium/close nine-camera grid required")
        capture = OpenUSDWorldTakeCapture(
            self.index, verify_creator_action=lambda *_: False)
        source_proof = capture.verify_take(pid, world_take_id)
        record = self.index.read_revision(pid, world_take_id, 1)
        source = record["data"]
        if (source.get("format") != WORLD_TAKE_FORMAT or
            len(source["original_scene_takes"]) != 1 or
            len(source["canonical_original_actors"]) < 3):
            raise PermissionError("One original 30s performance with three actors required")
        original = source["original_scene_takes"][0]
        if original["duration_tick"] < DURATION_TICKS:
            raise PermissionError("Original actor source Take does not cover 30 seconds")
        if (tuple(source["checkpoint_ticks"]) != NATIVE_CAMERA_SAMPLE_TICKS or
            source_proof["world_document_sha256"] !=
                source["world_document_sha256"]):
            raise PermissionError("Frozen world Take camera checkpoints do not cover film")
        shot_planner = FilmWorldShotPlanner(self.index)
        bound = []
        seen_ids = set()
        for desc in camera_shots:
            shot_id = _id(desc["shot_id"], "original director camera shot")
            revision = desc["shot_revision"]
            if type(revision) is not int or revision < 1 or shot_id in seen_ids:
                raise ValueError("Duplicate/invalid original camera shot identity")
            seen_ids.add(shot_id)
            info = shot_planner.inspect(
                pid, shot_id, revision,
                expected_world_sha=source["world_document_sha256"])
            doc = info["data"]
            if (doc["source_camera_scene_id"] != original["scene_id"] or
                doc["source_camera_scene_revision"] != original["scene_revision"] or
                doc["source_camera_scene_sha256"] != original["scene_sha256"] or
                doc["camera_set"] != original["set"]):
                raise PermissionError("Camera must belong to SAME original performing scene")
            bound.append((desc["angle"], desc["framing"], info))
        cameras = _native_cameras(self.index, pid, source, bound)
        performance = _performance_source(source)
        return {
            "format":FORMAT,
            "world_take_id":world_take_id,
            "world_take_sha256":record["document_sha256"],
            "original_world_sha256":source["world_document_sha256"],
            "source_scene_take_sha256":original["take_sha256"],
            "source_performance_sha256":_digest(performance),
            "camera_count":9,
            "fps":FPS,
            "original_film_ticks_per_second":T,
            "performance_duration_ticks":DURATION_TICKS,
            "frames_per_camera":FRAMES_PER_CAMERA,
            "full_camera_coverage_frames":9 * FRAMES_PER_CAMERA,
            "cameras":cameras,
            "only_one_original_source_performance":True,
            "original_audio_not_triplicated":True,
            "native_render_frames_produced":False,
            "film_master_created":False,
        }

    def publish(self, pid, rig_id, *, world_take_id, camera_shots,
                creator_event):
        _id(rig_id, "nine-camera editorial bank")
        doc = self._prepare(pid,world_take_id,camera_shots)
        scope = {
            "operation":"nvp.capture.usd_film01i_nine_original_cameras.v1",
            "project_id":pid, "rig_id":rig_id,
            "world_take_sha256":doc["world_take_sha256"],
            "performance_sha256":doc["source_performance_sha256"],
            "original_world_sha256":doc["original_world_sha256"],
            "camera_shot_shas":[x["camera_shot_sha256"] for x in doc["cameras"]],
        }
        if self._approve(creator_event,scope) is not True:
            raise PermissionError("Director has not approved the exact nine-camera source rig")
        dependencies = [
            {"object_id":world_take_id,"revision":1,"role":"source_take"}
        ] + [
            {"object_id":x["camera_shot_id"],
             "revision":x["camera_shot_revision"],"role":"camera"}
            for x in doc["cameras"]
        ]
        # Freeze exactly one source performance and nine camera viewpoints;
        # do not generate nine independent actor Takes.
        return self.index.register_revision(
            pid, rig_id, "presentation",doc,
            expected_revision=0,dependencies=dependencies)

    def verify(self, pid, rig_id):
        _require_pid(pid)
        _id(rig_id,"nine-camera film source rig")
        stored = self.index.read_revision(pid,rig_id,1)
        data = stored["data"]
        if stored["kind"] != "presentation" or data.get("format") != FORMAT:
            raise PermissionError("Not an original nine-camera film source")
        shots = [
            {"angle":x["angle"],"framing":x["framing"],
             "shot_id":x["camera_shot_id"],
             "shot_revision":x["camera_shot_revision"]}
            for x in data["cameras"]
        ]
        rebuilt=self._prepare(pid,data["world_take_id"],shots)
        if rebuilt != data:
            raise RuntimeError("Nine-camera original source changed after freeze")
        return {"status":"VERIFIED_ORIGINAL_ONE_PERFORMANCE_NINE_CAMERAS",
                "rig_id":rig_id,"rig_sha256":stored["document_sha256"],
                "world_take_sha256":data["world_take_sha256"],
                "source_performance_sha256":data["source_performance_sha256"],
                "camera_count":9,"frames_per_camera":720,
                "native_render_frames_produced":False}


class OriginalFilmPerformanceSampler:
    """Evaluate one source actor state per tick; reuse across nine cameras."""
    def __init__(self,index:FilmIndex,pid,rig_id):
        self.index=index
        self.pid=pid
        self.rig_id=rig_id
        self.world=None

    def __enter__(self):
        self.proof=OriginalNineCameraFilmSet(
            self.index,verify_creator_action=lambda *_:False).verify(
                self.pid,self.rig_id)
        self.data=self.index.read_revision(self.pid,self.rig_id,1)["data"]
        take=self.index.read_revision(
            self.pid,self.data["world_take_id"],1)["data"]
        self.actors=take["canonical_original_actors"]
        self._context=OpenUSDWorldComposer(self.index).open(
            self.pid,take["world_id"],take["world_revision"])
        self.world=self._context.__enter__()
        self.world.load([take["original_scene_takes"][0]["set"]])
        return self

    def __exit__(self,*args):
        if self.world is not None:
            self._context.__exit__(*args)
            self.world=None

    def frame(self,index):
        from pxr import Usd, UsdGeom
        if self.world is None:
            raise RuntimeError("Native original world is not open")
        if type(index) is not int or not 0 <= index < FRAMES_PER_CAMERA:
            raise ValueError("Only 720 original performance frames permitted")
        tick=index*T//FPS
        if tick > MAX_USD_EXACT_TICK:
            raise RuntimeError("Native USD cannot exactly encode this film tick")
        time=Usd.TimeCode(float(tick))
        # Every view sees the same authored source state; one independent
        # sampling pass evaluates original cast actor transforms and all
        # native time-sampled descendant attributes, including authored rigs.
        state=[]
        actor_positions=[]
        for item in self.actors:
            prim=self.world.stage.GetPrimAtPath(item["composed_actor_prim"])
            if not prim or not prim.IsDefined():
                raise RuntimeError("Original ActorID prim disappeared from source world")
            attributes=[]
            for child in Usd.PrimRange(prim):
                for attr in child.GetAttributes():
                    if attr.GetNumTimeSamples() > 0:
                        value=attr.Get(time)
                        if value is None:
                            raise RuntimeError("Animated original actor attribute missing")
                        attributes.append([str(child.GetPath()),attr.GetName(),str(value)])
            matrix=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(time)
            transform=[[round(float(matrix[i][j]),9) for j in range(4)]
                       for i in range(4)]
            xyz=matrix.ExtractTranslation()
            actor_positions.append({"actor_id":item["actor_id"],
                "source_prim":item["composed_actor_prim"],
                "position_m":[round(float(xyz[i]),9) for i in range(3)]})
            state.append({"actor_id":item["actor_id"],
                "composed_actor_prim":item["composed_actor_prim"],
                "world_transform":transform,
                "authored_timed_attributes":sorted(attributes)})
        state_sha=_digest(state)
        cameras=[]
        for item in self.data["cameras"]:
            prim=self.world.stage.GetPrimAtPath(item["native_composed_camera_path"])
            matrix=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(time)
            xyz=matrix.ExtractTranslation()
            cameras.append({"angle":item["angle"],"framing":item["framing"],
                "camera_path":item["native_composed_camera_path"],
                "camera_shot_sha256":item["camera_shot_sha256"],
                "camera_position_m":[round(float(xyz[i]),9) for i in range(3)],
                "original_actor_state_sha256":state_sha,
                "original_performance_sha256":self.data["source_performance_sha256"],
                "original_world_sha256":self.data["original_world_sha256"],
                "original_film_tick":tick,
                "native_cycles_render_produced":False})
        return {"frame":index,"original_film_tick":tick,
                "source_actor_count":len(state),
                "source_actor_state_sha256":state_sha,
                "source_actor_world_positions_m":actor_positions,
                "nine_synchronized_original_camera_views":cameras,
                "original_source_evaluated_not_rendered":True}
