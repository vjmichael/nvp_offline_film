"""WO2 A–E: source-bound, immutable, creator-approved rendering decisions.

This is a *presentation* revision attached to an exact OpenUSD scene, not
a mutation of USD geometry, captured performances, original PNGs or Takes.
The visual renderers consume these typed decisions; unknown shader code,
external HDRI URLs, file paths and arbitrary MaterialX graphs are rejected.
"""
from __future__ import annotations
import copy
import math

from backend.nvp_film_index import FilmIndex,_id,_require_pid,_sha
from backend.nvp_openusd_scene import OpenUSDSceneBridge

FORMAT="nvp.wo2.source_bound_presentation_look.v1"
ENVIRONMENTS=("neutral_studio","soft_daylight","golden_hour","moonlight")
FILTERS=("nearest","bilinear","trilinear")
TONE_CURVES=("linear","filmic_preview")
CHANNELS=("base_color","roughness","metallic","emission","normal","opacity")


def _number(value,low,high,name):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError("Invalid bounded look property: "+name)
    return float(value)


def _keys(value,expected,name):
    if type(value) is not dict or set(value)!=set(expected):
        raise ValueError("Invalid original scene presentation "+name)
    return value


def _pair(value,low,high,name):
    if type(value) is not list or len(value)!=2:
        raise ValueError("Invalid presentation UV "+name)
    return [_number(x,low,high,name) for x in value]


def default_look():
    return {
        "lighting":{"shadows":True,"shadow_resolution":1024,
                    "shadow_softness":2.,"direct_intensity":2.5,
                    "ambient_intensity":.7},
        "environment":{"preset":"neutral_studio","intensity":1.,
                       "reflections":1.},
        "camera":{"exposure_ev":0.,"tone_curve":"filmic_preview",
                  "depth_of_field":False,"f_stop":4.,
                  "focus_distance_m":5.},
        "textures":{"filter":"trilinear","anisotropy":4,
                    "transforms":{}},
        "materials":{},
    }


