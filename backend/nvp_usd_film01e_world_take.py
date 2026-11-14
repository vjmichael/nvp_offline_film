"""USD-FILM-01E: immutable world-composed Digital Take from EXISTING source Takes.

The original OpenUSDTakeCapture (scene+TemporalLedger), FilmIndex world,
01D camera-shot source, Production Bible ActorIDs/VoiceIDs, original PCM,
and director-selected dialogue are authoritative. This source-level world
Take composes, never replaces, the original verified Takes.

An original cast actor in any REQUIRED film set needs an exact frozen source
Take and unambiguous Production Bible link. A VoiceID is historical creative
casting metadata; it is NOT automatically audible dialogue. Actual voiced
lines require an independently verified ActorDialogueManager route.

NO renderer, invented audio, new actor identity, generated performance,
legal-permission flow, separate scene parser, or automatic film master.
01F must connect this new take format to actual native render/picture/audio.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math

from backend.nvp_film_index import FilmIndex, _id, _require_pid, _sha
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_openusd_take import OpenUSDTakeCapture, FORMAT as SCENE_TAKE_FORMAT
from backend.nvp_openusd_scene import MAX_USD_EXACT_TICK, _usd
from backend.nvp_usd_film01_world import OpenUSDWorldComposer
from backend.nvp_usd_film01d_shot_working_set import (
    FilmWorldShotPlanner, _camera_native,
)
from backend.nvp_production_bible_actors import ProductionBibleActors
from backend.nvp_film03_voice_identity import ProductionBibleVoiceIdentity
from backend.nvp_film03_dialogue_manager import ActorDialogueManager, REQUIRED as ROUTE_FIELDS
from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE

FORMAT = "nvp.usd_film01e.immutable_composed_world_take.v1"
CHECKPOINT_FORMAT = "nvp.usd_film01e.original_performance_checkpoint.v1"
MAX_REQUIRED_SETS = 8
MAX_ORIGINAL_AUDIO_EVENTS = 256
MAX_DIALOGUE_ROUTES = 32
AUDIO_TICKS_PER_SAMPLE = TICKS_PER_SECOND // SAMPLE_RATE
MAX_AUDIO_CHUNKS_PER_SOURCE = 512
MAX_AUDIO_SOURCE_BYTES = 256 * 1024 * 1024


def _verify_original_pcm_chunks(index,pid,source_record):
    """Read and rehash EVERY original 48k PCM chunk, not just first sample.

    Original PCM may be large. Process one previously registered <=1MiB
    FilmIndex blob at a time without synthesizing, stretching or mixing.
    """
    document=source_record["data"]
    parts=document.get("chunks")
    if (type(parts) is not list or
        not 1<=len(parts)<=MAX_AUDIO_CHUNKS_PER_SOURCE):
        raise RuntimeError("Original audio source chunk inventory is not bounded")
    offset=0
    total=0
    for part in parts:
        if type(part) is not dict or set(part)!={
            "first_sample","sample_count","blob_sha256","byte_count"
        }:
            raise RuntimeError("Original audio chunk metadata changed")
        _sha(part["blob_sha256"])
        if (type(part["first_sample"]) is not int or
            part["first_sample"]!=offset or
            type(part["sample_count"]) is not int or
            part["sample_count"]<1 or
            type(part["byte_count"]) is not int or
            part["byte_count"]!=part["sample_count"]*2 or
            part["byte_count"] > 1024*1024):
            raise RuntimeError("Original audio PCM is noncontiguous or altered")
        total+=part["byte_count"]
        if total>MAX_AUDIO_SOURCE_BYTES:
            raise ValueError("Original audio source exceeds bounded Take audit")
        block=index.get_blob(pid,part["blob_sha256"])
        if (len(block)!=part["byte_count"] or
            sha256(block).hexdigest()!=part["blob_sha256"]):
            raise RuntimeError("Original PCM chunk checksum is invalid")
        offset+=part["sample_count"]
    if offset!=document["sample_count"]:
        raise RuntimeError("Original PCM sample count changed")
    return {"samples":offset,"bytes_verified":total,"chunks_verified":len(parts)}


def _canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",",":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(x):
    return sha256(_canonical(x)).hexdigest()


def _capture(index):
    return OpenUSDTakeCapture(index,verify_creator_action=lambda *_:False)


def _actor_and_take_sources(index, pid, shot, scene_takes, *,
                            historic_cast=None):
    """Verify REQUIRED original scene Takes; preserve historical cast on replay."""
    if (type(scene_takes) is not list or
        not 1 <= len(scene_takes) <= MAX_REQUIRED_SETS):
        raise ValueError("One to eight exact original source Take bindings required")
    requested = {}
    for item in scene_takes:
        if type(item) is not dict or set(item) != {
            "set","take_id","take_sha256"
        }:
            raise ValueError("World source Take entry must have exact ID and SHA")
        set_name = item["set"]
        _id(item["take_id"], "original source Digital Take")
        _sha(item["take_sha256"])
        if type(set_name) is not str or set_name in requested:
            raise ValueError("Repeated or unrecognized source Take set")
        requested[set_name] = item
    world = index.read_revision(pid, shot["world_id"],shot["world_revision"])
    wdoc = world["data"]
    original_sets = {item["name"]:item for item in wdoc["sets"]}
    required = shot["director_required_sets"]
    if (set(requested) - set(required) or
        shot["camera_set"] not in requested or
        len({x["take_id"] for x in requested.values()}) != len(requested)):
        # A single original actor scene Take cannot be silently duplicated
        # as two independently performing world-set instances.
        raise PermissionError("Source Take must be camera-set based, not a foreign film set")
    verified = []
    cast_members = []
    audio_sources = []
    historical={(x["set"],x["original_actor_prim"]):x
                for x in (historic_cast or [])}
    if historic_cast is not None and (
        type(historic_cast) is not list or
        len(historical) != len(historic_cast)):
        raise RuntimeError("Historical original actor casting is ambiguous")
    registry = ProductionBibleActors(index.studio)
    voice_bible = ProductionBibleVoiceIdentity(
        index,verify_creator_action=lambda *_:False)
    take_host = _capture(index)
    source_time = TemporalLedger(index)
    originals = RecordedSoundSources(index)
    for set_name in required:
        original_set = original_sets[set_name]
        scene = index.read_revision(
            pid,original_set["scene_id"],original_set["scene_revision"])
        if (scene["kind"] != "scene" or
            scene["document_sha256"] != original_set["scene_sha256"]):
            raise PermissionError("Original set's scene SHA no longer matches saved world")
        roles = scene["data"]["prim_roles"]
        has_actors = any(role=="actor" for role in roles.values())
        if set_name not in requested:
            if has_actors:
                raise PermissionError(
                    "Director-required scene with actors needs a frozen original Take")
            continue
        inp = requested[set_name]
        frozen = index.read_revision(pid,inp["take_id"],1)
        fdoc = frozen["data"]
        if (frozen["kind"]!="take" or
            fdoc.get("format")!=SCENE_TAKE_FORMAT or
            fdoc.get("frozen") is not True or
            frozen["document_sha256"] != inp["take_sha256"] or
            fdoc["scene_id"] != original_set["scene_id"] or
            fdoc["scene_revision"] != original_set["scene_revision"] or
            fdoc["scene_document_sha256"] != scene["document_sha256"] or
            fdoc["duration_tick"] <= max(shot["camera_sample_ticks"])):
            raise PermissionError("Original source Take and selected camera time differ")
        if take_host.verify_take(pid,inp["take_id"])[
                "take_document_sha256"] != frozen["document_sha256"]:
            raise RuntimeError("Original authored scene Take cannot be independently verified")
        cast = (registry.require_complete_cast(pid,inp["take_id"])
                if has_actors and historic_cast is None else None)
        for prim, role in sorted(roles.items()):
            if role!="actor":
                continue
            if historic_cast is None:
                if cast is None or prim not in cast["actor_id_by_prim"]:
                    raise PermissionError("Original actor lacks StoryBible source casting")
                aid = cast["actor_id_by_prim"][prim]
                voice = voice_bible.current(pid,aid)["current"]
                identity = {
                    "set":set_name, "original_actor_prim":prim,
                    "composed_actor_prim":"/World/Sets/"+set_name+
                                          prim[len("/World"):],
                    "actor_id":aid,"source_take_id":inp["take_id"],
                    "source_take_sha256":frozen["document_sha256"],
                    "voice_id":voice["voice_id"] if voice else None,
                    "voice_cast_revision":voice["cast_revision"] if voice else None,
                    "voice_reference_sha256":(
                        voice["reference_audio_sha256"] if voice else None),
                    "voice_not_synthesized_from_identity":True,
                }
            else:
                identity = historical.get((set_name,prim))
                if (identity is None or
                    identity["source_take_id"]!=inp["take_id"] or
                    identity["source_take_sha256"]!=frozen["document_sha256"] or
                    identity["composed_actor_prim"]!=
                    "/World/Sets/"+set_name+prim[len("/World"):]):
                    raise PermissionError("Original historical ActorID source has changed")
                aid = identity["actor_id"]
                # StoryBible identities are lowercase 32-hex UUIDs, not
                # FilmIndex object IDs (which must begin with a letter).
                # Revalidate their native exact format without broadening
                # user-authored FilmIndex object identifiers.
                if (type(aid) is not str or len(aid)!=32 or
                    any(c not in "0123456789abcdef" for c in aid)):
                    raise ValueError("Invalid original StoryBible actor identifier")
                # Cast links may subsequently be retired/recast. Read exact
                # historical source link evidence, NOT just current cast.
                with index.studio._connection() as db:
                    linked = db.execute(
                        "SELECT 1 FROM nvp_bible_actor_links WHERE "
                        "project_id=? AND actor_id=? AND role='actor_prim' "
                        "AND source_family='filmindex' AND target_id=? "
                        "AND target_revision=1 AND actor_prim_path=? "
                        "AND source_sha256=? AND status='active' LIMIT 1",
                        (pid,aid,inp["take_id"],prim,
                         frozen["document_sha256"])).fetchone()
                if linked is None:
                    raise PermissionError("Historical ActorID source-cast link missing")
                if identity["voice_id"] is not None:
                    with index.studio._connection() as db:
                        old_voice = db.execute(
                            "SELECT reference_audio_sha256 FROM "
                            "nvp_bible_voice_casts WHERE project_id=? "
                            "AND actor_id=? AND voice_id=? AND cast_revision=?",
                            (pid,aid,identity["voice_id"],
                             identity["voice_cast_revision"])).fetchone()
                    if old_voice is None or (
                        old_voice["reference_audio_sha256"] !=
                        identity["voice_reference_sha256"]):
                        raise RuntimeError("Historical ActorID VoiceID was substituted")
            actor=registry.actor(pid,aid)
            if actor["actor_id"]!=aid:
                raise RuntimeError("Original StoryBible ActorID is missing")
            cast_members.append(identity)
        timeline=source_time._revision(
            pid,fdoc["timeline_id"],fdoc["timeline_revision"])
        if timeline["document_sha256"]!=fdoc["timeline_document_sha256"]:
            raise RuntimeError("Original source Take timeline SHA mismatch")
        event_count=timeline["data"]["event_count"]
        if event_count>MAX_ORIGINAL_AUDIO_EVENTS:
            raise ValueError("Source Take exceeds bounded exact-event audit")
        timeline_events=source_time.events_in(
            pid,fdoc["timeline_id"],fdoc["timeline_revision"],
            start_tick=0,end_tick=fdoc["duration_tick"],
            limit=MAX_ORIGINAL_AUDIO_EVENTS+1)
        if (timeline_events["next_cursor"] is not None or
            len(timeline_events["events"]) != event_count):
            raise RuntimeError("Original timeline events were truncated")
        for event in timeline_events["events"]:
            source = index.read_revision(
                pid,event["source_id"],event["source_revision"])
            if source["kind"] != "audio":
                continue
            sound = originals.describe(
                pid,event["source_id"],event["source_revision"])
            if sound["document_sha256"] != event["source_document_sha256"]:
                raise PermissionError("Original recorded source PCM SHA differs from timeline")
            if sound["data"]["sample_count"]<1:
                raise RuntimeError("Original sound has zero PCM samples")
            audit=_verify_original_pcm_chunks(index,pid,sound)
            audio_sources.append({
                "set":set_name, "source_take_id":inp["take_id"],
                "event_id":event["event_id"],
                "event_kind":event["event_kind"],
                "event_start_tick":event["start_tick"],
                "event_end_tick":event["end_tick"],
                "original_source_id":event["source_id"],
                "original_source_revision":event["source_revision"],
                "original_source_document_sha256":sound["document_sha256"],
                "sample_rate_hz":SAMPLE_RATE,
                "sample_count":sound["data"]["sample_count"],
                "original_pcm_chunks_verified":audit["chunks_verified"],
                "original_pcm_bytes_verified":audit["bytes_verified"],
                "ticks_per_original_pcm_sample":AUDIO_TICKS_PER_SAMPLE,
                "original_PCM_not_remixed":True,
            })
        verified.append({
            "set":set_name,"take_id":inp["take_id"],
            "take_sha256":frozen["document_sha256"],
            "scene_id":fdoc["scene_id"],
            "scene_revision":fdoc["scene_revision"],
            "scene_sha256":fdoc["scene_document_sha256"],
            "timeline_id":fdoc["timeline_id"],
            "timeline_revision":fdoc["timeline_revision"],
            "timeline_sha256":fdoc["timeline_document_sha256"],
            "duration_tick":fdoc["duration_tick"],
            "original_sample_digest_sha256":fdoc["sample_digest_sha256"],
        })
    return (
        sorted(verified,key=lambda x:x["set"]),
        sorted(cast_members,key=lambda x:(x["set"],x["original_actor_prim"])),
        sorted(audio_sources,key=lambda x:(x["set"],x["event_start_tick"],
                                            x["event_id"])),
    )


def _selected_dialogue(index, pid, requests, scene_takes, cast):
    if (type(requests) is not list or len(requests)>MAX_DIALOGUE_ROUTES):
        raise ValueError("Bounded source-selected actor dialogue required")
    known={(item["take_id"],item["take_sha256"]):item["set"] for item in scene_takes}
    members={(x["actor_id"],x["original_actor_prim"],x["source_take_id"]):
             x for x in cast}
    manager=ActorDialogueManager(index)
    chosen=[]
    seen=set()
    for req in requests:
        if type(req) is not dict or set(req)!=ROUTE_FIELDS:
            raise ValueError("Dialogue must contain exact authored route identity")
        route=manager.route(pid,req)
        key=(route["source_take_id"],route["source_take_sha256"])
        if key not in known:
            raise PermissionError("Selected dialogue belongs to another original scene Take")
        ident=(route["actor_id"],route["openusd_actor_prim_path"],
               route["source_take_id"])
        if ident not in members:
            raise PermissionError("Voice performance belongs to another world ActorID")
        selection=(route["selection_id"],route["selection_revision"],
                   route["performance_id"])
        if selection in seen:
            raise ValueError("Duplicate selected actor performance for world Take")
        seen.add(selection)
        voice=route["original_recorded_voice"]
        chosen.append({
            "set":known[key],
            "actor_id":route["actor_id"],
            "composed_actor_prim":members[ident]["composed_actor_prim"],
            "source_take_id":route["source_take_id"],
            "source_take_sha256":route["source_take_sha256"],
            "performance_id":route["performance_id"],
            "performance_document_sha256":route["performance_document_sha256"],
            "script_id":route["script_id"],
            "script_revision":route["script_revision"],
            "script_document_sha256":route["script_document_sha256"],
            "script_line_id":route["script_line_id"],
            "exact_dialogue_text_sha256":sha256(
                route["exact_director_selected_text"].encode("utf8")).hexdigest(),
            "selection_id":route["selection_id"],
            "selection_revision":route["selection_revision"],
            "selection_document_sha256":route["selection_document_sha256"],
            "voice_id":route["canonical_voice_id"],
            "voice_cast_revision":route["voice_identity_cast_revision"],
            "original_recorded_voice":voice,
            "source_line_start_tick":route["first_tick"],
            "source_line_end_tick":route["end_tick"],
            "source_selection_tick":route["film_time_tick"],
            "voice_available_only_if_original_verified":bool(voice),
            "generated_voice_or_audio":False,
        })
    return sorted(chosen,key=lambda x:(
        x["set"],x["source_selection_tick"],x["performance_id"]))


def _snapshot(index, pid, world_doc, shot, take_map, cast, tick):
    """Compute one fully real source USD checkpoint at exact Film Time."""
    if type(tick) is not int or not 0 <= tick <= MAX_USD_EXACT_TICK:
        raise ValueError("Exact integer film tick required")
    if tick not in shot["camera_sample_ticks"]:
        # This contract samples one of the frozen authored shot checkpoints;
        # future 01F can perform arbitrary-frame rendering after source QC.
        raise ValueError("Only original frozen shot checkpoint ticks may be sampled")
    Gf,Sdf,Usd,UsdGeom=_usd()
    originals=_capture(index)
    source_by_set={x["set"]:x for x in take_map}
    actor_by_set={}
    for member in cast:
        actor_by_set.setdefault(member["set"],[]).append(member)
    with OpenUSDWorldComposer(index).open(
        pid,shot["world_id"],shot["world_revision"]) as world:
        world.load(shot["director_required_sets"])
        with Usd.EditContext(world.stage, world.stage.GetSessionLayer()):
            for v,look in shot["director_looks"].items():
                world.switch_variant(v,look)
        camera_path, camera_sample=_camera_native(
            world,shot["camera_set"],shot["camera_prim_path"],[tick])
        expected=dict(zip(
            shot["camera_sample_ticks"],shot["original_camera_positions_m"]))[tick]
        if any(abs(a-b)>1e-6 for a,b in zip(camera_sample[0],expected)):
            raise PermissionError("Original native film camera differs from frozen shot")
        scenes=[]
        for set_name in shot["director_required_sets"]:
            item=source_by_set.get(set_name)
            if item is None:
                continue
            captured=originals.sample(
                pid,item["scene_id"],item["scene_revision"],
                item["timeline_id"],item["timeline_revision"],tick=tick)
            if (captured["scene_document_sha256"]!=item["scene_sha256"] or
                captured["timeline_document_sha256"]!=item["timeline_sha256"]):
                raise RuntimeError("Original source Take checkpoint SHA changed")
            source_poses={e["prim_path"]:e for e in captured["transforms"]}
            poses=[]
            for member in actor_by_set.get(set_name,[]):
                original=source_poses[member["original_actor_prim"]]
                composed=member["composed_actor_prim"]
                prim=world.stage.GetPrimAtPath(composed)
                if not prim or not prim.IsDefined() or not UsdGeom.Xformable(prim):
                    raise RuntimeError("Composed world is missing an original ActorID")
                transform=UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
                    Usd.TimeCode(float(tick)))
                pos=transform.ExtractTranslation()
                derived=[float(pos[i]) for i in range(3)]
                if any(not math.isfinite(v) for v in derived) or any(
                    abs(a-b)>1e-6 for a,b in zip(
                        derived,original["world_translation"])):
                    raise RuntimeError("Original ActorID performance moved in composed world")
                poses.append({
                    "actor_id":member["actor_id"],
                    "original_scene_prim":member["original_actor_prim"],
                    "composed_world_prim":composed,
                    "world_translation_m":derived,
                })
            scenes.append({
                "set":set_name,"source_take_id":item["take_id"],
                "original_camera_scene_or_performance_sha256":captured[
                    "scene_document_sha256"],
                "original_temporal_event_ids":[e["event_id"] for e in
                                                captured["active_events"]],
                "performance_channels_sha256":_digest(
                    captured.get("performance_channels",[])),
                "native_schema_samples_sha256":_digest(
                    captured.get("native_scene_schemas",[])),
                "original_skeletal_pose_sha256":_digest(
                    captured.get("skeletal_pose",[])),
                "actors":poses,
            })
        return {
            "format":CHECKPOINT_FORMAT,
            "tick":tick,
            "world_document_sha256":world.record["document_sha256"],
            "original_camera_path":camera_path,
            "original_camera_position_m":camera_sample[0],
            "scenes":scenes,
            "unrendered_source_data_only":True,
        }


class OpenUSDWorldTakeCapture:
    """New single-commit world Take; does not change old scene Take format."""

    def __init__(self,index:FilmIndex,*,verify_creator_action):
        if not isinstance(index,FilmIndex) or not callable(verify_creator_action):
            raise TypeError("First-party FilmIndex and creative host action required")
        self.index=index
        self._approve=verify_creator_action

    def _prepare(self,pid,world_id,world_revision,shot_id,shot_revision,
                 scene_takes,dialogue_requests,*,historic_cast=None):
        shot_record=FilmWorldShotPlanner(self.index).inspect(pid,shot_id,shot_revision)
        shot=shot_record["data"]
        world=self.index.read_revision(pid,world_id,world_revision)
        if (world["kind"]!="world" or shot["world_id"]!=world_id or
            shot["world_revision"]!=world_revision or
            shot["world_document_sha256"]!=world["document_sha256"]):
            raise PermissionError("World Take must use exact original camera/world source")
        takes,cast,audio=_actor_and_take_sources(
            self.index,pid,shot,scene_takes,
            historic_cast=historic_cast)
        chosen=_selected_dialogue(
            self.index,pid,dialogue_requests,takes,cast)
        checkpoints=[
            _snapshot(self.index,pid,world["data"],shot,takes,cast,tick)
            for tick in shot["camera_sample_ticks"]
        ]
        return world,shot_record,takes,cast,audio,chosen,checkpoints

    def freeze(self,pid,take_id,*,world_id,world_revision,shot_id,
               shot_revision,scene_takes,dialogue_requests=None,
               creator_event):
        _require_pid(pid)
        for key in (take_id,world_id,shot_id):
            _id(key,"original world/Take/shot identity")
        if len({take_id,world_id,shot_id})!=3:
            raise ValueError("World and shot identities must be distinct")
        if type(world_revision) is not int or world_revision<1 or (
            type(shot_revision) is not int or shot_revision<1):
            raise ValueError("Exact original world/shot revisions required")
        data=(
            [] if dialogue_requests is None else dialogue_requests)
        world,shot,takes,cast,audio,chosen,checkpoints=self._prepare(
            pid,world_id,world_revision,shot_id,shot_revision,
            scene_takes,data)
        scope={
            "operation":"nvp.freeze.usd_film01e_world_take.v1",
            "project_id":pid, "world_take_id":take_id,
            "world_id":world_id, "world_revision":world_revision,
            "world_sha256":world["document_sha256"],
            "shot_id":shot_id, "shot_revision":shot_revision,
            "shot_sha256":shot["document_sha256"],
            "original_take_shas":sorted(x["take_sha256"] for x in takes),
            "original_actor_ids":sorted(set(x["actor_id"] for x in cast)),
            "original_dialogue_selections":sorted(
                x["selection_document_sha256"] for x in chosen),
            "source_checkpoint_digest":_digest(checkpoints),
        }
        if self._approve(creator_event,dict(scope)) is not True:
            raise PermissionError("Director did not approve this exact world Take freeze")
        doc={
            "format":FORMAT,
            "world_id":world_id,"world_revision":world_revision,
            "world_document_sha256":world["document_sha256"],
            "camera_shot_id":shot_id,"camera_shot_revision":shot_revision,
            "camera_shot_document_sha256":shot["document_sha256"],
            "original_scene_takes":takes,
            "canonical_original_actors":cast,
            "original_timeline_audio_sources":audio,
            "original_selected_dialogue":chosen,
            "checkpoint_ticks":shot["data"]["camera_sample_ticks"],
            "checkpoint_digest_sha256":_digest(checkpoints),
            "ticks_per_second":TICKS_PER_SECOND,
            "original_audio_rate_hz":SAMPLE_RATE,
            "ticks_per_source_pcm_sample":AUDIO_TICKS_PER_SAMPLE,
            "frozen":True,"source_scene_takes_unchanged":True,
            "source_actor_identity_substitution":False,
            "dialogue_or_audio_generated":False,
            "finished_picture_rendered":False,
            "final_audio_mixed":False,
            "ready_for_original_render_build":False,
        }
        edges=[
            {"object_id":world_id,"revision":world_revision,"role":"world"},
            {"object_id":shot_id,"revision":shot_revision,"role":"camera"},
        ]
        for binding in takes:
            edges.append({"object_id":binding["take_id"],"revision":1,
                          "role":"source_take"})
        for selection in chosen:
            edges.append({"object_id":selection["selection_id"],
                          "revision":selection["selection_revision"],
                          "role":"presentation"})
            edges.append({"object_id":selection["performance_id"],
                          "revision":1,"role":"performance"})
            if selection["original_recorded_voice"] is not None:
                voice=selection["original_recorded_voice"]
                edges.append({"object_id":voice["source_id"],
                              "revision":voice["source_revision"],"role":"audio"})
        for sound in audio:
            edges.append({"object_id":sound["original_source_id"],
                          "revision":sound["original_source_revision"],
                          "role":"audio"})
        # FilmIndex disallows duplicate dependency edges; exact same source
        # can appear in multiple original sound/voice events in one film.
        dedup={(e["object_id"],e["revision"]):e for e in edges}
        edges=[dedup[k] for k in sorted(dedup)]
        source_shas = {
            (e["object_id"],e["revision"]):
                self.index.read_revision(
                    pid,e["object_id"],e["revision"])["document_sha256"]
            for e in edges
        }
        if (source_shas[(world_id,world_revision)]!=world["document_sha256"] or
            source_shas[(shot_id,shot_revision)]!=shot["document_sha256"] or
            any(source_shas[(x["take_id"],1)]!=x["take_sha256"] for x in takes)):
            raise RuntimeError("World Take source SHA changed before publication")
        def guard(db):
            for e in edges:
                row=db.execute(
                    "SELECT document_sha FROM film_object_revisions "
                    "WHERE project_id=? AND object_id=? AND revision=?",
                    (pid,e["object_id"],e["revision"])).fetchone()
                if (row is None or row["document_sha"] !=
                    source_shas[(e["object_id"],e["revision"])]):
                    raise RuntimeError("World Take original source changed at commit")
            # First freeze must observe exactly the cast and VoiceID history
            # it already sampled. Later recasts remain allowed; old source
            # and historical VoiceID are not updated.
            for actor in cast:
                linked=db.execute(
                    "SELECT 1 FROM nvp_bible_actor_links WHERE "
                    "project_id=? AND actor_id=? AND role='actor_prim' "
                    "AND source_family='filmindex' AND target_id=? "
                    "AND target_revision=1 AND actor_prim_path=? "
                    "AND source_sha256=? AND status='active' LIMIT 1",
                    (pid,actor["actor_id"],actor["source_take_id"],
                     actor["original_actor_prim"],
                     actor["source_take_sha256"])).fetchone()
                if linked is None:
                    raise RuntimeError("Actor's original source link changed during freeze")
                latest=db.execute(
                    "SELECT voice_id,cast_revision,reference_audio_sha256 "
                    "FROM nvp_bible_voice_casts WHERE project_id=? AND "
                    "actor_id=? ORDER BY cast_revision DESC LIMIT 1",
                    (pid,actor["actor_id"])).fetchone()
                expected=(
                    actor["voice_id"],actor["voice_cast_revision"],
                    actor["voice_reference_sha256"])
                observed=(
                    (latest["voice_id"],latest["cast_revision"],
                     latest["reference_audio_sha256"])
                    if latest is not None else (None,None,None))
                if expected != observed:
                    raise RuntimeError("Actor VoiceID changed during world Take freeze")
        return self.index.register_revision(
            pid,take_id,"take",doc,expected_revision=0,
            dependencies=edges,precommit_guard=guard)

    def verify_take(self,pid,take_id):
        _require_pid(pid)
        _id(take_id,"world-composed original Digital Take")
        row=self.index.read_revision(pid,take_id,1)
        doc=row["data"]
        if (row["kind"]!="take" or doc.get("format")!=FORMAT or
            doc.get("frozen") is not True or
            doc.get("finished_picture_rendered") is not False or
            doc.get("dialogue_or_audio_generated") is not False or
            doc.get("source_scene_takes_unchanged") is not True or
            doc.get("ticks_per_second")!=TICKS_PER_SECOND or
            doc.get("ticks_per_source_pcm_sample")!=AUDIO_TICKS_PER_SAMPLE):
            raise RuntimeError("Not an unchanged original world-composed Data Take")
        world,shot,takes,cast,audio,chosen,checkpoints=self._prepare(
            pid,doc["world_id"],doc["world_revision"],
            doc["camera_shot_id"],doc["camera_shot_revision"],
            [{"set":t["set"],"take_id":t["take_id"],
              "take_sha256":t["take_sha256"]}
             for t in doc["original_scene_takes"]],
            [],historic_cast=doc["canonical_original_actors"])
        # Historical dialogue is checked by its source SHA and old VoiceID,
        # not re-routed through the latest screenplay or later voice recasts.
        if (world["document_sha256"]!=doc["world_document_sha256"] or
            shot["document_sha256"]!=doc["camera_shot_document_sha256"] or
            takes!=doc["original_scene_takes"] or
            cast!=doc["canonical_original_actors"] or
            audio!=doc["original_timeline_audio_sources"] or
            doc["checkpoint_ticks"]!=shot["data"]["camera_sample_ticks"] or
            doc["checkpoint_digest_sha256"]!=_digest(checkpoints)):
            raise RuntimeError("Original world Take checkpoint or identity changed")
        original_voices=ProductionBibleVoiceIdentity(
            self.index,verify_creator_action=lambda *_:False)
        originals=RecordedSoundSources(self.index)
        for selected in doc["original_selected_dialogue"]:
            if (selected["source_take_id"] not in {x["take_id"] for x in takes} or
                selected["actor_id"] not in {x["actor_id"] for x in cast}):
                raise PermissionError("Stored selected dialogue belongs to different actor/Take")
            perf=self.index.read_revision(pid,selected["performance_id"],1)
            selection=self.index.read_revision(
                pid,selected["selection_id"],selected["selection_revision"])
            if (perf["document_sha256"]!=
                selected["performance_document_sha256"] or
                selection["document_sha256"]!=
                selected["selection_document_sha256"]):
                raise RuntimeError("Historical original dialogue source SHA changed")
            performance=perf["data"]
            if (perf["kind"]!="performance" or
                performance["source_take_id"]!=selected["source_take_id"] or
                performance["source_take_sha256"]!=selected["source_take_sha256"] or
                performance["production_bible"]["actor_id"]!=selected["actor_id"] or
                performance["script_line_id"]!=selected["script_line_id"] or
                performance["script_id"]!=selected["script_id"] or
                performance["script_revision"]!=selected["script_revision"] or
                performance["script_document_sha256"]!=
                    selected["script_document_sha256"] or
                performance["script_line_text_sha256"]!=
                    selected["exact_dialogue_text_sha256"] or
                performance["first_tick"]!=selected["source_line_start_tick"] or
                performance["end_tick"]!=selected["source_line_end_tick"] or
                not performance["first_tick"]<=selected["source_selection_tick"]<
                    performance["end_tick"] or
                selection["kind"]!="presentation" or
                selection["data"]["source_take_id"]!=
                    selected["source_take_id"] or
                selected["composed_actor_prim"] not in {
                    x["composed_actor_prim"] for x in cast
                    if x["actor_id"]==selected["actor_id"] and
                       x["source_take_id"]==selected["source_take_id"]
                }):
                raise PermissionError("Stored historical dialogue does not match source actor or script")
            if selected["original_recorded_voice"] is not None:
                voice=selected["original_recorded_voice"]
                sound=originals.describe(
                    pid,voice["source_id"],voice["source_revision"])
                if sound["document_sha256"]!=voice["original_pcm_document_sha256"]:
                    raise RuntimeError("Selected original recorded dialogue PCM lost")
                src=performance.get("recorded_voice_source")
                if (src is None or
                    src["audio_id"]!=voice["source_id"] or
                    src["audio_revision"]!=voice["source_revision"] or
                    src["audio_sha256"]!=voice["original_pcm_document_sha256"] or
                    selected["voice_id"]!=voice["voice_id"] or
                    selected["voice_cast_revision"]!=voice["voice_cast_revision"]):
                    raise PermissionError("Selected PCM or VoiceID differs from original performance")
                _verify_original_pcm_chunks(self.index,pid,sound)
                # Recast should NOT destroy playback of an old original
                # Take, but historical VoiceID decision must remain stored.
                with self.index.studio._connection() as db:
                    historic=db.execute(
                        "SELECT reference_audio_sha256 FROM nvp_bible_voice_casts "
                        "WHERE project_id=? AND actor_id=? AND cast_revision=? "
                        "AND voice_id=?",
                        (pid,selected["actor_id"],
                         selected["voice_cast_revision"],
                         selected["voice_id"])).fetchone()
                if (historic is None or historic["reference_audio_sha256"]!=
                    voice["voice_reference_audio_sha256"]):
                    raise RuntimeError("Historical ActorID VoiceID evidence changed")
        return {
            "status":"VERIFIED_ORIGINAL_WORLD_SOURCE_DATA_TAKE",
            "take_id":take_id,"take_document_sha256":row["document_sha256"],
            "world_document_sha256":world["document_sha256"],
            "original_take_count":len(takes),
            "canonical_actor_count":len(cast),
            "director_selected_dialogue_count":len(
                doc["original_selected_dialogue"]),
            "original_audio_event_count":len(audio),
            "checkpoint_count":len(checkpoints),
            "finished_picture_rendered":False,
            "original_recorded_audio_not_a_final_mix":True,
            "original_actor_source_unchanged":True,
        }

    def sample(self,pid,take_id,*,tick):
        report=self.verify_take(pid,take_id)
        item=self.index.read_revision(pid,take_id,1)["data"]
        if tick not in item["checkpoint_ticks"]:
            raise ValueError("Only frozen original checkpoint ticks accepted")
        shot=self.index.read_revision(
            pid,item["camera_shot_id"],item["camera_shot_revision"])["data"]
        return _snapshot(
            self.index,pid,item,shot,
            item["original_scene_takes"],
            item["canonical_original_actors"],tick)
