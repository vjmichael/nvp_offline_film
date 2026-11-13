"""USD-02C: typed time-sampled performance and scene-property channels.

These are native USD double attributes on authored prims, NOT a complete
UsdSkel rig, deforming geometry, light shader or optical camera yet.
The same immutable scene can be sampled at arbitrary film times without
creating or baking any 2D frames.
"""
from __future__ import annotations

import math
import re

from backend.nvp_temporal_ledger import _int, TICKS_PER_SECOND
from backend.nvp_openusd_scene import MAX_USD_EXACT_TICK, _usd

MAX_CHANNELS = 128
MAX_SAMPLES = 2048
TOKEN = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")
FIXED = {
    "camera.focal_length_mm": ("camera", 1.0, 300.0),
    "camera.focus_distance_m": ("camera", 0.01, 100000.0),
    "light.intensity": ("light", 0.0, 1000000.0),
    "light.temperature_kelvin": ("light", 1000.0, 40000.0),
}


def _channel(property_name, role):
    if not isinstance(property_name, str):
        raise ValueError("Invalid typed performance property")
    if property_name in FIXED:
        expected, low, high = FIXED[property_name]
        if role != expected:
            raise ValueError("Performance property not permitted on this scene role")
    elif property_name.startswith("face."):
        expected, low, high = "actor", 0.0, 1.0
        if role != expected or not TOKEN.fullmatch(property_name[5:]):
            raise ValueError("Invalid facial parameter")
    elif property_name.startswith("joint."):
        expected, low, high = "actor", -180.0, 180.0
        if role != expected or not TOKEN.fullmatch(property_name[6:]):
            raise ValueError("Invalid joint angle parameter")
    else:
        raise ValueError("Unsupported typed performance channel")
    return ("nvp:performance:" + property_name.replace(".", ":"), low, high)


def author_parameter_layer(prim_roles, channels, *, native_schemas=False):
    """Create a separate stronger USD opinions layer with typed scalar keys."""
    if (type(channels) is not list or len(channels) > MAX_CHANNELS):
        raise ValueError("Performance channel count exceeds bounded authoring")
    _, Sdf, Usd, _ = _usd()
    layer = Sdf.Layer.CreateAnonymous("nvp_parameters.usda")
    stage = Usd.Stage.Open(layer)
    # Author the same integer-tick rate as the composed OpenUSD root.
    # Otherwise USD rescales this sublayer's default 24-fps samples.
    stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
    seen = set()
    descriptors = []
    for entry in channels:
        if type(entry) is not dict or set(entry) != {"path", "property", "samples"}:
            raise ValueError("Expected path, property and exact-time samples")
        path, name = entry["path"], entry["property"]
        if path not in prim_roles:
            raise ValueError("Performance channel references an undeclared prim")
        attr, low, high = _channel(name, prim_roles[path])
        identity = (path, name)
        if identity in seen:
            raise ValueError("Multiple animation tracks for one authored property")
        seen.add(identity)
        samples = entry["samples"]
        if (type(samples) is not list or not 2 <= len(samples) <= MAX_SAMPLES):
            raise ValueError("Performance track must have bounded time samples")
        prim = stage.OverridePrim(path)
        usd_attr = prim.CreateAttribute(attr, Sdf.ValueTypeNames.Double, custom=True)
        prior = -1
        for sample in samples:
            if type(sample) is not dict or set(sample) != {"tick", "value"}:
                raise ValueError("Malformed performance key")
            tick = _int(sample["tick"], "performance event time",
                        maximum=MAX_USD_EXACT_TICK)
            val = sample["value"]
            if (tick <= prior or type(val) not in (int, float) or
                not math.isfinite(val) or not low <= val <= high):
                raise ValueError("Invalid timing or scalar bound for performance key")
            if not usd_attr.Set(float(val), Usd.TimeCode(float(tick))):
                raise RuntimeError("Failed to author native USD time sample")
            if native_schemas and name in FIXED:
                from backend.nvp_openusd_native_schemas import author_schema_property
                if not author_schema_property(stage,path,name,val,tick):
                    raise RuntimeError("Missing real native schema property")
            prior = tick
        descriptors.append({"path": path, "property": name, "usd_attribute": attr})
    return layer, sorted(descriptors, key=lambda v:(v["path"],v["property"]))


def evaluate_parameter_channels(stage, descriptions, prim_roles, tick):
    """Read composed USD animation values, not interpolated homegrown data."""
    _int(tick, "film time", maximum=MAX_USD_EXACT_TICK)
    if type(descriptions) is not list or len(descriptions) > MAX_CHANNELS:
        raise ValueError("Invalid scene performance manifest")
    _, _, Usd, _ = _usd()
    result = []
    for desc in descriptions:
        if type(desc) is not dict or set(desc) != {
            "path", "property", "usd_attribute"
        }:
            raise RuntimeError("Invalid frozen scene property descriptor")
        path, name = desc["path"], desc["property"]
        role = prim_roles.get(path)
        if role is None:
            raise RuntimeError("Scene performance property target disappeared")
        attr_name, lo, hi = _channel(name, role)
        if attr_name != desc["usd_attribute"]:
            raise RuntimeError("Native attribute identity changed")
        prim = stage.GetPrimAtPath(path)
        attribute = prim.GetAttribute(attr_name) if prim else None
        if not attribute or not attribute.IsValid():
            raise RuntimeError("Native USD property missing from composed scene")
        value = attribute.Get(Usd.TimeCode(float(tick)))
        if (value is None or not math.isfinite(float(value)) or
            not lo <= float(value) <= hi):
            raise RuntimeError("Invalid evaluated native USD channel value")
        result.append({"path":path,"property":name,
                       "time_tick":tick,"value":float(value)})
    return result
