"""INT-01C: exact G06/FilmIndex source-identity and G07/G09 render guards.

Pure synthetic receipts here do NOT claim physical microphone, real Lu,
installed Windows, Linux private-film confinement, or 30-minute acceptance.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import sqlite3

import pytest

from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from backend.nvp_g06_filming import G06Filming, TAKE_FORMAT
from backend.nvp_int01c_source_contract import (
    FORMAT, G06_TAKE, SAMPLE_TICKS, g06_binding,
    check_render_take, verify_render_assembly)


PID = "a" * 32
FOREIGN = "b" * 32
TID = "c" * 32
SCENE = "scene_g06_original"
CLIP = "d" * 32
ACTOR = "ACT_SOURCE_DIRECTOR"
OBJECT = "O_001122334455"


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _sha(value):
    return sha256(value).hexdigest()


def source():
    raw = (b"#usda 1.0\n"
           b'def Xform "World" { def Xform "Objects" {} }\n')
    acting = raw + b"\n# immutable source performance"
    pcm = b"\x03\x00\xfc\xff" * 480
    duration = TICKS_PER_SECOND * 2
    entry = {"clip_id": CLIP, "actor_id": ACTOR,
             "emitter_path": "/World/Objects/" + OBJECT,
             "emitter_position": [0., 0., 0.],
             "pcm_sha256": _sha(pcm),
             "sample_rate": 48000, "channels": 1,
             "sample_count": len(pcm)//2, "start_tick": 0,
             "duration_tick": len(pcm)//2 * SAMPLE_TICKS}
    doc = {"format": TAKE_FORMAT, "project_id": PID,
           "immutable": True, "source_is_original_openusd": True,
           "camera_tracks_frozen": False,
           "tick_rate": TICKS_PER_SECOND,
           "scene_id": SCENE, "source_stage_revision": 2,
           "scene_source_sha256": "1"*64,
           "original_usd_sha256": _sha(raw),
           "performance_usd_sha256": _sha(acting),
           "duration_tick": duration,
           "stage_setting": {"season":"summer","weather":"clear"},
           "stage_objects": [
               {"id": OBJECT, "role": "actor", "actor_id": ACTOR},
               {"id": "O_abcd98765432", "role": "prop", "actor_id": None}
           ],
           "events": [{"start_tick": 0, "end_tick": SAMPLE_TICKS*12,
                       "object_id": OBJECT, "actor_id": ACTOR}],
           "audio": [entry]}
    row = {"project_id": PID, "take_id": TID,
           "scene_id": SCENE, "source_stage_revision": 2,
           "source_sha256": "1"*64,
           "original_usd_sha256": _sha(raw),
           "performance_usd_sha256": _sha(acting),
           "take_sha256": _sha(_json(doc).encode("utf8"))}
    loaded = {"project_id": PID, "scene_id": SCENE,
              "take_id": TID, "take_sha256": row["take_sha256"],
              "original_usd": raw, "performance_usd": acting,
              "original_sha256": _sha(raw),
              "performance_sha256": _sha(acting),
              "duration_tick": duration,
              "events": doc["events"],
              "stage_objects": doc["stage_objects"],
              "stage_setting": doc["stage_setting"],
              "audio": [{**entry, "pcm16le": pcm}]}
    return row, doc, [entry], loaded


def bound_assembly():
    row, doc, sound, loaded = source()
    binding = g06_binding(PID,TID,row,doc,sound)
    loaded["source_binding"] = binding
    keys = {TID: binding["binding_sha256"]}
    return {"project_id": PID,
            "source_provenance": {
                "format": "nvp.int01c.source_provenance.v1",
                "project_id": PID,
                "take_binding_hashes": keys,
                "take_bindings_sha256": _sha(_json(keys).encode("utf8")),
                "all_source_take_count": 1},
            "all_source_take_count": 1,
            "loaded_source_take_count": 1,
            "window": None,
            "segments": [{
                "take_id": TID,"scene_id": SCENE,
                "take_sha256": row["take_sha256"],
                "start_tick": 0,"end_tick": TICKS_PER_SECOND,
                "source_in_tick": 0,"source_out_tick": TICKS_PER_SECOND}],
            "original_takes": {TID: loaded}}


def test_exact_g06_actor_pcm_and_clock_binding_roundtrip():
    row,doc,audio,take=source()
    binding=g06_binding(PID,TID,row,doc,audio)
    assert binding["format"]==FORMAT
    assert binding["scene_id"]==SCENE
    assert binding["sample_ticks"]==SAMPLE_TICKS
    assert binding["audio"][0]["actor_id"]==ACTOR
    assert binding["audio"][0]["duration_tick"]==len(take["audio"][0]["pcm16le"])//2*SAMPLE_TICKS
    assert verify_render_assembly(bound_assembly(),require_bindings=True)


@pytest.mark.parametrize("change",[
    lambda row,doc,audio: doc.update(project_id=FOREIGN),
    lambda row,doc,audio: doc.update(duration_tick=TICKS_PER_SECOND),
    lambda row,doc,audio: doc["events"][0].update(actor_id="ACT_FOREIGN"),
    lambda row,doc,audio: audio[0].update(emitter_path="/World"),
    lambda row,doc,audio: audio[0].update(duration_tick=SAMPLE_TICKS),
    lambda row,doc,audio: doc["stage_objects"][0].update(actor_id=None),
])
def test_corrupt_or_foreign_source_identity_fails_closed(change):
    row,doc,audio,_=source()
    change(row,doc,audio)
    with pytest.raises(RuntimeError):
        g06_binding(PID,TID,row,doc,audio)


def test_modified_original_usd_rejected_even_when_source_binding_remains():
    assembly=bound_assembly()
    assembly["original_takes"][TID]["performance_usd"]+=b"\n# changed"
    with pytest.raises(RuntimeError,match="OpenUSD"):
        verify_render_assembly(assembly,require_bindings=True)


def test_original_pcm_byte_actor_and_emitter_replacement_rejected():
    for replacement in ({"pcm16le": b"\x00"*1920},
                        {"actor_id": "ACT_FOREIGN"},
                        {"emitter_path": "/World"}):
        assembly=bound_assembly()
        assembly["original_takes"][TID]["audio"][0].update(replacement)
        with pytest.raises(RuntimeError):
            verify_render_assembly(assembly,require_bindings=True)


def test_world_events_and_actor_roster_tamper_rejected():
    for key,updated in (
        ("events",[{"start_tick":0,"end_tick":100,"object_id":OBJECT,
                    "actor_id":"ACT_FOREIGN"}]),
        ("stage_objects",[]),
        ("stage_setting",{"season":"winter"})):
        assembly=bound_assembly()
        assembly["original_takes"][TID][key]=updated
        with pytest.raises(RuntimeError,match="source world"):
            verify_render_assembly(assembly,require_bindings=True)


def test_cross_project_source_and_manifest_sha_tampering_refused():
    for change in (
        lambda x:x.update(project_id=FOREIGN),
        lambda x:x["source_provenance"].update(project_id=FOREIGN),
        lambda x:x["source_provenance"]["take_binding_hashes"].update(
            {TID:"0"*64}),
        lambda x:x["source_provenance"].update(all_source_take_count=2),
        lambda x:x["original_takes"][TID]["source_binding"].update(
            scene_id=FOREIGN),
    ):
        assembly=bound_assembly()
        change(assembly)
        with pytest.raises(RuntimeError):
            verify_render_assembly(assembly,require_bindings=True)


def test_edit_window_cannot_substitute_foreign_take_or_time():
    for mutate in (
        lambda seg:seg.update(scene_id=FOREIGN),
        lambda seg:seg.update(source_out_tick=TICKS_PER_SECOND*3),
        lambda seg:seg.update(take_sha256="0"*64),
        lambda seg:seg.update(start_tick="0"),
        lambda seg:seg.update(end_tick=-1),
    ):
        assembly=bound_assembly()
        mutate(assembly["segments"][0])
        with pytest.raises(RuntimeError):
            verify_render_assembly(assembly,require_bindings=True)


def test_older_synthetic_codec_fixture_is_not_a_trusted_production_source():
    assert verify_render_assembly({"original_takes": {}}) is False
    with pytest.raises(RuntimeError,match="requires G06 source provenance"):
        verify_render_assembly({"original_takes": {}},require_bindings=True)


def test_g06_metadata_reader_reuses_same_exact_source_contract():
    row,doc,audio,take=source()
    db=sqlite3.connect(":memory:")
    try:
        db.row_factory=sqlite3.Row
        G06Filming._schema(db)
        db.execute("""INSERT INTO g06_original_pcm(
            id,project_id,scene_id,actor_id,source_kind,pcm,
            pcm_sha256,sample_rate,channels,sample_count,recorded_at)
            VALUES(?,?,?,?,'native_microphone_pcm16le',?,?,?,?,?,?)""",
            (CLIP,PID,SCENE,ACTOR,take["audio"][0]["pcm16le"],
             audio[0]["pcm_sha256"],48000,1,audio[0]["sample_count"],
             "native-test"))
        db.execute("""INSERT INTO g06_frozen_takes(
            take_id,project_id,scene_id,source_stage_revision,
            source_sha256,original_usd_sha256,original_usd,
            performance_usd_sha256,performance_usd,performance_json,
            audio_json,take_sha256,frozen_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (TID,PID,SCENE,2,row["source_sha256"],
             row["original_usd_sha256"],take["original_usd"],
             row["performance_usd_sha256"],take["performance_usd"],
             _json(doc),_json(audio),row["take_sha256"],"native-test"))
        filming=G06Filming.__new__(G06Filming)
        observed,original,original_audio=filming._take_metadata(db,PID,TID)
        assert g06_binding(PID,TID,observed,original,original_audio)[
            "binding_sha256"]==g06_binding(PID,TID,row,doc,audio)[
            "binding_sha256"]
        db.execute("""UPDATE g06_original_pcm SET actor_id=?
            WHERE id=?""",("ACT_OTHER",CLIP))
        with pytest.raises(RuntimeError,match="identity"):
            filming._take_metadata(db,PID,TID)
        db.execute("""UPDATE g06_original_pcm SET actor_id=?,channels=?
            WHERE id=?""",(ACTOR,2,CLIP))
        with pytest.raises(RuntimeError,match="identity"):
            filming._take_metadata(db,PID,TID)
        db.execute("""UPDATE g06_original_pcm SET channels=?,sample_rate=?
            WHERE id=?""",(1,44100,CLIP))
        with pytest.raises(RuntimeError,match="identity"):
            filming._take_metadata(db,PID,TID)
    finally:
        db.close()


