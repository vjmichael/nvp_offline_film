"""DA-03 durable visibility ledger for non-atomic filming publication.

This does NOT make FilmIndex's separate immutable revisions atomic. It makes
an interrupted multi-object publication discoverable after process restart,
without deleting source history or inventing a creator-approved Take.
"""
from __future__ import annotations

import json
from backend.nvp_film_index import _id, _require_pid
from backend.nvp_studio import now
from backend.nvp_temporal_ledger import TemporalLedger, MAX_QUERY, TICKS_PER_SECOND
from backend.nvp_data_av_source import SAMPLE_RATE, FORMAT as ORIGINAL_PCM_FORMAT


class FilmingPublicationJournal:
    def __init__(self, index):
        self.index = index
        with index.studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS nvp_filming_publications (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                take_id TEXT NOT NULL,
                sound_timeline_id TEXT NOT NULL,
                source_ids_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN
                    ('PREPARING','INTERRUPTED','COMPLETED')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id,take_id))""")

    def begin(self, project_id, take_id, sound_timeline_id, source_ids):
        _require_pid(project_id)
        _id(take_id, "filming take")
        _id(sound_timeline_id, "filming timeline")
        if (type(source_ids) is not list or not source_ids or
            len(set(source_ids)) != len(source_ids)):
            raise ValueError("Expected distinct original sound sources")
        if take_id == sound_timeline_id or take_id in source_ids or sound_timeline_id in source_ids:
            raise ValueError("Filming publication identities must be distinct")
        for sid in source_ids:
            _id(sid, "filming source")
        with self.index.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.index._project(db, project_id)
            # A second batch must not claim an identity already reserved by a
            # different batch, including completed and interrupted batches.
            # Keep reservations for historical provenance; never silently reuse
            # a source or timeline after a crash.
            existing = db.execute("""SELECT take_id,sound_timeline_id,source_ids_json
                FROM nvp_filming_publications WHERE project_id=?""",
                (project_id,)).fetchall()
            claimed = {take_id, sound_timeline_id, *source_ids}
            # Reserve against the actual FilmIndex namespace too. A legacy
            # source or a non-journal writer may already own revision 1;
            # journal-only collision checks cannot detect that identity.
            # BEGIN IMMEDIATE serializes SQLite writers through admission.
            for identity in claimed:
                try:
                    self.index.read_revision(project_id, identity, 1)
                except KeyError:
                    pass
                else:
                    raise ValueError("Filming publication identity already exists in FilmIndex")
            for prior in existing:
                reserved = {prior["take_id"], prior["sound_timeline_id"],
                            *json.loads(prior["source_ids_json"])}
                if claimed.intersection(reserved):
                    raise ValueError("Filming publication identity reserved by another batch")
            db.execute("""INSERT INTO nvp_filming_publications
                (project_id,take_id,sound_timeline_id,source_ids_json,state,updated_at)
                VALUES(?,?,?,?,'PREPARING',?)""",
                (project_id,take_id,sound_timeline_id,
                 json.dumps(source_ids, separators=(",",":")),now()))

    def finish(self, project_id, take_id, *, completed):
        _require_pid(project_id)
        _id(take_id, "filming take")
        state = "COMPLETED" if completed else "INTERRUPTED"
        # Hold the SQLite writer reservation throughout dependency validation
        # and the terminal-state update. Previously validation used a separate
        # connection before BEGIN IMMEDIATE, allowing an interleaved writer to
        # change the observed publication state between those operations.
        with self.index.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT sound_timeline_id,source_ids_json
                FROM nvp_filming_publications WHERE project_id=? AND take_id=?
                AND state='PREPARING'""", (project_id,take_id)).fetchone()
            if row is None:
                raise RuntimeError("Filming publication journal state conflict")
            if completed:
                identities = [take_id,row["sound_timeline_id"],
                              *json.loads(row["source_ids_json"])]
                for identity in identities:
                    try:
                        self.index.read_revision(project_id,identity,1)
                    except KeyError as exc:
                        raise RuntimeError(
                            "Cannot complete filming publication with missing immutable dependencies"
                        ) from exc
            cur = db.execute("""UPDATE nvp_filming_publications
                SET state=?,updated_at=? WHERE project_id=? AND take_id=?
                AND state='PREPARING'""", (state,now(),project_id,take_id))
            if cur.rowcount != 1:
                raise RuntimeError("Filming publication journal state conflict")

    def interrupt_preparing(self, project_id, take_id, *, expected_updated_at):
        """Explicit recovery transition after independent worker-termination proof.

        The caller must establish OS custody and worker termination separately.
        Compare-and-set prevents a stale recovery observer from interrupting a
        publication whose journal has since advanced. Never delete or approve
        immutable FilmIndex revisions during recovery.
        """
        _require_pid(project_id)
        _id(take_id, "filming take")
        if not isinstance(expected_updated_at, str) or not expected_updated_at:
            raise ValueError("Expected observed publication timestamp")
        with self.index.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.index._project(db, project_id)
            cur = db.execute("""UPDATE nvp_filming_publications
                SET state='INTERRUPTED',updated_at=?
                WHERE project_id=? AND take_id=? AND state='PREPARING'
                AND updated_at=?""",
                (now(), project_id, take_id, expected_updated_at))
            if cur.rowcount != 1:
                raise RuntimeError("Filming publication recovery state conflict")
        return {"take_id": take_id, "state": "INTERRUPTED",
                "immutable_revisions_modified": False,
                "worker_termination_verified_by_journal": False}

    def unresolved(self, project_id):
        """Read-only recovery inventory; never auto-delete immutable originals."""
        _require_pid(project_id)
        with self.index.studio._connection() as db:
            self.index._project(db,project_id)
            rows=db.execute("""SELECT take_id,sound_timeline_id,source_ids_json,
                state,updated_at FROM nvp_filming_publications
                WHERE project_id=? AND state!='COMPLETED'
                ORDER BY take_id""",(project_id,)).fetchall()
        return [{"take_id":r["take_id"],
                 "sound_timeline_id":r["sound_timeline_id"],
                 "source_ids":json.loads(r["source_ids_json"]),
                 "state":r["state"],"updated_at":r["updated_at"]}
                for r in rows]

    def reconcile(self, project_id):
        """Read-only restart evidence; never promote, delete, or retry a Take.

        A journal state alone is not proof of immutable publication. Report
        each revision's actual presence separately so operators can distinguish
        an interrupted batch from a crash after the Take was committed.
        """
        records = self.unresolved(project_id)
        def revision_exists(identity):
            try:
                self.index.read_revision(project_id, identity, 1)
            except KeyError:
                return False
            return True
        for record in records:
            record["source_revisions_present"] = {
                sid: revision_exists(sid) for sid in record["source_ids"]
            }
            record["sound_timeline_present"] = revision_exists(
                record["sound_timeline_id"])
            record["take_present"] = revision_exists(record["take_id"])
            # Recovery is deliberately observational. Distinguish a crash
            # before any source publication from a partially committed batch,
            # and from a batch whose sources/timeline were fully committed.
            # None of these states authorizes deleting or approving a Take.
            present = sum(record["source_revisions_present"].values())
            total = len(record["source_ids"])
            record["source_revision_count"] = present
            record["expected_source_revision_count"] = total
            # A Take revision alone cannot establish a usable, approved film.
            # Missing journaled source/timeline revisions require investigation
            # before any playback, promotion, or recovery decision.
            if record["take_present"] and (present != total or not record["sound_timeline_present"]):
                record["resolution"] = "INCOMPLETE_FROZEN_TAKE_DEPENDENCIES"
            elif record["take_present"]:
                record["resolution"] = "VERIFY_FROZEN_TAKE_AND_APPROVAL"
            elif record["sound_timeline_present"]:
                record["resolution"] = "INTERRUPTED_TIMELINE_WITHOUT_TAKE"
            elif present == 0:
                record["resolution"] = "INTERRUPTED_BEFORE_SOURCE_PUBLICATION"
            elif present < total:
                record["resolution"] = "INTERRUPTED_PARTIAL_SOURCE_PUBLICATION"
            else:
                record["resolution"] = "INTERRUPTED_SOURCES_WITHOUT_TIMELINE"
        return records

    def visibility(self, project_id, take_id):
        """Fail-closed publication visibility for journaled filming Takes.

        An absent journal entry is NOT proof of an approved legacy Take.
        Readers must apply their separate legacy/creator approval policy.
        This query is observational and does not change immutable revisions.
        """
        _require_pid(project_id)
        _id(take_id, "filming take")
        with self.index.studio._connection() as db:
            self.index._project(db, project_id)
            row = db.execute("""SELECT state,sound_timeline_id,source_ids_json
                FROM nvp_filming_publications
                WHERE project_id=? AND take_id=?""", (project_id,take_id)).fetchone()
            if row is None:
                return {"take_id":take_id,"journaled":False,
                        "visible":False,"reason":"NO_JOURNAL_RECEIPT"}
            if row["state"] != "COMPLETED":
                return {"take_id":take_id,"journaled":True,
                        "visible":False,"reason":"PUBLICATION_"+row["state"]}
            identities = [take_id,row["sound_timeline_id"],
                          *json.loads(row["source_ids_json"])]
            revisions = {}
            for identity in identities:
                try:
                    revisions[identity] = self.index.read_revision(project_id,identity,1)
                except KeyError:
                    return {"take_id":take_id,"journaled":True,
                            "visible":False,"reason":"MISSING_IMMUTABLE_DEPENDENCY"}
            # Presence alone is insufficient: a corrupted completion receipt
            # must not authorize an unrelated frozen Take or sound timeline.
            take = revisions[take_id]
            timeline = revisions[row["sound_timeline_id"]]
            if (take["kind"] != "take" or
                take["data"].get("timeline_id") != row["sound_timeline_id"] or
                take["data"].get("timeline_revision") != 1 or
                take["data"].get("timeline_document_sha256") != timeline["document_sha256"] or
                timeline["kind"] != "temporal"):
                return {"take_id":take_id,"journaled":True,
                        "visible":False,"reason":"PUBLICATION_BINDING_MISMATCH"}
            # Verify semantic source ownership, not merely the existence of
            # arbitrary FilmIndex objects with the expected identities. A
            # completed receipt must bind every original source exactly once
            # through the frozen temporal timeline.
            expected = set(json.loads(row["source_ids_json"]))
            found = set()
            timeline_data = timeline["data"]
            duration = timeline_data.get("duration_tick")
            if duration is None:
                return {"take_id":take_id,"journaled":True,
                        "visible":False,"reason":"PUBLICATION_SOURCE_BINDING_MISMATCH"}
            ledger = TemporalLedger(self.index)
            cursor = None
            while True:
                page = ledger.events_in(project_id,row["sound_timeline_id"],1,
                    start_tick=0,end_tick=int(duration),limit=MAX_QUERY,after=cursor)
                for event in page["events"]:
                    if event["event_kind"] not in ("sound","dialogue"):
                        continue
                    sid = event["source_id"]
                    payload = event["payload"]
                    # A matching source ID alone does not establish a usable
                    # original recording: check provenance and sample coverage.
                    sample_tick = TICKS_PER_SECOND // SAMPLE_RATE
                    source_data = revisions[sid]["data"] if sid in expected else {}
                    # Source-clock-mapped original recordings may cover a
                    # slightly longer/shorter Film Time interval due to real
                    # measured ADC drift. Never infer source sample count
                    # from nominal 48-kHz duration for those recordings.
                    # A forged/mismatched clock must remain UNREADABLE.
                    if sid in expected and (
                            "source_sync" in payload or "clock_evidence" in payload):
                        try:
                            from backend.nvp_original_clock_binding import verified_original_clock
                            source_sync=verified_original_clock(
                                self.index,project_id,sid,
                                event["start_tick"],event["end_tick"],
                                payload.get("source_sync"),
                                payload.get("clock_evidence"),
                                source_sample_count=source_data.get("sample_count"))
                            if source_sync is None:
                                raise RuntimeError("Independent clock map absent")
                            required_samples=source_sync["source_sample_count"]
                        except (KeyError,TypeError,ValueError,RuntimeError):
                            return {"take_id":take_id,"journaled":True,
                                    "visible":False,
                                    "reason":"PUBLICATION_SOURCE_BINDING_MISMATCH"}
                    else:
                        required_samples = (
                            event["end_tick"]-event["start_tick"]+sample_tick-1
                        )//sample_tick
                    if (sid not in expected or sid in found or
                        event["source_revision"] != 1 or
                        event.get("source_document_sha256") != revisions[sid]["document_sha256"] or
                        payload.get("original_recording") is not True or
                        payload.get("format") != "nvp.data_av.filming_capture.v1" or
                        payload.get("source_sample_rate") != SAMPLE_RATE or
                        payload.get("acoustic_mix_frozen") is not False or
                        not isinstance(payload.get("usd_prim_path"), str) or
                        not payload["usd_prim_path"].startswith("/World/") or
                        revisions[sid]["kind"] != "audio" or
                        source_data.get("format") != ORIGINAL_PCM_FORMAT or
                        source_data.get("sample_rate") != SAMPLE_RATE or
                        source_data.get("channels") != 1 or
                        source_data.get("sample_encoding") != "signed_16_le" or
                        source_data.get("flattened_soundtrack") is not False or
                        source_data.get("immutable_source") is not True or
                        type(source_data.get("sample_count")) is not int or
                        source_data["sample_count"] < required_samples or
                        required_samples <= 0):
                        return {"take_id":take_id,"journaled":True,
                                "visible":False,"reason":"PUBLICATION_SOURCE_BINDING_MISMATCH"}
                    found.add(sid)
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            if found != expected:
                return {"take_id":take_id,"journaled":True,
                        "visible":False,"reason":"PUBLICATION_SOURCE_BINDING_MISMATCH"}
            return {"take_id":take_id,"journaled":True,
                    "visible":True,"reason":"COMPLETED_DEPENDENCIES_PRESENT"}
