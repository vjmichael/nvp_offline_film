"""NVP FILM-01 — original 30-second THREE-SHOT source and real AV preview.

Original test narrative: "Last Light at Relay Nine — Signal Restored".
Author three true immutable OpenUSD Takes (one canonical scene with three
revisions), recorded native 48k PCM, source events, a three-node digital
slate and a two-cut source edit. Optional finite real CPU raster export:
720 authored 640x360 PNG frames + exact 30s original PCM WAV in an archive.

This is a CI/user-review *candidate*, not human creative approval,
photorealistic 2K master, movie-player file, DCI-ready DCP or a claim that
NVP's virtual gold fill/summer sun already illuminates the rendered pixels.
No FFmpeg, fake still-image video, auto-authorized source overwrite or
external command.
"""
from __future__ import annotations

import argparse
import base64
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import struct
import wave
from zipfile import ZipFile, ZIP_DEFLATED

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_assets import OpenUSDAssetRegistry
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_wo6_07f_rendered_av import rendered_source_window
from backend.nvp_virtual_light_fx import make_simple_virtual_fx,evaluate_virtual_light_fx

FORMAT="nvp.film01.real_original_30_second_source.v1"
RENDER_FORMAT="nvp.film01.source_raster_30_second_preview_receipt.v1"
DURATION=30
SHOT_SECONDS=10
FPS=24
FRAMES=DURATION*FPS
T=TICKS_PER_SECOND
SAMPLES_PER_FRAME=2000
TITLE="Last Light at Relay Nine: Signal Restored"
SLATE_SCENE="Relay Nine"
SOURCE_IDS=("RelayArrivalTake","RelayDiscoveryTake","RelayRekindleTake")
AUDIO_IDS=("RelayArrivalRoomTone","RelayDiscoveryRoomTone",
           "RelayRekindleRoomTone")
SHOTS=(
    ("Arrival","A craft returns to the dark relay station.",
     [-7,0,0],[-1.5,0,0],[-2.5,-1,0],[-2.5,-1,0],[0,0,18]),
    ("Discovery","An engineer reaches the silent antenna.",
     [-1.5,0,0],[-1.0,0,0],[-2.5,-1,0],[0.3,-1,0],[1,0,12]),
    ("Rekindle","The engineer reconnects the beacon and hears the signal.",
     [-1,0,0],[-1.0,0,0],[0.3,-1,0],[1.4,0.2,0],[0,0,10]),
)


def _audio_tone(kind,*,seconds=SHOT_SECONDS):
    """Original deterministic sound idea, deliberately not cinema-mastered."""
    freq=(73,109,173)[kind]
    chunk=[]
    for second in range(seconds):
        out=bytearray()
        for local in range(48000):
            pos=(second*48000+local)/48000
            fade=min(1.0,pos*3.0,(seconds-pos)*3.0)
            phase=2*math.pi*freq*pos
            # Subtle sound motion, not an imported stock song or artwork.
            envelope=(0.10+0.035*math.sin(2*math.pi*.38*pos))
            v=int(max(-32768,min(32767,32767*fade*envelope*(
                0.74*math.sin(phase)+0.26*math.sin(phase*1.5)))))
            out.extend(struct.pack("<h",v))
        chunk.append(bytes(out))
    return chunk


def _chirp():
    out=bytearray()
    for n in range(24000):
        t=n/48000
        freq=440+400*t
        amp=min(1,t*30,(.5-t)*10)
        value=int(12500*max(0,amp)*math.sin(2*math.pi*freq*t))
        out.extend(struct.pack("<h",value))
    return bytes(out)


