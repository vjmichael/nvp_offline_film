"""DA-03 durable visibility ledger for non-atomic filming publication.

This does NOT make FilmIndex's separate immutable revisions atomic. It makes
an interrupted multi-object publication discoverable after process restart,
without deleting source history or inventing a creator-approved Take.
"""
from __future__ import annotations

import json
from backend.nvp_film_index import _id, _require_pid
from backend.nvp_studio import now


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
        # A success receipt must not be issued for an incomplete publication.
        # Inspect immutable revisions before changing the journal state; failure
        # leaves PREPARING visible to restart reconciliation.
        if completed:
            with self.index.studio._connection() as db:
                row = db.execute("""SELECT sound_timeline_id,source_ids_json
                    FROM nvp_filming_publications WHERE project_id=? AND take_id=?
                    AND state='PREPARING'""", (project_id,take_id)).fetchone()
            if row is None:
                raise RuntimeError("Filming publication journal state conflict")
            identities = [take_id,row["sound_timeline_id"],
                          *json.loads(row["source_ids_json"])]
            for identity in identities:
                try:
                    self.index.read_revision(project_id,identity,1)
                except KeyError as exc:
                    raise RuntimeError("Cannot complete filming publication with missing immutable dependencies") from exc
        with self.index.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            cur = db.execute("""UPDATE nvp_filming_publications
                SET state=?,updated_at=? WHERE project_id=? AND take_id=?
                AND state='PREPARING'""", (state,now(),project_id,take_id))
            if cur.rowcount != 1:
                raise RuntimeError("Filming publication journal state conflict")

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
