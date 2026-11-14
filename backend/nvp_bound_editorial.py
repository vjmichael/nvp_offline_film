"""SCALE-02C: atomic FilmIndex-bound, compact editorial revision publication.

Native trusted-host operation, not creator authorization or source decoding.
A large edit is staged on disk and published with its indexed clip references
inside FilmIndex's original SQLite transaction (precommit_guard).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from backend.nvp_editorial_catalog import EditorialCatalog, _positive, MAX_I64
from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_source_film_bridge import FORMAT as SOURCE_FORMAT

FORMAT = "nvp.edit.scale.bound.v1"


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _source_capacity(data, fps_num, fps_den):
    """Conservative bound from probe metadata, NOT independent decode evidence."""
    if data.get("format") != SOURCE_FORMAT or data.get("probe", {}).get("decoded_and_verified") is not False:
        raise RuntimeError("Edit source is not an indexed external original")
    probe = data["probe"]
    video = [x for x in probe.get("streams", []) if x.get("kind") == "video"]
    if len(video) != 1:
        raise RuntimeError("Only a single video stream is currently supported")
    rate = video[0].get("avg_frame_rate")
    if not isinstance(rate, str) or "/" not in rate:
        raise RuntimeError("Source frame rate not independently known")
    numerator, denominator = (int(x) for x in rate.split("/"))
    if numerator <= 0 or denominator <= 0 or Fraction(numerator, denominator) != Fraction(fps_num, fps_den):
        raise RuntimeError("Source/editor frame rate mismatch; retiming not implemented")
    duration = probe.get("duration_seconds_reported")
    try:
        seconds = Decimal(duration)
    except (TypeError, InvalidOperation) as exc:
        raise RuntimeError("Source duration not independently known") from exc
    if not seconds.is_finite() or seconds <= 0:
        raise RuntimeError("Invalid reported source duration")
    # FFprobe's human-readable duration can have rounding uncertainty.
    # The source bound is conservative and not a promise of complete decode.
    return int(seconds * Decimal(numerator) / Decimal(denominator))


class BoundEditorialPublisher:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("An authoritative FilmIndex is required")
        self.index = index
        self.catalog = EditorialCatalog(index.studio)
        with index.studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS scale_editorial_source_bindings (
                project_id TEXT NOT NULL,
                edit_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                ordinal INTEGER NOT NULL,
                source_id TEXT NOT NULL,
                source_revision INTEGER NOT NULL,
                source_document_sha256 TEXT NOT NULL,
                PRIMARY KEY(project_id,edit_id,revision,ordinal),
                FOREIGN KEY(project_id,edit_id,revision,ordinal)
                  REFERENCES scale_editorial_clips(project_id,edit_id,revision,ordinal),
                FOREIGN KEY(project_id,source_id,source_revision)
                  REFERENCES film_object_revisions(project_id,object_id,revision))""")
            db.execute("""CREATE INDEX IF NOT EXISTS scale_source_to_edit
                ON scale_editorial_source_bindings
                (project_id,source_id,source_revision,edit_id,revision)""")

    def publish(self, project_id, edit_id, clips, *, fps_num=24, fps_den=1,
                expected_revision=0):
        """Atomically publish FilmIndex edit and every exact source reference.

        The iterable is consumed once into bounded disk-backed staging.
        A deleted/disconnected original may still be included in a planning
        edit; actual native processing must rehash and verify it first.
        """
        _require_pid(project_id)
        _id(edit_id, "edit identity")
        _positive(fps_num, "fps numerator")
        _positive(fps_den, "fps denominator")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected edit revision must be nonnegative")
        revision = expected_revision + 1
        with tempfile.TemporaryDirectory(prefix="nvp-edit-stage-") as tmp:
            staged = sqlite3.connect(Path(tmp) / "clips.sqlite3")
            try:
                staged.execute("""CREATE TABLE rows (
                    ordinal INTEGER PRIMARY KEY, source_id TEXT NOT NULL,
                    source_revision INTEGER NOT NULL,
                    source_document_sha256 TEXT NOT NULL,
                    source_first_frame INTEGER NOT NULL,
                    frame_count INTEGER NOT NULL,
                    output_first_frame INTEGER NOT NULL)""")
                digest = hashlib.sha256()
                seen = {}
                position = 1
                count = 0
                for clip in clips:
                    if type(clip) is not dict or set(clip) != {
                        "source_id", "source_revision", "source_first_frame", "frame_count"
                    }:
                        raise ValueError("Invalid indexed clip structure")
                    sid = _id(clip["source_id"], "source asset")
                    rev = _positive(clip["source_revision"], "source revision")
                    first = _positive(clip["source_first_frame"], "source start")
                    frames = _positive(clip["frame_count"], "clip duration")
                    if first > MAX_I64 - frames + 1 or position > MAX_I64 - frames + 1:
                        raise OverflowError("Compact clip frame range overflow")
                    key = (sid, rev)
                    if key not in seen:
                        record = self.index.read_revision(project_id, sid, rev)
                        if record["kind"] != "asset":
                            raise RuntimeError("Editorial source must be an exact FilmIndex asset")
                        seen[key] = (record["document_sha256"],
                                     _source_capacity(record["data"], fps_num, fps_den))
                    sha, capacity = seen[key]
                    if first + frames - 1 > capacity:
                        raise RuntimeError("Edit clip exceeds source reported frame duration")
                    item = (count, sid, rev, sha, first, frames, position)
                    staged.execute("INSERT INTO rows VALUES (?,?,?,?,?,?,?)", item)
                    digest.update(_encoded(item))
                    position += frames
                    count += 1
                if not count:
                    raise ValueError("Film edit requires at least one clip")
                staged.commit()
                total_frames = position - 1
                clip_sha = digest.hexdigest()
                document = {"format": FORMAT, "clip_count": count,
                            "total_frames": total_frames,
                            "fps_num": fps_num, "fps_den": fps_den,
                            "clip_manifest_sha256": clip_sha,
                            "binding": "indexed_exact_filmindex_source_revisions",
                            "source_range_evidence": "reported_duration_not_full_decode",
                            "creator_approved": False, "rendered": False}
                def guard(db):
                    db.execute("""INSERT INTO scale_editorial_revisions
                        (project_id,edit_id,revision,frame_rate_num,frame_rate_den,
                         total_frames,source_manifest_sha256)
                        VALUES (?,?,?,?,?,?,?)""",
                        (project_id, edit_id, revision, fps_num, fps_den,
                         total_frames, clip_sha))
                    checked_hash = hashlib.sha256()
                    checked_count = 0
                    for item in staged.execute("""SELECT ordinal,source_id,
                        source_revision,source_document_sha256,source_first_frame,
                        frame_count,output_first_frame FROM rows ORDER BY ordinal"""):
                        ordinal, sid, source_rev, sha, first, frames, out = item
                        source = self.index._read_revision(db, project_id, sid, source_rev)
                        if source is None or source["kind"] != "asset" or source["document_sha"] != sha:
                            raise RuntimeError("Exact FilmIndex source revision changed")
                        db.execute("""INSERT INTO scale_editorial_clips
                            (project_id,edit_id,revision,ordinal,source_id,
                             source_revision,source_first_frame,frame_count,
                             output_first_frame) VALUES (?,?,?,?,?,?,?,?,?)""",
                            (project_id,edit_id,revision,ordinal,sid,
                             source_rev,first,frames,out))
                        db.execute("""INSERT INTO scale_editorial_source_bindings
                            (project_id,edit_id,revision,ordinal,source_id,
                             source_revision,source_document_sha256)
                            VALUES (?,?,?,?,?,?,?)""",
                            (project_id,edit_id,revision,ordinal,sid,source_rev,sha))
                        checked_hash.update(_encoded(tuple(item)))
                        checked_count += 1
                    if checked_count != count or checked_hash.hexdigest() != clip_sha:
                        raise RuntimeError("Staged edit manifest changed before commit")
                return self.index.register_revision(
                    project_id, edit_id, "edit", document,
                    expected_revision=expected_revision,
                    dependencies=[], precommit_guard=guard)
            finally:
                staged.close()

    def clips(self, project_id, edit_id, revision, *, first_frame=1, limit=100):
        """Page an exact published FilmIndex edit; reject missing/broken binding."""
        rec = self.index.read_revision(project_id, edit_id, revision)
        data = rec["data"]
        if rec["kind"] != "edit" or data.get("format") != FORMAT:
            raise RuntimeError("Not a FilmIndex-bound compact editorial revision")
        page = self.catalog.clips(project_id, edit_id, revision,
                                  first_frame=first_frame, limit=limit)
        if page["total_frames"] != data["total_frames"]:
            raise RuntimeError("Indexed edit summary disagrees with FilmIndex")
        with self.index.studio._connection() as db:
            bindings = {}
            for clip in page["clips"]:
                row = db.execute("""SELECT b.source_document_sha256,
                    b.source_id, b.source_revision, r.document_sha
                    FROM scale_editorial_source_bindings b
                    JOIN film_object_revisions r
                    ON r.project_id=b.project_id AND r.object_id=b.source_id
                        AND r.revision=b.source_revision
                    WHERE b.project_id=? AND b.edit_id=? AND b.revision=?
                      AND b.ordinal=?""",
                    (project_id, edit_id, revision, clip["ordinal"])).fetchone()
                if (row is None or row["source_document_sha256"] != row["document_sha"]
                    or row["source_id"] != clip["source_id"]
                    or row["source_revision"] != clip["source_revision"]):
                    raise RuntimeError("Exact source binding missing or invalid")
                bindings[clip["ordinal"]] = row["source_document_sha256"]
        return {**page, "film_document_sha256": rec["document_sha256"],
                "clips": [{**c, "source_document_sha256": bindings[c["ordinal"]]}
                          for c in page["clips"]]}

    def verify_revision(self, project_id, edit_id, revision):
        """Stream independently across all stored clip references and hashes.

        This validates indexed metadata, not decoded source frames. It must be
        invoked before an effectful native conform/film-master publication.
        """
        rec = self.index.read_revision(project_id, edit_id, revision)
        doc = rec["data"]
        if rec["kind"] != "edit" or doc.get("format") != FORMAT:
            raise RuntimeError("Not an authoritative compact bound edit")
        digest = hashlib.sha256()
        expected_frame = 1
        expected_ordinal = 0
        with self.index.studio._connection() as db:
            source = db.execute("""SELECT c.ordinal,c.source_id,c.source_revision,
                b.source_document_sha256,c.source_first_frame,
                c.frame_count,c.output_first_frame,r.document_sha
                FROM scale_editorial_clips c
                LEFT JOIN scale_editorial_source_bindings b
                  ON b.project_id=c.project_id AND b.edit_id=c.edit_id
                    AND b.revision=c.revision AND b.ordinal=c.ordinal
                LEFT JOIN film_object_revisions r
                  ON r.project_id=b.project_id AND r.object_id=b.source_id
                    AND r.revision=b.source_revision
                WHERE c.project_id=? AND c.edit_id=? AND c.revision=?
                ORDER BY c.ordinal""", (project_id, edit_id, revision))
            for row in source:
                ordinal, sid, source_rev, sha, first, frames, out, actual = row
                if (ordinal != expected_ordinal or out != expected_frame or
                    sha is None or sha != actual or
                    first < 1 or frames < 1 or first > MAX_I64 - frames + 1 or
                    expected_frame > MAX_I64 - frames + 1):
                    raise RuntimeError("Bound editorial source or interval was altered")
                digest.update(_encoded(
                    (ordinal, sid, source_rev, sha, first, frames, out)))
                expected_frame += frames
                expected_ordinal += 1
            row = db.execute("""SELECT frame_rate_num,frame_rate_den,total_frames,
                source_manifest_sha256 FROM scale_editorial_revisions
                WHERE project_id=? AND edit_id=? AND revision=?""",
                (project_id, edit_id, revision)).fetchone()
        if (row is None or expected_ordinal != doc["clip_count"] or
            expected_frame - 1 != doc["total_frames"] or
            row["total_frames"] != doc["total_frames"] or
            row["frame_rate_num"] != doc["fps_num"] or
            row["frame_rate_den"] != doc["fps_den"] or
            digest.hexdigest() != doc["clip_manifest_sha256"] or
            row["source_manifest_sha256"] != doc["clip_manifest_sha256"]):
            raise RuntimeError("Compact edit and FilmIndex revision disagree")
        return {"status": "VERIFIED_INDEXED_SOURCE_BINDINGS",
                "film_document_sha256": rec["document_sha256"],
                "clip_count": expected_ordinal, "total_frames": expected_frame - 1,
                "source_bytes_decoded": False}
