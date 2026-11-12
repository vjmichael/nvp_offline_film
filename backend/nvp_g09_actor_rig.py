"""G09-B: actual time-sampled UsdSkel acting and source-synced face rig.

Only original G06 ActorIDs and G06 original PCM can drive the result. The
human-reviewed G09 acting document selects creative style; the G06 original
USD determines world/root translation. Each output is a NEW derived USDA.
Frozen originals, original PCM and original Take JSON never change.

This first implementation authors real UsdSkel rotations/translations
AND actual moving humanoid proxy geometry (torso/limbs/face), not merely a
rig description. It makes no claim of captured human motion, realistic
muscles, natural cloth/hair, phoneme-accurate visemes or expressive voice TTS.
"""
from __future__ import annotations

from array import array
from hashlib import sha256
import math
import struct
import sys

from backend.nvp_g09_actor import _validate as validate_actor_doc
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_g09e_pcm import (
    VerifiedSQLitePCM,WindowedVoiceSamples,verified_pcm_digest)
from backend.nvp_g06_sealed_capture import VerifiedSealedPCM

SAMPLE_RATE=48000
FILM_STEP=TICKS_PER_SECOND//24
MAX_ACTORS=12
MAX_SAMPLES_PER_ACTOR=4000
MAX_USD_OUTPUT_BYTES=24*1024*1024
MAX_ORIGINAL_PCM_BYTES=12*1024*1024
J=[
 "Body","Body/Hips","Body/Hips/Torso","Body/Hips/Torso/Neck",
 "Body/Hips/Torso/Neck/Head","Body/Hips/Torso/Neck/Head/Jaw",
 "Body/Hips/Torso/LeftUpperArm","Body/Hips/Torso/LeftUpperArm/LeftForearm",
 "Body/Hips/Torso/RightUpperArm","Body/Hips/Torso/RightUpperArm/RightForearm",
 "Body/Hips/LeftThigh","Body/Hips/LeftThigh/LeftShin",
 "Body/Hips/RightThigh","Body/Hips/RightThigh/RightShin"]
PARENT={n:n.rsplit("/",1)[0] if "/" in n else None for n in J}
OFFSETS=[
 (0.,0.,0.),(0.,0.,.62),(0.,0.,.37),(0.,0.,.68),
 (0.,0.,.16),(0.,-.22,-.11),
 (-.34,0.,.45),(0.,0.,-.43),
 (.34,0.,.45),(0.,0.,-.43),
 (-.19,0.,-.54),(0.,0.,-.50),
 (.19,0.,-.54),(0.,0.,-.50)
]
# Keyed to performer posture in the SOURCE Take; no separate root path
# is evaluated from a newer screenplay or editable scene.
ACTION_STYLES={"walk":1.,"jog":1.65,"run":2.35,"crawl":.75}
EMOTIONAL_HEAD={"neutral":0.,"joy":-.09,"sadness":.18,
                 "anger":-.11,"fear":.12,"surprise":-.05,"focus":-.03}


def _source_events(source,actor_id):
    return sorted((x for x in source["events"]
                   if x.get("actor_id")==actor_id),
                  key=lambda x:(x["start_tick"],x["id"]))


def _voice_envelopes(source,actor,original):
    """True RMS from verified native mono 48k PCM, never guessed words.

    Source sample analysis happens entirely in private host/worker memory.
    Only bounded numeric mouth-open samples enter new derived scene layers;
    raw PCM stays in the G06 source store.
    """
    by_id={x["clip_id"]:x for x in original["audio"]}
    indexed={x["clip_id"]:x for x in source["audio"]}
    selected=[]
    for selection in actor["voice_clips"]:
        if selection["review"]!="approved":continue
        clip=by_id.get(selection["clip_id"])
        ref=indexed.get(selection["clip_id"])
        if clip is None or ref is None:
            raise RuntimeError("Approved actor voice original is missing")
        if (ref["actor_id"]!=actor["actor_id"] or
            clip["pcm_sha256"]!=ref["pcm_sha256"] or
            len(clip["pcm16le"])!=ref["sample_count"]*2 or
            (len(clip["pcm16le"])>MAX_ORIGINAL_PCM_BYTES and
             not isinstance(clip["pcm16le"],(VerifiedSQLitePCM,VerifiedSealedPCM))) or
            verified_pcm_digest(clip["pcm16le"])!=ref["pcm_sha256"]):
            raise RuntimeError("Actor voice was not the reviewed original recording")
        if isinstance(clip["pcm16le"],(VerifiedSQLitePCM,VerifiedSealedPCM)):
            # The 960-sample RMS window never copies the original recording.
            pcm=WindowedVoiceSamples(clip["pcm16le"])
        else:
            pcm=array("h")
            pcm.frombytes(clip["pcm16le"])
            if sys.byteorder!="little":pcm.byteswap()
        selected.append((ref,pcm))
    return selected


