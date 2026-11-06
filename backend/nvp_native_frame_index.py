"""NVP-owned, versioned SQLite source-frame index.

A source's SHA-256 is established at ingest; interactive lookups do NOT
rehash the media. A file stamp is an unverified change detector, not a
cryptographic source-authenticity claim. Final conform remains gated separately.
"""
from __future__ import annotations
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import tempfile

SCHEMA_VERSION = 1
MAX_LINE = 4096
MAX_FRAMES = 2**63 - 1
MAX_STREAM_METADATA = 65536
ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,79}\Z")
PROJECT = re.compile(r"[0-9a-f]{32}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
RATIONAL = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)\Z")


def stamp(path):
    """Fast change signal. It does NOT verify current source bytes."""
    path = Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("Source must be an absolute non-symlink regular file")
    s = path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_size <= 0:
        raise RuntimeError("Original media offline or not regular")
    return {"device": s.st_dev, "inode": s.st_ino, "size": s.st_size,
            "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns}


def sha_small_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _native_executable(path):
    p = Path(path)
    if not p.is_absolute() or not p.is_file() or p.is_symlink():
        raise ValueError("Explicit absolute native tool path required")
    return p


def _identity(project, asset, source_sha):
    if not (isinstance(project, str) and PROJECT.fullmatch(project) and
            isinstance(asset, str) and ID.fullmatch(asset) and
            isinstance(source_sha, str) and SHA.fullmatch(source_sha)):
        raise ValueError("Invalid exact FilmIndex source identity")


def _parse_record(line):
    if len(line) > MAX_LINE:
        raise RuntimeError("Oversized FFprobe frame record")
    data = {}
    for part in line.strip().split("|"):
        if not part:
            continue
        if "=" not in part:
            raise RuntimeError("Unexpected FFprobe frame record")
        key, value = part.split("=", 1)
        if key not in {"key_frame", "best_effort_timestamp", "pts", "pkt_pos"}:
            raise RuntimeError("Unsupported indexed-frame metadata")
        data[key] = value
    if not data:
        return None
    key = data.get("key_frame")
    pts = data.get("best_effort_timestamp", data.get("pts"))
    if key not in ("0", "1") or pts in (None, "N/A"):
        raise RuntimeError("No exact FFprobe presentation timestamp")
    try:
        n = int(pts)
        pos = data.get("pkt_pos")
        byte_offset = None if pos is None or pos == "N/A" else int(pos)
    except ValueError as exc:
        raise RuntimeError("Invalid frame timestamp or packet position") from exc
    if not -2**63 <= n < 2**63 or (byte_offset is not None and byte_offset < 0):
        raise RuntimeError("Out-of-range frame timestamp/packet offset")
    return (n, int(key), byte_offset)


class NVPFrameIndex:
    def __init__(self, cache_root, *, ffprobe):
        self.root = Path(cache_root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError("NVP index cache must have trusted absolute root")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.ffprobe = _native_executable(ffprobe)
        self.tool_sha = sha_small_file(self.ffprobe)

    def _path(self, project, asset, source_sha):
        _identity(project, asset, source_sha)
        key = hashlib.sha256(_json({
            "schema": SCHEMA_VERSION, "project": project,
            "asset": asset, "source_sha256": source_sha,
        }).encode("ascii")).hexdigest()
        folder = self.root / project / key[:2]
        if folder.exists() and folder.is_symlink():
            raise RuntimeError("Unsafe NVP cache parent")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        return folder / (key + ".sqlite3")

    @staticmethod
    def _open_readonly(path):
        return sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)

    def _stream(self, source):
        cmd = [str(self.ffprobe), "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=index,time_base,start_pts,codec_name",
               "-show_streams", "-of", "json", str(source)]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=60, check=False)
        if result.returncode != 0 or len(result.stdout) > MAX_STREAM_METADATA:
            raise RuntimeError("Native stream header inspection failed")
        record = json.loads(result.stdout)
        streams = record.get("streams", [])
        if len(streams) != 1:
            raise RuntimeError("NVP v1 index requires a single selected video stream")
        item = streams[0]
        matched = RATIONAL.fullmatch(item.get("time_base", ""))
        if not matched:
            raise RuntimeError("Invalid source timebase")
        num, den = map(int, matched.groups())
        if num > 2**63 - 1 or den > 2**63 - 1:
            raise RuntimeError("Source timebase overflow")
        return {"time_base_num": num, "time_base_den": den,
                "stream_index": int(item["index"]),
                "stream_start_pts": None if item.get("start_pts") in (None, "N/A")
                else int(item["start_pts"]),
                "codec": item.get("codec_name")}

    def ensure(self, project, asset, source_sha, source):
        """One full initial frame scan, O(1)-metadata warm path.

        No original content SHA is calculated. Stored source SHA is the prior
        FilmIndex ingest identity, not proof that removable bytes remain intact.
        """
        _identity(project, asset, source_sha)
        source = Path(source)
        before = stamp(source)
        path = self._path(project, asset, source_sha)
        if path.is_symlink():
            raise RuntimeError("Unsafe indexed source cache")
        if path.exists():
            with self._open_readonly(path) as db:
                row = db.execute("SELECT value FROM header WHERE key='metadata'").fetchone()
                if row is None:
                    raise RuntimeError("Invalid NVP frame index metadata")
                header = json.loads(row[0])
                if (header.get("schema") != SCHEMA_VERSION or
                    header.get("project") != project or header.get("asset") != asset or
                    header.get("source_sha256") != source_sha or
                    header.get("source_stamp") != before or
                    header.get("frame_count", 0) <= 0):
                    raise RuntimeError("Stale NVP index; explicit source reacceptance needed")
                return {"status": "REUSED_SOURCE_STAMP_UNVERIFIED", "path": str(path),
                        **header}
        meta = self._stream(source)
        lock = path.with_suffix(".building")
        try:
            fd_lock = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RuntimeError("Interrupted index build requires host reconciliation") from exc
        os.close(fd_lock)
        stage = None
        try:
            fd, name = tempfile.mkstemp(prefix=".nvpframes-", suffix=".tmp",
                                         dir=path.parent)
            os.close(fd)
            stage = Path(name)
            with sqlite3.connect(stage) as db:
                db.execute("CREATE TABLE frames (ordinal INTEGER PRIMARY KEY, pts INTEGER NOT NULL, keyframe INTEGER NOT NULL, packet_pos INTEGER)")
                db.execute("CREATE TABLE header (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                command = [str(self.ffprobe), "-v", "error", "-select_streams", "v:0",
                           "-show_frames", "-show_entries",
                           "frame=key_frame,best_effort_timestamp,pts,pkt_pos",
                           "-of", "compact=p=0:nk=0", str(source)]
                proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                count = 0
                previous = None
                keyframes = 0
                try:
                    while True:
                        line = proc.stdout.readline(MAX_LINE + 1)
                        if not line:
                            break
                        item = _parse_record(line.decode("ascii", "strict"))
                        if item is None:
                            continue
                        pts, key, packet = item
                        if previous is not None and pts <= previous:
                            raise RuntimeError("Ambiguous or non-monotonic video frame PTS")
                        previous = pts
                        db.execute("INSERT INTO frames VALUES (?,?,?,?)",
                                   (count, pts, key, packet))
                        count += 1
                        keyframes += key
                        if count >= MAX_FRAMES:
                            raise RuntimeError("Indexed source exceeds 64-bit frame range")
                    code = proc.wait(timeout=120)
                    if code != 0 or not count or not keyframes:
                        raise RuntimeError("FFprobe frame scan incomplete or missing keyframes")
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=15)
                    proc.stdout.close()
                if stamp(source) != before:
                    raise RuntimeError("Original changed during frame indexing")
                header = {"schema": SCHEMA_VERSION, "project": project,
                          "asset": asset, "source_sha256": source_sha,
                          "source_stamp": before, "ffprobe_sha256": self.tool_sha,
                          "frame_count": count, "keyframe_count": keyframes, **meta}
                db.execute("INSERT INTO header VALUES (?,?)", ("metadata", _json(header)))
                db.commit()
            if path.exists():
                raise RuntimeError("Concurrent frame index publication")
            os.replace(stage, path)
            stage = None
            return {"status": "CREATED_SOURCE_STAMP_UNVERIFIED", "path": str(path),
                    **header}
        finally:
            if stage is not None:
                stage.unlink(missing_ok=True)
            if path.exists():
                lock.unlink(missing_ok=True)

    def window(self, project, asset, source_sha, source, *, first_zero, count):
        if (type(first_zero) is not int or type(count) is not int or
            first_zero < 0 or not 1 <= count <= 96):
            raise ValueError("NVP indexed window must be bounded to 1..96 frames")
        info = self.ensure(project, asset, source_sha, source)
        if first_zero + count > info["frame_count"]:
            raise ValueError("Requested frame window exceeds indexed source")
        with self._open_readonly(info["path"]) as db:
            rows = db.execute("SELECT ordinal,pts,keyframe,packet_pos FROM frames WHERE ordinal>=? AND ordinal<? ORDER BY ordinal",
                              (first_zero, first_zero + count)).fetchall()
            anchor = db.execute("SELECT ordinal,pts,packet_pos FROM frames WHERE ordinal<=? AND keyframe=1 ORDER BY ordinal DESC LIMIT 1",
                                (first_zero,)).fetchone()
        if len(rows) != count or anchor is None:
            raise RuntimeError("Index missing expected frame/keyframe range")
        return {"index_status": info["status"], "index_path": info["path"],
                "frames": [{"ordinal": r[0], "pts": r[1], "keyframe": bool(r[2]),
                            "packet_pos": r[3]} for r in rows],
                "seek_anchor": {"ordinal": anchor[0], "pts": anchor[1],
                                "packet_pos": anchor[2]},
                "stream_start_pts": info["stream_start_pts"],
                "time_base_num": info["time_base_num"],
                "time_base_den": info["time_base_den"],
                "source_stamp": info["source_stamp"],
                "source_integrity": "SOURCE_STAMP_UNVERIFIED"}


def seek_seconds(target_pts, stream_start_pts, num, den):
    if stream_start_pts is None:
        stream_start_pts = 0
    if target_pts < stream_start_pts:
        raise RuntimeError("Requested time predates source start")
    with localcontext() as context:
        context.prec = 38
        seconds = Decimal(target_pts - stream_start_pts) * Decimal(num) / Decimal(den)
        return format(seconds, ".12f")
