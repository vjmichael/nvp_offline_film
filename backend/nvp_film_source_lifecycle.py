"""SLATE-04: explicit source-data retirement and dependency-safe deletion.

Immutability: no in-place edits to frozen Digital Takes and source revisions.
Deletability: a creator may *retire* an object (trash; retain historical
source for pinned edits) or *purge its FilmIndex registration* once there
are no recorded dependent revisions. Never silently cascade through a cut.

The SQL transaction protects against concurrent FilmIndex commits. This
does NOT physically erase orphan blob bytes: offline physical garbage
collection/recovery requires its own audited, creator-authorized worker.
"""
from __future__ import annotations

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_studio import now

STATES=frozenset(("RETIRED","RESTORED","PURGED"))
TABLE="nvp_film_source_retirements"
MAX_REASON=500


def _table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS nvp_film_source_retirements (
        project_id TEXT NOT NULL,
        object_id TEXT NOT NULL,
        state TEXT NOT NULL,
        retired_at TEXT,
        restored_at TEXT,
        purged_at TEXT,
        last_head_revision INTEGER NOT NULL,
        last_head_document_sha256 TEXT NOT NULL,
        reason TEXT NOT NULL,
        PRIMARY KEY(project_id,object_id),
        FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
        CHECK(state IN ('RETIRED','RESTORED','PURGED'))
    )""")


def _active_dependents(db,project_id,object_id):
    """Only authoritative recorded links. Must run in SQLite writer lease."""
    direct=db.execute("""SELECT source_id,source_revision
        FROM film_dependencies WHERE project_id=? AND target_id=?
        ORDER BY source_id,source_revision LIMIT 33""",
        (project_id,object_id)).fetchall()
    # Paged catalogs use proper typed FilmIndex dependencies. Legacy
    # editorial and temporal sources may also use normalized source
    # binding tables; refuse physical purge where those exist.
    legacy=0
    for name,col in (
        ("scale_editorial_source_bindings","source_id"),
        ("nvp_time_editorial_clips","source_id"),
        ("nvp_temporal_events","source_id")):
        if db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
            AND name=?""",(name,)).fetchone():
            legacy+=db.execute(
                "SELECT COUNT(*) FROM "+name+" WHERE project_id=? AND "+col+"=?",
                (project_id,object_id)).fetchone()[0]
    return {
        "typed_dependents":[
            {"object_id":r["source_id"],"revision":r["source_revision"]}
            for r in direct],
        "at_least_typed":len(direct),
        "legacy_indexed_count":legacy,
        "purge_blocked":bool(direct or legacy),
    }