def _amplitude_at(source,tick,voice,edits=None):
    """Actual PCM jaw timing follows G07 sound enable, gain and offset.

    Each editorial shot can shift or mute the source independently. Reusing
    one Take never silently reuses a stale mouth animation.
    """
    decisions=({v["clip_id"]:v for v in edits} if edits is not None else None)
    peak=0.
    for ref,pcm in voice:
        choice=decisions.get(ref["clip_id"]) if decisions is not None else None
        if decisions is not None and (
                choice is None or not choice["enabled"] or not choice["gain"]):
            continue
        start=ref["start_tick"]+(choice["offset_tick"] if choice else 0)
        duration=ref["duration_tick"]
        if not start<=tick<start+duration:continue
        sample=int((tick-start)*SAMPLE_RATE//TICKS_PER_SECOND)
        lo=max(0,sample-480)
        hi=min(len(pcm),sample+480)
        if hi<=lo:continue
        # O(960) per evaluated Film Time sample, bounded even for long clips.
        rms=math.sqrt(sum((v/32768)**2 for v in pcm[lo:hi])/(hi-lo))
        peak=max(peak,rms)
    # Adaptive but bounded noise gate/compression. This drives only stylized
    # jaw aperture and does not state which phonemes the actor actually spoke.
    return min(1.,max(0.,(peak-.012)*8.))


def _active(events,tick,kind):
    return [e for e in events if e["kind"] in kind and
            e["start_tick"]<=tick<e["end_tick"]]


def _local_pose(actor,events,tick,voice,voice_edits=None):
    """Deterministic, bounded joint rotations and visible body keypoints."""
    motion=_active(events,tick,ACTION_STYLES)
    movement=motion[-1] if motion else None
    action=movement["kind"] if movement else "still"
    strength=ACTION_STYLES.get(action,0.)
    phase=(tick/TICKS_PER_SECOND)*2*math.pi*(.9+.38*strength)
    # Actor root translation remains the independently frozen G06 movement.
    scale=actor["gait_strength"]*strength
    mood=actor["emotion"]
    emotion_strength=actor["expression_strength"]
    cues=actor.get("expression_cues",[])
    recent=[(i,c) for i,c in enumerate(cues) if c["at_tick"]<=tick]
    if recent:
        i,cue=recent[-1]
        mood=cue["emotion"]
        emotion_strength=cue["strength"]
        previous_emotion=(cues[i-1]["emotion"] if i>0
                          else actor["emotion"])
        previous_strength=(cues[i-1]["strength"] if i>0
                           else actor["expression_strength"])
        eased=min(1.,max(0.,(tick-cue["at_tick"])/(
            TICKS_PER_SECOND*.24)))
    else:
        previous_emotion=mood
        previous_strength=emotion_strength
        eased=1.
    style={"restrained":.58,"natural":1.,"neutral":.65,
           "energetic":1.45,"heavy":.85}[actor["movement"]]
    left=math.sin(phase)*scale*style
    right=-left
    arms=math.sin(phase+.9)*scale*style
    sit=action=="crawl"
    note=_active(events,tick,("gesture","look","expression"))
    gesture=any(x["kind"]=="gesture" for x in note)
    look=any(x["kind"]=="look" for x in note)
    joy=emotion_strength
    jaw=_amplitude_at(None,tick,voice,voice_edits)*(.45+.55*joy)
    rate=actor["blink_rate"]
    blink=0.
    if rate>0:
        cycle=60./rate
        mark=(tick/TICKS_PER_SECOND)%cycle
        blink=max(0.,1-abs(mark-.09)/.07)
    torso=.12 if sit else -.015*scale*math.cos(phase)
    head=(EMOTIONAL_HEAD[previous_emotion]*previous_strength*(1-eased)+
          EMOTIONAL_HEAD[mood]*joy*eased)+(.13 if look else 0.)
    rot=[(0.,0.,0.) for _ in J]
    def assign(i,axis,theta):
        e=list(rot[i]);e[axis]=theta;rot[i]=tuple(e)
    assign(1,0,torso)
    assign(2,0,torso*.4)
    assign(4,0,head)
    assign(4,2,.04*math.sin(phase*.5) if look else 0)
    assign(5,0,min(.75,jaw*.62))
    assign(6,0,-arms*.47-(.75 if gesture else 0.))
    assign(8,0,arms*.47-(.75 if gesture else 0.))
    assign(7,0,-(.16 if gesture else 0.))
    assign(9,0,-(.16 if gesture else 0.))
    assign(10,0,left*.40+(.48 if sit else 0))
    assign(12,0,right*.40+(.48 if sit else 0))
    assign(11,0,max(0,-left)*.36+(.55 if sit else 0))
    assign(13,0,max(0,-right)*.36+(.55 if sit else 0))
    # Stylized body mesh uses the exact same joint-state source as UsdSkel.
    smile_modes={"joy":.75,"surprise":.15,"sadness":-.65,
                 "anger":-.38,"fear":-.27,"focus":-.10,"neutral":0.}
    smile=((smile_modes[previous_emotion]*previous_strength*(1-eased))+
           smile_modes[mood]*joy*eased)
    return {"rotations":rot,"jaw":jaw,"blink":blink,"smile":smile,
            "action":action,"gesture":gesture,
            "movement_intensity":min(1.,strength*scale),
            "source_tick":int(tick)}


def _q(angle,axis):
    from pxr import Gf
    return Gf.Quatf(math.cos(angle*.5),
        Gf.Vec3f(*tuple(math.sin(angle*.5)*v for v in axis)))


def _quat(rot):
    """Compose XYZ local Euler; no guessed BVH source coordinate conversion."""
    from pxr import Gf
    x,y,z=rot
    return _q(z,(0.,0.,1.))*_q(y,(0.,1.,0.))*_q(x,(1.,0.,0.))


def _times(duration,events,source_audio,voice_edits=None,expression_cues=()):
    if type(duration) is not int or duration<=0 or duration>3*3600*TICKS_PER_SECOND:
        raise ValueError("Original film duration is outside this character profile")
    # Cues begin/end on exact Film Time; 24 Hz interleaved world-frame
    # sampling is a DERIVED acting layer, never the source time clock.
    values=set(range(0,duration+1,FILM_STEP))
    values.add(duration)
    for event in events:
        values.add(event["start_tick"])
        values.add(event["end_tick"])
    audio_choices=({v["clip_id"]:v for v in voice_edits}
                   if voice_edits is not None else None)
    for clip in source_audio:
        choice=audio_choices.get(clip["clip_id"]) if audio_choices is not None else None
        if audio_choices is not None and (
                choice is None or not choice["enabled"] or not choice["gain"]):
            continue
        start=clip["start_tick"]+(choice["offset_tick"] if choice else 0)
        for boundary in (start,start+clip["duration_tick"]):
            if 0<=boundary<=duration:values.add(boundary)
    for cue in expression_cues:
        values.add(cue["at_tick"])
        eased=cue["at_tick"]+TICKS_PER_SECOND//4
        if eased<=duration:values.add(eased)
    # Exact director facial cues and a modest ease-in key preserve film-time
    # intent even when the film format is projected at a different frame rate.
    for cue in events:
        if cue["kind"]=="expression":
            values.add(cue["start_tick"])
    if len(values)>MAX_SAMPLES_PER_ACTOR:
        raise ValueError("This Take requires a longer-form actor animation worker")
    return sorted(values)


def _material(stage,path,color):
    from pxr import UsdShade,Sdf,Gf
    mat=UsdShade.Material.Define(stage,path)
    shader=UsdShade.Shader.Define(stage,path+"/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    rgb=tuple(int(color[k:k+2],16)/255 for k in (1,3,5))
    shader.CreateInput("diffuseColor",Sdf.ValueTypeNames.Color3f).Set(
        Gf.Vec3f(*rgb))
    shader.CreateInput("roughness",Sdf.ValueTypeNames.Float).Set(.7)
    shader.CreateOutput("surface",Sdf.ValueTypeNames.Token)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),"surface")
    return mat


