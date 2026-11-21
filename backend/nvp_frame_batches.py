"""FILM-01A: restartable, source-hash-bound frame batches.

Worker-side only. The native host must authorize an exact FilmIndex edit,
supervise the worker, resource-admit execution and publish final output.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path

FORMAT = "nvp.picture.frame_batch.v1"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sync_dir(directory):
    if os.name != "nt":
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def iter_batches(rows, *, source_revision_sha256, batch_frames=48,
                 start_frame=1):
    """Lazily seal a bounded batch from source rows, regardless of film length.

    'rows' can be an iterator backed by an indexed edit/timeline cursor, so
    this never materializes a whole feature's frame map. A resumed cursor
    must supply its exact first output frame. No permission is conferred.
    """
    if (type(batch_frames) is not int or not 1 <= batch_frames <= 96 or
        type(start_frame) is not int or not 1 <= start_frame < 2**63 or
        type(source_revision_sha256) is not str or
        len(source_revision_sha256) != 64 or
        any(c not in "0123456789abcdef" for c in source_revision_sha256)):
        raise ValueError("Invalid batch bounds, start frame or source revision digest")
    active, expected = [], start_frame
    seen = False

    def seal(frames):
        doc = {"format": FORMAT,
               "source_revision_sha256": source_revision_sha256,
               "start_frame": frames[0]["edit_frame"],
               "end_frame_exclusive": frames[-1]["edit_frame"] + 1,
               "frames": frames}
        doc["plan_sha256"] = _sha(_canonical(doc))
        return doc

    for row in rows:
        if type(row) is not dict or set(row) != {
            "edit_frame", "source_frame", "source_sha256", "shot_id"
        }:
            raise ValueError("Incomplete or unexpected source mapping")
        n, src = row["edit_frame"], row["source_frame"]
        digest, shot = row["source_sha256"], row["shot_id"]
        if (type(n) is not int or n != expected or n >= 2**63 or
            type(src) is not int or not 1 <= src < 2**63 or
            type(digest) is not str or len(digest) != 64 or
            any(c not in "0123456789abcdef" for c in digest) or
            type(shot) is not str or not 1 <= len(shot) <= 160):
            raise ValueError("Untrusted, non-contiguous or invalid source frame mapping")
        active.append(dict(row))
        seen = True
        expected += 1
        if len(active) == batch_frames:
            yield seal(active)
            active = []
    if active:
        yield seal(active)
    if not seen:
        raise ValueError("Cannot plan an empty film")


def plan_batches(rows, *, source_revision_sha256, batch_frames=48):
    """Legacy short-fixture wrapper; long-form producers MUST use iter_batches."""
    return list(iter_batches(rows, source_revision_sha256=source_revision_sha256,
                             batch_frames=batch_frames))


def _check_plan(packet):
    if type(packet) is not dict or set(packet) != {
        "format", "source_revision_sha256", "start_frame",
        "end_frame_exclusive", "frames", "plan_sha256"
    }:
        raise ValueError("Invalid batch plan")
    bare = {k: v for k, v in packet.items() if k != "plan_sha256"}
    if (packet["format"] != FORMAT or
        packet["plan_sha256"] != _sha(_canonical(bare)) or
        type(packet["frames"]) is not list or
        not 1 <= len(packet["frames"]) <= 96 or
        type(packet["start_frame"]) is not int or
        packet["start_frame"] < 1):
        raise ValueError("Altered or unsupported batch plan")
    expected = packet["start_frame"]
    for row in packet["frames"]:
        if (type(row) is not dict or row.get("edit_frame") != expected or
            type(row.get("source_frame")) is not int or
            type(row.get("source_sha256")) is not str):
            raise ValueError("Invalid batch frame sequence")
        expected += 1
    if packet["end_frame_exclusive"] != expected:
        raise ValueError("Altered batch boundary")


def _file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def verify_batch(root, packet):
    """Accept checkpoint reuse only after independent bytes and receipt checks."""
    _check_plan(packet)
    root = Path(root)
    folder = root / packet["plan_sha256"]
    if root.is_symlink() or folder.is_symlink() or not folder.is_dir():
        return False
    manifest = folder / "receipt.json"
    if manifest.is_symlink() or not manifest.is_file():
        return False
    try:
        raw = manifest.read_bytes()
        receipt = json.loads(raw)
        if raw != _canonical(receipt):
            return False
        outputs = []
        for row in packet["frames"]:
            name = f"frame_{row['edit_frame']:09d}.png"
            frame = folder / name
            if frame.is_symlink() or not frame.is_file():
                return False
            digest = _file_sha(frame)
            if digest != row["source_sha256"]:
                return False
            outputs.append({"frame": row["edit_frame"], "name": name,
                            "sha256": digest, "size_bytes": frame.stat().st_size})
        return receipt == {"format": FORMAT,
                           "plan_sha256": packet["plan_sha256"], "outputs": outputs}
    except (OSError, ValueError, TypeError, KeyError):
        return False


def materialize_batch(root, packet, *, get_source_bytes):
    """Create verified batch or safely reuse; never overwrite uncertain output."""
    _check_plan(packet)
    if not callable(get_source_bytes):
        raise TypeError("Trusted FilmIndex source reader required")
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Unsafe or missing host-authorized batch root")
    folder = root / packet["plan_sha256"]
    if folder.exists() or folder.is_symlink():
        if verify_batch(root, packet):
            return {"status": "VERIFIED_REUSED", "plan_sha256": packet["plan_sha256"]}
        raise RuntimeError("Incomplete/altered batch requires host reconciliation; refusing overwrite")
    folder.mkdir(mode=0o700)
    _sync_dir(root)
    outputs = []
    for row in packet["frames"]:
        data = get_source_bytes(dict(row))
        if type(data) is not bytes or _sha(data) != row["source_sha256"]:
            raise RuntimeError("Indexed source bytes disagree with authorized frame")
        name = f"frame_{row['edit_frame']:09d}.png"
        with (folder / name).open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        outputs.append({"frame": row["edit_frame"], "name": name,
                        "sha256": row["source_sha256"], "size_bytes": len(data)})
    receipt = {"format": FORMAT, "plan_sha256": packet["plan_sha256"],
               "outputs": outputs}
    with (folder / "receipt.json").open("xb") as stream:
        stream.write(_canonical(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    _sync_dir(folder)
    if not verify_batch(root, packet):
        raise RuntimeError("New frame batch failed independent verification")
    return {"status": "VERIFIED_CREATED", "plan_sha256": packet["plan_sha256"]}