def write_original_30s_source(destination,*,approve_test_only):
    """Fresh isolated original source, never silently mutates a director's film."""
    if approve_test_only is not True:
        raise PermissionError("Only test-authorized disposable NVP original source staging")
    root=Path(destination)
    if not root.is_absolute() or root.exists() or root.is_symlink():
        raise PermissionError("Create a fresh absolute original short workspace")
    root.mkdir(parents=True,mode=0o700)
    studio=Studio(root/"short.sqlite3")
    project=studio.create_project(
        TITLE,"Three original 10s shots; two cuts, original mono sound and 3D source")
    pid=project["id"]
    index=FilmIndex(studio)
    assets=OpenUSDAssetRegistry(index)
    geometry=(
        ("RelayCore","sphere",1.8,[0.25,0.42,0.75]),
        ("ServiceCraft","cube",1.0,[0.83,0.62,0.22]),
        ("Engineer","sphere",0.52,[0.70,0.80,0.9]),
    )
    bindings=[]
    for name,shape,size,color in geometry:
        assets.publish(
            pid,name,shape=shape,size_m=size,
            preview_material={
                "base_color_rgb":color,"roughness":0.57,
                "metallic":0.12})
        bindings.append({
            "path":"/World/"+name,"asset_id":name,
            "asset_revision":1})
    scene=OpenUSDSceneBridge(index)
    temporal=TemporalLedger(index)
    sound=RecordedSoundSources(index)
    take_host=OpenUSDTakeCapture(
        index,verify_creator_action=lambda event,scope:(
            event=="CI_ONLY_APPROVE_SOURCE_CAPTURE" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1" and
            scope["duration_tick"]==SHOT_SECONDS*T))
    take_reports=[]
    for shot,(name,description,craft0,craft1,actor0,actor1,camera) in enumerate(SHOTS):
        poses=[
            {"path":"/World/RelayCore","role":"prop","position":[0,0,0]},
            {"path":"/World/ServiceCraft","role":"actor","position":craft0},
            {"path":"/World/Engineer","role":"actor","position":actor0},
            {"path":"/World/Camera","role":"camera","position":camera},
            {"path":"/World/PracticalLight","role":"light",
             "position":([2,3,5] if shot<2 else [0.5,2,5])},
        ]
        curves=[
            {"path":"/World/ServiceCraft","samples":[
                {"tick":0,"position":craft0},
                {"tick":SHOT_SECONDS*T,"position":craft1}]},
            {"path":"/World/Engineer","samples":[
                {"tick":0,"position":actor0},
                {"tick":SHOT_SECONDS*T,"position":actor1}]},
        ]
        if shot==2:
            # A timed move of a real light exists separately from future
            # virtual gold-fill shader and film-clock strobe FX work.
            curves.append({"path":"/World/PracticalLight","samples":[
                {"tick":0,"position":[0.5,2,5]},
                {"tick":SHOT_SECONDS*T,"position":[2,2,5]}]})
        scene_revision=scene.publish(
            pid,"Relay30Scene",prims=poses,curves=curves,
            native_schemas=True,asset_bindings=bindings,
            expected_revision=shot)
        pcm=sound.publish(pid,AUDIO_IDS[shot],_audio_tone(shot))
        events=[
            {"event_id":"Camera"+name,"event_kind":"camera",
             "subject_id":"DirectorCamera","start_tick":0,
             "end_tick":SHOT_SECONDS*T,
             "source_id":"Relay30Scene","source_revision":shot+1,
             "payload":{"usd_prim_path":"/World/Camera",
                        "original_director_shot":name}},
            {"event_id":"Sound"+name,"event_kind":"sound",
             "subject_id":"RelayCore","start_tick":0,
             "end_tick":SHOT_SECONDS*T,
             "source_id":AUDIO_IDS[shot],"source_revision":1,
             "payload":{"gain":0.8,"original_recorded_pcm":True,
                        "mastered_sound":False}},
            {"event_id":"Movement"+name,"event_kind":"action",
             "subject_id":"Engineer","start_tick":0,
             "end_tick":SHOT_SECONDS*T,
             "source_id":"Relay30Scene","source_revision":shot+1,
             "payload":{"usd_prim_path":"/World/Engineer"}},
        ]
        if shot==2:
            beep=sound.publish(pid,"RelaySignalChirp",[_chirp()])
            events.append({
                "event_id":"BeaconSignalRestored",
                "event_kind":"sound","subject_id":"RelayCore",
                "start_tick":6*T,"end_tick":6*T+T//2,
                "source_id":"RelaySignalChirp","source_revision":1,
                "payload":{"gain":0.9,
                           "source_linked_action":"MovementRekindle",
                           "original_event":True}})
        timeline=temporal.publish(
            pid,"Relay30Timeline"+name,events,
            duration_tick=SHOT_SECONDS*T)
        take=take_host.freeze(
            pid,SOURCE_IDS[shot],scene_id="Relay30Scene",
            scene_revision=shot+1,
            timeline_id="Relay30Timeline"+name,
            timeline_revision=1,sample_ticks=[0,5*T,9*T],
            creator_event="CI_ONLY_APPROVE_SOURCE_CAPTURE")
        if take_host.verify_take(pid,SOURCE_IDS[shot])[
                "status"]!="VERIFIED_FROZEN_DATA_TAKE":
            raise RuntimeError("Original source Take verification failed")
        take_reports.append({
            "scene_revision":shot+1,"scene_sha256":scene_revision["document_sha256"],
            "take_id":SOURCE_IDS[shot],
            "take_sha256":take["document_sha256"],
            "timeline_id":"Relay30Timeline"+name,
            "timeline_sha256":timeline["document_sha256"],
            "sound_id":AUDIO_IDS[shot],
            "sound_sha256":pcm["document_sha256"],
            "shot":name,"action":description,
            "start_output_frame":shot*SHOT_SECONDS*FPS,
            "end_output_frame":(shot+1)*SHOT_SECONDS*FPS,
        })
    slate=DigitalSlateBranches(index,verify_editor_action=lambda *_:False)
    nodes=[]
    segments=[]
    for i,item in enumerate(take_reports):
        branch_id=f"Relay30Branch{i}"
        nodes.append({
            "branch_id":branch_id,"kind":"performance",
            "parent_id":None if i==0 else "Relay30Branch0",
            "fork_tick":None if i==0 else (i*T),
            "group_id":f"Cut{i}","primary":True,
            "take_id":item["take_id"],
            "source_start_tick":0,"source_end_tick":SHOT_SECONDS*T,
            "shot_id":None,"shot_revision":None,
            "slate":{
                "scene":SLATE_SCENE,"setup":f"Setup{i}",
                "shot":item["shot"],"camera":"OriginalCamera",
                "take_number":i+1,"wild":False,
                "script_revision":"1","notes":item["action"],
            },
        })
        segments.append({
            "segment_id":f"Relay30Cut{i}",
            "branch_id":branch_id,
            "source_in_tick":0,"source_out_tick":SHOT_SECONDS*T,
        })
    graph=slate.publish_graph(
        pid,"Relay30Slate",scene_id="Relay30Scene",
        scene_label=SLATE_SCENE,nodes=nodes)
    assembly=SlateSequenceAssembly(
        slate,verify_editor_action=lambda event,scope:(
            event=="CI_ONLY_COMMIT_EDITOR_SOURCE" and
            scope["operation"]=="nvp.slate.commit_assembled_edit.v1" and
            scope["segment_count"]==3 and
            scope["duration_tick"]==DURATION*T and
            scope["final_render_approval"] is False))
    edit=assembly.commit(
        pid,"Relay30Edit",graph_id="Relay30Slate",
        graph_revision=1,segments=segments,
        editor_event="CI_ONLY_COMMIT_EDITOR_SOURCE")
    reopened=assembly.open_edit(pid,"Relay30Edit",1)
    if (reopened["document_sha256"]!=edit["document_sha256"] or
            reopened["data"]["duration_tick"]!=DURATION*T or
            len(reopened["data"]["segments"])!=3):
        raise RuntimeError("Original 30s three-shot editorial proof mismatched")
    sun=make_simple_virtual_fx(
        "locked_summer_3pm_sun","/World/RelayCore",
        fx_id="RelaySummer3PM",intensity=1.15)
    gold=make_simple_virtual_fx(
        "gold_fill","/World/Engineer",
        fx_id="RelayVirtualGoldFill",intensity=0.27)
    # Artistic FX are separate authored design intentions: current 07F
    # CPU raster does NOT apply those to the actual PNG.
    planned_fx=[
        evaluate_virtual_light_fx(sun,0,final_render=True),
        evaluate_virtual_light_fx(gold,24*T,final_render=True),
    ]
    report={
        "format":FORMAT,
        "status":"SOURCE_AUTHORED_NOT_A_FINISHED_MOVIE",
        "title":TITLE,"project_id":pid,
        "duration_seconds":DURATION,"fps":FPS,
        "target_frames":FRAMES,
        "source_scene_id":"Relay30Scene",
        "slate_id":"Relay30Slate","slate_sha256":graph["document_sha256"],
        "edit_id":"Relay30Edit","edit_sha256":edit["document_sha256"],
        "shots":take_reports,"shot_count":3,"hard_cuts":2,
        "original_sound_in_each_take":True,
        "timed_beacon_signal_event":True,
        "virtual_artistic_lighting_proposals":planned_fx,
        "virtual_artistic_lighting_rendered_in_pixels":False,
        "source_takes_frozen_and_verified":True,
        "rendered_picture_frames":0,
        "finished_mixed_master":False,
        "photorealistic_story_quality_approved":False,
        "full_color_managed_2k_dci_delivery":False,
        "creator_release_approved":False,
        "synthetic_fixture_is_not_director_authorization":True,
    }
    (root/"original-source-report.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf8")
    return report