def _geom(stage,path,kind,material):
    from pxr import UsdGeom,UsdShade
    if kind=="capsule":
        mesh=UsdGeom.Capsule.Define(stage,path)
        mesh.CreateRadiusAttr(.12)
        mesh.CreateHeightAttr(.8)
    elif kind=="sphere":
        mesh=UsdGeom.Sphere.Define(stage,path)
        mesh.CreateRadiusAttr(.5)
    else:raise ValueError("Unknown actor geometry")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return mesh


def _visible(stage,path,actor):
    """Real time-sampled USD geometry, subordinate to original ActorID root."""
    from pxr import Sdf,UsdGeom,Usd
    root=UsdGeom.Xform.Define(stage,path+"/G09ActorRig")
    root.GetPrim().CreateAttribute(
        "nvp:g09:ActorID",Sdf.ValueTypeNames.String).Set(actor["actor_id"])
    mats={}
    for name,key in [("skin","skin_color"),("wardrobe","wardrobe_color"),
                     ("hair","hair_color"),("eye","eye_color")]:
        mats[name]=_material(stage,path+"/G09ActorRig/Mats/"+name,
                              actor[key])
    shapes={
      "Torso":("capsule","wardrobe",.27,.77),
      "Head":("sphere","skin",.29,.56),
      "LeftArm":("capsule","wardrobe",.095,.5),
      "RightArm":("capsule","wardrobe",.095,.5),
      "LeftLeg":("capsule","wardrobe",.125,.58),
      "RightLeg":("capsule","wardrobe",.125,.58),
      "LeftHand":("sphere","skin",.10,.17),
      "RightHand":("sphere","skin",.10,.17),
      "Jaw":("sphere","skin",.16,.09),
      "LeftEye":("sphere","eye",.064,.06),
      "RightEye":("sphere","eye",.064,.06),
      "Hair":("sphere","hair",.3,.18),
      "LeftBrow":("sphere","hair",.11,.045),
      "RightBrow":("sphere","hair",.11,.045),
      "MouthLeft":("sphere","skin",.055,.048),
      "MouthRight":("sphere","skin",.055,.048)}
    prims={}
    for label,(kind,mat,radius,height) in shapes.items():
        path2=path+"/G09ActorRig/Visible/"+label
        node=UsdGeom.Xform.Define(stage,path2)
        geo=_geom(stage,path2+"/Mesh",kind,mats[mat])
        if kind=="sphere":geo.GetRadiusAttr().Set(radius)
        else:
            geo.GetRadiusAttr().Set(radius)
            geo.GetHeightAttr().Set(height)
        prims[label]=UsdGeom.XformCommonAPI(node)
    # Original frozen proxy remains in the immutable Take. Hide only its
    # DERIVED COPIES so that visible articulated geometry takes its place.
    for suffix in ("Geometry","Head"):
        original=stage.GetPrimAtPath(path+"/"+suffix)
        if original and original.IsA(UsdGeom.Imageable):
            UsdGeom.Imageable(original).MakeInvisible()
    return prims


