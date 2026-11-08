"""Pure, source-safe virtual cinematic light-to-raster binding (NOT DCI).

Provides deliberate nonphysical per-USD-prim artist light contributions.
No physical bounce card, path traced GI, screen-space face tracking or
untrusted browser/LLM actor permissions. Renderer's actual pixel shader
must consume the returned per-prim instructions for effect to be visible.

This adapter is PREVIEW-ONLY. Exact Take + Film Time, original FX SHA,
creator-owned FilmIndex permissions and a future persistent virtual-FX
revision are separate upstream obligations; a JSON sidecar alone is not
an approved finished film light rig.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_virtual_light_fx import evaluate_virtual_light_fx

FORMAT="nvp.vlight.native_virtual_shader_preview.v1"
SCENE_TARGET="/World/Scene"  # virtual whole-scene namespace, not a real mesh
MAX_VIRTUAL_FX=12
MAX_SCENE_TARGETS=256
MAX_PREVIEW_GAIN=16.0


def evaluate_scene_virtual_lighting(effects,scene_paths,film_tick):
    """Return strict immutable per-object virtual diffuse light overlays.

    Applied only by NVP's existing real OpenUSD pixel raster. Never makes
    a new scene, approved Take, PCM sample, image source or shader path.
    """
    if type(effects) not in (list,tuple) or len(effects)>MAX_VIRTUAL_FX:
        raise ValueError("Bounded typed virtual film-light list required")
    if (type(scene_paths) not in (list,tuple,set) or
            not 1<=len(scene_paths)<=MAX_SCENE_TARGETS or
            any(type(s) is not str or not s.startswith("/World/")
                for s in scene_paths) or
            len(set(scene_paths))!=len(scene_paths)):
        raise ValueError("Actual frozen USD scene target registry required")
    valid=set(scene_paths)
    if type(film_tick) is not int or film_tick<0:
        raise ValueError("Valid exact original Film Time required")
    ids=set()
    maps={path:[] for path in valid}
    evaluations=[]
    for fx in sorted(effects,key=lambda x:x.get("fx_id","") if isinstance(x,dict) else ""):
        proof=evaluate_virtual_light_fx(
            fx,film_tick,final_render=True)
        kind=proof["kind"]
        identifier=proof["fx_id"]
        target=proof["target_path"]
        if identifier in ids:
            raise ValueError("Duplicate original virtual lighting FX identity")
        ids.add(identifier)
        if kind=="locked_summer_3pm_sun" and target==SCENE_TARGET:
            targets=sorted(valid)
        elif target in valid:
            targets=[target]
        else:
            raise PermissionError("Virtual light cannot address an absent source prim")
        intensity=proof["evaluated_intensity"]
        if type(intensity) not in (int,float) or not 0<=intensity<=MAX_PREVIEW_GAIN:
            raise PermissionError("Virtual light exceeds bounded source preview power")
        rgb=tuple(proof["evaluated_color_rgb"])
        if len(rgb)!=3 or any(
                type(x) not in (int,float) or not math.isfinite(x) or
                not 0<=x<=16 for x in rgb):
            raise PermissionError("Invalid virtual light color for native raster")
        direction=None
        if kind=="locked_summer_3pm_sun":
            az=math.radians(proof["sun_azimuth_deg"])
            el=math.radians(proof["sun_elevation_deg"])
            direction=(math.cos(el)*math.cos(az),
                       math.cos(el)*math.sin(az),math.sin(el))
        # A digital virtual fill intentionally ignores ray path, inverse
        # squared distance and other physical lighting rules.
        instruction=(rgb,float(intensity),direction)
        for path in targets:
            maps[path].append(instruction)
        evaluations.append({
            "fx_id":identifier,"kind":kind,
            "target_path":target,"affected_objects":len(targets),
            "evaluated_intensity":intensity,
            "color_rgb":list(rgb),
            "source_fx_decision_sha256":proof["fx_decision_sha256"],
            "source_film_tick":str(film_tick),
            "light_physically_path_traced":False,
        })
    doc_sha=sha256(json.dumps(list(effects),
        sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return maps,{
        "format":FORMAT,
        "fx_source_sha256":doc_sha,
        "source_film_tick":str(film_tick),
        "effect_count":len(evaluations),
        "evaluated_effects":evaluations,
        "real_scene_pixel_shader_consumes_fx":bool(evaluations),
        "physical_bounce_board_required":False,
        "original_frozen_usd_modified":False,
        "shader_render_reference_calibrated":False,
        "artist_approved_final_lighting":False,
    }
