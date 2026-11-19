"""Compact, source-bound 24fps chunk indexing; no rendering or authority.

Retain v1 six-digit chunk identities and canonical JSON rows. The only
schedule-wide working set is the already bounded editorial segment table.
"""
from bisect import bisect_right
from dataclasses import dataclass
import hashlib
import json

from backend.nvp_slate_edit_assembly import MAX_SEGMENTS
from backend.nvp_temporal_ledger import MAX_TICK
from backend.nvp_p1f_sustained_delivery import FRAME_TICKS, MAX_CHUNK_FRAMES

# Existing stable six-digit chunk namespace and exact IEEE-754 USD tick range.
MAX_CHUNKS = 10**6
MAX_TOTAL_FRAMES = min(MAX_CHUNKS * MAX_CHUNK_FRAMES,
                       MAX_TICK // FRAME_TICKS, (2**53-1) // FRAME_TICKS)
MAX_PAGE = 64


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


@dataclass(frozen=True)
class _Segment:
    first_chunk: int
    first_frame: int
    end_frame: int
    source_tick: int
    segment_id: str
    take_id: str
    take_sha: str
    shot_id: str | None
    shot_sha: str | None


class ChunkSchedule:
    """Independent instance per verified source operation, never persistent cache."""
    def __init__(self, segments):
        if type(segments) is not list or not 1 <= len(segments) <= MAX_SEGMENTS:
            raise ValueError("Original editorial segment bounds required")
        rows = []
        cursor = count = 0
        for s in segments:
            first, end = s["timeline_start_tick"], s["timeline_end_tick"]
            source, source_end = s["source_in_tick"], s["source_out_tick"]
            if (any(type(v) is not int or not 0 <= v <= MAX_TICK
                    for v in (first, end, source, source_end)) or
                first != cursor or end <= first or source_end <= source or
                any(v % FRAME_TICKS for v in (first, end, source, source_end)) or
                end-first != source_end-source):
                raise RuntimeError("Original cut has a gap or requires hidden retiming")
            start_frame, stop_frame = first//FRAME_TICKS, end//FRAME_TICKS
            n = (stop_frame-start_frame+MAX_CHUNK_FRAMES-1)//MAX_CHUNK_FRAMES
            if stop_frame > MAX_TOTAL_FRAMES or count+n > MAX_CHUNKS:
                raise ValueError("Original cut exceeds exact tick or chunk identity range")
            rows.append(_Segment(count, start_frame, stop_frame, source,
                s["segment_id"], s["source_take_id"], s["source_take_document_sha256"],
                s["source_shot_id"], s["source_shot_document_sha256"]))
            count += n
            cursor = end
        self._rows = tuple(rows)
        self._starts = tuple(r.first_chunk for r in rows)
        self.total_frames = cursor//FRAME_TICKS
        self.total_chunks = count

    def _entry(self, row, i):
        first = row.first_frame + (i-row.first_chunk)*MAX_CHUNK_FRAMES
        count = min(MAX_CHUNK_FRAMES, row.end_frame-first)
        return {"index": i, "chunk_id": "P2FilmChunk"+str(i).zfill(6),
                "first_frame": first, "frame_count": count,
                "segment_id": row.segment_id, "source_take_id": row.take_id,
                "source_take_sha256": row.take_sha, "source_shot_id": row.shot_id,
                "source_shot_sha256": row.shot_sha,
                "source_start_tick": str(row.source_tick+(first-row.first_frame)*FRAME_TICKS)}

    def entries(self, start=0, stop=None):
        if stop is None:
            stop = self.total_chunks
        if (type(start) is not int or type(stop) is not int or
                not 0 <= start <= stop <= self.total_chunks):
            raise ValueError("Invalid original chunk interval")
        if start == stop:
            return
        pos = bisect_right(self._starts, start)-1
        for i in range(start, stop):
            if pos+1 < len(self._starts) and i == self._starts[pos+1]:
                pos += 1
            yield self._entry(self._rows[pos], i)

    def page(self, start, limit):
        if (type(start) is not int or not 0 <= start < self.total_chunks or
                type(limit) is not int or not 1 <= limit <= MAX_PAGE):
            raise ValueError("Invalid bounded original chunk page")
        return list(self.entries(start, min(start+limit, self.total_chunks)))

    def digest(self, *, cancelled=lambda: False):
        if not callable(cancelled):
            raise TypeError("Trusted cancellation callback required")
        h = hashlib.sha256()
        for row in self.entries():
            if row["index"] % MAX_PAGE == 0 and cancelled():
                raise InterruptedError("Creator cancelled original schedule validation")
            h.update(_canon(row)+b"\n")
        if cancelled():
            raise InterruptedError("Creator cancelled original schedule validation")
        return h.hexdigest()
