"""NVP V-LIGHT-FX: deterministic *virtual* cinematography lighting decisions.

A gold/silver "bounce" may be an invisible targeted fill, not a physical
reflector. A perpetual "summer 3 PM" sun is a locked cinematic direction,
not necessarily a geophysical ephemeris. These are *evaluated source data*,
NOT live native raster shading, GI, approved edit or DCI color evidence.

Independent light clocks may be used live; a record/capture event pins their
phase to Film Time so any final frame is reproducible offline. The caller is
responsible for immutable authoring and creator permission, not this module.
"""
from __future__ import annotations

import hashlib
import json
import math

from backend.nvp_temporal_ledger import TICKS_PER_SECOND

FORMAT="nvp.vlight_fx.digital_cinematic_lighting.v1"
SCHEMA_KEYS=frozenset((
    "format","fx_id","kind","target_path","clock_mode","anchor_film_tick",
    "anchor_monotonic_ns","frequency_hz","phase_cycles","duty_cycle",
    "intensity","color_rgb","direction_azimuth_deg",
    "direction_elevation_deg","decay_seconds","random_seed",
))
KINDS=frozenset(("silver_fill","gold_fill","locked_summer_3pm_sun",
                 "police_red_blue","firework_flash"))
CLOCK_MODES=frozenset(("film","captured_independent","independent_live"))
RGB={
    "silver_fill":(0.92,0.96,1.0),
    "gold_fill":(1.0,0.76,0.36),
    "locked_summer_3pm_sun":(1.0,0.88,0.72),
    "police_red_blue":(1.0,0.07,0.05),
    "firework_flash":(1.0,0.78,0.45),
}


def _finite(v,name,low,high):
    if type(v) not in (int,float) or not math.isfinite(v) or not low<=v<=high:
        raise ValueError(name+" must be finite and bounded")
    return float(v)


def _check_fx(fx):
    if type(fx) is not dict or set(fx)!=SCHEMA_KEYS:
        raise ValueError("Virtual light FX requires exact typed authoring fields")
    if fx["format"]!=FORMAT or fx["kind"] not in KINDS or (
            fx["clock_mode"] not in CLOCK_MODES):
        raise ValueError("Unknown virtual light/clock schema")
    for key in ("fx_id","target_path"):
        if (type(fx[key]) is not str or not 1<=len(fx[key])<=128 or
                any(ord(c)<33 or ord(c)>126 for c in fx[key])):
            raise ValueError("Invalid virtual light identity or target")
    if not fx["target_path"].startswith("/World/"):
        raise ValueError("Light target must be a real scene prim path")
    for key in ("anchor_film_tick","random_seed"):
        if type(fx[key]) is not int or fx[key]<0 or fx[key]>2**53-1:
            raise ValueError("Invalid deterministic FX timestamp or seed")
    monotonic=fx["anchor_monotonic_ns"]
    if fx["clock_mode"]=="film":
        if monotonic is not None:
            raise ValueError("Film-time light must not depend on live system clock")
    elif fx["clock_mode"]=="captured_independent":
        if type(monotonic) is not int or monotonic<0:
            raise ValueError("Captured free-running light needs original monotonic time")
    elif monotonic is not None and (type(monotonic) is not int or monotonic<0):
        raise ValueError("Invalid live oscillator anchor")
    for name,lo,hi in (
        ("frequency_hz",0,60),("phase_cycles",-100000,100000),
        ("duty_cycle",0.01,0.99),("intensity",0,100000),
        ("direction_azimuth_deg",-360,360),
        ("direction_elevation_deg",-90,90),
        ("decay_seconds",0.01,3600),
    ):
        _finite(fx[name],name,lo,hi)
    rgb=fx["color_rgb"]
    if type(rgb) is not list or len(rgb)!=3:
        raise ValueError("Virtual FX RGB needs exactly three channels")
    for v in rgb:
        _finite(v,"RGB",0,16)
    if fx["kind"]=="police_red_blue" and fx["frequency_hz"]<=0:
        raise ValueError("Cyclic police light FX needs positive frequency")