def _proxy_positions(actor,pose):
    """Actor-local joint endpoints used for USD animated visible anatomy."""
    z=actor["height_scale"];w=actor["shoulder_width"]
    swing=pose["rotations"]
    def bend(a):return math.sin(a)
    left_leg=swing[10][0];right_leg=swing[12][0]
    left_arm=swing[6][0];right_arm=swing[8][0]
    pelvis=.55*z
    head=1.83*z
    shoulder=1.41*z
    def limb(center_x,top_z,angle,length):
        return (center_x,-math.sin(angle)*length*.35,
                top_z-math.cos(angle)*length*.5)
    result={
      "Torso":(0.,0.,1.12*z),
      "Head":(0.,0.,head),
      "LeftArm":limb(-.37*w,shoulder,left_arm,.5*z),
      "RightArm":limb(.37*w,shoulder,right_arm,.5*z),
      "LeftLeg":limb(-.20*w,pelvis,left_leg,.56*z),
      "RightLeg":limb(.20*w,pelvis,right_leg,.56*z),
      "LeftHand":limb(-.37*w,shoulder,left_arm,.96*z),
      "RightHand":limb(.37*w,shoulder,right_arm,.96*z),
      "Jaw":(0.,-.26*z,1.67*z-.12*z*pose["jaw"]),
      "LeftEye":(-.105*w,-.263*z,1.94*z),
      "RightEye":(.105*w,-.263*z,1.94*z),
      "Hair":(0.,0.,head+.29*z),
      "LeftBrow":(-.105*w,-.266*z,2.04*z+pose["smile"]*.03*z),
      "RightBrow":(.105*w,-.266*z,2.04*z+pose["smile"]*.03*z),
      "MouthLeft":(-.095*w,-.277*z,1.7*z+pose["smile"]*.06*z),
      "MouthRight":(.095*w,-.277*z,1.7*z+pose["smile"]*.06*z)}
    return result


