"""CAM-FX-02: deterministic stronger *director-owned* OpenUSD camera layer.

Generate an actual USD stage with a camera rail at exact Film Time. Keep it
outside the original 01D shot/01E ActorID Take, original camera bank and
PCM. The rendered camera is virtual (no physical track/collider). This
native source layer is NOT itself a human-approved Cycles film frame.
"""
from __future__ import annotations

from hashlib import sha256
import math
import re

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
from backend.nvp_openusd_native_schemas import MM_PER_CAMERA_UNIT,METERS_PER_UNIT
from backend.nvp_plan02c_rails import evaluate_rail

RAIL_TOKEN=re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
FORMAT="nvp.cam_fx02.native_immutable_stronger_director_camera_layer.v1"
CAMERA_ROOT="/World/NVPDirectorRails"
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
    """Only exact original source-keyed Film Time samples, not 2D frame grid.

    Four bounded subdivisions per authored segment are a derivative
    interpolation readback check, NOT an authoritative 24fps film stream.
    """
    keys={spec["film_start_tick"],spec["film_end_tick"]}
    for left,right in zip(spec["nodes"],spec["nodes"][1:]):
        a=left["tick"];b=right["tick"]
        keys.update(a+(b-a)*i//4 for i in range(5))
    keys.update(n["tick"] for n in spec["nodes"])
    samples=sorted(keys)
    if len(samples)>MAX_CAMERA_SAMPLES:
        raise MemoryError("Original Film Time rail sampling exceeds limit")
    return samples


def _author(stage,rail_id,spec):
    from pxr import Gf,Usd,UsdGeom
    path=camera_rail_path(rail_id)
    UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage,1.0)
    # Match NVP DATA-TIME-01: a USD timecode is one original Film Time
    # tick, NOT a 24fps frame or an arbitrary animation second.
    stage.SetTimeCodesPerSecond(float(T))
    stage.SetFramesPerSecond(float(T))
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


def generate_source_rail_layer(rail_id,spec):
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


