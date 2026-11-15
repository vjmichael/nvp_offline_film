"""DATA-AV-01: volatile UsdMedia.SpatialAudio adapters to frozen scene sound.

OpenUSD descriptors are authored in a PRIVATE, IN-MEMORY review stage. They
are not stored over frozen source USD layers. A hashed NVP source URI is
descriptive only; NVP's native sound reader resolves the indexed source, not
the arbitrary OpenUSD filesystem asset resolver.
"""
from __future__ import annotations

import hashlib
import math

from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND, _int

SCHEMA="nvp.data_av.usd_spatial_bindings.v1"


def spatial_audio_at(index:FilmIndex,project_id,scene_id,scene_revision,
                     timeline_id,timeline_revision,tick,*,limit=32):
    if not isinstance(index,FilmIndex):
        raise TypeError("Authoritative NVP FilmIndex required")
    _int(tick, "time tick")
    _int(limit, "spatial source budget", minimum=1, maximum=32)
    from pxr import Sdf,Usd,UsdMedia
    record,stage=OpenUSDSceneBridge(index).open(
        project_id,scene_id,scene_revision)
    timeline=TemporalLedger(index)
    # The timeline also contains camera, motion and editorial events. Query
    # original sound kinds separately so unrelated events cannot consume the
    # audio budget or conceal an audible source behind a SQL LIMIT.
    events=[]
    for kind in ("sound", "dialogue"):
        events.extend(timeline.events_at(
            project_id,timeline_id,timeline_revision,
            tick=tick,limit=limit+1,event_kind=kind))
        if len(events)>limit:
            raise RuntimeError("Native USD spatial source budget exceeded")
    events.sort(key=lambda event: (event["start_tick"], event["event_id"]))
    descriptors=[]
    roles=record["data"]["prim_roles"]
    for event in events:
        if event["event_kind"] not in ("sound","dialogue"):
            continue
        source=index.read_revision(
            project_id,event["source_id"],event["source_revision"])
        if source["document_sha256"]!=event["source_document_sha256"]:
            raise RuntimeError("Recorded audio event source revision changed")
        if source["kind"]!="audio":
            raise RuntimeError("Spatial source is not indexed recorded audio")
        path=event["payload"].get("usd_prim_path")
        if path not in roles:
            raise RuntimeError("Unbound spatial sound emitter")
        gain=event["payload"].get("gain",1.0)
        if (type(gain) not in (int,float) or not math.isfinite(gain) or
            not 0<=gain<=2):
            raise ValueError("Invalid spatial source gain")
        ident="Audio_"+hashlib.sha256(
            event["event_id"].encode("utf8")).hexdigest()[:20]
        authored_path=path+"/"+ident
        prim=UsdMedia.SpatialAudio.Define(stage,authored_path)
        if not prim.GetPrim().IsValid():
            raise RuntimeError("Native UsdMedia.SpatialAudio schema unavailable")
        # Virtual hashed URI: not a trusted file path or an instruction to
        # USD's asset resolver to open external media.
        prim.CreateFilePathAttr(Sdf.AssetPath(
            "nvp-sha256://"+source["document_sha256"]))
        prim.CreateAuralModeAttr("spatial")
        prim.CreatePlaybackModeAttr("onceFromStartToEnd")
        prim.CreateGainAttr(float(gain))
        # USD floating time codes are not an exact Film Time representation.
        # Preserve integer ticks as private review-stage metadata; the indexed
        # frozen event remains authoritative for playback and synchronization.
        start_tick = _int(event["start_tick"], "sound event start")
        end_tick = _int(event["end_tick"], "sound event end")
        if end_tick < start_tick:
            raise RuntimeError("Invalid indexed sound event interval")
        # Bind the transient descriptor to its immutable indexed provenance.
        # These fields are identifiers, never resolver paths or executable input.
        prim.GetPrim().SetCustomDataByKey("nvp:eventId", event["event_id"])
        prim.GetPrim().SetCustomDataByKey("nvp:sourceDocumentSha256", source["document_sha256"])
        prim.GetPrim().SetCustomDataByKey("nvp:sourceRevision", str(event["source_revision"]))
        prim.GetPrim().SetCustomDataByKey("nvp:filmTimeStartTick", str(start_tick))
        prim.GetPrim().SetCustomDataByKey("nvp:filmTimeEndTick", str(end_tick))
        prim.GetPrim().SetCustomDataByKey("nvp:filmTimeTicksPerSecond", str(TICKS_PER_SECOND))
        prim.CreateStartTimeAttr(Sdf.TimeCode(float(start_tick)))
        prim.CreateEndTimeAttr(Sdf.TimeCode(float(end_tick)))
        descriptors.append({
            "event_id":event["event_id"],
            "usd_schema":"UsdMediaSpatialAudio",
            "usd_prim_path":authored_path,
            "emitter_path":path,
            "source_id":event["source_id"],
            "source_revision":event["source_revision"],
            "source_document_sha256":source["document_sha256"],
            "film_time_ticks_per_second":str(TICKS_PER_SECOND),
            "start_tick":str(start_tick),
            "end_tick":str(end_tick),
            "gain":float(gain),
            "revised_frozen_layer":False,
        })
    return {"format":SCHEMA,"bindings":descriptors,
            "scene_document_sha256":record["document_sha256"],
            "original_modified":False}

def spatial_audio_at_precise_time(index: FilmIndex, project_id, scene_id,
                                  scene_revision, timeline_id,
                                  timeline_revision, film_time, *, limit=32):
    """Query original spatial sound using a structured exact Film Time address.

    Decimal tick strings are required across desktop/JSON boundaries so a
    JavaScript number cannot silently round a subframe address.
    """
    if type(film_time) is not dict or set(film_time) != {
            "ticks", "ticks_per_second"}:
        raise ValueError("Exact Film Time requires ticks and ticks_per_second")
    ticks = film_time["ticks"]
    rate = film_time["ticks_per_second"]
    if (type(ticks) is not str or not ticks or
            not ticks.isascii() or not ticks.isdecimal() or
            (len(ticks) > 1 and ticks[0] == "0")):
        raise ValueError("Film Time ticks must be canonical decimal text")
    if rate != str(TICKS_PER_SECOND) or type(rate) is not str:
        raise ValueError("Unsupported Film Time tick rate")
    # Validate the decimal width before integer conversion, even on Python
    # runtimes with different integer-string conversion limits.
    if len(ticks) > 19:
        raise ValueError("Film Time ticks exceed supported integer range")
    tick = _int(int(ticks), "time tick")
    result = spatial_audio_at(
        index, project_id, scene_id, scene_revision,
        timeline_id, timeline_revision, tick, limit=limit)
    return {**result, "queried_film_time": {
        "ticks": ticks, "ticks_per_second": rate}}
