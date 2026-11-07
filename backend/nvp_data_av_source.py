"""DATA-AV-01: immutable, chunk-addressed recorded audio source data.

This is NOT a soundtrack, BWF requirement, decoder or sound renderer.
Audio is a source asset linked by exact FilmIndex revision to a semantic
sound event in a frozen Digital Take. Each PCM chunk is independently
SHA-verified when accessed, keeping reads bounded even on long recordings.
"""
from __future__ import annotations

from backend.nvp_film_index import FilmIndex, _id, _require_pid
from backend.nvp_temporal_ledger import _int

FORMAT = "nvp.data_av.recorded_pcm.v1"
SAMPLE_RATE = 48000
MAX_CHUNK_BYTES = 1024 * 1024
MAX_CHUNKS = 4096
MAX_READ_SAMPLES = 8192


class RecordedSoundSources:
    def __init__(self, index: FilmIndex):
        if not isinstance(index, FilmIndex):
            raise TypeError("Trusted FilmIndex is required")
        self.index = index

    def publish(self, project_id, source_id, chunks, *, expected_revision=0):
        """Record ORIGINAL mono PCM16LE chunks without a mandatory WAV/BWF.

        The capture worker, not a model or browser-supplied filename, supplies
        these bytes. One full recording can exceed RAM; only the current
        <=1MiB chunk is held at once. No normalized stereo soundtrack is stored.
        """
        _require_pid(project_id)
        _id(source_id, "recorded audio source ID")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Invalid audio source revision")
        manifest=[]
        position=0
        for part in chunks:
            if (type(part) is not bytes or not 0 < len(part) <= MAX_CHUNK_BYTES
                    or len(part) % 2 or len(manifest)>=MAX_CHUNKS):
                raise ValueError("Recorded PCM chunk must be bounded, even-sized PCM16LE")
            count=len(part)//2
            sha=self.index.put_blob(project_id,part,
                                    media_type="audio/x-nvp-pcm16le")
            manifest.append({"first_sample":position,"sample_count":count,
                             "blob_sha256":sha,"byte_count":len(part)})
            position+=count
        if not manifest:
            raise ValueError("A recorded sound source must contain samples")
        doc={"format":FORMAT,"sample_rate":SAMPLE_RATE,"channels":1,
             "sample_encoding":"signed_16_le","sample_count":position,
             "chunks":manifest,"immutable_source":True,
             "flattened_soundtrack":False,"bwf_required":False}
        return self.index.register_revision(
            project_id,source_id,"audio",doc,
            expected_revision=expected_revision)

    def describe(self,project_id,source_id,revision):
        record=self.index.read_revision(project_id,source_id,revision)
        doc=record["data"]
        if (record["kind"]!="audio" or doc.get("format")!=FORMAT or
                doc.get("sample_rate")!=SAMPLE_RATE or
                doc.get("channels")!=1 or
                doc.get("sample_encoding")!="signed_16_le" or
                doc.get("immutable_source") is not True):
            raise RuntimeError("Not an immutable NVP recorded source signal")
        return record

    def read(self,project_id,source_id,revision,first_sample,count):
        """Read an exact bounded mono sample window; never touch other chunks."""
        _int(first_sample,"first audio sample")
        _int(count,"audio sample window",minimum=1,maximum=MAX_READ_SAMPLES)
        doc=self.describe(project_id,source_id,revision)["data"]
        if first_sample+count>doc["sample_count"]:
            raise ValueError("Audio sample request extends past immutable source")
        out=bytearray(count*2)
        delivered=0
        last=0
        for entry in doc["chunks"]:
            first=entry["first_sample"];n=entry["sample_count"]
            if (type(first) is not int or type(n) is not int or
                    first!=last or n<=0 or n*2!=entry["byte_count"] or
                    n*2>MAX_CHUNK_BYTES):
                raise RuntimeError("Tampered recorded source chunk layout")
            last=first+n
            start=max(first,first_sample)
            end=min(last,first_sample+count)
            if start>=end:
                continue
            block=self.index.get_blob(project_id,entry["blob_sha256"])
            if len(block)!=entry["byte_count"]:
                raise RuntimeError("Changed source chunk content")
            source_offset=(start-first)*2
            target_offset=(start-first_sample)*2
            length=(end-start)*2
            out[target_offset:target_offset+length]=block[
                source_offset:source_offset+length]
            delivered+=end-start
        if last!=doc["sample_count"] or delivered!=count:
            raise RuntimeError("Incomplete or altered original audio samples")
        return bytes(out)
