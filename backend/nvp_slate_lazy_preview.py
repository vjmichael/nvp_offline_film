"""SLATE-04: bounded, on-demand source-data preview lookup for mixed Take cuts.

The edit manifest is the thin EDL. Moving the playhead never opens a USD
stage, loads actor geometry, runs a renderer, decodes a video frame or places
the entire shoot into RAM. For a selected tick, verify exactly ONE source
Take/optional SHOT revision and derive the source tick by integer offset.

Explicit structural preview can then open only that selected source stage
and evaluate selected prim transforms. This is source DATA inspection,
NOT picture generation, full 3D character deformation or audio playback.
"""
from __future__ import annotations

from bisect import bisect_right
import hashlib
import json

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_slate_edit_assembly import FORMAT as EDIT_FORMAT, _digest
from backend.nvp_temporal_ledger import _int, MAX_TICK
from backend.nvp_openusd_take import FORMAT as TAKE_FORMAT
from backend.nvp_openusd_shot_overrides import FORMAT as SHOT_FORMAT

FORMAT="nvp.slate.lazy_source_preview.v1"
MAX_SAMPLES=16
MAX_PRIM_PATHS=16
QUALITIES=frozenset(("thumbnail","interactive","inspection"))


def _hash(value):
    return hashlib.sha256(json.dumps(
        value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
    ).hexdigest()


class SlateLazyPreview:
    def __init__(self,index:FilmIndex):
        if not isinstance(index,FilmIndex):
            raise TypeError("Trusted immutable FilmIndex source required")
        self.index=index

    def _manifest(self,project_id,edit_id,revision):
        _require_pid(project_id)
        _id(edit_id,"committed assembly")
        _int(revision,"committed assembly revision",minimum=1)
        edit=self.index.read_revision(project_id,edit_id,revision)
        doc=edit["data"]
        if (edit["kind"]!="edit" or doc.get("format")!=EDIT_FORMAT or
            doc.get("explicit_editor_commit") is not True or
            doc.get("render_approved") is not False or
            doc.get("retimed") is not False or
            type(doc.get("segments")) is not list or
            not 1<=len(doc["segments"])<=500 or
            _digest(doc["segments"])!=doc["ordered_segment_sha256"]):
            raise RuntimeError("Not a valid sealed non-retimed data-assembly edit")
        graph=self.index.read_revision(
            project_id,doc["graph_id"],doc["graph_revision"])
        if (graph["document_sha256"]!=doc["graph_document_sha256"] or
            graph["kind"]!="presentation"):
            raise RuntimeError("Committed cut source catalog SHA changed")
        # Basic ordered-edit consistency checks use only small JSON. These
        # never fetch the graph's thousands of branches or OpenUSD layers.
        expected_start=0
        for part in doc["segments"]:
            if (part["timeline_start_tick"]!=expected_start or
                part["timeline_end_tick"]-part["timeline_start_tick"]!=
                 part["source_out_tick"]-part["source_in_tick"] or
                part["timeline_end_tick"]<=expected_start or
                part.get("source_data_copied") is not False):
                raise RuntimeError("Corrupt or implicit-retimed assembled source interval")
            expected_start=part["timeline_end_tick"]
        if expected_start!=doc["duration_tick"]:
            raise RuntimeError("Committed edit timeline duration changed")
        return edit,graph

    def select(self,project_id,edit_id,revision,*,film_tick,
               quality="interactive"):
        """Locate one exact reference without loading any USD source layers."""
        _int(film_tick,"requested edit Film Time",maximum=MAX_TICK)
        if quality not in QUALITIES:
            raise ValueError("Unknown bounded source preview quality")
        edit,graph=self._manifest(project_id,edit_id,revision)
        segments=edit["data"]["segments"]
        starts=[row["timeline_start_tick"] for row in segments]
        if film_tick>=edit["data"]["duration_tick"]:
            return {
                "format":FORMAT,"status":"AFTER_ASSEMBLED_CUT",
                "edit_document_sha256":edit["document_sha256"],
                "film_tick":film_tick,"source_data_loaded":False,
                "picture_generated":False,
            }
        at=bisect_right(starts,film_tick)-1
        if at<0 or film_tick>=segments[at]["timeline_end_tick"]:
            raise RuntimeError("No exact segment covers assembled film time")
        part=segments[at]
        take=self.index.read_revision(
            project_id,part["source_take_id"],part["source_take_revision"])
        if (take["kind"]!="take" or
            take["data"].get("format")!=TAKE_FORMAT or
            take["data"].get("frozen") is not True or
            take["document_sha256"]!=part["source_take_document_sha256"]):
            raise RuntimeError("Committed source Take has lost frozen identity")
        shot=None
        if part["source_shot_id"] is not None:
            shot=self.index.read_revision(
                project_id,part["source_shot_id"],part["source_shot_revision"])
            if (shot["kind"]!="presentation" or
                shot["data"].get("format")!=SHOT_FORMAT or
                shot["document_sha256"]!=part["source_shot_document_sha256"] or
                shot["data"]["take_id"]!=take["object_id"]):
                raise RuntimeError("Committed shot source identity changed")
        source_tick=part["source_in_tick"]+(
            film_tick-part["timeline_start_tick"])
        if (source_tick>=part["source_out_tick"] or
            source_tick>=take["data"]["duration_tick"] or
            shot is not None and not (
                shot["data"]["start_tick"]<=source_tick<
                shot["data"]["end_tick"])):
            raise RuntimeError("Selected original source time outside immutable bounds")
        ticket={
            "format":FORMAT,
            "status":"SOURCE_REFERENCE_SELECTED",
            "project_id":project_id,
            "edit_id":edit_id,"edit_revision":revision,
            "edit_document_sha256":edit["document_sha256"],
            "source_catalog_document_sha256":graph["document_sha256"],
            "segment_id":part["segment_id"],"branch_id":part["branch_id"],
            "timeline_tick":film_tick,
            "source_tick":source_tick,
            "source_in_tick":part["source_in_tick"],
            "source_out_tick":part["source_out_tick"],
            "source_take_id":take["object_id"],
            "source_take_revision":take["revision"],
            "source_take_document_sha256":take["document_sha256"],
            "source_shot_id":part["source_shot_id"],
            "source_shot_revision":part["source_shot_revision"],
            "source_shot_document_sha256":part["source_shot_document_sha256"],
            "preview_quality":quality,
            "source_data_loaded":False,
            "full_3d_world_loaded":False,
            "picture_generated":False,
            "worker_started":False,
            "source_data_copied":False,
            "final_render_approved":False,
        }
        ticket["cache_key"]=_hash({
            "take_sha":ticket["source_take_document_sha256"],
            "shot_sha":ticket["source_shot_document_sha256"],
            "source_tick":source_tick,"quality":quality,
            "format":FORMAT,
        })
        return ticket

    def window(self,project_id,edit_id,revision,*,first_tick,
               count,step_tick,quality="thumbnail"):
        """Bounded data-only preview ticket batch, no eager USD/asset loading."""
        _int(first_tick,"preview window starting tick",maximum=MAX_TICK)
        _int(count,"preview request count",minimum=1,maximum=MAX_SAMPLES)
        _int(step_tick,"preview sample interval",minimum=1,maximum=MAX_TICK)
        if first_tick+(count-1)*step_tick>MAX_TICK:
            raise ValueError("Preview window exceeds Film Time range")
        tickets=[
            self.select(project_id,edit_id,revision,
                        film_tick=first_tick+i*step_tick,quality=quality)
            for i in range(count)]
        return {
            "format":"nvp.slate.bounded_preview_window.v1",
            "project_id":project_id,"edit_id":edit_id,
            "edit_revision":revision,
            "tickets":tickets,
            "distinct_source_take_shas":sorted({
                t["source_take_document_sha256"] for t in tickets
                if t["status"]=="SOURCE_REFERENCE_SELECTED"}),
            "max_samples":MAX_SAMPLES,
            "picture_generated":False,
            "all_sources_loaded":False,
        }

    def structural_sample(self,ticket,*,prim_paths):
        """Explicitly load ONE selected USD scene and sample <=16 prims.

        Preview path data are not final image pixels; future authorized
        renderer workers can use exact source SHA/tick from the ticket.
        """
        if (type(ticket) is not dict or
            ticket.get("format")!=FORMAT or
            ticket.get("status")!="SOURCE_REFERENCE_SELECTED" or
            type(prim_paths) is not list or
            not 1<=len(prim_paths)<=MAX_PRIM_PATHS or
            any(type(p) is not str for p in prim_paths) or
            len(set(prim_paths))!=len(prim_paths)):
            raise ValueError("Bounded existing-prim data inspection required")
        source=self.select(
            ticket["project_id"],ticket["edit_id"],ticket["edit_revision"],
            film_tick=ticket["timeline_tick"],
            quality=ticket["preview_quality"])
        if source!=ticket:
            raise RuntimeError("Source reference ticket changed before preview")
        from backend.nvp_openusd_scene import (
            OpenUSDSceneBridge, _usd, _evaluate)
        from backend.nvp_openusd_shot_overrides import OpenUSDShotOverrides
        from backend.nvp_openusd_take import FORMAT as FROZEN
        stage_reader=OpenUSDSceneBridge(self.index)
        take=self.index.read_revision(
            ticket["project_id"],ticket["source_take_id"],
            ticket["source_take_revision"])
        if take["data"].get("format")!=FROZEN:
            raise RuntimeError("Not a frozen USD Take")
        if ticket["source_shot_id"] is not None:
            shot_reader=OpenUSDShotOverrides(
                self.index,verify_director_action=lambda *_:False)
            shot,scene,stage=shot_reader.open_shot(
                ticket["project_id"],ticket["source_shot_id"],
                ticket["source_shot_revision"],tick=ticket["source_tick"])
            if (shot["document_sha256"]!=ticket["source_shot_document_sha256"] or
                scene["document_sha256"]!=take["data"]["scene_document_sha256"]):
                raise RuntimeError("Selected shot does not match immutable Take scene")
        else:
            scene,stage=stage_reader.open(
                ticket["project_id"],take["data"]["scene_id"],
                take["data"]["scene_revision"])
            if scene["document_sha256"]!=take["data"]["scene_document_sha256"]:
                raise RuntimeError("Source scene changed")
        Gf,Sdf,Usd,UsdGeom=_usd()
        result=[
            _evaluate(stage,p,ticket["source_tick"],Sdf,Usd,UsdGeom)
            for p in prim_paths]
        return {
            "format":"nvp.slate.structural_preview.v1",
            "cache_key":ticket["cache_key"],
            "source_tick":ticket["source_tick"],
            "source_take_document_sha256":ticket["source_take_document_sha256"],
            "source_shot_document_sha256":ticket["source_shot_document_sha256"],
            "prim_states":result,"prim_count":len(result),
            "one_source_scene_loaded":True,"picture_generated":False,
            "actor_performance_audio_or_ik_rendered":False,
            "final_render_approved":False,
        }