def render_original_30s_review(source_root,output_zip,*,max_frames=FRAMES):
    """Actual first-party OpenUSD CPU PNG + sample-aligned mono PCM export.

    Intended for a throwaway CI source fixture, not user-approved DCP.
    A partial export is never delivered as a 30-second finished film.
    """
    root=Path(source_root)
    out=Path(output_zip)
    if (not root.is_absolute() or not out.is_absolute() or
            out.exists() or out.is_symlink() or
            type(max_frames) is not int or not 1<=max_frames<=FRAMES):
        raise ValueError("Fresh absolute export target and 1..720 frames required")
    report=json.loads((root/"original-source-report.json").read_text())
    if (report["format"]!=FORMAT or report["target_frames"]!=FRAMES or
            not report["source_takes_frozen_and_verified"]):
        raise PermissionError("No intact original 30s authored source")
    studio=Studio(root/"short.sqlite3")
    index=FilmIndex(studio)
    pid=report["project_id"]
    edit=index.read_revision(pid,report["edit_id"],1)
    if edit["document_sha256"]!=report["edit_sha256"]:
        raise PermissionError("Original 30s edit SHA changed")
    rows=[]
    all_samples=bytearray()
    # Memory is bounded to one native six-frame render window and the
    # half-minute PCM buffer, not a flattened RGB frame sequence.
    with ZipFile(out,"x",compression=ZIP_DEFLATED,compresslevel=5) as bundle:
        for start in range(0,max_frames,6):
            count=min(6,max_frames-start)
            packet=rendered_source_window(
                index,pid,report["edit_id"],1,report["edit_sha256"],
                start,count,camera_path="/World/Camera")
            if (packet["count"]!=count or
                    packet["actual_audio_sample_count"]!=2000*count or
                    packet["source_modified"] is not False):
                raise RuntimeError("Actual picture/PCM render window mismatch")
            for image in packet["images"]:
                n=image["output_frame_zero"]
                raw=base64.b64decode(image["frame_image_data_url"].split(",",1)[1],
                                    validate=True)
                if sha256(raw).hexdigest()!=image["frame_png_sha256"]:
                    raise RuntimeError("Native original source PNG SHA mismatch")
                name=f"preview_frames/frame_{n:04d}.png"
                bundle.writestr(name,raw)
                rows.append({
                    "frame_zero":n,"frame_png_sha256":image["frame_png_sha256"],
                    "original_source_take_sha256":image["source_take_sha256"],
                    "source_segment_id":image["source_segment_id"],
                    "source_film_tick":image["original_source_tick"],
                    "preview_resolution":"640x360_not_DCI",
                })
            wav=base64.b64decode(
                packet["source_audio_wav_data_url"].split(",",1)[1],validate=True)
            if sha256(wav).hexdigest()!=packet["source_audio_wav_sha256"]:
                raise RuntimeError("Native original PCM WAV SHA changed")
            with wave.open(BytesIO(wav),"rb") as audio:
                if (audio.getframerate()!=48000 or
                        audio.getsampwidth()!=2 or audio.getnchannels()!=1 or
                        audio.getnframes()!=count*SAMPLES_PER_FRAME):
                    raise RuntimeError("Original soundtrack timing mismatch")
                all_samples.extend(audio.readframes(count*SAMPLES_PER_FRAME))
        complete=max_frames==FRAMES
        if len(rows)!=max_frames or len(all_samples)!=max_frames*2000*2:
            raise RuntimeError("Incomplete or missing original film frames/samples")
        wav_buffer=BytesIO()
        with wave.open(wav_buffer,"wb") as write:
            write.setnchannels(1)
            write.setsampwidth(2)
            write.setframerate(48000)
            write.writeframes(bytes(all_samples))
        complete_wav=wav_buffer.getvalue()
        bundle.writestr("audio/original_source_review_48k_mono.wav",complete_wav)
        proof={
            "format":RENDER_FORMAT,"source_format":FORMAT,
            "edit_sha256":report["edit_sha256"],
            "source_title":TITLE,"frames_rendered_from_usd":len(rows),
            "intended_30s_output_frames":FRAMES,
            "film_duration_seconds":len(rows)/FPS,
            "all_720_frames_really_rendered":complete,
            "fully_rendered_short_is_creatively_approved":False,
            "exact_pcm_samples":len(all_samples)//2,
            "audio_wav_sha256":sha256(complete_wav).hexdigest(),
            "frame_receipts":rows,
            "native_raster_preview_only":True,
            "source_3d_geometry_not_photorealism_verified":True,
            "virtual_gold_and_sun_fx_applied_to_render":False,
            "playable_muxed_movie_created":False,
            "dci_master_or_dcp_created":False,
            "independent_visual_review_needed":True,
        }
        bundle.writestr(
            "original_30s_preview_receipt.json",
            json.dumps(proof,sort_keys=True,indent=2)+"\n")
        bundle.writestr(
            "README.txt",
            "NVP ORIGINAL SOURCE PREVIEW\n"
            "These are genuinely rendered 640x360 OpenUSD PNGs and matching "
            "original 48 kHz mono WAV source samples. The archive is NOT a "
            "playable synchronized movie, a photorealistic render acceptance, "
            "2K theatrical master or cinema-compliant DCP.\n"
            "Open the PNG sequence in an appropriate video editor and import "
            "the WAV at 24fps/48kHz for manual evaluation.\n")
    return {
        "format":RENDER_FORMAT,
        "zip_path":str(out),"complete_720_frame_source_preview":complete,
        "rendered_frame_count":len(rows),"audio_sample_count":len(all_samples)//2,
        "director_quality_accepted":False,"dci_delivery_accepted":False,
    }


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root",type=Path,required=True)
    cli.add_argument("--render-review-zip",type=Path)
    cli.add_argument("--max-frames",type=int,default=FRAMES)
    cli.add_argument("--consent",required=True)
    args=cli.parse_args()
    if args.consent!="I_APPROVE_DISPOSABLE_ORIGINAL_30S_CI_SOURCE":
        cli.error("Only the opt-in disposable CI source workspace is supported")
    source=write_original_30s_source(
        args.root.resolve(),approve_test_only=True)
    if args.render_review_zip:
        result=render_original_30s_review(
            args.root.resolve(),args.render_review_zip.resolve(),
            max_frames=args.max_frames)
    else:
        result={"status":source["status"],"target_frames":source["target_frames"],
                "source_project_id":source["project_id"]}
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