def _write_proxy_key(prims,actor,pose,tick):
    from pxr import Gf,Usd
    t=Usd.TimeCode(float(tick))
    positions=_proxy_positions(actor,pose)
    for part,xyz in positions.items():
        prims[part].SetTranslate(Gf.Vec3d(*xyz),t)
    # Mouth aperture is tied only to ORIGINAL native PCM amplitude; eye
    # lid motion is a director-authored stylized anim, not a capture claim.
    jaw=pose["jaw"]
    prims["Jaw"].SetScale(Gf.Vec3f(1.,.8,1.+jaw*1.5),t)
    eyelid=max(.12,1.-pose["blink"]*.88)
    for eye in ("LeftEye","RightEye"):
        prims[eye].SetScale(Gf.Vec3f(1.,1.,eyelid),t)
    for mouth in ("MouthLeft","MouthRight"):
        prims[mouth].SetScale(Gf.Vec3f(
            1.+max(0.,pose["smile"])*.65,1.,1.),t)
    hair=actor["hair"]
    if hair=="bald":
        prims["Hair"].SetScale(Gf.Vec3f(.001,.001,.001),t)
    else:
        prims["Hair"].SetScale(Gf.Vec3f(
            1.1 if hair=="long" else 1.,
            1.1 if hair=="long" else 1.,
            {"short":.65,"medium":1.,"long":1.35}[hair]),t)


