"""PLAN-02-B: typed, immutable evidence for independent original PCM clocks.

An attached ADC sample-to-Film-Time mapping is accepted ONLY if it matches
a separately source-hashed FilmIndex clock evidence revision and the exact
source sample count/PCM digest. Missing or forged evidence must fail closed.
This is a derived playback clock, never a modified original audio source.
"""
from __future__ import annotations

import re

from backend.nvp_film_index import _id,_sha
from backend.nvp_independent_device_sync import (
    FORMAT, _digest, verified_source_map)

SHA=re.compile(r"^[a-f0-9]{64}$")


def verified_original_clock(index,project_id,source_id,start_tick,end_tick,
                            source_sync,clock_evidence, *,
                            source_sample_count=None,original_pcm_sha256=None):
    if source_sync is None and clock_evidence is None:
        return None
    if (type(source_sync) is not dict or type(clock_evidence) is not dict or
            set(clock_evidence)!={"object_id","document_sha256"}):
        raise RuntimeError("Independent source requires exact clock evidence")
    evidence_id=_id(clock_evidence["object_id"],"independent clock evidence")
    evidence_sha=_sha(clock_evidence["document_sha256"])
    record=index.read_revision(project_id,evidence_id,1)
    data=record["data"]
    if (record["kind"]!="audio" or record["document_sha256"]!=evidence_sha or
            data.get("format")!=FORMAT or
            data.get("original_pcm_unmodified") is not True or
            data.get("hardware_genlocked") is not False or
            data.get("timing_physically_certified") is not False or
            data.get("creator_approved_recording") is not False):
        raise RuntimeError("Independent original clock source was changed or falsely certified")
    ids=data.get("source_ids")
    maps=data.get("sample_maps")
    models=data.get("clock_models")
    digests=data.get("original_mono_pcm_sha256")
    if (type(ids) is not list or len(ids)!=2 or len(set(ids))!=2 or
            type(maps) is not list or len(maps)!=2 or
            type(models) is not list or len(models)!=2 or
            type(digests) is not list or len(digests)!=2 or
            source_id not in ids):
        raise RuntimeError("Independent clock source catalog is inconsistent")
    i=ids.index(source_id)
    model=models[i]
    expected=maps[i]
    if (source_sync!=expected or type(model) is not dict or
            expected.get("source_clock_model_sha256")!=_digest(model) or
            expected.get("device_id")!=model.get("device_id") or
            expected.get("source_sample_count")!=model.get("source_sample_count") or
            type(digests[i]) is not str or not SHA.fullmatch(digests[i])):
        raise RuntimeError("Independent ADC source map or original sound hash is forged")
    if type(start_tick) is not int or type(end_tick) is not int:
        raise RuntimeError("Original source event lost exact Film Time")
    count=expected["source_sample_count"] if source_sample_count is None else source_sample_count
    verified_source_map(expected,source_sample_count=count,
                        event_start=start_tick,event_end=end_tick)
    if original_pcm_sha256 is not None:
        if type(original_pcm_sha256) is not str or original_pcm_sha256!=digests[i]:
            raise RuntimeError("Original independent PCM source changed after clock seal")
    return expected
