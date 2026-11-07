"""Original 30-minute NVP DATA-FIRST movie pilot source authoring.

Creates an original experimental narrative sequence, "Last Light at Relay
Nine", with actual native OpenUSD geometry, exact-time character/camera
movement, 60 real authored cuts, six original recorded PCM sound motifs,
a combined temporal event ledger, and a frozen 30m Digital Take stored
in real FilmIndex/SQLite. Source/shot/audio files are not placeholders;
they are authored original data and may be reopened or re-shot.

This is SOURCE PRODUCTION proof, NOT 43,200 rendered cinema frames, a
flattened DCP, a director-reviewed film, calibrated XYZ12 or finished
30-minute playback. No CI-generated story passes human creative approval.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import math
import os
import struct

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_wo4_resource_budget import plan_feature

FORMAT="nvp.wo5.original_30minute_source_pilot.v1"
FPS=24
DURATION=30*60
FRAMES=FPS*DURATION
SHOT_SECONDS=30
REEL_SECONDS=5*60
T=TICKS_PER_SECOND
TAGS=(
    ("Arrival","A repair crew approaches a dark relay station."),
    ("Discovery","The crew learns why its beacon stopped transmitting."),
    ("Repair","A lone engineer attempts to restore the broken array."),
    ("Blackout","The relay loses power as the signal begins to return."),
    ("Reconnection","Backup power illuminates the communications array."),
    ("Departure","The crew sends the final message and leaves the station."),
)

def _keys(points):
    return [{"tick":int(s*T),"position":list(p)} for s,p in points]

def _motif(index):
    """One-second original 48kHz mono PCM16 with act-specific notes.

    An authored temporary source motif, not a cinematic final mix.
    """
    freq=(110,164,220,147,247,196)[index]
    out=bytearray()
    for n in range(48000):
        t=n/48000
        amplitude=(0.16+0.045*math.sin(2*math.pi*(index+1)*0.3*t))
        ramp=min(1,t*10,(1-t)*10)
        sample=int(32767*amplitude*max(0,ramp)*
                   (0.7*math.sin(2*math.pi*freq*t)+
                    0.3*math.sin(2*math.pi*(freq/2)*t)))
        out.extend(struct.pack("<h",sample))
    return bytes(out)

def write_original_30minute_source(destination,*,approve_test_only):
    """Author the source once; do not overwrite a prior director workspace."""
    if approve_test_only is not True:
        raise PermissionError(
            "This function is a CI source-only authoring experiment, not a director grant")
    root=Path(destination)
    if not root.is_absolute() or root.exists() or root.is_symlink():
        raise PermissionError("Fresh trusted original-pilot working root required")
    root.mkdir(mode=0o700,parents=True)
    studio=Studio(root/"pilot.sqlite3")
    project=studio.create_project("Last Light at Relay Nine",
                                  "Six-act original 30-minute 3D source pilot")
    pid=project["id"]
    index=FilmIndex(studio)
    assets=OpenUSDAssetRegistry(index)
    palette=[
        ("RelayCore","sphere",2.8,[.15,.3,.75]),
        ("ServiceCraft","cube",1.5,[.72,.56,.15]),
        ("Engineer","sphere",.4,[.65,.79,.85]),
    ]
    bound=[]
    for name,shape,size,color in palette:
        assets.publish(pid,name,shape=shape,size_m=size,
            preview_material={"base_color_rgb":color,"roughness":.55,
                              "metallic":.15})
        bound.append({"path":"/World/"+name,"asset_id":name,
                      "asset_revision":1})
    prims=[
        {"path":"/World/RelayCore","role":"prop","position":[0,0,0]},
        {"path":"/World/ServiceCraft","role":"actor","position":[-14,0,0]},
        {"path":"/World/Engineer","role":"actor","position":[-9,-1,0]},
        {"path":"/World/WideCamera","role":"camera","position":[0,-26,12]},
        {"path":"/World/CloseCamera","role":"camera","position":[2,-12,3]},
        {"path":"/World/TravelCamera","role":"camera","position":[-14,-10,6]},
        {"path":"/World/RelayKey","role":"light","position":[2,1,7]},
    ]
    curves=[
        {"path":"/World/ServiceCraft","samples":_keys([
            (0,[-14,0,0]),(300,[-10,0,0]),(600,[-6,-2,0]),
            (900,[-4,-3,0]),(1200,[0,-3,0]),(1500,[6,-1,0]),
            (1800,[17,0,0])])},
        {"path":"/World/Engineer","samples":_keys([
            (0,[-9,-1,0]),(300,[-5,-1,0]),(600,[-2,-1,0]),
            (900,[-1,-.4,2]),(1200,[0,0,3]),
            (1500,[-1,-2,0]),(1800,[3,-4,0])])},
        {"path":"/World/TravelCamera","samples":_keys([
            (0,[-14,-10,6]),(450,[-8,-9,5]),
            (900,[-4,-8,4]),(1350,[2,-9,4]),(1800,[10,-9,6])])},
        {"path":"/World/CloseCamera","samples":_keys([
            (0,[2,-12,3]),(600,[0,-10,3]),
            (1200,[-2,-8,3]),(1800,[0,-10,3])])},
    ]
    scene=OpenUSDSceneBridge(index)
    authored=scene.publish(
        pid,"RelayNineScene",prims=prims,curves=curves,
        native_schemas=True,asset_bindings=bound)
    shots=[]
    camera_paths=["/World/WideCamera","/World/TravelCamera",
                  "/World/CloseCamera"]
    for i in range(DURATION//SHOT_SECONDS):
        start=i*SHOT_SECONDS*T
        end=(i+1)*SHOT_SECONDS*T
        shots.append({
            "shot_id":f"RelayShot{i:03d}",
            "camera_path":camera_paths[(i+i//10)%3],
            "start_tick":str(start),"end_tick":str(end),
            "pattern":("tracking" if i%3==1 else
                       "reaction" if i%3==2 else "master"),
        })
    shot_doc=ExactTimeShotSequence(index).publish(
        pid,"RelayNineShotEdit",
        scene_id="RelayNineScene",scene_revision=1,
        duration_tick=str(DURATION*T),shots=shots)
    audio=RecordedSoundSources(index)
    events=[]
    audio_sources=[]
    for i,(name,description) in enumerate(TAGS):
        original_pcm=_motif(i)
        sid=f"RelayAct{i+1}Tone"
        tone=audio.publish(pid,sid,[original_pcm])
        audio_sources.append({
            "act":name,"source_id":sid,"original_pcm_sha256":
                sha256(original_pcm).hexdigest(),
            "source_document_sha256":tone["document_sha256"],
            "intro_first_tick":(i*REEL_SECONDS+15)*T,
        })
        events.append({
            "event_id":f"ToneAct{i+1}",
            "event_kind":"sound","subject_id":"RelayCore",
            "start_tick":(i*REEL_SECONDS+15)*T,
            "end_tick":(i*REEL_SECONDS+16)*T,
            "source_id":sid,"source_revision":1,
            "payload":{"usd_prim_path":"/World/RelayCore",
                       "source_sample_rate":48000,
                       "original_mono_pcm":True,
                       "cinema_master_created":False},
        })
    for shot in shots:
        events.append({
            "event_id":shot["shot_id"],
            "event_kind":"camera","subject_id":"DirectorCamera",
            "start_tick":int(shot["start_tick"]),
            "end_tick":int(shot["end_tick"]),
            "source_id":"RelayNineScene","source_revision":1,
            "payload":{"usd_prim_path":shot["camera_path"],
                       "shot_id":shot["shot_id"],
                       "observation_pattern":shot["pattern"]},
        })
    temporal=TemporalLedger(index)
    temporal.publish(
        pid,"RelayNineOriginalActions",events,
        duration_tick=DURATION*T)
    freezer=OpenUSDTakeCapture(
        index,verify_creator_action=lambda event,scope:
            event=="CI_ORIGINAL_SOURCE_AUTHORING_ONLY" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1" and
            scope["duration_tick"]==DURATION*T)
    take=freezer.freeze(
        pid,"RelayNineOriginalTake",
        scene_id="RelayNineScene",scene_revision=1,
        timeline_id="RelayNineOriginalActions",timeline_revision=1,
        sample_ticks=[i*150*T for i in range(12)],
        creator_event="CI_ORIGINAL_SOURCE_AUTHORING_ONLY")
    verified=freezer.verify_take(pid,"RelayNineOriginalTake")
    if verified["status"]!="VERIFIED_FROZEN_DATA_TAKE":
        raise RuntimeError("Real original scene+sound Take did not reopen")
    plan=plan_feature(frames=FRAMES,profile="2K_FLAT_24",
                      channels=2,max_reel_frames=7200)
    if plan["reel_count"]!=6 or any(
            reel["frame_count"]!=7200 for reel in plan["reels"]):
        raise RuntimeError("Original 30m six-reel 24fps Film Time plan changed")
    # A real director can now edit the source scene revision and freeze a
    # NEW Take; the original scene, shot edit, sound and Take stay immutable.
    report={
        "format":FORMAT,
        "status":"ORIGINAL_30_MINUTE_NATIVE_SOURCE_AUTHORED_NOT_RENDERED",
        "title":project["title"],"project_id":pid,
        "source_scene_id":"RelayNineScene",
        "source_scene_document_sha256":authored["document_sha256"],
        "take_id":"RelayNineOriginalTake",
        "take_document_sha256":take["document_sha256"],
        "source_take_frozen_verified":True,
        "shot_sequence_id":"RelayNineShotEdit",
        "shot_count":len(shots),
        "all_shots_exactly_cover_30_minutes":True,
        "act_count":len(TAGS),
        "acts":[{"name":name,"premise":description,
                 "first_tick":i*REEL_SECONDS*T}
                for i,(name,description) in enumerate(TAGS)],
        "original_audio_sources":audio_sources,
        "duration_ticks":DURATION*T,"duration_seconds":DURATION,
        "target_frames":FRAMES,
        "reel_plan":plan["reels"],
        "production_candidate_complete":False,
        "real_43200_dci_xyz12_frames_rendered":False,
        "real_dcp_picture_and_sound_published":False,
        "director_creative_reviewed":False,
        "cinema_release_approved":False,
        "procedural_source_authoring_is_not_human_approval":True,
        "ffmpeg_used":False,
    }
    # Report is separate from creator-approved FilmIndex evidence.
    serialized=json.dumps(report,sort_keys=True,indent=2)+"\n"
    with (root/"source-evidence.json").open("x",encoding="utf8") as out:
        out.write(serialized)
        out.flush();os.fsync(out.fileno())
    return report

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--output-root",type=Path,required=True)
    args=ap.parse_args()
    report=write_original_30minute_source(
        args.output_root.resolve(),approve_test_only=True)
    print(json.dumps({
        "status":report["status"],"frames":report["target_frames"],
        "shots":report["shot_count"],
        "take_document_sha256":report["take_document_sha256"],
        "director_creative_reviewed":False},
        sort_keys=True),flush=True)
