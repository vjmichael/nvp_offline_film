"""CAM-01: director's virtual optical lens workbench before freezing a Take.

A lens is an optical camera model, NOT an arbitrary postproduction filter.
Users can preview focal length, filmback, focus and f-stop on one composed
immutable scene revision at any native source tick, without recording a Take.

Fast camera-space data are computed ONCE, sliders alter client projections
locally without re-opening USD. An authorized preview renderer can use the
same native scene and draft optics to produce a real Cycles picture later.
"""
from __future__ import annotations

import hashlib
import json
import math

from backend.nvp_film_index import FilmIndex,_id,_require_pid
from backend.nvp_openusd_scene import OpenUSDSceneBridge,_usd,MAX_USD_EXACT_TICK
from backend.nvp_openusd_native_schemas import MM_PER_CAMERA_UNIT
from backend.nvp_temporal_ledger import _int
from backend.nvp_slate_proxy_recipe import canonical,sha

FORMAT="nvp.camera.lens_workbench.v1"
PRESET_FORMAT="nvp.camera.optical_preset.v1"
PRESETS={
    "ultrawide_18":{"focal_length_mm":18.0,"description":"Wide location and interior"},
    "wide_24":{"focal_length_mm":24.0,"description":"Wide dramatic scene coverage"},
    "story_35":{"focal_length_mm":35.0,"description":"Natural wide storytelling"},
    "standard_50":{"focal_length_mm":50.0,"description":"Balanced medium framing"},
    "portrait_85":{"focal_length_mm":85.0,"description":"Portrait and close-up"},
    "tele_135":{"focal_length_mm":135.0,"description":"Narrow long-lens framing"},
}
SENSORS={
    "full_frame":{"width_mm":36.0,"height_mm":20.25},
    "super_35":{"width_mm":24.89,"height_mm":14.0},
    "micro_four_thirds":{"width_mm":17.3,"height_mm":9.73},
}
MAX_MARKERS=128


def _finite(value,minimum,maximum,name):
    if type(value) not in (int,float) or not math.isfinite(value) or not minimum<=value<=maximum:
        raise ValueError("Lens "+name+" must be a bounded finite physical quantity")
    return float(value)


def lens_settings(*,lens="standard_50",sensor="full_frame",f_stop=2.8,
                  focus_distance_m=5.0,custom_focal_mm=None,
                  custom_sensor_width_mm=None,custom_sensor_height_mm=None):
    """Exactly a perspective camera; filter looks remain a separate stack."""
    if lens not in PRESETS or sensor not in SENSORS:
        raise ValueError("Unknown director lens/sensor preset")
    width=(SENSORS[sensor]["width_mm"] if custom_sensor_width_mm is None
           else custom_sensor_width_mm)
    height=(SENSORS[sensor]["height_mm"] if custom_sensor_height_mm is None
            else custom_sensor_height_mm)
    f=(PRESETS[lens]["focal_length_mm"] if custom_focal_mm is None
       else custom_focal_mm)
    f=_finite(f,8,300,"focal length mm")
    width=_finite(width,6,70,"sensor width mm")
    height=_finite(height,4,50,"sensor height mm")
    ratio=width/height
    if not 1.0<=ratio<=3.5:
        raise ValueError("A native spherical sensor crop requires plausible aspect ratio")
    n=_finite(f_stop,0.7,32,"aperture f-number")
    distance=_finite(focus_distance_m,0.1,1000,"focus distance meters")
    hfov=math.degrees(2*math.atan(width/(2*f)))
    vfov=math.degrees(2*math.atan(height/(2*f)))
    return {
        "format":FORMAT,
        "preset":lens,"sensor":sensor,
        "focal_length_mm":f,
        "sensor_width_mm":width,"sensor_height_mm":height,
        "f_stop":n,"focus_distance_m":distance,
        "horizontal_fov_degrees":hfov,"vertical_fov_degrees":vfov,
        "squeeze_factor":1.0,
        "projection":"perspective",
        "lens_type":"spherical",
        "distortion_filter_applied":False,
        "lens_effect_stack":[],
        "optics_mathematically_previewed":True,
    }


def _stage(index,project_id,scene_id,revision):
    scene,stage=OpenUSDSceneBridge(index).open(project_id,scene_id,revision)
    if scene["data"].get("contains_external_references") is not False:
        raise PermissionError("No external USD references in pre-take workbench")
    if scene["data"].get("native_schema_version") is None:
        raise RuntimeError("A native UsdGeom.Camera is required for optics preview")
    return scene,stage


