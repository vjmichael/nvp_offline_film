"""DATA-TIME-01: frame-independent authoritative film event timeline.

A film is an indexed history of actions, dialogue, camera, lighting and world
changes. Frame/sample grids are derived only at presentation/output boundaries.
Immutable event revisions and exact FilmIndex source SHA references are
published together in one SQLite transaction.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from backend.nvp_film_index import FilmIndex, _id, _require_pid

FORMAT = "nvp.temporal.events.v1"
# Integer tick timebase covers 44.1/48/96/192 kHz and popular fractional
# video cadences exactly, without deciding a film's actual delivery FPS.
TICKS_PER_SECOND = 7_056_000_000
MAX_TICK = 2**63 - 1
MAX_EVENT_JSON = 4096
MAX_QUERY = 500
KINDS = frozenset({
    "action", "gesture", "expression", "dialogue", "camera", "lighting",
    "prop", "world", "sound", "music", "cut", "annotation",
})


def _int(value, name, *, minimum=0, maximum=MAX_TICK):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid " + name)
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def tick_from_frame(frame_zero, fps_num, fps_den):
    """Exact output sampling time. Nonrepresentable rates must be explicit."""
    _int(frame_zero, "frame index")
    _int(fps_num, "fps numerator", minimum=1)
    _int(fps_den, "fps denominator", minimum=1)
    numerator = frame_zero * TICKS_PER_SECOND * fps_den
    tick, rem = divmod(numerator, fps_num)
    if rem or tick > MAX_TICK:
        raise ValueError("Requested output cadence is not exact in NVP v1 ticks")
    return tick


def frame_at_tick(tick, fps_num, fps_den, *, rounding="floor"):
    """Output projection, never an underlying authoritative event coordinate."""
    _int(tick, "timeline tick")
    _int(fps_num, "fps numerator", minimum=1)
    _int(fps_den, "fps denominator", minimum=1)
    numerator, denominator = tick * fps_num, TICKS_PER_SECOND * fps_den
    q, r = divmod(numerator, denominator)
    if rounding == "floor":
        return q
    if rounding == "ceil":
        return q + bool(r)
    if rounding == "exact":
        if r:
            raise ValueError("Event time lies between output frame boundaries")
        return q
    raise ValueError("Unknown explicit output rounding mode")


class TemporalLedger:
    """Native trusted-host metadata index; not a creator authorization API."""

    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Authoritative FilmIndex required")
        self.index = index
        with self.index.studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS nvp_temporal_events (
                project_id TEXT NOT NULL,
                timeline_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision > 0),
                event_id TEXT NOT NULL,
                event_kind TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                start_tick INTEGER NOT NULL CHECK(start_tick >= 0),
                end_tick INTEGER NOT NULL CHECK(end_tick >= start_tick),
                source_id TEXT NOT NULL,
                source_revision INTEGER NOT NULL CHECK(source_revision > 0),
                source_document_sha256 TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(project_id,timeline_id,revision,event_id)
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS nvp_event_time_seek
                ON nvp_temporal_events(project_id,timeline_id,revision,
                                        start_tick,end_tick,event_id)""")
            db.execute("""CREATE INDEX IF NOT EXISTS nvp_event_kind_subject_seek
                ON nvp_temporal_events(project_id,timeline_id,revision,
                                        event_kind,subject_id,start_tick)""")
            db.execute("""CREATE INDEX IF NOT EXISTS nvp_event_source_dependents
                ON nvp_temporal_events(project_id,source_id,source_revision,
                                        timeline_id,revision)""")

    def publish(self, project_id, timeline_id, events, *,
                duration_tick, expected_revision=0):
        _require_pid(project_id)
        _id(timeline_id, "temporal timeline identity")
        _int(duration_tick, "duration", minimum=1)
        _int(expected_revision, "expected revision")
        revision = expected_revision + 1
        with tempfile.TemporaryDirectory(prefix="nvp-events-") as tmp:
            staged = sqlite3.connect(Path(tmp) / "timed.sqlite")
            try:
                staged.execute("""CREATE TABLE source_events (
                    event_id TEXT PRIMARY KEY, event_kind TEXT NOT NULL,
                    subject_id TEXT NOT NULL, start_tick INTEGER NOT NULL,
                    end_tick INTEGER NOT NULL, source_id TEXT NOT NULL,
                    source_revision INTEGER NOT NULL,
                    source_document_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL)""")
                source_refs = {}
                count = 0
                for event in events:
                    if type(event) is not dict or set(event) != {
                        "event_id", "event_kind", "subject_id", "start_tick",
                        "end_tick", "source_id", "source_revision", "payload"
                    }:
                        raise ValueError("Event must contain exact typed timing and source fields")
                    eid = _id(event["event_id"], "event ID")
                    sid = _id(event["source_id"], "event source")
                    subject = _id(event["subject_id"], "event subject")
                    kind = event["event_kind"]
                    if kind not in KINDS:
                        raise ValueError("Unrecognized authored film event kind")
                    start = _int(event["start_tick"], "event start")
                    end = _int(event["end_tick"], "event end")
                    if end < start or start >= duration_tick or end > duration_tick:
                        raise ValueError("Event lies outside authoritative film time")
                    src_rev = _int(event["source_revision"], "source revision", minimum=1)
                    payload = event["payload"]
                    if type(payload) is not dict:
                        raise ValueError("Event payload must be structured data")
                    raw = _canonical(payload)
                    if len(raw) > MAX_EVENT_JSON:
                        raise ValueError("Event payload too large")
                    if sid == timeline_id:
                        raise ValueError("No circular timeline source reference")
                    key = (sid, src_rev)
                    if key not in source_refs:
                        record = self.index.read_revision(project_id, sid, src_rev)
                        source_refs[key] = record["document_sha256"]
                    staged.execute("INSERT INTO source_events VALUES (?,?,?,?,?,?,?,?,?)",
                                   (eid, kind, subject, start, end, sid, src_rev,
                                    source_refs[key], raw.decode("ascii")))
                    count += 1
                if not count:
                    raise ValueError("An authored timeline requires at least one event")
                staged.commit()
                digest = hashlib.sha256()
                for row in staged.execute("""SELECT event_id,event_kind,subject_id,
                    start_tick,end_tick,source_id,source_revision,
                    source_document_sha256,payload_json FROM source_events
                    ORDER BY start_tick,event_id"""):
                    digest.update(_canonical(list(row)) + b"\n")
                seal = digest.hexdigest()
                doc = {
                    "format": FORMAT, "ticks_per_second": TICKS_PER_SECOND,
                    "duration_tick": duration_tick, "event_count": count,
                    "event_manifest_sha256": seal,
                    "authority": "authored_action_time_not_output_frames",
                    "creator_approved": False,
                    "presentation_frames_rendered": False,
                }

                def guard(db):
                    confirmed = hashlib.sha256()
                    copied = 0
                    for row in staged.execute("""SELECT event_id,event_kind,subject_id,
                        start_tick,end_tick,source_id,source_revision,
                        source_document_sha256,payload_json FROM source_events
                        ORDER BY start_tick,event_id"""):
                        eid, kind, subject, start, end, sid, sr, sha, payload = row
                        source = self.index._read_revision(db, project_id, sid, sr)
                        if source is None or source["document_sha"] != sha:
                            raise RuntimeError("Immutable event source revision changed")
                        db.execute("""INSERT INTO nvp_temporal_events
                            (project_id,timeline_id,revision,event_id,event_kind,
                             subject_id,start_tick,end_tick,source_id,
                             source_revision,source_document_sha256,payload_json)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (project_id,timeline_id,revision,eid,kind,subject,
                             start,end,sid,sr,sha,payload))
                        confirmed.update(_canonical(list(row)) + b"\n")
                        copied += 1
                    if copied != count or confirmed.hexdigest() != seal:
                        raise RuntimeError("Timed event staging changed before FilmIndex commit")
                return self.index.register_revision(
                    project_id, timeline_id, "temporal", doc,
                    expected_revision=expected_revision, dependencies=[],
                    precommit_guard=guard)
            finally:
                staged.close()

    def _revision(self, project_id, timeline_id, revision):
        record = self.index.read_revision(project_id,timeline_id,revision)
        if (record["kind"] != "temporal" or
            record["data"].get("format") != FORMAT or
            record["data"].get("ticks_per_second") != TICKS_PER_SECOND):
            raise RuntimeError("Not an NVP authored temporal source timeline")
        return record

    def events_at(self, project_id, timeline_id, revision, *, tick, limit=100,
                  event_kind=None, subject_id=None):
        """Query actions active at a moment plus instantaneous actions at tick."""
        _int(tick,"time tick")
        _int(limit,"result limit",minimum=1,maximum=MAX_QUERY)
        if event_kind is not None and event_kind not in KINDS:
            raise ValueError("Unknown event kind")
        if subject_id is not None:
            _id(subject_id, "event subject filter")
        self._revision(project_id,timeline_id,revision)
        with self.index.studio._connection() as db:
            rows=db.execute("""SELECT event_id,event_kind,subject_id,start_tick,
                end_tick,source_id,source_revision,source_document_sha256,payload_json
                FROM nvp_temporal_events
                WHERE project_id=? AND timeline_id=? AND revision=?
                  AND start_tick <= ? AND end_tick >= ?
                  AND (end_tick > ? OR start_tick=end_tick)
                  AND (? IS NULL OR event_kind=?)
                  AND (? IS NULL OR subject_id=?)
                ORDER BY start_tick,event_id LIMIT ?""",
                (project_id,timeline_id,revision,tick,tick,tick,
                 event_kind,event_kind,subject_id,subject_id,limit)).fetchall()
        return [self._display(r) for r in rows]

    def events_in(self, project_id, timeline_id, revision, *, start_tick,
                  end_tick, limit=100, after=None):
        """Page sparse events overlapping [start,end); no frame expansion."""
        start = _int(start_tick, "range start")
        end = _int(end_tick, "range end")
        _int(limit, "page size", minimum=1, maximum=MAX_QUERY)
        if end <= start:
            raise ValueError("Requested event interval must be positive")
        self._revision(project_id,timeline_id,revision)
        if after is None:
            cursor_tick,cursor_id = -1, ""
        else:
            if type(after) is not tuple or len(after)!=2:
                raise ValueError("Cursor must be exact (start_tick,event_id)")
            cursor_tick = _int(after[0], "cursor tick")
            cursor_id = _id(after[1],"cursor event")
        with self.index.studio._connection() as db:
            rows=db.execute("""SELECT event_id,event_kind,subject_id,start_tick,
                end_tick,source_id,source_revision,source_document_sha256,payload_json
                FROM nvp_temporal_events
                WHERE project_id=? AND timeline_id=? AND revision=?
                  AND start_tick < ?
                  AND (end_tick > ? OR (start_tick=end_tick AND start_tick >= ?))
                  AND (start_tick > ? OR
                       (start_tick = ? AND event_id > ?))
                ORDER BY start_tick,event_id LIMIT ?""",
                (project_id,timeline_id,revision,end,start,start,
                 cursor_tick,cursor_tick,cursor_id,limit)).fetchall()
        events=[self._display(r) for r in rows]
        next_cursor=((events[-1]["start_tick"],events[-1]["event_id"])
                     if len(events)==limit else None)
        return {"events": events, "next_cursor": next_cursor}

    @staticmethod
    def _display(row):
        event_id,kind,subject,start,end,sid,rev,sha,payload=row
        return {"event_id":event_id,"event_kind":kind,"subject_id":subject,
                "start_tick":start,"end_tick":end,"source_id":sid,
                "source_revision":rev,"source_document_sha256":sha,
                "payload":json.loads(payload)}

    def event_by_id(self,project_id,timeline_id,revision,event_id):
        """One exact indexed original event, even after 500+ source cues.

        Film Time and Audio source authority remain the original sealed
        timeline manifest and immutable FilmIndex source revision. Never
        interpret a truncated time-window result as the whole film.
        """
        _id(event_id,"source event identity")
        self.verify(project_id,timeline_id,revision)
        with self.index.studio._connection() as db:
            row=db.execute("""SELECT event_id,event_kind,subject_id,
                start_tick,end_tick,source_id,source_revision,
                source_document_sha256,payload_json FROM nvp_temporal_events
                WHERE project_id=? AND timeline_id=? AND revision=?
                  AND event_id=?""",
                (project_id,timeline_id,revision,event_id)).fetchone()
        if row is None:
            raise KeyError("Original timeline event does not exist")
        event=self._display(row)
        source=self.index.read_revision(
            project_id,event["source_id"],event["source_revision"])
        if source["document_sha256"]!=event["source_document_sha256"]:
            raise RuntimeError("Original indexed event source changed")
        return event

    def verify(self, project_id,timeline_id,revision):
        record=self._revision(project_id,timeline_id,revision)
        digest=hashlib.sha256()
        count=0
        with self.index.studio._connection() as db:
            for row in db.execute("""SELECT event_id,event_kind,subject_id,
                start_tick,end_tick,source_id,source_revision,
                source_document_sha256,payload_json FROM nvp_temporal_events
                WHERE project_id=? AND timeline_id=? AND revision=?
                ORDER BY start_tick,event_id""",
                (project_id,timeline_id,revision)):
                sid,sr,sha=row[5:8]
                proof=db.execute("""SELECT document_sha FROM film_object_revisions
                    WHERE project_id=? AND object_id=? AND revision=?""",
                    (project_id,sid,sr)).fetchone()
                if proof is None or proof["document_sha"]!=sha:
                    raise RuntimeError("Timed source identity altered")
                digest.update(_canonical(list(row))+b"\n")
                count+=1
        if count!=record["data"]["event_count"] or (
            digest.hexdigest()!=record["data"]["event_manifest_sha256"]):
            raise RuntimeError("Immutable authored timeline manifest mismatch")
        return {"status":"VERIFIED_INDEXED_EVENT_PROVENANCE",
                "event_count":count,"document_sha256":record["document_sha256"],
                "rendered_frames":False}
