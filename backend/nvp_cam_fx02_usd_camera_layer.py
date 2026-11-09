"""CAM-FX-02: deterministic stronger *director-owned* OpenUSD camera layer.

Generate an actual USD stage with a camera rail at exact Film Time. Keep it
outside the original 01D shot/01E ActorID Take, original camera bank and
PCM. The rendered camera is virtual (no physical track/collider). This
native source layer is NOT itself a human-approved Cycles film frame.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import math
import re

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_openusd_native_schemas import MM_PER_CAMERA_UNIT,METERS_PER_UNIT
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_cam_fx01_camera_rails import evaluate_rail,OriginalCameraRails

RAIL_TOKEN=re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
FORMAT="nvp.cam_fx02.native_immutable_stronger_director_camera_layer.v1"
CAMERA_ROOT="/World/NVPDirectorRails"
FILM_FPS=24
MAX_CAMERA_SAMPLES=2305
MAX_LAYER_BYTES=12*1024*1024


def _unit(a):
    length=math.sqrt(sum(v*v for v in a))
    if length<1e-8 or not math.isfinite(length):
        raise ValueError("Camera orientation has no stable direction")
    return [x/length for x in a]


def _cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],
            a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0]]


def camera_matrix_rows(sample):
    """Film +Z-up, USD Camera looks down local -Z, local +Y is image up.

    Gf matrices use row-vector storage; basis axes occupy their rows and
    metres occupy the final row. Near vertical moves choose a stable
    backup up-vector rather than dividing by almost-zero cross products.
    """
    p=sample["position_m"]
    target=sample["target_m"]
    forward=_unit([target[i]-p[i] for i in range(3)])
    z=[-v for v in forward]
    up=[0.,0.,1.]
    if abs(sum(a*b for a,b in zip(z,up)))>.999:
        up=[0.,1.,0.]
    x=_unit(_cross(up,z))
    y=_unit(_cross(z,x))
    theta=math.radians(sample["roll_deg"])
    cs,sn=math.cos(theta),math.sin(theta)
    xr=[cs*x[i]+sn*y[i] for i in range(3)]
    yr=[-sn*x[i]+cs*y[i] for i in range(3)]
    return [
        [*xr,0.],[*yr,0.],[*z,0.],
        [float(v) for v in p]+[1.],
    ]


def camera_rail_path(rail_id):
    _id(rail_id,"original director rail")
    if not RAIL_TOKEN.fullmatch(rail_id):
        raise ValueError("Rail identity must also be a native OpenUSD prim token")
    return CAMERA_ROOT+"/"+rail_id


def film_time_samples(spec):
    """Render-ready 24fps keys plus all original director handles/midpoints."""
    begin,end=spec["film_start_tick"],spec["film_end_tick"]
    keys={begin,end}
    keys.update(node["tick"] for node in spec["nodes"])
    keys.update((a["tick"]+b["tick"])//2
                for a,b in zip(spec["nodes"],spec["nodes"][1:]))
    frames=(end-begin)*FILM_FPS//T+2
    for f in range(frames+1):
        tick=begin+f*T//FILM_FPS
        if begin<=tick<=end:
            keys.add(tick)
    result=sorted(keys)
    if len(result)>MAX_CAMERA_SAMPLES:
        raise MemoryError("Director layer sample count exceeds per-shot rail budget")
    return result


def _author(stage,rail_id,spec):
    from pxr import Gf,Usd,UsdGeom
    path=camera_rail_path(rail_id)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage,1.0)
    # Match NVP DATA-TIME-01: a USD timecode is one original Film Time
    # tick, NOT a 24fps frame or an arbitrary animation second.
    stage.SetTimeCodesPerSecond(float(T))
    stage.SetFramesPerSecond(float(FILM_FPS))
    stage.SetStartTimeCode(float(spec["film_start_tick"]))
    stage.SetEndTimeCode(float(spec["film_end_tick"]))
    if (abs(stage.GetTimeCodesPerSecond()-float(T))>.5 or
        stage.GetStartTimeCode()!=float(spec["film_start_tick"]) or
        stage.GetEndTimeCode()!=float(spec["film_end_tick"])):
        raise RuntimeError("Director camera layer lost original Film Time range/clock")
    # Authored stronger camera opinions must not change the ORIGINAL
    # /World prim's type. An over preserves the weaker original Xform.
    stage.OverridePrim("/World")
    UsdGeom.Scope.Define(stage,CAMERA_ROOT)
    cam=UsdGeom.Camera.Define(stage,path)
    transform=cam.AddTransformOp(
        precision=UsdGeom.XformOp.PrecisionDouble,
        opSuffix="NVPFilmTime")
    cam.GetHorizontalApertureAttr().Set(
        spec["filmback_mm"][0]/MM_PER_CAMERA_UNIT)
    cam.GetVerticalApertureAttr().Set(
        spec["filmback_mm"][1]/MM_PER_CAMERA_UNIT)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(.01,10000.))
    samples=film_time_samples(spec)
    for tick in samples:
        sample=evaluate_rail(spec,tick)
        matrix=Gf.Matrix4d(*[v for row in camera_matrix_rows(sample)
                            for v in row])
        when=Usd.TimeCode(float(tick))
        if (not transform.Set(matrix,when) or
            not cam.GetFocalLengthAttr().Set(
                sample["focal_length_mm"]/MM_PER_CAMERA_UNIT,when) or
            not cam.GetFocusDistanceAttr().Set(
                sample["focus_distance_m"]/METERS_PER_UNIT,when) or
            not cam.GetFStopAttr().Set(sample["f_stop"],when)):
            raise RuntimeError("Unable to author exact original Film Time camera values")
    return path,samples


def _check_native(stage,path,spec,ticks):
    from pxr import Usd,UsdGeom
    cam=UsdGeom.Camera.Get(stage,path)
    if not cam or not cam.GetPrim().IsDefined():
        raise RuntimeError("Native original camera path did not compose")
    xform=UsdGeom.Xformable(cam)
    verified=[]
    for tick in ticks:
        expected=evaluate_rail(spec,tick)
        time=Usd.TimeCode(float(tick))
        matrix=xform.GetLocalTransformation(time)
        actual=matrix.ExtractTranslation()
        if any(abs(float(actual[i])-expected["position_m"][i])>1e-5
               for i in range(3)):
            raise RuntimeError("Native camera no longer follows director rail")
        optics=[
            (cam.GetFocalLengthAttr().Get(time)*MM_PER_CAMERA_UNIT,
             expected["focal_length_mm"]),
            (cam.GetFocusDistanceAttr().Get(time)*METERS_PER_UNIT,
             expected["focus_distance_m"]),
            (cam.GetFStopAttr().Get(time),expected["f_stop"]),
        ]
        if any(abs(float(a)-float(b))>1e-4 for a,b in optics):
            raise RuntimeError("Original director optics changed in USD composition")
        # Orientation is independently read from the evaluated USD matrix.
        expected_rows=camera_matrix_rows(expected)
        if any(abs(float(matrix[i][j])-expected_rows[i][j])>1e-5
               for i in range(4) for j in range(4)):
            raise RuntimeError("Composed USD camera orientation or rail transform changed")
        verified.append(tick)
    return verified


def _read_strong_layer(byte_source):
    from pxr import Sdf
    if type(byte_source) is not bytes or not 60<len(byte_source)<=MAX_LAYER_BYTES:
        raise ValueError("Only bounded authored original USD rail layer")
    layer=Sdf.Layer.CreateAnonymous("nvp-camera-director-verified.usda")
    if not layer.ImportFromString(byte_source.decode("utf8")):
        raise RuntimeError("Source-authored OpenUSD director layer could not parse")
    return layer


def generate_camera_director_layer(rail_id,spec):
    """Author and independently read actual USD bytes; no source Take writes."""
    from pxr import Usd
    stage=Usd.Stage.CreateInMemory()
    path,ticks=_author(stage,rail_id,spec)
    _check_native(stage,path,spec,ticks)
    data=stage.GetRootLayer().ExportToString().encode("utf8")
    if len(data)>MAX_LAYER_BYTES:
        raise MemoryError("Strong director camera layer exceeds source budget")
    source=_read_strong_layer(data)
    reopened=Usd.Stage.Open(source,load=Usd.Stage.LoadAll)
    if not reopened:
        raise RuntimeError("Original director camera rail USD cannot reopen")
    if (abs(reopened.GetTimeCodesPerSecond()-float(T))>.5 or
        reopened.GetStartTimeCode()!=float(spec["film_start_tick"]) or
        reopened.GetEndTimeCode()!=float(spec["film_end_tick"])):
        raise RuntimeError("Independently reopened director layer lost original clock")
    if _check_native(reopened,path,spec,ticks)!=ticks:
        raise RuntimeError("Source-native director camera rail readback incomplete")
    return data


@contextmanager
def open_approved_camera_layer(index:FilmIndex,pid,rail_id,revision):
    """Temporary *stronger* layer on original loaded world, not root edits.

    Returns real first-party USD and original Film Time sample metadata.
    Only immutable approved FilmIndex revisions are allowed, never drafts.
    """
    from pxr import Usd,UsdGeom
    _require_pid(pid)
    approved=OriginalCameraRails(
        index,verify_director_action=lambda *_:False).verify(
            pid,rail_id,revision)
    spec=approved["rail_spec"]
    doc=index.read_revision(pid,approved["world_take_id"],1)["data"]
    layer_bytes=index.get_blob(pid,approved["rail_layer_sha256"])
    if sha256(layer_bytes).hexdigest()!=approved["rail_layer_sha256"]:
        raise RuntimeError("Director USD blob no longer matches source revision")
    layer=_read_strong_layer(layer_bytes)
    shot_set=doc["original_scene_takes"][0]["set"]
    with OpenUSDWorldComposer(index).open(
            pid,doc["world_id"],doc["world_revision"]) as world:
        world.load([shot_set])
        stage=world.stage
        if abs(stage.GetTimeCodesPerSecond()-float(T))>.5:
            raise RuntimeError("Original 01E world and director camera rail use different clocks")
        path=camera_rail_path(rail_id)
        if stage.GetPrimAtPath(CAMERA_ROOT).IsDefined():
            raise PermissionError("Original source world already owns the rail rig namespace")
        root_before=stage.GetRootLayer().ExportToString()
        at=[spec["film_start_tick"],
            (spec["film_start_tick"]+spec["film_end_tick"])//2,
            spec["film_end_tick"]]
        actors=[a["composed_actor_prim"]
                for a in doc["canonical_original_actors"]]
        from backend.nvp_usd_film01d_shot_working_set import FilmWorldShotPlanner
        original_shot=FilmWorldShotPlanner(index).inspect(
            pid,doc["camera_shot_id"],doc["camera_shot_revision"],
            expected_world_sha=doc["world_document_sha256"])
        if original_shot["document_sha256"]!=doc["camera_shot_document_sha256"]:
            raise RuntimeError("Authoritative 01D camera shot changed")
        raw_camera=original_shot["data"]["camera_prim_path"]
        if not raw_camera.startswith("/World/"):
            raise RuntimeError("Original 01D camera prim was invalid")
        source_camera_path="/World/Sets/"+shot_set+raw_camera[len("/World"):]
        original_camera=UsdGeom.Camera.Get(stage,source_camera_path)
        if not original_camera or not original_camera.GetPrim().IsDefined():
            raise RuntimeError("No original 01D source camera in current USD set")
        camera_before=[
            UsdGeom.Xformable(original_camera).ComputeLocalToWorldTransform(
                Usd.TimeCode(float(t))) for t in at]
        original_world_type=stage.GetPrimAtPath("/World").GetTypeName()
        original={}
        for actor_path in actors:
            prim=stage.GetPrimAtPath(actor_path)
            if not prim.IsDefined():
                raise RuntimeError("Original ActorID source disappeared")
            xform=UsdGeom.Xformable(prim)
            if not xform:
                raise RuntimeError("Original performance prim has no USD xform")
            original[actor_path]=[
                xform.ComputeLocalToWorldTransform(Usd.TimeCode(float(t)))
                for t in at]
        session=stage.GetSessionLayer()
        session.subLayerPaths.insert(0,layer.identifier)
        try:
            verified=_check_native(stage,path,spec,film_time_samples(spec))
            for actor_path,matrices in original.items():
                xform=UsdGeom.Xformable(stage.GetPrimAtPath(actor_path))
                if any(xform.ComputeLocalToWorldTransform(
                        Usd.TimeCode(float(t)))!=before
                       for t,before in zip(at,matrices)):
                    raise RuntimeError("Strong director camera changed original ActorID pose")
            source_camera_after=UsdGeom.Xformable(
                stage.GetPrimAtPath(source_camera_path))
            if (stage.GetPrimAtPath("/World").GetTypeName()!=original_world_type or
                any(source_camera_after.ComputeLocalToWorldTransform(
                    Usd.TimeCode(float(t)))!=before
                    for t,before in zip(at,camera_before))):
                raise RuntimeError("Stronger rail layer changed original 01D camera or world root")
            if stage.GetRootLayer().ExportToString()!=root_before:
                raise RuntimeError("Director rail contaminated original source world USD layer")
            yield {
                "format":FORMAT,"stage":stage,
                "camera_path":path,"rail_id":rail_id,
                "revision":revision,"rail_layer_sha256":approved[
                    "rail_layer_sha256"],
                "original_world_take_sha256":approved["world_take_sha256"],
                "original_source_camera_bank_sha256":approved[
                    "camera_bank_sha256"],
                "native_verified_time_samples":verified,
                "film_time_ticks_per_second":T,
                "original_actor_takes_pcm_unchanged":True,
                "original_01d_source_camera_unchanged":True,
                "source_world_root_layer_unchanged":True,
                "native_cycles_frames_rendered":0,
                "human_picture_approved":False}
        finally:
            # Release only our separate stronger opinion, never rewrite
            # or save original root, actor/camera bank or source Take.
            if layer.identifier in session.subLayerPaths:
                session.subLayerPaths.remove(layer.identifier)
            if stage.GetRootLayer().ExportToString()!=root_before:
                raise RuntimeError("Original root layer changed while camera rig was in session")