def author_actor_world(original_usd,source,approved,*,source_pcm,
                       voice_edits=None,edit_clip_id=None):
    """Returns exact new acting USD bytes and independently checked receipt."""
    if (type(original_usd) is not bytes or len(original_usd)>8*1024*1024
        or type(source_pcm) is not list):
        raise ValueError("The original actor film world cannot be opened")
    document=approved["performance"]
    if approved["sha256"]!=sha256(_canonical(document)).hexdigest():
        raise RuntimeError("Approved actor plan was changed")
    validate_actor_doc(document,document["take_id"],
                       source["take_sha256"],source)
    from pxr import Gf,Sdf,Usd,UsdGeom,UsdSkel,Vt
    layer=Sdf.Layer.CreateAnonymous("g09-actor-derived.usda")
    if (not layer.ImportFromString(original_usd.decode("utf8","strict")) or
        layer.subLayerPaths or layer.GetExternalReferences()):
        raise RuntimeError("Original USD actor world cannot be independently reopened")
    stage=Usd.Stage.Open(layer,Usd.Stage.LoadNone)
    root=stage.GetPrimAtPath("/World")
    if not root:raise RuntimeError("Original actor world has no Film World root")
    root.CreateAttribute("nvp:g09:actorOriginalUsdSha256",
                         Sdf.ValueTypeNames.String).Set(sha256(original_usd).hexdigest())
    root.CreateAttribute("nvp:g09:actorTakeSha256",
                         Sdf.ValueTypeNames.String).Set(source["take_sha256"])
    root.CreateAttribute("nvp:g09:actorApprovedRevision",
                         Sdf.ValueTypeNames.Int).Set(int(approved["revision"]))
    root.CreateAttribute("nvp:g09:actorApprovedSha256",
                         Sdf.ValueTypeNames.String).Set(approved["sha256"])
    stage.SetTimeCodesPerSecond(float(TICKS_PER_SECOND))
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(float(source["duration_tick"]))
    count=0;keys=0
    available={x["actor_id"]:x for x in source["stage_objects"]
               if x["role"]=="actor"}
    for actor in document["actors"]:
        original=available[actor["actor_id"]]
        path="/World/Objects/"+original["id"]
        if not stage.GetPrimAtPath(path):
            raise RuntimeError("Approved performer is not in the original USD")
        rig_path=path+"/G09ActorRig"
        skeleton_root=UsdSkel.Root.Define(stage,rig_path+"/SkeletonRoot")
        skeleton=UsdSkel.Skeleton.Define(stage,rig_path+"/SkeletonRoot/Skeleton")
        topology=UsdSkel.Topology(Vt.TokenArray(J))
        valid,reason=topology.Validate()
        if not valid:raise RuntimeError("USD ActorID skeleton topology invalid")
        skeleton.GetJointsAttr().Set(Vt.TokenArray(J))
        rest=Vt.Matrix4dArray()
        for offset in OFFSETS:
            mat=Gf.Matrix4d(1.)
            mat.SetTranslate(Gf.Vec3d(*offset))
            rest.append(mat)
        skeleton.GetRestTransformsAttr().Set(rest)
        skeleton.GetBindTransformsAttr().Set(rest)
        anim=UsdSkel.Animation.Define(stage,rig_path+"/SkeletonRoot/Animation")
        anim.GetJointsAttr().Set(Vt.TokenArray(J))
        bind=UsdSkel.BindingAPI.Apply(skeleton.GetPrim())
        if not bind.CreateAnimationSourceRel().SetTargets(
                [anim.GetPrim().GetPath()]):
            raise RuntimeError("USD actor animation could not bind")
        prims=_visible(stage,path,actor)
        events=_source_events(source,actor["actor_id"])
        voice=_voice_envelopes(source,actor,source_pcm)
        times=_times(source["duration_tick"],events,
                     [s for s in source["audio"]
                      if s["actor_id"]==actor["actor_id"]],
                     voice_edits,actor["expression_cues"])
        offsets=Vt.Vec3fArray([Gf.Vec3f(*x) for x in OFFSETS])
        scales=Vt.Vec3hArray([Gf.Vec3h(1.,1.,1.) for _ in J])
        for tick in times:
            pose=_local_pose(actor,events,tick,voice,voice_edits)
            anim.GetTranslationsAttr().Set(offsets,Usd.TimeCode(float(tick)))
            rotations=Vt.QuatfArray([_quat(x) for x in pose["rotations"]])
            anim.GetRotationsAttr().Set(rotations,Usd.TimeCode(float(tick)))
            _write_proxy_key(prims,actor,pose,tick)
        keys+=len(times);count+=1
    produced=layer.ExportToString().encode("utf8")
    if not 0<len(produced)<=MAX_USD_OUTPUT_BYTES:
        raise ValueError("Derived actor performance exceeds the native USD budget")
    second=Sdf.Layer.CreateAnonymous("g09-independent-actor-audit.usda")
    if (not second.ImportFromString(produced.decode("utf8")) or
        second.subLayerPaths or second.GetExternalReferences()):
        raise RuntimeError("Actor USD failed independent reopen")
    stage2=Usd.Stage.Open(second,Usd.Stage.LoadNone)
    origin=stage2.GetPrimAtPath("/World")
    if (not origin or origin.GetAttribute(
            "nvp:g09:actorOriginalUsdSha256").Get()!=
            sha256(original_usd).hexdigest()):
        raise RuntimeError("Actor performance lost original USD provenance")
    cache=UsdSkel.Cache()
    for actor in document["actors"]:
        path="/World/Objects/"+actor["object_id"]+"/G09ActorRig/SkeletonRoot/Skeleton"
        skeleton=UsdSkel.Skeleton(stage2.GetPrimAtPath(path))
        if not skeleton or not skeleton.GetPrim().IsA(UsdSkel.Skeleton):
            raise RuntimeError("Actor skeleton not present on independent reopen")
        if [str(x) for x in skeleton.GetJointsAttr().Get()]!=J:
            raise RuntimeError("Actor joint hierarchy changed during derivation")
        query=cache.GetSkelQuery(skeleton)
        if not query:raise RuntimeError("Real animated USD actor skeleton cannot resolve")
        sample=query.ComputeJointSkelTransforms(Usd.TimeCode(0))
        if sample is None or len(sample)!=len(J):
            raise RuntimeError("Animated USD actor joint transforms did not evaluate")
    from backend.nvp_g09_actor import _json as _ajson,_sha as _asha
    sound_digest=(_asha(_ajson(voice_edits).encode("utf8"))
                  if voice_edits is not None else None)
    return produced,{"format":"nvp.g09.actor_usd.v1",
        "edit_clip_id":edit_clip_id,
        "sound_edit_sha256":sound_digest,
        "take_sha256":source["take_sha256"],
        "actor_approved_sha256":approved["sha256"],
        "original_usd_sha256":sha256(original_usd).hexdigest(),
        "derived_usd_sha256":sha256(produced).hexdigest(),
        "actors":count,"joint_count_per_actor":len(J),
        "source_time_samples":keys,"actor_id_binding_verified":True,
        "original_audio_untouched":True,
        "mouth_motion_uses_original_pcm_rms":True,
        "phoneme_alignment_verified":False,
        "recorded_facial_capture":False,
        "final_human_surface_quality_verified":False}