def validate_look(look,scene_roles):
    _keys(look,("lighting","environment","camera","textures","materials"),
          "look")
    if type(scene_roles) is not dict:
        raise TypeError("Source authored scene roles required")
    lighting=_keys(look["lighting"],(
        "shadows","shadow_resolution","shadow_softness",
        "direct_intensity","ambient_intensity"),"lighting")
    if type(lighting["shadows"]) is not bool or lighting["shadow_resolution"] not in (
            512,1024,2048):
        raise ValueError("Unsupported bounded shadow-map budget")
    light={
        "shadows":lighting["shadows"],
        "shadow_resolution":lighting["shadow_resolution"],
        "shadow_softness":_number(lighting["shadow_softness"],0.,12.,"shadow softness"),
        "direct_intensity":_number(lighting["direct_intensity"],0.,12.,"sun intensity"),
        "ambient_intensity":_number(lighting["ambient_intensity"],0.,4.,"ambient intensity"),
    }
    env=_keys(look["environment"],("preset","intensity","reflections"),"environment")
    if env["preset"] not in ENVIRONMENTS:
        raise ValueError("Unknown packaged original environment preset")
    environment={
        "preset":env["preset"],
        "intensity":_number(env["intensity"],0.,4.,"environment intensity"),
        "reflections":_number(env["reflections"],0.,3.,"reflection strength"),
    }
    cam=_keys(look["camera"],(
        "exposure_ev","tone_curve","depth_of_field","f_stop","focus_distance_m"),"camera")
    if type(cam["depth_of_field"]) is not bool or cam["tone_curve"] not in TONE_CURVES:
        raise ValueError("Unsupported camera presentation transform")
    camera={
        "exposure_ev":_number(cam["exposure_ev"],-8.,8.,"exposure"),
        "tone_curve":cam["tone_curve"],
        "depth_of_field":cam["depth_of_field"],
        "f_stop":_number(cam["f_stop"],1.,22.,"f-stop"),
        "focus_distance_m":_number(cam["focus_distance_m"],.1,10000.,"focus"),
    }
    textures=_keys(look["textures"],("filter","anisotropy","transforms"),"textures")
    if textures["filter"] not in FILTERS or type(textures["anisotropy"]) is not int or (
        textures["anisotropy"] not in (1,2,4,8,16)):
        raise ValueError("Unsupported mip/anisotropy policy")
    transforms=textures["transforms"]
    if type(transforms) is not dict or len(transforms)>32:
        raise ValueError("Too many original USD texture presentation overrides")
    uv={}
    for path,channels in transforms.items():
        if (type(path) is not str or scene_roles.get(path) not in (
                "actor","prop","environment") or
            type(channels) is not dict or not channels or
            len(channels)>len(CHANNELS)):
            raise ValueError("UV transform targets must be original mesh source paths")
        uv[path]={}
        for channel,item in channels.items():
            if channel not in CHANNELS:
                raise ValueError("Unknown original UV texture channel")
            _keys(item,("repeat","offset","rotation_deg"),"UV transform")
            uv[path][channel]={
                "repeat":_pair(item["repeat"],.01,64.,"repeat"),
                "offset":_pair(item["offset"],-64.,64.,"offset"),
                "rotation_deg":_number(item["rotation_deg"],-360.,360.,"rotation"),
            }
    textures_result={"filter":textures["filter"],
                     "anisotropy":textures["anisotropy"],"transforms":uv}
    materials=look["materials"]
    if type(materials) is not dict or len(materials)>32:
        raise ValueError("Too many source-bound presentation materials")
    material_result={}
    for path,item in materials.items():
        if type(path) is not str or scene_roles.get(path) not in (
                "actor","prop","environment"):
            raise ValueError("Translucency requires a real source actor or prop")
        _keys(item,("opacity","transmission","ior","thickness_m"),"physical material")
        material_result[path]={
            "opacity":_number(item["opacity"],0.,1.,"opacity"),
            "transmission":_number(item["transmission"],0.,1.,"transmission"),
            "ior":_number(item["ior"],1.,2.5,"index of refraction"),
            "thickness_m":_number(item["thickness_m"],0.,10.,"material thickness"),
        }
    return {"lighting":light,"environment":environment,"camera":camera,
            "textures":textures_result,"materials":material_result}


def propose_look(mood,scene_roles):
    """Deterministic suggestion *only*, safe for future AI tool proposals.

    No AI/model suggestion is a grant to persist or affect an original Take.
    """
    if mood not in ("natural","dramatic","warm","night","product"):
        raise ValueError("Unknown bounded assistant filmmaking intention")
    look=default_look()
    if mood=="dramatic":
        look["lighting"].update({"direct_intensity":4.,"ambient_intensity":.28})
        look["camera"]["exposure_ev"]=-.6
    elif mood=="warm":
        look["environment"]["preset"]="golden_hour"
        look["lighting"]["direct_intensity"]=2.8
    elif mood=="night":
        look["environment"]["preset"]="moonlight"
        look["camera"]["exposure_ev"]=-1.
        look["lighting"].update({"ambient_intensity":.3,"direct_intensity":.8})
    elif mood=="product":
        look["environment"].update({"preset":"neutral_studio","reflections":1.5})
        look["lighting"]["shadow_softness"]=4.
    return {"format":"nvp.wo2.creator_look_proposal.v1",
            "intent":mood,
            "look":validate_look(look,scene_roles),
            "persisted":False,"creator_approved":False,
            "original_source_modified":False}


