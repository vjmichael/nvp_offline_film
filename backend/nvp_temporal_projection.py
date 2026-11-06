"""DATA-TIME-01B: derive bounded presentation samples from authoritative events.

World actions, dialogue, camera, audio and character state live on the same
source timeline independently of video FPS. This projection does not render
anything, interpolate motion, grant model authority, or publish a master.
"""
from __future__ import annotations

from backend.nvp_temporal_ledger import (
    TemporalLedger, frame_at_tick, tick_from_frame, _int)

FORMAT = "nvp.temporal.presentation_window.v1"
MAX_SAMPLES = 96
MAX_EVENTS = 200


class TemporalProjection:
    def __init__(self, ledger: TemporalLedger):
        if not isinstance(ledger,TemporalLedger):
            raise TypeError("Authoritative NVP temporal event ledger required")
        self.ledger=ledger

    def prepare(self, project_id, timeline_id, revision, *,
                start_tick, end_tick, fps_num, fps_den):
        start=_int(start_tick,"projected first tick")
        end=_int(end_tick,"projected end tick")
        if end<=start:
            raise ValueError("Production time window must be positive")
        doc=self.ledger._revision(project_id,timeline_id,revision)
        if end>doc["data"]["duration_tick"]:
            raise ValueError("Projection extends beyond authored film")
        first=frame_at_tick(start,fps_num,fps_den,rounding="ceil")
        stop=frame_at_tick(end,fps_num,fps_den,rounding="ceil")
        count=stop-first
        if count<1 or count>MAX_SAMPLES:
            raise ValueError("Requested presentation samples exceed bounded work unit")
        sample_ticks=[tick_from_frame(frame,fps_num,fps_den)
                      for frame in range(first,stop)]
        if any(t<start or t>=end for t in sample_ticks):
            raise RuntimeError("Exact presentation time projection failed")
        page=self.ledger.events_in(
            project_id,timeline_id,revision,
            start_tick=start,end_tick=end,limit=MAX_EVENTS+1)
        if len(page["events"])>MAX_EVENTS or page["next_cursor"] is not None:
            raise RuntimeError("Event-dense interval requires smaller presentation windows")
        return {
            "format":FORMAT,"project_id":project_id,
            "timeline_id":timeline_id,"timeline_revision":revision,
            "timeline_document_sha256":doc["document_sha256"],
            "start_tick":start,"end_tick":end,
            "ticks_per_second":doc["data"]["ticks_per_second"],
            "fps_num":fps_num,"fps_den":fps_den,
            "presentation_samples":[
                {"presentation_frame_zero":first+i,"time_tick":tick}
                for i,tick in enumerate(sample_ticks)],
            "active_source_events":page["events"],
            "creator_approved":False,"rendered_frames":False,
            "output": "NOT_RENDERED_EVENT_DATA_ONLY",
        }
