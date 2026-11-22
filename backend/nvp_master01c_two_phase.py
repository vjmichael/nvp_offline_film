"""MASTER-01C: prepare and verify native AV without worker-side FilmIndex effects.

Stage is a source-bound, unapproved artifact. Only a trusted operation host
that already established human authority and an OS worker-stop witness may
call the commit phase. This module itself grants no permission or film approval.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_film_index import FilmIndex, _id
from backend.nvp_longform_review import (
    FORMAT, REEL_FORMAT, FPS, AUDIO_RATE, MIN_FRAMES, MAX_FRAMES,
    MAX_REEL_FRAMES, MAX_REELS, MAX_MEDIA_BYTES, _binary, _native,
    _verify_stream_copy, probe_reel, reopen_review,
)

MANIFEST = "nvp.master01c.prepared_longform_review.v1"


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _bound_reels(index: FilmIndex, project_id: str, review_id: str,
                 source_refs: list[dict], *, ffprobe: str) -> tuple[list[dict], int, tuple[int, int]]:
    if not isinstance(index, FilmIndex):
        raise TypeError("A trusted existing FilmIndex is required")
    _id(review_id, "new unapproved technical review ID")
    if type(source_refs) is not list or not 2 <= len(source_refs) <= MAX_REELS:
        raise ValueError("Only 2–12 exact technical reels can be prepared")
    seen, sources, total, dimensions = set(), [], 0, None
    for ref in source_refs:
        if type(ref) is not dict or set(ref) != {"object_id", "revision"}:
            raise ValueError("Exact source reference shape required")
        oid, revision = _id(ref["object_id"], "reel ID"), ref["revision"]
        if type(revision) is not int or revision < 1 or oid == review_id or (oid, revision) in seen:
            raise ValueError("Invalid repeated or self-referential reel")
        seen.add((oid, revision))
        record = index.read_revision(project_id, oid, revision)
        data = record["data"]
        if (record["kind"] != "presentation" or data.get("format") != REEL_FORMAT
            or type(data.get("frames")) is not int
            or not 1 <= data["frames"] <= MAX_REEL_FRAMES
            or data.get("creator_approved_final_master") is not False
            or data.get("dcp_delivered") is not False):
            raise RuntimeError("Only bounded original unapproved reels are permitted")
        digest = data["movie_sha256"]
        file = index.verify_media_file(project_id, digest, "video/quicktime")
        stats = probe_reel(Path(file["path"]), ffprobe=ffprobe, expected_frames=data["frames"])
        size = (stats["width"], stats["height"])
        if dimensions is not None and dimensions != size:
            raise RuntimeError("Reel raster differs; no implicit resampling allowed")
        dimensions = size
        total += stats["frames"]
        if total > MAX_FRAMES:
            raise ValueError("Prepared movie exceeds bounded 60-second gate")
        sources.append({"object_id": oid, "revision": revision,
                        "document_sha256": record["document_sha256"],
                        "movie_sha256": digest, "frames": stats["frames"],
                        "path": file["path"]})
    if total < MIN_FRAMES:
        raise ValueError("Prepared movie must be at least 30 seconds")
    return sources, total, dimensions


def prepare_unpublished(index: FilmIndex, project_id: str, review_id: str,
                        source_refs: list[dict], stage: Path, *,
                        ffmpeg: str | None = None, ffprobe: str | None = None) -> dict:
    """Render into host-chosen, new private staging; NO FilmIndex writes.

    Must run inside an OS-contained native worker with an already-sealed plan.
    The independent host will re-probe and verify every source before publish.
    """
    try:
        index.read_revision(project_id, review_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Unapproved review identity already published")
    ff, probe = _binary("ffmpeg", ffmpeg), _binary("ffprobe", ffprobe)
    sources, total, size = _bound_reels(index, project_id, review_id, source_refs, ffprobe=probe)
    stage = Path(stage)
    if (not stage.is_absolute() or stage.is_symlink() or stage.exists()
        or not stage.parent.is_dir() or stage.parent.is_symlink()):
        raise RuntimeError("Prepared film must use a new private staging directory")
    stage.mkdir(mode=0o700)
    listing = stage / "ordered.ffconcat"
    with listing.open("xb") as stream:
        stream.write(b"ffconcat version 1.0\n")
        for reel in sources:
            source = reel["path"]
            if "\n" in source or "\r" in source:
                raise RuntimeError("Unsafe newline in indexed source path")
            escaped = source.replace("'", "'\\''")
            stream.write(("file '" + escaped + "'\n").encode("utf-8"))
        stream.flush(); os.fsync(stream.fileno())
    movie = stage / "prepared.mov"
    _native([ff, "-nostdin", "-hide_banner", "-v", "error", "-xerror",
             "-f", "concat", "-safe", "0", "-i", str(listing),
             "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
             "-fs", str(MAX_MEDIA_BYTES), "-f", "mov", str(movie)], timeout=480)
    if (movie.is_symlink() or movie.stat().st_size > MAX_MEDIA_BYTES):
        raise RuntimeError("Prepared film is symlinked or exceeds media budget")
    stats = probe_reel(movie, ffprobe=probe, expected_frames=total)
    if (stats["width"], stats["height"]) != size or stats["audio_samples"] != total * 2000:
        raise RuntimeError("Prepared movie does not preserve exact AV clock or raster")
    evidence = _verify_stream_copy(sources, movie, ffmpeg=ff, ffprobe=probe)
    for reel in sources:
        index.verify_media_file(project_id, reel["movie_sha256"], "video/quicktime")
    digest = _file_sha(movie)
    document = {"format": FORMAT, "status": "technical_review_unapproved",
                "project_id": project_id, "frames": total, "fps": FPS,
                "duration_seconds": total / FPS, "width": size[0], "height": size[1],
                "video_codec": stats["video_codec"], "audio_codec": stats["audio_codec"],
                "audio_samples": stats["audio_samples"], "movie_sha256": digest,
                "reels": [{k: v for k, v in item.items() if k != "path"} for item in sources],
                "stream_copy_evidence": evidence,
                "creator_approved_final_master": False, "dcp_delivered": False}
    manifest = {"format": MANIFEST, "project_id": project_id, "review_id": review_id,
                "source_refs": source_refs, "movie_sha256": digest,
                "movie_bytes": movie.stat().st_size, "document": document,
                "dependencies": [{"object_id": r["object_id"],
                                  "revision": r["revision"], "role": "presentation"}
                                 for r in sources]}
    location = stage / "prepared.json"
    with location.open("xb") as handle:
        handle.write(canonical_bytes(manifest))
        handle.flush(); os.fsync(handle.fileno())
    # The host checks the same hash; no media/index write occurred in worker.
    return {"status": "PREPARED_UNPUBLISHED", "manifest_sha256": _file_sha(location),
            "movie_sha256": digest, "frames": total, "film_index_modified": False}


def verify_prepared(index: FilmIndex, stage: Path, *, ffmpeg: str | None = None,
                    ffprobe: str | None = None) -> dict:
    """Independently replay the content and source proofs; no FilmIndex writes."""
    ff, probe = _binary("ffmpeg", ffmpeg), _binary("ffprobe", ffprobe)
    stage = Path(stage)
    manifest_file, movie = stage / "prepared.json", stage / "prepared.mov"
    if (stage.is_symlink() or not stage.is_dir() or manifest_file.is_symlink()
        or movie.is_symlink() or not manifest_file.is_file() or not movie.is_file()):
        raise RuntimeError("Incomplete or symlinked native preparation stage")
    raw = manifest_file.read_bytes()
    manifest = json.loads(raw)
    if (canonical_bytes(manifest) != raw or manifest.get("format") != MANIFEST):
        raise RuntimeError("Invalid canonical prepared film manifest")
    project, review = manifest["project_id"], manifest["review_id"]
    if (movie.stat().st_size != manifest["movie_bytes"]
        or movie.stat().st_size > MAX_MEDIA_BYTES
        or _file_sha(movie) != manifest["movie_sha256"]):
        raise RuntimeError("Prepared AV bytes changed after native worker stopped")
    sources, total, size = _bound_reels(index, project, review,
                                        manifest["source_refs"], ffprobe=probe)
    document = manifest["document"]
    deps = [{"object_id": r["object_id"], "revision": r["revision"],
             "role": "presentation"} for r in sources]
    if (manifest["dependencies"] != deps
        or document.get("format") != FORMAT
        or document.get("status") != "technical_review_unapproved"
        or document.get("project_id") != project
        or document.get("movie_sha256") != manifest["movie_sha256"]
        or document.get("creator_approved_final_master") is not False
        or document.get("dcp_delivered") is not False
        or document.get("frames") != total
        or document.get("reels") != [{k: v for k,v in r.items() if k != "path"} for r in sources]
        or document.get("width") != size[0] or document.get("height") != size[1]
        or document.get("audio_samples") != total * 2000
        or document.get("duration_seconds") != total / FPS):
        raise RuntimeError("Prepared film source/document binding is inconsistent")
    stats = probe_reel(movie, ffprobe=probe, expected_frames=total)
    evidence = _verify_stream_copy(sources, movie, ffmpeg=ff, ffprobe=probe)
    if (stats["width"], stats["height"]) != size or evidence != document["stream_copy_evidence"]:
        raise RuntimeError("Prepared source order or compressed AV content changed")
    return {"manifest": manifest, "manifest_sha256": _file_sha(manifest_file),
            "movie": movie, "movie_sha256": manifest["movie_sha256"],
            "frames": total, "dependencies": deps, "document": document}


def commit_prepared(index: FilmIndex, stage: Path, *,
                    ffmpeg: str | None = None, ffprobe: str | None = None) -> dict:
    """Trusted-host-only commit AFTER a durable OS worker-stop witness.

    Never call from a model, local browser route, or worker. The production
    host must establish creator authorization & exact source bindings before
    this operation. Safe repeat after a host crash: same revision, no replay.
    """
    proof = verify_prepared(index, stage, ffmpeg=ffmpeg, ffprobe=ffprobe)
    manifest = proof["manifest"]
    project, review = manifest["project_id"], manifest["review_id"]
    expected_document, expected_edges = proof["document"], proof["dependencies"]
    try:
        existing = index.read_revision(project, review)
    except KeyError:
        existing = None
    if existing is None:
        media = index.put_media_file(project, proof["movie"], "video/quicktime",
                                     max_bytes=MAX_MEDIA_BYTES)
        if media["sha256"] != manifest["movie_sha256"]:
            raise RuntimeError("FilmIndex stored a movie with unexpected digest")
        # Do not swallow a failed commit or a simulated host crash. A later
        # independently authorized reconciliation may compare an already
        # published immutable revision and finish without running FFmpeg.
        index.register_revision(project, review, "presentation", expected_document,
                                expected_revision=0, dependencies=expected_edges)
    existing = index.read_revision(project, review, 1)
    if (existing["kind"] != "presentation" or existing["data"] != expected_document
        or existing["dependencies"] != sorted(expected_edges, key=lambda x:
                (x["object_id"], x["revision"], x["role"]))
        or len(index.history(project, review)) != 1):
        raise RuntimeError("Conflicting film publication at a previously used review identity")
    reopen = reopen_review(index, project, review, ffmpeg=ffmpeg, ffprobe=ffprobe)
    if (reopen["movie_sha256"] != manifest["movie_sha256"] or
        reopen["frames"] != manifest["document"]["frames"]):
        raise RuntimeError("Committed film differs from prepared original")
    return {"state": "COMMITTED_UNAPPROVED", "review_id": review,
            "revision": existing["revision"],
            "document_sha256": existing["document_sha256"],
            "movie_sha256": reopen["movie_sha256"], "frames": reopen["frames"],
            "creator_approved_final_master": False, "replayed": False}