"""NVP-MASTER-01A: source-indexed 30–60s technical *review* assembly.

Join independently indexed, bounded 24fps ProRes/PCM24 reels without inventing
creator approvals, neural generation, or a feature-length rendering capability.

The production host must authorize the operation and supervise FFmpeg; this
service neither grants permission nor silently rewrites a FilmIndex source.
"""
from __future__ import annotations

import json
import hashlib
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import tempfile

from backend.nvp_film_index import FilmIndex, _id

FORMAT = "nvp.master01a.multireel_technical_review.v1"
REEL_FORMAT = "nvp.master01a.technical_av_reel.v1"
FPS = 24
AUDIO_RATE = 48000
MIN_FRAMES = 24 * 30
MAX_FRAMES = 24 * 60
MAX_REEL_FRAMES = 480  # Existing worker limits; do NOT relax without worker tests.
MAX_REELS = 12
MAX_MEDIA_BYTES = 2 * 1024**3  # FilmIndex streaming media index limit.


def _native(argv: list[str], *, timeout: int) -> bytes:
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Native media worker unavailable or timed out") from exc
    if result.returncode:
        raise RuntimeError("Native media operation failed: " +
                           result.stderr.decode("utf-8", "replace")[-1500:])
    return result.stdout


def _binary(name: str, requested: str | None) -> str:
    value = requested or name
    if not isinstance(value, str) or not value:
        raise ValueError("Invalid media executable")
    found = shutil.which(value)
    if not found:
        raise RuntimeError("Required native executable missing: " + name)
    return found


def probe_reel(movie: Path, *, ffprobe: str, expected_frames: int | None = None) -> dict:
    """Independently decode stream metadata; enforce exact 24 fps PCM sample clock."""
    if movie.is_symlink() or not movie.is_file():
        raise RuntimeError("Missing or symlinked indexed source media")
    raw = _native([ffprobe, "-v", "error", "-count_frames", "-show_streams",
                   "-of", "json", str(movie)], timeout=90)
    try:
        streams = json.loads(raw)["streams"]
        video = [s for s in streams if s.get("codec_type") == "video"]
        audio = [s for s in streams if s.get("codec_type") == "audio"]
        if len(streams) != 2 or len(video) != 1 or len(audio) != 1:
            raise ValueError("Expected exactly one video and one audio stream")
        v, a = video[0], audio[0]
        frames = int(v["nb_read_frames"])
        fps = Fraction(v["avg_frame_rate"])
        audio_samples = Fraction(int(a["duration_ts"])) * Fraction(a["time_base"])*AUDIO_RATE
        width, height = int(v["width"]), int(v["height"])
        if (v.get("codec_name") != "prores" or v.get("codec_tag_string") != "apch"
            or v.get("pix_fmt") != "yuv422p10le" or fps != FPS
            or a.get("codec_name") != "pcm_s24le" or a.get("sample_rate") != str(AUDIO_RATE)
            or int(a["channels"]) != 2 or width < 64 or height < 64
            or width % 2 or height % 2 or frames < 1 or audio_samples != frames * 2000):
            raise ValueError("Source media stream profile or exact AV clock mismatch")
        if expected_frames is not None and frames != expected_frames:
            raise ValueError("Indexed source frame count differs from decoded media")
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise RuntimeError("Invalid or incompatible ProRes/PCM24 AV reel") from exc
    # Exact samples/frames alone do not exclude timestamp gaps at reel joins.
    # Require both independent packet clocks to begin at zero and be contiguous.
    for selector, expected in (("v:0", Fraction(frames, FPS)),
                               ("a:0", Fraction(frames * 2000, AUDIO_RATE))):
        _verify_packet_clock(movie, ffprobe=ffprobe, selector=selector,
                             expected_seconds=expected)
    return {"frames": frames, "width": width, "height": height, "fps": FPS,
            "audio_samples": int(audio_samples), "video_codec": "prores_422_hq",
            "audio_codec": "pcm_s24le", "sample_rate": AUDIO_RATE, "channels": 2}





def _verify_packet_clock(movie: Path, *, ffprobe: str, selector: str,
                         expected_seconds: Fraction) -> None:
    raw = _native([ffprobe, "-v", "error", "-select_streams", selector,
                   "-show_streams", "-show_packets",
                   "-show_entries", "stream=time_base:packet=pts,duration",
                   "-of", "json", str(movie)], timeout=120)
    try:
        body = json.loads(raw)
        tb = Fraction(body["streams"][0]["time_base"])
        rows = body["packets"]
        if not rows or tb <= 0:
            raise ValueError("No timed packets")
        next_pts = 0
        for row in rows:
            pts = int(row["pts"])
            duration = int(row["duration"])
            if pts != next_pts or duration <= 0:
                raise ValueError("Gapped, overlapping or non-monotonic packet timestamps")
            next_pts = pts + duration
        if next_pts * tb != expected_seconds:
            raise ValueError("Packet timestamp extent differs from exact film clock")
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
        raise RuntimeError("Source/review packet timestamps are not contiguous") from exc


