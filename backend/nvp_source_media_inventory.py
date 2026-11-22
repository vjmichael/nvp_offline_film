"""SCALE-02B: FFprobe metadata and verified storage-volume associations.

Native desktop adapter only. Volume IDs are host-assigned logical identities,
NOT evidence that a removable device has a stable physical hardware ID.
Media source hashes remain authoritative in ExternalMediaCatalog.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from backend.nvp_w1g_owned_subprocess import run_owned_subprocess
import tempfile

from backend.nvp_external_media_catalog import ExternalMediaCatalog, _read_and_hash
from backend.nvp_film_index import _id, _require_pid
from backend.nvp_studio import now

PROBE_LIMIT = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_RATIONAL = re.compile(r"(0|[1-9][0-9]*)/([1-9][0-9]*)\Z")


def _fraction(value):
    """Preserve source timebase as an exact rational; unknown stays null."""
    if value is None or value in ("N/A", "0/0", ""):
        return None
    if type(value) is not str or not _RATIONAL.fullmatch(value):
        raise RuntimeError("Invalid FFprobe rational timebase")
    a, b = (int(n) for n in value.split("/"))
    if a > 2**63 - 1 or b > 2**63 - 1:
        raise RuntimeError("FFprobe timebase exceeds signed 64-bit range")
    return value


def _bounded_string(value, maximum=160):
    if value is None:
        return None
    if type(value) is not str or len(value) > maximum or "\x00" in value:
        raise RuntimeError("Malformed FFprobe string")
    return value


def normalize_probe(document):
    """Retain bounded, factual stream metadata; never claim footage decoded."""
    if type(document) is not dict or type(document.get("streams")) is not list:
        raise RuntimeError("FFprobe response missing streams")
    if len(document["streams"]) > 128:
        raise RuntimeError("Unbounded FFprobe stream list")
    result = []
    for stream in document["streams"]:
        if type(stream) is not dict:
            raise RuntimeError("Malformed FFprobe stream")
        typ = stream.get("codec_type")
        if typ not in ("video", "audio", "subtitle", "data", "attachment"):
            continue
        index = stream.get("index")
        if type(index) is not int or not 0 <= index <= 65535:
            raise RuntimeError("Invalid native stream index")
        item = {"index": index, "kind": typ,
                "codec": _bounded_string(stream.get("codec_name")),
                "time_base": _fraction(stream.get("time_base"))}
        if typ == "video":
            width, height = stream.get("width"), stream.get("height")
            if (type(width) is not int or type(height) is not int or
                not 1 <= width <= 65536 or not 1 <= height <= 65536):
                raise RuntimeError("Invalid source video dimensions")
            item.update(width=width, height=height,
                        avg_frame_rate=_fraction(stream.get("avg_frame_rate")),
                        raw_frame_rate=_fraction(stream.get("r_frame_rate")),
                        pixel_format=_bounded_string(stream.get("pix_fmt")),
                        color_primaries=_bounded_string(stream.get("color_primaries")),
                        color_transfer=_bounded_string(stream.get("color_transfer")),
                        color_space=_bounded_string(stream.get("color_space")))
        elif typ == "audio":
            channels = stream.get("channels")
            if type(channels) is not int or not 1 <= channels <= 256:
                raise RuntimeError("Invalid native audio channels")
            item.update(channels=channels,
                        channel_layout=_bounded_string(stream.get("channel_layout")),
                        sample_rate=_bounded_string(stream.get("sample_rate")))
        result.append(item)
    if not result:
        raise RuntimeError("No recognized source media streams")
    fmt = document.get("format") or {}
    if type(fmt) is not dict:
        raise RuntimeError("Invalid native container metadata")
    return {"format": "nvp.source.probe.v1",
            "container": _bounded_string(fmt.get("format_name")),
            "duration_seconds_reported": _bounded_string(fmt.get("duration")),
            "streams": result,
            "decoded_and_verified": False}


def ffprobe_media(path, *, ffprobe="ffprobe", timeout=60):
    """Read metadata from the actual local media using an explicit native tool."""
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError("Invalid native probe timeout")
    if type(ffprobe) is not str or not ffprobe or "\x00" in ffprobe:
        raise ValueError("Invalid native executable")
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise RuntimeError("Source media unavailable for probing")
    args = [ffprobe, "-v", "error", "-show_entries",
            "format=format_name,duration:stream=index,codec_type,codec_name,time_base,"
            "width,height,avg_frame_rate,r_frame_rate,pix_fmt,color_primaries,"
            "color_transfer,color_space,channels,channel_layout,sample_rate",
            "-of", "json", str(p)]
    # ffprobe is an independent native executable; no shell or path expansion.
    # Avoid collecting an untrusted native process's stdout/stderr in RAM.
    # This is a disk-backed, bounded *read*; final output size is checked
    # before parsing. It is not a process-level disk quota.
    with tempfile.TemporaryFile() as report:
        completed = run_owned_subprocess(
            args, stdout=report, stderr=subprocess.DEVNULL,
            timeout=timeout, check=False)
        size = report.seek(0, os.SEEK_END)
        if completed.returncode != 0 or size > PROBE_LIMIT:
            raise RuntimeError("Native FFprobe failed or exceeded metadata limit")
        report.seek(0)
        try:
            document = json.loads(report.read(PROBE_LIMIT + 1))
        except (UnicodeError, ValueError) as exc:
            raise RuntimeError("Unreadable FFprobe metadata") from exc
    return normalize_probe(document)


class SourceMediaInventory:
    """Additional normalized metadata and logical volume records in Studio SQLite."""

    def __init__(self, catalog: ExternalMediaCatalog):
        if not isinstance(catalog, ExternalMediaCatalog):
            raise TypeError("Existing source catalog required")
        self.catalog = catalog
        self.studio = catalog.studio
        with self.studio._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS scale_source_volumes (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                volume_id TEXT NOT NULL,
                registered_root TEXT NOT NULL,
                label TEXT NOT NULL,
                PRIMARY KEY(project_id,volume_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS scale_source_details (
                project_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                volume_id TEXT NOT NULL,
                path_relative TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                probe_json TEXT NOT NULL,
                probe_tool TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                PRIMARY KEY(project_id,asset_id),
                FOREIGN KEY(project_id,asset_id)
                    REFERENCES scale_source_media(project_id,asset_id) ON DELETE CASCADE,
                FOREIGN KEY(project_id,volume_id)
                    REFERENCES scale_source_volumes(project_id,volume_id))""")

    def register_volume(self, project_id, volume_id, root, *, label):
        _require_pid(project_id)
        _id(volume_id, "logical storage volume")
        if type(label) is not str or not 1 <= len(label) <= 120:
            raise ValueError("Invalid volume label")
        root = Path(root)
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise ValueError("Trusted native storage root must be an existing directory")
        with self.studio._connection() as db:
            db.execute("INSERT INTO scale_source_volumes VALUES (?,?,?,?)",
                       (project_id, volume_id, str(root), label))
        return {"volume_id": volume_id, "identity": "host_assigned_logical_volume",
                "root": str(root)}

    def enrich(self, project_id, asset_id, volume_id, *, ffprobe="ffprobe"):
        """Bind an already hashed asset to a volume and actual media metadata.

        Full source rehash occurs before and after probe to reject changed bytes.
        Metadata never becomes proof of a decoded picture/audio master.
        """
        _require_pid(project_id)
        _id(asset_id, "source asset")
        _id(volume_id, "logical volume")
        with self.studio._connection() as db:
            asset = db.execute("""SELECT media_path,sha256,size_bytes
                FROM scale_source_media WHERE project_id=? AND asset_id=?""",
                (project_id, asset_id)).fetchone()
            volume = db.execute("""SELECT registered_root FROM scale_source_volumes
                WHERE project_id=? AND volume_id=?""",
                (project_id, volume_id)).fetchone()
        if asset is None or volume is None:
            raise KeyError("Source or volume not registered in this project")
        path, root = Path(asset["media_path"]), Path(volume["registered_root"])
        if root.is_symlink() or not root.is_dir():
            raise RuntimeError("Storage volume offline or unsafe")
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise PermissionError("Source is outside registered volume") from exc
        if not relative.parts or any(part == ".." for part in relative.parts):
            raise PermissionError("Invalid volume-relative source path")
        pre = _read_and_hash(path)
        if pre["sha256"] != asset["sha256"] or pre["size_bytes"] != asset["size_bytes"]:
            raise RuntimeError("Original source no longer matches indexed hash")
        media = ffprobe_media(path, ffprobe=ffprobe)
        post = _read_and_hash(path)
        if post["sha256"] != pre["sha256"] or post["size_bytes"] != pre["size_bytes"]:
            raise RuntimeError("Original source changed during FFprobe")
        raw = json.dumps(media, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self.studio._connection() as db:
            db.execute("""INSERT INTO scale_source_details VALUES (?,?,?,?,?,?,?,?)""",
                       (project_id, asset_id, volume_id, relative.as_posix(),
                        pre["sha256"], raw, ffprobe, now()))
        return {"asset_id": asset_id, "volume_id": volume_id,
                "source_sha256": pre["sha256"], "media": media}

    def describe(self, project_id, asset_id):
        """Metadata remains available when the original volume is disconnected."""
        _require_pid(project_id)
        _id(asset_id, "source asset")
        with self.studio._connection() as db:
            row = db.execute("""SELECT d.volume_id,d.path_relative,d.source_sha256,
                       d.probe_json,v.label
                FROM scale_source_details d JOIN scale_source_volumes v
                  ON v.project_id=d.project_id AND v.volume_id=d.volume_id
                WHERE d.project_id=? AND d.asset_id=?""",
                (project_id, asset_id)).fetchone()
        if row is None:
            raise KeyError("No verified source metadata record")
        return {"asset_id": asset_id, "volume_id": row["volume_id"],
                "relative_path": row["path_relative"], "volume_label": row["label"],
                "sha256": row["source_sha256"], "media": json.loads(row["probe_json"]),
                "availability": self.catalog.probe(project_id, asset_id)["status"]}

    def relink_volume(self, project_id, volume_id, new_root):
        """Re-home a volume only when *every* registered source rehashes exactly.

        No partial relink, no source ID replacement, no unverified path update.
        """
        _require_pid(project_id)
        _id(volume_id, "logical volume")
        new_root = Path(new_root)
        if not new_root.is_absolute() or new_root.is_symlink() or not new_root.is_dir():
            raise ValueError("New storage root is not a trusted existing directory")
        with self.studio._connection() as db:
            volume = db.execute("""SELECT 1 FROM scale_source_volumes
                WHERE project_id=? AND volume_id=?""", (project_id, volume_id)).fetchone()
            rows = db.execute("""SELECT d.asset_id,d.path_relative,d.source_sha256,
                       m.size_bytes FROM scale_source_details d
                       JOIN scale_source_media m ON m.project_id=d.project_id
                         AND m.asset_id=d.asset_id
                       WHERE d.project_id=? AND d.volume_id=?
                       ORDER BY d.asset_id""", (project_id, volume_id)).fetchall()
        if volume is None:
            raise KeyError("Unknown project storage volume")
        # Verification is outside the write transaction so long disk reads
        # do not block metadata/UI queries. Rehash again on actual consumption.
        paths = []
        for row in rows:
            target = new_root / row["path_relative"]
            check = _read_and_hash(target)
            if check["sha256"] != row["source_sha256"] or check["size_bytes"] != row["size_bytes"]:
                raise RuntimeError("Relocated source checksum mismatch; no paths changed")
            paths.append((str(target), project_id, row["asset_id"]))
        with self.studio._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for path, pid, aid in paths:
                db.execute("""UPDATE scale_source_media SET media_path=?
                    WHERE project_id=? AND asset_id=?""", (path, pid, aid))
            db.execute("""UPDATE scale_source_volumes SET registered_root=?
                WHERE project_id=? AND volume_id=?""",
                (str(new_root), project_id, volume_id))
        return {"volume_id": volume_id, "relinked_assets": len(paths),
                "verified_at_relink": True}
