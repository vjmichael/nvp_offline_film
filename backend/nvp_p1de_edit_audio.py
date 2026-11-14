"""P1-D/E selective bridge onto canonical DATA-AV FilmIndex and frozen OpenUSD Takes.

Uses exact integer Film Time, immutable FilmIndex edit revisions and verified
original PCM. Actor-owned dry stereo is a disposable native derivative, not a
new original recording, a flattened master, HRTF or a film deliverable.

The host must authenticate and consume a one-use creator authorization. No
browser/model token or UI affordance is an approval.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import struct

from backend.nvp_data_av_source import RecordedSoundSources, SAMPLE_RATE
from backend.nvp_data_av_scene import _pan
from backend.nvp_film_index import FilmIndex, _id, _sha, _require_pid
from backend.nvp_openusd_take import OpenUSDTakeCapture, FORMAT as TAKE_FORMAT
from backend.nvp_openusd_time_state import OpenUSDTimeState
from backend.nvp_original_clock_binding import verified_original_clock
from backend.nvp_independent_device_sync import interpolated_window
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND, _int

FORMAT = "nvp.p1de.source_edit_audio.v1"
SAMPLE_TICK = TICKS_PER_SECOND // SAMPLE_RATE
MAX_SEGMENTS = 48
MAX_ACTORS_PER_SEGMENT = 4
MAX_WINDOW_SAMPLES = 4096
MAX_EVENT_PAGES = 8


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _gain(value):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 2:
        raise ValueError("Actor sound level must be finite and between zero and two")
    return float(value)


def _read_take(index, pid, take_id, take_sha):
    _id(take_id, "source Take")
    _sha(take_sha)
    take = index.read_revision(pid, take_id, 1)
    doc = take["data"]
    if (take["kind"] != "take" or take["document_sha256"] != take_sha or
            doc.get("format") != TAKE_FORMAT or doc.get("frozen") is not True or
            doc.get("host_creator_action_verified") is not True or
            doc.get("ticks_per_second") != TICKS_PER_SECOND):
        raise RuntimeError("Source cut requires an unchanged approved frozen OpenUSD Take")
    proof = OpenUSDTakeCapture(
        index, verify_creator_action=lambda event, scope: False
    ).verify_take(pid, take_id)
    if proof["take_document_sha256"] != take_sha:
        raise RuntimeError("Frozen Take failed independent source verification")
    scene = index.read_revision(pid, doc["scene_id"], doc["scene_revision"])
    timeline = index.read_revision(pid, doc["timeline_id"], doc["timeline_revision"])
    if (scene["document_sha256"] != doc["scene_document_sha256"] or
            timeline["document_sha256"] != doc["timeline_document_sha256"]):
        raise RuntimeError("Frozen scene/timeline SHA is no longer authoritative")
    if TemporalLedger(index).verify(pid, doc["timeline_id"], doc["timeline_revision"])[
            "document_sha256"] != timeline["document_sha256"]:
        raise RuntimeError("Original sound event ledger was changed")
    return take, scene


def _sound_events(index, pid, take):
    doc = take["data"]
    clock = TemporalLedger(index)
    after = None
    found = []
    for _ in range(MAX_EVENT_PAGES):
        page = clock.events_in(pid, doc["timeline_id"], doc["timeline_revision"],
                               start_tick=0, end_tick=doc["duration_tick"],
                               limit=500, after=after)
        found.extend(e for e in page["events"]
                     if e["event_kind"] in ("sound", "dialogue"))
        after = page["next_cursor"]
        if after is None:
            return found
    raise RuntimeError("Original film event index exceeds bounded native admission")


def _bound_segments(index, pid, segments):
    if type(segments) is not list or not 1 <= len(segments) <= MAX_SEGMENTS:
        raise ValueError("Choose a bounded, nonempty source-edit sequence")
    sources = RecordedSoundSources(index)
    deps = {}
    ready = []
    cache = {}
    duration = 0
    for item in segments:
        if type(item) is not dict or set(item) != {
            "take_id", "take_sha256", "in_tick", "out_tick", "listener_path", "audio"
        }:
            raise ValueError("Edit needs exact Take, source interval, listener and actor audio")
        take_id = _id(item["take_id"], "edited Take ID")
        take_sha = _sha(item["take_sha256"])
        key = (take_id, take_sha)
        if key not in cache:
            take, scene = _read_take(index, pid, take_id, take_sha)
            events = _sound_events(index, pid, take)
            cache[key] = (take, scene, events)
        take, scene, events = cache[key]
        start = _int(item["in_tick"], "source cut start")
        end = _int(item["out_tick"], "source cut end", minimum=1)
        if (end <= start or end > take["data"]["duration_tick"] or
                start % SAMPLE_TICK or end % SAMPLE_TICK):
            raise ValueError("Sound-bearing edit cuts require exact native 48k sample boundaries")
        listener = item["listener_path"]
        if (type(listener) is not str or
                scene["data"].get("prim_roles", {}).get(listener) not in
                ("camera", "anchor", "actor")):
            raise ValueError("Virtual listener is not an original authored scene object")
        audio = item["audio"]
        if type(audio) is not list or len(audio) > MAX_ACTORS_PER_SEGMENT:
            raise ValueError("Too many actor-owned sounds in one source cut")
        audible = {e["event_id"]: e for e in events if e["event_kind"] == "dialogue"
                   and e["end_tick"] > start and e["start_tick"] < end}
        if len(audio) != len(audible):
            raise ValueError("Every overlapping actor dialogue needs an explicit sound decision")
        used = set()
        checked = []
        for decision in audio:
            if type(decision) is not dict or set(decision) != {
                "event_id", "actor_id", "source_id", "source_revision",
                "source_sha256", "enabled", "gain"
            }:
                raise ValueError("Actor audio decision has unrecognized source fields")
            eid = _id(decision["event_id"], "original sound event")
            actor = _id(decision["actor_id"], "original ActorID")
            sid = _id(decision["source_id"], "original PCM source")
            rev = _int(decision["source_revision"], "source revision", minimum=1)
            original_sha = _sha(decision["source_sha256"])
            event = audible.get(eid)
            if (event is None or eid in used or actor != event["subject_id"] or
                    sid != event["source_id"] or rev != event["source_revision"] or
                    original_sha != event["source_document_sha256"]):
                raise RuntimeError("ActorID or original PCM source substitution refused")
            path = event["payload"].get("usd_prim_path")
            if scene["data"]["prim_roles"].get(path) != "actor":
                raise RuntimeError("Dialogue emitter is not an original scene actor")
            record = sources.describe(pid, sid, rev)
            if record["document_sha256"] != original_sha:
                raise RuntimeError("Original mono PCM source SHA changed")
            if type(decision["enabled"]) is not bool:
                raise ValueError("Actor sound enabled must be an explicit boolean")
            # Read the initial bounded source window through verified PCM blobs.
            sources.read(pid, sid, rev, 0, min(16, record["data"]["sample_count"]))
            checked.append({
                "event_id": eid, "actor_id": actor, "source_id": sid,
                "source_revision": rev, "source_sha256": original_sha,
                "enabled": decision["enabled"], "gain": _gain(decision["gain"])
            })
            deps[(sid, rev, "audio")] = {
                "object_id": sid, "revision": rev, "role": "audio"
            }
            used.add(eid)
        deps[(take_id, 1, "source_take")] = {
            "object_id": take_id, "revision": 1, "role": "source_take"
        }
        deps[(take["data"]["timeline_id"], take["data"]["timeline_revision"], "temporal")] = {
            "object_id": take["data"]["timeline_id"],
            "revision": take["data"]["timeline_revision"], "role": "temporal"
        }
        ready.append({
            "take_id": take_id, "take_sha256": take_sha,
            "scene_sha256": scene["document_sha256"],
            "timeline_sha256": take["data"]["timeline_document_sha256"],
            "in_tick": start, "out_tick": end, "listener_path": listener,
            "audio": checked
        })
        duration += end - start
        if duration > 3 * 60 * 60 * TICKS_PER_SECOND:
            raise ValueError("This native edit exceeds the initial three-hour clock cap")
    if len(deps) > 128:
        raise ValueError("Edit needs paged source dependencies before it can be published")
    return ready, duration, list(deps.values())


class P1DEConform:
    """Trusted host-only bridge; source editing != worker or release authority."""

    def __init__(self, index: FilmIndex, *, approve_edit):
        if not isinstance(index, FilmIndex) or not callable(approve_edit):
            raise TypeError("Native FilmIndex and trusted creator approval are required")
        self.index = index
        self.approve_edit = approve_edit

    def publish(self, pid, edit_id, segments, *, expected_revision=0, creator_event):
        _require_pid(pid)
        _id(edit_id, "edit identity")
        _int(expected_revision, "expected edit revision")
        # Deep copy and revalidate across every user-supplied object, including
        # callbacks that could mutate the original payload during approval.
        frozen = json.loads(_canonical(segments))
        bound, duration, deps = _bound_segments(self.index, pid, frozen)
        doc = {
            "format": FORMAT, "ticks_per_second": TICKS_PER_SECOND,
            "sample_rate": SAMPLE_RATE, "segments": bound, "duration_tick": duration,
            "source_modified": False, "flattened_soundtrack": False,
            "picture_rendered": False, "master_approved": False
        }
        sha = _digest(doc)
        scope = {
            "operation": "nvp.p1de.publish_source_edit.v1",
            "project_id": pid, "edit_id": edit_id,
            "expected_revision": expected_revision,
            "source_edit_sha256": sha
        }
        if self.approve_edit(creator_event, dict(scope)) is not True:
            raise PermissionError("Creator did not approve this exact native source edit")

        def guard(db):
            for dep in deps:
                row = self.index._read_revision(
                    db, pid, dep["object_id"], dep["revision"])
                if row is None:
                    raise RuntimeError("Original edit source disappeared before publication")
                if dep["role"] == "source_take":
                    expected = next(x["take_sha256"] for x in bound
                                    if x["take_id"] == dep["object_id"])
                    if row["document_sha"] != expected:
                        raise RuntimeError("Original Take SHA changed before publication")
            if _digest(doc) != sha:
                raise RuntimeError("Approved edit mutated during publication")

        receipt = self.index.register_revision(
            pid, edit_id, "edit", doc,
            expected_revision=expected_revision, dependencies=deps,
            precommit_guard=guard)
        return {**receipt, "source_edit_sha256": sha,
                "duration_tick": duration, "source_modified": False}

    def read(self, pid, edit_id, revision=None):
        _require_pid(pid)
        row = self.index.read_revision(pid, edit_id, revision)
        if row["kind"] != "edit" or row["data"].get("format") != FORMAT:
            raise RuntimeError("Not a P1-D/E native source edit")
        doc = row["data"]
        source_segments = [
            {key: segment[key] for key in (
                "take_id", "take_sha256", "in_tick", "out_tick",
                "listener_path", "audio")}
            for segment in doc["segments"]
        ]
        bound, duration, deps = _bound_segments(self.index, pid, source_segments)
        if (bound != doc["segments"] or duration != doc["duration_tick"] or
                doc.get("ticks_per_second") != TICKS_PER_SECOND or
                doc.get("sample_rate") != SAMPLE_RATE or
                doc.get("source_modified") is not False or
                doc.get("flattened_soundtrack") is not False or
                doc.get("picture_rendered") is not False or
                doc.get("master_approved") is not False or
                sorted(deps, key=lambda x: (x["object_id"], x["revision"], x["role"])) !=
                row["dependencies"]):
            raise RuntimeError("Source edit record and approved dependencies differ")
        return {**row, "source_edit_sha256": _digest(doc)}

    def plan(self, pid, edit_id, revision, *, first_sample, count):
        """Exact bounded source-time plan for P1-F and future P2 workers."""
        start = _int(first_sample, "film audio sample")
        n = _int(count, "bounded film window", minimum=1, maximum=MAX_WINDOW_SAMPLES)
        record = self.read(pid, edit_id, revision)
        if (start + n) * SAMPLE_TICK > record["data"]["duration_tick"]:
            raise ValueError("Requested sound window crosses approved film end")
        slices = []
        cursor = 0
        for seg in record["data"]["segments"]:
            total = (seg["out_tick"] - seg["in_tick"]) // SAMPLE_TICK
            a = max(cursor, start)
            b = min(cursor + total, start + n)
            if a < b:
                slices.append({
                    "take_id": seg["take_id"], "take_sha256": seg["take_sha256"],
                    "source_first_sample": seg["in_tick"] // SAMPLE_TICK + (a - cursor),
                    "output_first_sample": a, "sample_count": b - a,
                    "listener_path": seg["listener_path"], "audio": seg["audio"]
                })
            cursor += total
            if cursor >= start + n:
                break
        if sum(x["sample_count"] for x in slices) != n:
            raise RuntimeError("Non-contiguous source conform")
        return {"edit_document_sha256": record["document_sha256"],
                "source_edit_sha256": record["source_edit_sha256"],
                "first_sample": start, "sample_count": n, "slices": slices}

    def audio_window(self, pid, edit_id, revision, *, first_sample, count):
        """Render true source-timed, actor-filtered stereo from verified OpenUSD/PCM.

        Does not create a file or accept a transport/worker command. Existing
        native OpenUSD evaluation supplies listener/emitter motion; each actor's
        original PCM is independently reread and preserved.
        """
        plan = self.plan(pid, edit_id, revision, first_sample=first_sample, count=count)
        sound = RecordedSoundSources(self.index)
        state = OpenUSDTimeState(self.index)
        left = [0.] * count
        right = [0.] * count
        for part in plan["slices"]:
            take = self.index.read_revision(pid, part["take_id"], 1)
            timeline = TemporalLedger(self.index)
            begin = part["source_first_sample"] * SAMPLE_TICK
            end = (part["source_first_sample"] + part["sample_count"]) * SAMPLE_TICK
            page = timeline.events_in(pid, take["data"]["timeline_id"],
                                      take["data"]["timeline_revision"],
                                      start_tick=begin, end_tick=end, limit=100)
            if page["next_cursor"] is not None:
                raise RuntimeError("Native sound-event page is incomplete")
            events = {ev["event_id"]: ev for ev in page["events"]
                      if ev["event_kind"] == "dialogue"}
            at_a = state.evaluate(pid, take["data"]["scene_id"],
                                  take["data"]["scene_revision"],
                                  take["data"]["timeline_id"],
                                  take["data"]["timeline_revision"], tick=begin)
            at_b = state.evaluate(pid, take["data"]["scene_id"],
                                  take["data"]["scene_revision"],
                                  take["data"]["timeline_id"],
                                  take["data"]["timeline_revision"], tick=end - 1)
            positions_a = {o["path"]: o["world_translation"] for o in at_a["objects"]}
            positions_b = {o["path"]: o["world_translation"] for o in at_b["objects"]}
            listener = part["listener_path"]
            if listener not in positions_a or listener not in positions_b:
                raise RuntimeError("Original virtual listening camera unavailable")
            if set(events) != {a["event_id"] for a in part["audio"]
                              if a["event_id"] in events}:
                raise RuntimeError("Native original dialogue does not match approved actor list")
            for choice in part["audio"]:
                if not choice["enabled"]:
                    continue
                ev = events.get(choice["event_id"])
                if ev is None:
                    continue
                if (ev["subject_id"] != choice["actor_id"] or
                        ev["source_id"] != choice["source_id"] or
                        ev["source_document_sha256"] != choice["source_sha256"]):
                    raise RuntimeError("Actor/source substitution during native mix")
                path = ev["payload"]["usd_prim_path"]
                if path not in positions_a or path not in positions_b:
                    raise RuntimeError("Original moving actor is not in the OpenUSD scene")
                source_count = sound.describe(
                    pid, choice["source_id"], choice["source_revision"]
                )["data"]["sample_count"]
                a = max(begin, ev["start_tick"])
                b = min(end, ev["end_tick"])
                first = max(0, (a + SAMPLE_TICK - 1) // SAMPLE_TICK)
                last = min((end // SAMPLE_TICK),
                           (b + SAMPLE_TICK - 1) // SAMPLE_TICK)
                if last <= first:
                    continue
                n = last - first
                clock = verified_original_clock(
                    self.index, pid, choice["source_id"],
                    ev["start_tick"], ev["end_tick"],
                    ev["payload"].get("source_sync"),
                    ev["payload"].get("clock_evidence"),
                    source_sample_count=source_count)
                if clock is None:
                    source_first = max(0, (first * SAMPLE_TICK -
                                           ev["start_tick"]) // SAMPLE_TICK)
                    n = min(n, source_count - source_first)
                    if n <= 0:
                        continue
                    raw = sound.read(pid, choice["source_id"],
                                     choice["source_revision"], source_first, n)
                    values = struct.unpack("<" + str(n) + "h", raw)
                else:
                    values = interpolated_window(
                        lambda pos, size: sound.read(
                            pid, choice["source_id"], choice["source_revision"],
                            pos, size),
                        source_count, clock, first * SAMPLE_TICK, n,
                        ticks_per_output_sample=SAMPLE_TICK)
                original_gain = _gain(ev["payload"].get("gain", 1.0))
                for i, sample in enumerate(values):
                    local = first + i - part["source_first_sample"]
                    offset = (part["output_first_sample"] - first_sample) + local
                    if not 0 <= offset < count:
                        raise RuntimeError("Native sound source cursor escaped edited window")
                    fraction = (local + .5) / part["sample_count"]
                    emitter = [
                        positions_a[path][j] +
                        (positions_b[path][j] - positions_a[path][j]) * fraction
                        for j in range(3)]
                    listener_pos = [
                        positions_a[listener][j] +
                        (positions_b[listener][j] - positions_a[listener][j]) * fraction
                        for j in range(3)]
                    gl, gr = _pan(emitter, listener_pos,
                                  original_gain * choice["gain"])
                    left[offset] += sample * gl
                    right[offset] += sample * gr
        pcm = bytearray(count * 4)
        for i in range(count):
            struct.pack_into("<hh", pcm, i * 4,
                             max(-32768, min(32767, round(left[i]))),
                             max(-32768, min(32767, round(right[i]))))
        out = bytes(pcm)
        return {"format": "nvp.p1de.derived_stereo_window.v1",
                "first_sample": first_sample, "sample_count": count,
                "channels": 2, "sample_rate": SAMPLE_RATE,
                "pcm_sha256": hashlib.sha256(out).hexdigest(),
                "pcm_base64": base64.b64encode(out).decode("ascii"),
                "edit_document_sha256": plan["edit_document_sha256"],
                "source_modified": False, "master_approved": False,
                "renderer": "native_verified_OpenUSD_actor_PCM_dry_stereo"}