class OriginalSceneLook:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Original FilmIndex is required")
        self.index=index

    def _source(self,pid,scene_id,revision,scene_sha):
        _require_pid(pid);_id(scene_id,"USD scene")
        if type(revision) is not int or revision<1:
            raise ValueError("Exact original scene revision required")
        _sha(scene_sha)
        record,_=OpenUSDSceneBridge(self.index).open(pid,scene_id,revision)
        if record["document_sha256"]!=scene_sha:
            raise PermissionError("Original source scene revision changed")
        return record

    def _check_material_sources(self,pid,source,checked):
        """Ensure every proposed UV edit names a real SHA-verified image.

        A model or user cannot make a plausible-looking material look by
        connecting a nonexistent channel or mixing fractional opacity
        with a previously cutout-masked original source.
        """
        from backend.nvp_openusd_assets import OpenUSDAssetRegistry
        assets=OpenUSDAssetRegistry(self.index)
        channels={}
        for binding in source["data"].get("asset_bindings",[]):
            rec,_=assets.open(pid,binding["asset_id"],
                              binding["asset_revision"])
            if rec["document_sha256"]!=binding["asset_document_sha256"]:
                raise PermissionError("Presentation target original asset changed")
            material=rec["data"].get("preview_material") or {}
            available=set(material.get("pbr_maps") or {})
            if material.get("texture"):available.add("base_color")
            channels[binding["path"]]=available
        for rig in source["data"].get("skeleton_rigs",[]):
            available=set(rig.get("pbr_maps") or {})
            if rig.get("texture"):available.add("base_color")
            channels[rig["path"]]=available
        for path,overrides in checked["textures"]["transforms"].items():
            if not set(overrides)<=channels.get(path,set()):
                raise ValueError(
                    "Original USD source material lacks requested UV channel")
        for path,mat in checked["materials"].items():
            if mat["opacity"]<1. and "opacity" in channels.get(path,set()):
                raise ValueError(
                    "Fractional opacity cannot overwrite binary source cutouts")
        return True

    def assistant_scene_brief(self,pid,*,scene_id,scene_revision,scene_sha256):
        """Read bounded verified USD facts for a future local AI director.

        No remote requests, model execution, external paths, raw recordings
        or access to unrelated source revisions is performed by this tool.
        """
        source=self._source(pid,scene_id,scene_revision,scene_sha256)
        from backend.nvp_openusd_assets import OpenUSDAssetRegistry
        assets=OpenUSDAssetRegistry(self.index)
        materials=[]
        for bind in source["data"].get("asset_bindings",[])[:64]:
            record,_=assets.open(pid,bind["asset_id"],bind["asset_revision"])
            if record["document_sha256"]!=bind["asset_document_sha256"]:
                raise PermissionError("AI material brief source changed")
            material=record["data"].get("preview_material") or {}
            materials.append({
                "path":bind["path"],
                "geometry":record["data"]["shape"],
                "asset_document_sha256":record["document_sha256"],
                "roughness":material.get("roughness"),
                "metallic":material.get("metallic"),
                "original_image_channels":(
                    (["base_color"] if material.get("texture") else [])+
                    sorted((material.get("pbr_maps") or {}).keys())),
            })
        roles=source["data"]["prim_roles"]
        return {
            "format":"nvp.wo2.assistant_source_scene_brief.v1",
            "project_scoped":True,
            "scene_id":scene_id,"scene_revision":scene_revision,
            "scene_sha256":scene_sha256,
            "cameras":sorted(x for x,r in roles.items() if r=="camera")[:16],
            "lights":sorted(x for x,r in roles.items() if r=="light")[:32],
            "actors":sorted(x for x,r in roles.items() if r=="actor")[:32],
            "material_sources":materials,
            "supported_look_capabilities":[
                "soft_shadows","environment_reflections",
                "camera_exposure","depth_of_field","UV_transform",
                "texture_filtering","opacity","transmission","ior"],
            "source_mutation_permitted":False,
            "source_modified":False,
        }

    def validate_assistant_proposal(self,pid,*,scene_id,scene_revision,
                                    scene_sha256,look,rationale):
        """Validate an external model suggestion; never save or execute it."""
        if (type(rationale) is not str or not 1<=len(rationale)<=1200 or
            any(ord(c)<32 and c not in "\n\t" for c in rationale) or
            any(token in rationale.lower() for token in (
                r"\x00", r"\u0000", r"\0"))):
            raise ValueError("Assistant reasoning must be bounded plain text")
        source=self._source(pid,scene_id,scene_revision,scene_sha256)
        checked=validate_look(look,source["data"]["prim_roles"])
        self._check_material_sources(pid,source,checked)
        changes=[]
        standard=default_look()
        for area in ("lighting","environment","camera","textures","materials"):
            if checked[area]!=standard[area]:
                changes.append(area)
        return {
            "format":"nvp.wo2.assistant_look_proposal.v1",
            "scene_sha256":scene_sha256,
            "look":checked,"rationale":rationale,
            "changed_areas":changes,
            "project_scoped":True,
            "creator_approved":False,"persisted":False,
            "source_modified":False,
            "may_execute_native_tools":False,
            "may_author_shader_code":False,
        }

    def publish(self,pid,look_id,*,scene_id,scene_revision,
                scene_sha256,look,expected_revision=0,approve):
        _id(look_id,"presentation decision identity")
        source=self._source(pid,scene_id,scene_revision,scene_sha256)
        checked=validate_look(look,source["data"]["prim_roles"])
        self._check_material_sources(pid,source,checked)
        if not callable(approve):
            raise PermissionError("A real desktop creator approval is required")
        approved=approve({
            "format":FORMAT,"scene_id":scene_id,
            "scene_revision":scene_revision,
            "scene_sha256":scene_sha256,
            "look_id":look_id,"expected_revision":expected_revision,
            "look":copy.deepcopy(checked),
        })
        if approved is not True:
            return {"format":FORMAT,"status":"DENIED",
                    "original_modified":False}
        # Re-read original source after the OS approval dialog. Exact SHA
        # and revision are a precommit source dependency, not a UI promise.
        self._source(pid,scene_id,scene_revision,scene_sha256)
        result=self.index.register_revision(
            pid,look_id,"presentation",{
                "format":FORMAT,"scene_id":scene_id,
                "scene_revision":scene_revision,
                "scene_document_sha256":scene_sha256,
                "look":checked,
                "original_modified":False,
            },expected_revision=expected_revision,
            dependencies=[{"object_id":scene_id,
                           "revision":scene_revision,"role":"scene"}])
        return {"format":FORMAT,"status":"PRESENTATION_REVISION_APPROVED",
                "look_id":look_id,
                "revision":result["revision"],
                "document_sha256":result["document_sha256"],
                "source_scene_sha256":scene_sha256,
                "original_modified":False,"ffmpeg_used":False}

    def catalog(self,pid,*,scene_id,scene_revision,scene_sha256):
        """Show only approved presentation revisions of this exact USD scene."""
        self._source(pid,scene_id,scene_revision,scene_sha256)
        options=[]
        for row in self.index.list_objects(pid,kind="presentation")[:128]:
            rec=self.index.read_revision(pid,row["object_id"])
            data=rec["data"]
            if (data.get("format")==FORMAT and
                data.get("scene_id")==scene_id and
                data.get("scene_revision")==scene_revision and
                data.get("scene_document_sha256")==scene_sha256 and
                data.get("original_modified") is False):
                options.append({
                    "look_id":row["object_id"],
                    "revision":rec["revision"],
                    "document_sha256":rec["document_sha256"],
                })
        return {"format":FORMAT,"scene_sha256":scene_sha256,
                "looks":options,
                "original_modified":False}

    def open(self,pid,look_id,revision,*,scene_sha256):
        _sha(scene_sha256)
        record=self.index.read_revision(pid,look_id,revision)
        data=record["data"]
        if (record["kind"]!="presentation" or
            data.get("format")!=FORMAT or
            data.get("scene_document_sha256")!=scene_sha256 or
            data.get("original_modified") is not False):
            raise PermissionError("Presentation look is not bound to requested source")
        source=self._source(pid,data["scene_id"],data["scene_revision"],
                            scene_sha256)
        checked=validate_look(data["look"],source["data"]["prim_roles"])
        self._check_material_sources(pid,source,checked)
        return {"format":FORMAT,"look":checked,
                "scene_sha256":scene_sha256,
                "look_document_sha256":record["document_sha256"],
                "original_modified":False}