def evaluate_virtual_light_fx(fx,film_tick,*,monotonic_ns=None,final_render=False):
    """Evaluate exact authored light intent without editing any source.

    Result is an artist's targetable *light suggestion* for a future
    renderer adapter, not proof a surface was illuminated. After capture,
    a recorded independent effect uses Film Time exclusively.
    """
    _check_fx(fx)
    if type(film_tick) is not int or not 0<=film_tick<=2**53-1:
        raise ValueError("Exact integer Film Time required")
    if type(final_render) is not bool:
        raise TypeError("Explicit final/preview evaluation required")
    if final_render and fx["clock_mode"]=="independent_live":
        raise PermissionError("An uncaptured wall-clock effect cannot alter a final film")
    if fx["clock_mode"]=="independent_live":
        if type(monotonic_ns) is not int or monotonic_ns<0:
            raise ValueError("Live independent light needs explicit monotonic timestamp")
        anchor=fx["anchor_monotonic_ns"]
        if anchor is None:
            raise PermissionError("Live oscillator must record an anchor first")
        seconds=(monotonic_ns-anchor)/1e9
    else:
        # Even captured-independent effects are evaluated from the saved
        # synchronized Film Time anchor, never a nondeterministic clock.
        seconds=(film_tick-fx["anchor_film_tick"])/TICKS_PER_SECOND
    phase=seconds*fx["frequency_hz"]+fx["phase_cycles"]
    fraction=phase-math.floor(phase)
    intensity=float(fx["intensity"])
    rgb=list(fx["color_rgb"])
    if fx["kind"]=="police_red_blue":
        red=fraction<fx["duty_cycle"]
        rgb=[1.0,0.06,0.025] if red else [0.025,0.10,1.0]
        intensity*=1.0 if red else 0.85
    elif fx["kind"]=="firework_flash":
        # The light is a timed envelope; particles and actual fireworks
        # scene geometry are independent, still-unimplemented systems.
        if seconds<0:
            intensity=0.0
        else:
            jitter_seed=f"{fx['random_seed']}:{math.floor(phase)}".encode("ascii")
            rng=int.from_bytes(hashlib.sha256(jitter_seed).digest()[:4],"big")/2**32
            intensity*=math.exp(-seconds/fx["decay_seconds"])*(0.85+0.15*rng)
    # silver/gold fills and locked sun are constant until intentionally
    # animated by a separate authored keyframe/FX track.
    proof={
        "format":FORMAT,"fx_id":fx["fx_id"],"kind":fx["kind"],
        "clock_mode":fx["clock_mode"],"target_path":fx["target_path"],
        "film_tick":str(film_tick),"phase_cycles":round(phase,9),
        "evaluated_intensity":round(intensity,9),
        "evaluated_color_rgb":[round(x,9) for x in rgb],
        "sun_azimuth_deg":fx["direction_azimuth_deg"] if
                            fx["kind"]=="locked_summer_3pm_sun" else None,
        "sun_elevation_deg":fx["direction_elevation_deg"] if
                              fx["kind"]=="locked_summer_3pm_sun" else None,
        "cinematic_artistic_cheat":True,
        "physical_bounce_reflector_required":False,
        "usd_light_or_renderer_change_applied":False,
        "original_source_modified":False,
        "dci_render_or_photometric_accuracy_proven":False,
    }
    proof["fx_decision_sha256"]=hashlib.sha256(json.dumps(
        fx,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return proof


def captured_light_fx(fx,*,film_tick,monotonic_ns):
    """Freeze a creator-triggered independent oscillator into source Film Time."""
    _check_fx(fx)
    if fx["clock_mode"]!="independent_live":
        raise ValueError("Only an actual live light can be captured")
    if type(film_tick) is not int or film_tick<0:
        raise ValueError("Capture Film Time must be exact integer")
    if type(monotonic_ns) is not int or monotonic_ns<0:
        raise ValueError("Capture needs original monotonic timestamp")
    anchor=fx["anchor_monotonic_ns"]
    if anchor is None or monotonic_ns<anchor:
        raise PermissionError("Capture must follow a native oscillator start")
    delta=(monotonic_ns-anchor)/1e9*fx["frequency_hz"]
    # Keep the exact existing oscillator phase at the capture instant.
    result=dict(fx)
    result.update(
        clock_mode="captured_independent",
        anchor_film_tick=film_tick,
        anchor_monotonic_ns=monotonic_ns,
        phase_cycles=fx["phase_cycles"]+delta,
    )
    _check_fx(result)
    return result


def make_simple_virtual_fx(kind,target_path,*,fx_id,clock_mode="film",
                           anchor_film_tick=0,anchor_monotonic_ns=None,
                           frequency_hz=0.0,intensity=1.0,seed=0,
                           azimuth=245.0,elevation=42.0,
                           decay_seconds=0.4):
    """Explicit new creator-facing preset; not an automatic scene mutation.

    'Summer 3 PM' is a chosen continuous art direction, not a computed
    astronomical local sun position. Artists may adjust azimuth/elevation.
    """
    if kind not in KINDS:
        raise ValueError("Unknown simple virtual lighting preset")
    return {
        "format":FORMAT,"fx_id":fx_id,"kind":kind,
        "target_path":target_path,"clock_mode":clock_mode,
        "anchor_film_tick":anchor_film_tick,
        "anchor_monotonic_ns":anchor_monotonic_ns,
        "frequency_hz":frequency_hz,
        "phase_cycles":0.0,"duty_cycle":0.5,
        "intensity":intensity,"color_rgb":list(RGB[kind]),
        "direction_azimuth_deg":azimuth,
        "direction_elevation_deg":elevation,
        "decay_seconds":decay_seconds,
        "random_seed":seed,
    }
