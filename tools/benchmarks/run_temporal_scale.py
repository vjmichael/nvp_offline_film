#!/usr/bin/env python3
"""DATA-TIME-01 benchmark of the actual FilmIndex+TemporalLedger runtime.

No imported video source or OpenUSD rendering is necessary for an authored
film time index. Publishes 10,000+ source-bound actions over a 3-hour film
with exact revision manifests, then measures bounded point and interval
lookups. Full audit is timed separately, never inside per-tick preview calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND


def timed(fn):
    start=time.perf_counter()
    value=fn()
    return time.perf_counter()-start,value


def run(args):
    if not 100<=args.events<=100000:
        raise ValueError("Expected bounded 100..100000 timed events")
    if not 60<=args.duration_seconds<=3*3600+600:
        raise ValueError("Expected bounded feature-duration event time")
    with tempfile.TemporaryDirectory(prefix="nvp-native-events-") as tmp:
        studio=Studio(Path(tmp)/"studio.sqlite")
        pid=studio.create_project("NVP Temporal Scale","data only")["id"]
        index=FilmIndex(studio)
        index.register_revision(pid,"actor_source","performance",{
            "format":"nvp.benchmark.actor.v1","label":"Actor"
        },expected_revision=0)
        ledger=TemporalLedger(index)
        duration=args.duration_seconds*TICKS_PER_SECOND
        def events():
            for n in range(args.events):
                start=n*duration//args.events
                yield {
                    "event_id":f"action_{n:08d}",
                    "event_kind":"action",
                    "subject_id":"actor_a",
                    "start_tick":start,
                    "end_tick":start+1,
                    "source_id":"actor_source",
                    "source_revision":1,
                    "payload":{"kind":"transient","ordinal":n},
                }
        publish_s,_=timed(lambda:ledger.publish(
            pid,"feature_timeline",events(),duration_tick=duration))
        point_samples=[]
        interval_samples=[]
        expected_source=index.read_revision(
            pid,"feature_timeline",1)["document_sha256"]
        for n in range(250):
            # Query an exact event start, testing long duration near 3h too.
            tick=(n*args.events//250)*duration//args.events
            elapsed,result=timed(lambda:ledger.events_at(
                pid,"feature_timeline",1,tick=tick,limit=8))
            if len(result)!=1 or result[0]["start_tick"]!=tick:
                raise RuntimeError("Authoritative timed event lookup failed")
            point_samples.append(elapsed)
            begin=tick
            stop=min(duration,tick+duration//args.events*4)
            elapsed,page=timed(lambda:ledger.events_in(
                pid,"feature_timeline",1,start_tick=begin,
                end_tick=stop,limit=100))
            if not page["events"] or len(page["events"])>100:
                raise RuntimeError("Bounded timed event interval lookup failed")
            interval_samples.append(elapsed)
        verify_s,proof=timed(lambda:ledger.verify(
            pid,"feature_timeline",1))
        if (proof["event_count"]!=args.events or
            proof["document_sha256"]!=expected_source):
            raise RuntimeError("FilmIndex temporal manifest proof changed")
        data={
            "format":"nvp.temporal_scale_benchmark.v1",
            "events":args.events,
            "duration_seconds":args.duration_seconds,
            "timebase_ticks_per_second":TICKS_PER_SECOND,
            "frames_generated":0,
            "publish_and_transactional_source_proof_seconds":publish_s,
            "point_lookup_median_ms":1000*statistics.median(point_samples),
            "point_lookup_p95_ms":1000*sorted(point_samples)[237],
            "interval_lookup_median_ms":1000*statistics.median(interval_samples),
            "interval_lookup_p95_ms":1000*sorted(interval_samples)[237],
            "deliberate_full_provenance_verify_seconds":verify_s,
            "per_lookup_full_feature_scan":False,
            "source_revision_document_sha256":expected_source,
            "status":"MEASURED_NO_PIXEL_RENDERING",
        }
        out=Path(args.output).absolute()
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(data,indent=2,sort_keys=True),encoding="utf-8")
        print(json.dumps(data,indent=2,sort_keys=True))
        return data


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--events",type=int,default=10000)
    parser.add_argument("--duration-seconds",type=int,default=10800)
    parser.add_argument("--output",required=True)
    return run(parser.parse_args(argv))


if __name__=="__main__":
    main()
