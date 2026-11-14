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
from backend.nvp_temporal_ledger import TemporalLedger

SCHEMA="nvp.data_av.usd_spatial_bindings.v1"


def spatial_audio_at(index:FilmIndex,project_id,scene_id,scene_revision,
                     timeline_id,timeline_revision,tick,*,limit=32):
    if not isinstance(index,FilmIndex):
        raise TypeError("Authoritative NVP FilmIndex required")
    from pxr import Sdf,Usd,UsdMedia
    record,stage=OpenUSDSceneBridge(index).open(
        project_id,scene_id,scene_revision)
    timeline=TemporalLedger(index)
    events=timeline.events_at(project_id,timeline_id,timeline_revision,
                              tick=tick,limit=limit+1)
    if len(events)>limit:
        raise RuntimeError("Native USD spatial source budget exceeded")
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
        prim.CreateStartTimeAttr(Sdf.TimeCode(float(event["start_tick"])))
        prim.CreateEndTimeAttr(Sdf.TimeCode(float(event["end_tick"])))
        descriptors.append({
            "event_id":event["event_id"],
            "usd_schema":"UsdMediaSpatialAudio",
            "usd_prim_path":authored_path,
            "emitter_path":path,
            "source_id":event["source_id"],
            "source_revision":event["source_revision"],
            "source_document_sha256":source["document_sha256"],
            "start_tick":str(event["start_tick"]),
            "end_tick":str(event["end_tick"]),
            "gain":float(gain),
            "revised_frozen_layer":False,
        })
    return {"format":SCHEMA,"bindings":descriptors,
            "scene_document_sha256":record["document_sha256"],
            "original_modified":False}