def _video_packet_hashes(movie: Path, *, ffprobe: str, frames: int) -> list[str]:
    """SHA-256 of real compressed ProRes packets in presentation order."""
    raw = _native([ffprobe, "-v", "error", "-select_streams", "v:0",
                   "-show_packets", "-show_data_hash", "sha256",
                   "-show_entries", "packet=data_hash", "-of", "json",
                   str(movie)], timeout=120)
    try:
        values = [p["data_hash"] for p in json.loads(raw)["packets"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Cannot verify original video packet payloads") from exc
    if len(values) != frames or any(
        not isinstance(value, str) or not value.startswith("SHA256:")
        or len(value) != 71 or not all(c in "0123456789abcdef" for c in value[7:])
        for value in values
    ):
        raise RuntimeError("Compressed video packet count or SHA proof invalid")
    return values


def _decoded_pcm(movie: Path, *, ffmpeg: str, frames: int) -> bytes:
    """Bounded PCM24 exact evidence: 60 seconds requires <=17.3 MiB."""
    raw = _native([ffmpeg, "-nostdin", "-v", "error", "-xerror",
                   "-i", str(movie), "-map", "0:a:0", "-c:a", "pcm_s24le",
                   "-f", "s24le", "pipe:1"], timeout=180)
    if len(raw) != frames * 2000 * 6:
        raise RuntimeError("Decoded PCM24 reel length differs from picture clock")
    return raw


def _verify_stream_copy(reels: list[dict], movie: Path, *,
                        ffmpeg: str, ffprobe: str) -> dict:
    """Prove concatenated compressed video and decoded audio are byte-identical.

    Frame totals alone could hide duplicated footage, dropped packets or
    padded/shifted silence. This compares EVERY compressed frame packet and
    EVERY decoded stereo PCM24 sample, in the director-specified reel order.
    """
    frames = sum(r["frames"] for r in reels)
    ordered = []
    pcm = hashlib.sha256()
    for reel in reels:
        src = Path(reel["path"])
        ordered.extend(_video_packet_hashes(src, ffprobe=ffprobe, frames=reel["frames"]))
        pcm.update(_decoded_pcm(src, ffmpeg=ffmpeg, frames=reel["frames"]))
    delivered_packets = _video_packet_hashes(movie, ffprobe=ffprobe, frames=frames)
    if delivered_packets != ordered:
        raise RuntimeError("Source-to-review video packet content/order changed")
    delivered_audio = _decoded_pcm(movie, ffmpeg=ffmpeg, frames=frames)
    delivered_pcm_sha = hashlib.sha256(delivered_audio).hexdigest()
    if delivered_pcm_sha != pcm.hexdigest():
        raise RuntimeError("Source-to-review PCM audio samples differ")
    packet_sha = hashlib.sha256("\n".join(ordered).encode("ascii")).hexdigest()
    return {"compressed_video_packet_order_sha256": packet_sha,
            "decoded_pcm24_sha256": delivered_pcm_sha,
            "all_video_packets_identical": True,
            "all_audio_samples_identical": True}


def index_technical_reel(index: FilmIndex, project_id: str, reel_id: str,
                         producer_id: str, producer_revision: int, *,
                         ffprobe: str | None = None) -> dict:
    """Bind an already indexed, independently probed AV source to a bounded reel.

    Does not import arbitrary filesystem media or create creator approval. An
    existing NVP presentation/master revision is the provenance link, and its
    exact media SHA must already be in this same project's FilmIndex.
    """
    if not isinstance(index, FilmIndex):
        raise TypeError("A trusted FilmIndex instance is required")
    _id(reel_id, "technical reel ID")
    _id(producer_id, "existing producer ID")
    if reel_id == producer_id or type(producer_revision) is not int or producer_revision < 1:
        raise ValueError("Invalid producer identity or revision")
    original = index.read_revision(project_id, producer_id, producer_revision)
    if original["kind"] not in ("presentation", "master"):
        raise ValueError("Only indexed video presentation/master producers can supply AV reels")
    source = original["data"]
    digest = source.get("movie_sha256") or source.get("rendered_mov_sha256")
    if not isinstance(digest, str):
        raise RuntimeError("Indexed video producer has no immutable movie SHA")
    checked = index.verify_media_file(project_id, digest, "video/quicktime")
    stats = probe_reel(Path(checked["path"]), ffprobe=_binary("ffprobe", ffprobe))
    if not 1 <= stats["frames"] <= MAX_REEL_FRAMES:
        raise ValueError("Existing source exceeds per-reel worker limit")
    if source.get("frames", source.get("frame_count")) != stats["frames"]:
        raise RuntimeError("Producer frame metadata differs from decoded AV")
    doc = {"format": REEL_FORMAT, "frames": stats["frames"], "fps": FPS,
           "movie_sha256": checked["sha256"],
           "producer_id": producer_id, "producer_revision": producer_revision,
           "producer_document_sha256": original["document_sha256"],
           "creator_approved_final_master": False, "dcp_delivered": False,
           "status": "indexed_technical_reel_not_new_approval"}
    created = index.register_revision(project_id, reel_id, "presentation", doc,
         expected_revision=0, dependencies=[{"object_id": producer_id,
                                               "revision": producer_revision,
                                               "role": "presentation"}])
    return {"reel_id": reel_id, "revision": created["revision"],
            "frames": stats["frames"], "movie_sha256": checked["sha256"],
            "creator_approved_final_master": False}


def assemble_review(index: FilmIndex, project_id: str, review_id: str,
                    source_refs: list[dict], *, ffmpeg: str | None = None,
                    ffprobe: str | None = None) -> dict:
    """Publish a nonapproved media review with immutable per-reel dependency edges.

    source_refs entries contain EXACTLY object_id and revision. No paths or
    model-declared approvals are accepted. The source AV must already be
    indexed under this project and its bytes independently rehashed.
    """
    if not isinstance(index, FilmIndex):
        raise TypeError("A trusted FilmIndex instance is required")
    _id(review_id, "technical review ID")
    if not isinstance(source_refs, list) or not 2 <= len(source_refs) <= MAX_REELS:
        raise ValueError("A review requires 2–12 indexed short reels")
    # Fail fast before any native work on an already used output ID.
    try:
        index.read_revision(project_id, review_id)
    except KeyError:
        pass
    else:
        raise RuntimeError("Review identity already published; never overwrite")
    ff = _binary("ffmpeg", ffmpeg)
    probe = _binary("ffprobe", ffprobe)
    reels, dependencies, total, dimensions, seen = [], [], 0, None, set()
    for item in source_refs:
        if type(item) is not dict or set(item) != {"object_id", "revision"}:
            raise ValueError("Each reel needs exactly an object_id and revision")
        oid, revision = _id(item["object_id"], "source reel ID"), item["revision"]
        if type(revision) is not int or revision < 1 or oid == review_id:
            raise ValueError("Invalid reel revision or self-reference")
        if (oid, revision) in seen:
            raise ValueError("Repeated reel references are not permitted")
        seen.add((oid, revision))
        source = index.read_revision(project_id, oid, revision)
        data = source["data"]
        if (source["kind"] != "presentation" or data.get("format") != REEL_FORMAT
            or data.get("creator_approved_final_master") is not False
            or data.get("dcp_delivered") is not False
            or type(data.get("frames")) is not int
            or not 1 <= data["frames"] <= MAX_REEL_FRAMES):
            raise RuntimeError("Only indexed, unapproved bounded AV reels may be assembled")
        checked = index.verify_media_file(project_id, data["movie_sha256"], "video/quicktime")
        details = probe_reel(Path(checked["path"]), ffprobe=probe,
                             expected_frames=data["frames"])
        if dimensions is None:
            dimensions = (details["width"], details["height"])
        elif dimensions != (details["width"], details["height"]):
            raise RuntimeError("Reel dimensions incompatible; no implicit rescaling")
        total += details["frames"]
        if total > MAX_FRAMES:
            raise ValueError("Technical review exceeds 60-second bounded film gate")
        reels.append({"object_id": oid, "revision": revision,
                      "document_sha256": source["document_sha256"],
                      "movie_sha256": checked["sha256"], "frames": details["frames"],
                      "path": checked["path"]})
        dependencies.append({"object_id": oid, "revision": revision, "role": "presentation"})
    if total < MIN_FRAMES:
        raise ValueError("Technical review must contain at least 30 seconds of frames")
    # The concat demuxer references only trusted FilmIndex-generated hash paths.
    # Stage in an isolated, application-owned project tree, never an external path.
    stage_parent = index.blob_root / project_id
    stage_parent.mkdir(exist_ok=True)
    if stage_parent.is_symlink() or not stage_parent.resolve().is_relative_to(index.blob_root):
        raise RuntimeError("Review staging escaped the film project")
    with tempfile.TemporaryDirectory(prefix=".master01a-", dir=stage_parent) as temp:
        temp = Path(temp)
        listing = temp / "reels.ffconcat"
        with listing.open("x", encoding="utf-8", newline="\n") as out:
            out.write("ffconcat version 1.0\n")
            for reel in reels:
                # FFmpeg concat paths are apostrophe-escaped; hashes themselves
                # contain only hex and our generated directory names are bounded.
                escaped = reel["path"].replace("'", "'\\''")
                out.write("file '" + escaped + "'\n")
        output = temp / "review.mov"
        _native([ff, "-nostdin", "-hide_banner", "-v", "error", "-xerror",
                 "-f", "concat", "-safe", "0", "-i", str(listing),
                 "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
                 "-f", "mov", str(output)], timeout=480)
        result = probe_reel(output, ffprobe=probe, expected_frames=total)
        if result["audio_samples"] != total * 2000 or (result["width"], result["height"]) != dimensions:
            raise RuntimeError("Native multi-reel AV output differs from source clock")
        stream_evidence = _verify_stream_copy(reels, output, ffmpeg=ff, ffprobe=probe)
        # Rehash each input after native work; detect concurrent external damage.
        for reel in reels:
            index.verify_media_file(project_id, reel["movie_sha256"], "video/quicktime")
        media = index.put_media_file(project_id, output, "video/quicktime", max_bytes=MAX_MEDIA_BYTES)
        doc = {"format": FORMAT, "status": "technical_review_unapproved",
               "project_id": project_id, "frames": total, "fps": FPS,
               "duration_seconds": total / FPS,
               "width": result["width"], "height": result["height"],
               "video_codec": result["video_codec"], "audio_codec": result["audio_codec"],
               "audio_samples": result["audio_samples"], "movie_sha256": media["sha256"],
               "reels": [{k: v for k, v in x.items() if k != "path"} for x in reels],
               "stream_copy_evidence": stream_evidence,
               "creator_approved_final_master": False, "dcp_delivered": False}
        indexed = index.register_revision(project_id, review_id, "presentation", doc,
                                          expected_revision=0, dependencies=dependencies)
        return {"status": "VERIFIED_TECHNICAL_REVIEW_UNAPPROVED",
                "review_id": review_id, "revision": indexed["revision"],
                "document_sha256": indexed["document_sha256"],
                "movie_sha256": media["sha256"], "frames": total,
                "duration_seconds": total / FPS, "creator_approved_final_master": False}


def reopen_review(index: FilmIndex, project_id: str, review_id: str, *,
                  ffprobe: str | None = None, ffmpeg: str | None = None) -> dict:
    """Verify stored media, whole-film clock and exact indexed reel lineage."""
    row = index.read_revision(project_id, review_id, 1)
    data = row["data"]
    if (row["kind"] != "presentation" or data.get("format") != FORMAT
        or data.get("status") != "technical_review_unapproved"
        or data.get("creator_approved_final_master") is not False
        or data.get("dcp_delivered") is not False
        or type(data.get("frames")) is not int
        or not MIN_FRAMES <= data["frames"] <= MAX_FRAMES):
        raise RuntimeError("Not an unapproved long-form technical review")
    deps = [{"object_id": x["object_id"], "revision": x["revision"],
             "role": "presentation"} for x in data["reels"]]
    if sorted(deps, key=lambda d: (d["object_id"],d["revision"],d["role"])) != row["dependencies"]:
        raise RuntimeError("Technical review source dependency edges changed")
    if sum(x["frames"] for x in data["reels"]) != data["frames"]:
        raise RuntimeError("Technical review reel frame totals changed")
    source_paths = []
    for reel in data["reels"]:
        source = index.read_revision(project_id, reel["object_id"], reel["revision"])
        if source["document_sha256"] != reel["document_sha256"] or source["data"].get("movie_sha256") != reel["movie_sha256"]:
            raise RuntimeError("Technical review source revision provenance changed")
        source_paths.append(index.verify_media_file(project_id, reel["movie_sha256"], "video/quicktime")["path"])
    checked = index.verify_media_file(project_id, data["movie_sha256"], "video/quicktime")
    probe = _binary("ffprobe", ffprobe)
    technical = probe_reel(Path(checked["path"]), ffprobe=probe, expected_frames=data["frames"])
    if (technical["audio_samples"] != data["audio_samples"]
        or technical["width"] != data["width"] or technical["height"] != data["height"]):
        raise RuntimeError("Technical review video/audio or raster changed")
    fresh = _verify_stream_copy(
        [{**r, "path": p} for r, p in zip(data["reels"], source_paths)],
        Path(checked["path"]), ffmpeg=_binary("ffmpeg", ffmpeg), ffprobe=probe)
    if fresh != data.get("stream_copy_evidence"):
        raise RuntimeError("Original compressed picture/decoded audio comparison changed")
    return {"status": "VERIFIED_TECHNICAL_REVIEW_UNAPPROVED",
            "review_id": review_id, "frames": data["frames"],
            "duration_seconds": data["duration_seconds"],
            "movie_sha256": data["movie_sha256"], "path": checked["path"],
            "creator_approved_final_master": False}