class FilmSourceLifecycle:
    def __init__(self,index:FilmIndex,*,verify_creator_action):
        if not isinstance(index,FilmIndex) or not callable(verify_creator_action):
            raise TypeError("Trusted FilmIndex and creator source deletion policy required")
        self.index=index
        self.authorize=verify_creator_action
        with self.index.studio._connection() as db:
            _table(db)

    def inspect(self,project_id,object_id):
        _require_pid(project_id)
        _id(object_id,"source object")
        with self.index.studio._connection() as db:
            self.index._project(db,project_id)
            o=db.execute("""SELECT kind,head_revision FROM film_objects
                WHERE project_id=? AND object_id=?""",
                (project_id,object_id)).fetchone()
            state=db.execute("""SELECT * FROM nvp_film_source_retirements
                WHERE project_id=? AND object_id=?""",
                (project_id,object_id)).fetchone()
            deps=_active_dependents(db,project_id,object_id)
        return {
            "project_id":project_id,"object_id":object_id,
            "exists":o is not None,"kind":o["kind"] if o else None,
            "head_revision":o["head_revision"] if o else None,
            "state":state["state"] if state else "ACTIVE",
            "last_document_sha256":state["last_head_document_sha256"] if state else None,
            **deps,
            "physical_blobs_deleted":False,
        }

    def retire(self,project_id,object_id,*,reason,creator_event,
               expected_head_revision):
        """Retire/trash: preserve all old committed references and bytes."""
        _require_pid(project_id)
        _id(object_id,"source identity")
        if type(reason) is not str or not 1<=len(reason.strip())<=MAX_REASON:
            raise ValueError("Creator must give bounded source retirement reason")
        with self.index.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.index._project(db,project_id)
            obj=db.execute("""SELECT kind,head_revision FROM film_objects
                WHERE project_id=? AND object_id=?""",
                (project_id,object_id)).fetchone()
            if obj is None or obj["head_revision"]!=expected_head_revision:
                raise RuntimeError("Source changed or no longer exists")
            previous=db.execute("""SELECT state FROM nvp_film_source_retirements
                WHERE project_id=? AND object_id=?""",
                (project_id,object_id)).fetchone()
            if previous is not None and previous["state"]!="RESTORED":
                raise RuntimeError("Source has already been retired or purged")
            head=self.index._read_revision(
                db,project_id,object_id,obj["head_revision"])
            scope={
                "operation":"nvp.film.source.retire.v1",
                "project_id":project_id,"object_id":object_id,
                "kind":obj["kind"],
                "expected_head_revision":expected_head_revision,
                "head_document_sha256":head["document_sha"],
                "reason":reason.strip(),
                "dependent_legacy_edits_preserved":True,
                "physical_bytes_deleted":False,
            }
            if self.authorize(creator_event,dict(scope)) is not True:
                raise PermissionError("Creator did not explicitly retire source")
            db.execute("""INSERT INTO nvp_film_source_retirements
                (project_id,object_id,state,retired_at,last_head_revision,
                 last_head_document_sha256,reason)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(project_id,object_id) DO UPDATE SET
                state='RETIRED',retired_at=excluded.retired_at,
                last_head_revision=excluded.last_head_revision,
                last_head_document_sha256=excluded.last_head_document_sha256,
                reason=excluded.reason""",
                (project_id,object_id,"RETIRED",now(),expected_head_revision,
                 head["document_sha"],reason.strip()))
            deps=_active_dependents(db,project_id,object_id)
        return {
            "state":"RETIRED","project_id":project_id,"object_id":object_id,
            "source_truth_modified":False,
            "historical_edits_preserved":True,
            "physical_blobs_deleted":False,
            **deps,
        }

    def restore(self,project_id,object_id,*,creator_event):
        """Undo retirement as an explicit creator-authorized source action."""
        _require_pid(project_id)
        _id(object_id,"source identity")
        with self.index.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            record=db.execute("""SELECT state,last_head_revision,
                last_head_document_sha256 FROM nvp_film_source_retirements
                WHERE project_id=? AND object_id=?""",
                (project_id,object_id)).fetchone()
            if record is None or record["state"]!="RETIRED":
                raise RuntimeError("Only retired, still-existing sources can be restored")
            current=self.index._read_revision(
                db,project_id,object_id,record["last_head_revision"])
            if (current is None or
                current["document_sha"]!=record["last_head_document_sha256"]):
                raise RuntimeError("Retired source revision is no longer present")
            scope={
                "operation":"nvp.film.source.restore.v1",
                "project_id":project_id,"object_id":object_id,
                "head_revision":record["last_head_revision"],
                "head_document_sha256":record["last_head_document_sha256"],
                "final_render_approval":False,
            }
            if self.authorize(creator_event,scope) is not True:
                raise PermissionError("Creator did not restore source")
            db.execute("""UPDATE nvp_film_source_retirements
                SET state='RESTORED',restored_at=? WHERE project_id=?
                AND object_id=? AND state='RETIRED'""",
                (now(),project_id,object_id))
        return {"state":"RESTORED","source_truth_modified":False,
                "physical_blobs_deleted":False}

    def purge_unreferenced(self,project_id,object_id,*,creator_event):
        """Remove an unused FilmIndex source registration, *not* blob bytes.

        All historical source refs must have been deleted separately first;
        a still-referenced original cannot be purged. This is never a
        recursive or blind cascade delete through a director's prior edits.
        """
        _require_pid(project_id)
        _id(object_id,"source identity")
        with self.index.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            record=db.execute("""SELECT state,last_head_revision,
                last_head_document_sha256 FROM nvp_film_source_retirements
                WHERE project_id=? AND object_id=?""",
                (project_id,object_id)).fetchone()
            if record is None or record["state"]!="RETIRED":
                raise RuntimeError("Purge requires prior explicit retirement")
            deps=_active_dependents(db,project_id,object_id)
            if deps["purge_blocked"]:
                raise RuntimeError("Source is still used by immutable past/active revisions")
            obj=db.execute("""SELECT head_revision FROM film_objects
                WHERE project_id=? AND object_id=?""",
                (project_id,object_id)).fetchone()
            if obj is None or obj["head_revision"]!=record["last_head_revision"]:
                raise RuntimeError("Retired source changed before purge")
            scope={
                "operation":"nvp.film.source.purge_registration.v1",
                "project_id":project_id,"object_id":object_id,
                "head_document_sha256":record["last_head_document_sha256"],
                "all_recorded_dependents_removed":True,
                "physical_blobs_deleted":False,
            }
            if self.authorize(creator_event,scope) is not True:
                raise PermissionError("Creator did not authorize irreversible source purge")
            removed=db.execute("""DELETE FROM film_objects
                WHERE project_id=? AND object_id=? AND head_revision=?""",
                (project_id,object_id,record["last_head_revision"]))
            if removed.rowcount!=1:
                raise RuntimeError("Source changed during purge")
            db.execute("""UPDATE nvp_film_source_retirements
                SET state='PURGED',purged_at=? WHERE project_id=? AND object_id=?""",
                (now(),project_id,object_id))
        return {"state":"PURGED","registration_deleted":True,
                "source_data_mutated":False,
                "physical_blobs_deleted":False,
                "orphan_media_gc_separately_required":True}