def _canonical(doc):
    import json
    return json.dumps(doc,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf8")


class ActorFrameEvaluator:
    """Bounded native frame evaluator; original PCM parsed once per Take.

    Many film frames reuse the same frozen source. Decoding 48kHz PCM on
    every frame would waste memory/CPU and hurt preview frame pacing.
    """
    def __init__(self,source,approval):
        doc=approval["performance"]
        if approval["sha256"]!=sha256(_canonical(doc)).hexdigest():
            raise RuntimeError("Approved actor source digest changed")
        validate_actor_doc(doc,doc["take_id"],source["take_sha256"],source)
        self.cast={x["actor_id"]:x for x in doc["actors"]}
        self.events={id:_source_events(source,id) for id in self.cast}
        self.voice={id:_voice_envelopes(source,actor,source["audio"])
                    for id,actor in self.cast.items()}

    def sample(self,actor_id,tick,voice_edits=None):
        actor=self.cast.get(actor_id)
        if actor is None:
            raise KeyError("The selected ActorID was not in this original Take")
        pose=_local_pose(actor,self.events[actor_id],tick,
                         self.voice[actor_id],voice_edits)
        return _proxy_positions(actor,pose),pose


def sample_visible_actor(source,actor,original_audio,tick):
    """Single-shot native evaluation; use ActorFrameEvaluator for sequences."""
    events=_source_events(source,actor["actor_id"])
    voice=_voice_envelopes(source,actor,original_audio)
    pose=_local_pose(actor,events,tick,voice)
    return _proxy_positions(actor,pose),pose