def test_real_private_reel_worker_refuses_unbound_g06_source_without_ci_scope():
    from unittest.mock import patch
    from backend.nvp_g09e_sealed_worker import (
        _serialize_window,ProtectedFilmReelError)
    with patch.dict("os.environ",{
        "GITHUB_ACTIONS":"false",
        "NVP_W1F_TEST_APPROVAL":"CI_SOURCE_ONLY"}):
        with pytest.raises(ProtectedFilmReelError,match="authenticated original"):
            _serialize_window({"original_takes":{}},0,1,1,{})


def test_canonical_compare_requires_real_host_scope_even_for_ordinary_movie():
    filming=G06Filming.__new__(G06Filming)
    class G04:
        live=None
    class G05:
        g04=G04()
    filming.g05=G05()
    with pytest.raises(PermissionError,match="Trusted host"):
        filming.compare_canonical_source(PID,TID,"canonical-take",object())
    with pytest.raises(PermissionError,match="Trusted host"):
        filming.compare_canonical_source(PID,TID,"canonical-take",object(),
            source_authority=lambda project,operation: False)


def test_canonical_filmindex_cannot_be_called_from_locked_g06_film():
    filming=G06Filming.__new__(G06Filming)
    class G04:
        live=object()
    class G05:
        g04=G04()
    filming.g05=G05()
    with pytest.raises(PermissionError,match="Protected films"):
        filming.compare_canonical_source(PID,TID,"canonical-take",object())
