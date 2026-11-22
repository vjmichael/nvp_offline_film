"""USD-02D: actual UsdGeom.Camera and UsdLux.SphereLight schema controls.

NVP authored coordinates use meters. USD camera lens properties use tenths
of a scene unit, so 35 mm focal length is 0.35 when metersPerUnit=1.
These attributes coexist with the earlier typed NVP control properties.
"""
from __future__ import annotations

import math
from backend.nvp_openusd_scene import _usd
from backend.nvp_temporal_ledger import _int

SCHEMA = "nvp.usd.camera_sphere_light.v1"
METERS_PER_UNIT = 1.0
MM_PER_CAMERA_UNIT = METERS_PER_UNIT * 100.0


def _lux():
    try:
        from pxr import UsdLux
    except ImportError as exc:
        raise RuntimeError("Real OpenUSD UsdLux required") from exc
    return UsdLux


def define_native_scene_prim(stage, path, role):
    _, _, _, UsdGeom = _usd()
    if role == "camera":
        # Native scene units are METERS, whereas USD camera focal/aperture
        # values use tenths of a scene unit. Do not inherit USD's generic
        # scene-unit defaults of 50 and 20.955 (which would become 5000mm
        # focal and 2095.5mm sensor in an NVP meter-scale scene).
        camera=UsdGeom.Camera.Define(stage, path)
        if (not camera.GetFocalLengthAttr().Set(50.0/MM_PER_CAMERA_UNIT) or
            not camera.GetHorizontalApertureAttr().Set(36.0/MM_PER_CAMERA_UNIT) or
            not camera.GetVerticalApertureAttr().Set(20.25/MM_PER_CAMERA_UNIT) or
            not camera.GetFocusDistanceAttr().Set(5.0/METERS_PER_UNIT)):
            raise RuntimeError("Cannot author meter-aware NVP native camera defaults")
        return camera
    if role == "light":
        return _lux().SphereLight.Define(stage, path)
    return UsdGeom.Xform.Define(stage, path)


def _schema_attribute_for_over(stage, path, name):
    _, _, _, UsdGeom = _usd()
    prim = stage.OverridePrim(path)
    if name == "camera.focal_length_mm":
        return UsdGeom.Camera(prim).CreateFocalLengthAttr(), 1/MM_PER_CAMERA_UNIT
    if name == "camera.focus_distance_m":
        return UsdGeom.Camera(prim).CreateFocusDistanceAttr(), 1/METERS_PER_UNIT
    if name in ("light.intensity", "light.temperature_kelvin"):
        api = _lux().LightAPI(prim)
        if name == "light.intensity":
            return api.CreateIntensityAttr(), 1.0
        return api.CreateColorTemperatureAttr(), 1.0
    return None, None


def author_schema_property(stage, path, name, value, tick):
    """Author native schema time sample into a stronger over, not typed Xform."""
    _, _, Usd, _ = _usd()
    attr, factor = _schema_attribute_for_over(stage, path, name)
    if attr is None:
        return False
    if not attr.Set(float(value)*factor, Usd.TimeCode(float(tick))):
        raise RuntimeError("Failed native camera/light sample")
    if name == "light.temperature_kelvin":
        attr = _lux().LightAPI(stage.GetPrimAtPath(path)).CreateEnableColorTemperatureAttr()
        if not attr.Set(True):
            raise RuntimeError("Failed native light temperature enable")
    return True


def evaluate_native_schema(stage, path, role, tick, controls):
    """Read actual native camera/light schemas, checking parity with controls."""
    _, _, Usd, UsdGeom = _usd()
    _int(tick, "schema time", maximum=2**53-1)
    if role not in ("camera", "light"):
        return None
    prim = stage.GetPrimAtPath(path)
    if not prim or not prim.IsDefined():
        raise RuntimeError("Native schema prim missing")
    if role == "camera":
        if not prim.IsA(UsdGeom.Camera):
            raise RuntimeError("Native USD camera schema missing")
        cam = UsdGeom.Camera(prim)
        data = {
            "schema": "UsdGeom.Camera",
            "focal_length_mm": float(
                cam.GetFocalLengthAttr().Get(Usd.TimeCode(float(tick)))) *
                MM_PER_CAMERA_UNIT,
            "focus_distance_m": float(
                cam.GetFocusDistanceAttr().Get(Usd.TimeCode(float(tick)))) *
                METERS_PER_UNIT,
            "projection": str(cam.GetProjectionAttr().Get()),
        }
        names={"camera.focal_length_mm":"focal_length_mm",
               "camera.focus_distance_m":"focus_distance_m"}
    else:
        Lux=_lux()
        if not prim.IsA(Lux.SphereLight):
            raise RuntimeError("Native USD light schema missing")
        api=Lux.LightAPI(prim)
        data={"schema":"UsdLux.SphereLight",
              "intensity":float(api.GetIntensityAttr().Get(Usd.TimeCode(float(tick)))),
              "temperature_kelvin":float(
                  api.GetColorTemperatureAttr().Get(Usd.TimeCode(float(tick)))),
              "temperature_enabled":bool(api.GetEnableColorTemperatureAttr().Get())}
        names={"light.intensity":"intensity",
               "light.temperature_kelvin":"temperature_kelvin"}
    for control in controls:
        if control["path"]==path and control["property"] in names:
            actual=data[names[control["property"]]]
            if not math.isclose(actual,float(control["value"]),
                                rel_tol=2e-5,abs_tol=1e-4):
                raise RuntimeError("Native schema value differs from authored control")
    return {"prim_path":path,"time_tick":tick,**data}