class VirtualCameraWorkbench:
    def __init__(self,index:FilmIndex,*,verify_director_action=None):
        if not isinstance(index,FilmIndex):
            raise TypeError("Lens workbench needs a trusted FilmIndex")
        self.index=index
        self.approve=verify_director_action

    def snapshot(self,project_id,scene_id,scene_revision,*,tick,camera_path,
                 max_markers=MAX_MARKERS):
        """One immutable scene evaluation; all subsequent lens sliders are local."""
        _require_pid(project_id)
        _id(scene_id,"source scene")
        tick=_int(tick,"scene source-time tick",maximum=MAX_USD_EXACT_TICK)
        if type(max_markers) is not int or not 1<=max_markers<=MAX_MARKERS:
            raise ValueError("Invalid live camera marker budget")
        scene,stage=_stage(self.index,project_id,scene_id,scene_revision)
        roles=scene["data"]["prim_roles"]
        if camera_path not in roles or roles[camera_path]!="camera":
            raise ValueError("Select an actual authored camera in the scene")
        _,_,Usd,UsdGeom=_usd()
        t=Usd.TimeCode(float(tick))
        camera_prim=stage.GetPrimAtPath(camera_path)
        if not camera_prim.IsA(UsdGeom.Camera):
            raise RuntimeError("Selected camera lacks native USD camera schema")
        if str(UsdGeom.Imageable(camera_prim).ComputeVisibility(t))=="invisible":
            raise RuntimeError("Director chose a hidden source camera")
        camera=UsdGeom.Camera(camera_prim)
        projection=str(camera.GetProjectionAttr().Get(t))
        if projection!="perspective":
            raise RuntimeError("Pre-take lens workbench supports perspective optics only")
        origin=UsdGeom.Xformable(camera_prim).ComputeLocalToWorldTransform(t)
        to_camera=origin.GetInverse()
        markers=[]
        for path,role in sorted(roles.items()):
            if role=="camera":
                continue
            prim=stage.GetPrimAtPath(path)
            if str(UsdGeom.Imageable(prim).ComputeVisibility(t))=="invisible":
                continue
            world=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(t)
            p=world.ExtractTranslation()
            local=to_camera.Transform(p)
            xyz=[float(x) for x in local]
            if any(not math.isfinite(x) or abs(x)>1_000_000 for x in xyz):
                raise RuntimeError("Scene camera-projection data are invalid")
            markers.append({
                "path":path,"role":role,"camera_space_xyz":xyz,
                "hint_radius_m":0.6 if role=="actor" else 0.4,
            })
            if len(markers)>max_markers:
                raise ValueError("Too many visible scene subjects for live lens overlay")
        return {
            "format":FORMAT,
            "project_id":project_id,"scene_id":scene_id,
            "scene_revision":scene_revision,
            "scene_document_sha256":scene["document_sha256"],
            "source_tick":tick,"camera_path":camera_path,
            "markers":markers,
            "source_actor_poses_edited":False,
            "frozen_take_created":False,
            "preview_mode":"instant_projection_not_film_render",
            "source_scene_loaded_once":True,
        }

    def save_preset(self,project_id,preset_id,*,settings,creator_event,
                    expected_revision=0):
        """Persist a director-approved optical preset without touching scene."""
        _require_pid(project_id)
        _id(preset_id,"camera preset ID")
        if self.approve is None:
            raise PermissionError("A trusted director approval service is required")
        if type(settings) is not dict:
            raise ValueError("Exact typed optics required")
        revalidated=lens_settings(
            lens=settings["preset"],sensor=settings["sensor"],
            f_stop=settings["f_stop"],
            focus_distance_m=settings["focus_distance_m"],
            custom_focal_mm=settings["focal_length_mm"],
            custom_sensor_width_mm=settings["sensor_width_mm"],
            custom_sensor_height_mm=settings["sensor_height_mm"])
        if revalidated!=settings:
            raise ValueError("Preset camera optics contain unapproved fields")
        digest=sha(canonical(settings))
        scope={
            "operation":"nvp.camera.save_optical_preset.v1",
            "project_id":project_id,"preset_id":preset_id,
            "expected_revision":expected_revision,
            "optics_sha256":digest,"source_scene_changed":False,
            "film_master_approved":False,
        }
        if self.approve(creator_event,scope) is not True:
            raise PermissionError("Director did not approve camera setup preset")
        return self.index.register_revision(
            project_id,preset_id,"presentation",
            {"format":PRESET_FORMAT,"optics":settings,
             "optics_sha256":digest,"source_scene_changed":False,
             "rendered_picture":False,"director_preset_approved":True},
            expected_revision=expected_revision,dependencies=[])

    def open_preset(self,project_id,preset_id,revision):
        record=self.index.read_revision(project_id,preset_id,revision)
        doc=record["data"]
        if (record["kind"]!="presentation" or
            doc.get("format")!=PRESET_FORMAT or
            doc.get("director_preset_approved") is not True or
            doc.get("source_scene_changed") is not False or
            doc["optics_sha256"]!=sha(canonical(doc["optics"]))):
            raise RuntimeError("Invalid saved immutable director lens preset")
        return record
