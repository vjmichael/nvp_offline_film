"""SCALE-01: compact, project-scoped editorial intervals.

SQLite metadata only, NOT camera media custody, frame rendering or approvals.
This extends the existing Studio database and never changes FilmIndex objects.
All source assets remain independently identified by authoritative FilmIndex.
"""
from __future__ import annotations

import sqlite3
from backend.nvp_studio import Studio

MAX_I64 = 2**63 - 1


def _positive(value, what):
    if type(value) is not int or not 1 <= value <= MAX_I64:
        raise ValueError(what + " must be a positive signed 64-bit integer")
    return value


def _identity(value, what):
    if type(value) is not str or not 1 <= len(value) <= 120 or any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-"
        for ch in value
    ):
        raise ValueError("Invalid " + what)
    return value


class EditorialCatalog:
    """Indexed clip decisions; no per-frame materialization or film-length cap.

    Each revision is immutable, and clip insertion is one SQLite transaction.
    The caller must verify source identity/ownership with FilmIndex before
    submitting a revision; this database stores references, not permissions.
    """

    def __init__(self, studio: Studio):
        if not isinstance(studio, Studio):
            raise TypeError("An existing trusted Studio is required")
        self.studio = studio
        with studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS scale_editorial_revisions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                edit_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision > 0),
                frame_rate_num INTEGER NOT NULL CHECK(frame_rate_num > 0),
                frame_rate_den INTEGER NOT NULL CHECK(frame_rate_den > 0),
                total_frames INTEGER NOT NULL CHECK(total_frames > 0),
                source_manifest_sha256 TEXT NOT NULL,
                PRIMARY KEY(project_id, edit_id, revision))""")
            db.execute("""CREATE TABLE IF NOT EXISTS scale_editorial_clips (
                project_id TEXT NOT NULL,
                edit_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
                source_id TEXT NOT NULL,
                source_revision INTEGER NOT NULL CHECK(source_revision > 0),
                source_first_frame INTEGER NOT NULL CHECK(source_first_frame > 0),
                frame_count INTEGER NOT NULL CHECK(frame_count > 0),
                output_first_frame INTEGER NOT NULL CHECK(output_first_frame > 0),
                PRIMARY KEY(project_id, edit_id, revision, ordinal),
                FOREIGN KEY(project_id, edit_id, revision)
                    REFERENCES scale_editorial_revisions(project_id, edit_id, revision)
                    ON DELETE CASCADE)""")
            db.execute("""CREATE INDEX IF NOT EXISTS scale_editorial_seek
                ON scale_editorial_clips(project_id, edit_id, revision, output_first_frame)""")

    def publish(self, project_id, edit_id, revision, *, fps_num, fps_den,
                source_manifest_sha256, clips):
        """Record a compact edit atomically; caller owns source preflight.

        'clips' is an iterable of source IDs and bounded intervals; it is
        consumed incrementally inside the transaction. The contiguous output
        timeline is derived, never trusted from the input.
        """
        _identity(edit_id, "edit ID")
        _positive(revision, "revision")
        _positive(fps_num, "frame rate numerator")
        _positive(fps_den, "frame rate denominator")
        if (type(source_manifest_sha256) is not str or
            len(source_manifest_sha256) != 64 or
            any(ch not in "0123456789abcdef" for ch in source_manifest_sha256)):
            raise ValueError("Invalid immutable source manifest hash")
        # Validate exact project existence by the FK without taking all project data.
        with self.studio._connection() as db:
            db.execute("INSERT INTO scale_editorial_revisions VALUES (?,?,?,?,?,?,?)",
                       (project_id, edit_id, revision, fps_num, fps_den, 1,
                        source_manifest_sha256))
            position = 1
            count = 0
            for clip in clips:
                if type(clip) is not dict or set(clip) != {
                    "source_id", "source_revision", "source_first_frame", "frame_count"
                }:
                    raise ValueError("Unexpected compact clip fields")
                source_id = _identity(clip["source_id"], "source ID")
                source_revision = _positive(clip["source_revision"], "source revision")
                first = _positive(clip["source_first_frame"], "source first frame")
                frames = _positive(clip["frame_count"], "clip frame count")
                if first > MAX_I64 - frames + 1 or position > MAX_I64 - frames + 1:
                    raise OverflowError("Clip source/output interval exceeds signed 64-bit range")
                db.execute("""INSERT INTO scale_editorial_clips (project_id,edit_id,revision,ordinal,source_id,source_revision,source_first_frame,frame_count,output_first_frame) VALUES (?,?,?,?,?,?,?,?,?)""",
                           (project_id, edit_id, revision, count, source_id,
                            source_revision, first, frames, position))
                position += frames
                count += 1
            if not count:
                raise ValueError("An editorial revision requires clips")
            db.execute("""UPDATE scale_editorial_revisions SET total_frames=?
                WHERE project_id=? AND edit_id=? AND revision=?""",
                (position - 1, project_id, edit_id, revision))
        return {"edit_id": edit_id, "revision": revision, "total_frames": position - 1,
                "clip_count": count}

    def clips(self, project_id, edit_id, revision, *, first_frame=1, limit=100):
        """Seek relevant clips without loading the entire project or timeline."""
        _positive(first_frame, "seek frame")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Page limit must be 1..1000")
        with self.studio._connection() as db:
            found = db.execute("""SELECT total_frames FROM scale_editorial_revisions
                WHERE project_id=? AND edit_id=? AND revision=?""",
                (project_id, edit_id, revision)).fetchone()
            if found is None:
                raise KeyError("Unknown editorial revision")
            # Indexed predecessor lookup finds the interval spanning the
            # seek frame without scanning all preceding shots in a feature.
            predecessor = db.execute("""SELECT MAX(output_first_frame)
                FROM scale_editorial_clips
                WHERE project_id=? AND edit_id=? AND revision=?
                  AND output_first_frame <= ?""",
                (project_id, edit_id, revision, first_frame)).fetchone()[0]
            if first_frame > found["total_frames"]:
                rows = []
            else:
                threshold = predecessor if predecessor is not None else first_frame
                rows = db.execute("""SELECT ordinal,source_id,source_revision,
                      source_first_frame,frame_count,output_first_frame
                    FROM scale_editorial_clips
                    WHERE project_id=? AND edit_id=? AND revision=?
                      AND output_first_frame >= ?
                    ORDER BY output_first_frame LIMIT ?""",
                    (project_id, edit_id, revision, threshold, limit)).fetchall()
        return {"total_frames": found["total_frames"],
                "clips": [dict(row) for row in rows]}
