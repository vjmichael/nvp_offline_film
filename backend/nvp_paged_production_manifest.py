"""Immutable bounded source pages for the existing read-only production journal.

No executable or approval authority; the journal owns the transaction and
creator consent. The root commits the entire ordered canonical page stream.
"""
import hashlib
import json
import re

FORMAT = "nvp.wo4.production_job.paged.v2"
PAGE_SIZE = 64
MAX_PAGE_BYTES = 256 * 1024
MAX_SEGMENTS = 10**6
_SHA = re.compile(r"[0-9a-f]{64}\Z")

SCHEMA = """
CREATE TABLE IF NOT EXISTS production_manifest_pages(
    job_id TEXT NOT NULL REFERENCES production_jobs(job_id),
    page_index INTEGER NOT NULL CHECK(page_index>=0),
    page_json TEXT NOT NULL,
    page_sha256 TEXT NOT NULL,
    PRIMARY KEY(job_id,page_index)
);
"""


def canon(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=True).encode("ascii")


def normalize(item, position, last_end, safe_source):
    if type(item) is not dict or set(item) != {
            "start_tick","end_tick","source_path","source_sha256","source_bytes"}:
        raise ValueError("Exact original source media segment required")
    start,end=item["start_tick"],item["end_tick"]
    if (type(start) is not int or type(end) is not int or not 0<=start<end<=2**63-1
            or (last_end is not None and start!=last_end)):
        raise ValueError("Original source clocks must be contiguous")
    digest,size=item["source_sha256"],item["source_bytes"]
    if (type(digest) is not str or not _SHA.fullmatch(digest) or
            type(size) is not int or not 1<=size<=2**63-1):
        raise ValueError("Exact original source bytes and SHA required")
    path=safe_source(item["source_path"])
    if type(path) is not str or not 1<=len(path)<=2048:
        raise ValueError("Bounded original source path required")
    return {"position":position,"start_tick":start,"end_tick":end,
            "source_path":path,"source_sha256":digest,"source_bytes":size}


def scan(factory, safe_source, consume=lambda *_:None):
    """Two-pass replayable factory; only one page of normalized rows retained."""
    if not callable(factory):
        raise TypeError("Trusted replayable source-page factory required")
    h=hashlib.sha256(); count=pages=0; first=end=None; short=False
    for supplied in factory():
        if (short or type(supplied) is not list or not 1<=len(supplied)<=PAGE_SIZE
                or count+len(supplied)>MAX_SEGMENTS):
            raise ValueError("Full bounded pages followed by at most one short page required")
        rows=[]
        for item in supplied:
            row=normalize(item,count,end,safe_source)
            if first is None: first=row["start_tick"]
            end=row["end_tick"]; count+=1; rows.append(row)
        short=len(rows)<PAGE_SIZE
        raw=canon({"page_index":pages,"segments":rows})
        if len(raw)>MAX_PAGE_BYTES:
            raise ValueError("Original manifest page exceeds byte budget")
        digest=hashlib.sha256(raw).hexdigest()
        h.update(bytes.fromhex(digest)); consume(pages,raw,digest,rows); pages+=1
    if not count:
        raise ValueError("Empty original production manifest")
    return {"segment_count":count,"page_count":pages,"page_size":PAGE_SIZE,
            "start_tick":first,"end_tick":end,"pages_sha256":h.hexdigest()}


def verify(db,job_id,root):
    """Stream every committed page and compare EVERY source row, including tail.

    Never trust a mutable status row instead of the approved source manifest.
    Call within the journal's existing guarded transaction/snapshot.
    """
    expected={k:root[k] for k in ("segment_count","page_count","page_size",
                                  "start_tick","end_tick","pages_sha256")}
    cursor=db.execute("""SELECT position,start_tick,end_tick,source_path,expected_sha256,
        expected_bytes FROM production_segments WHERE job_id=? ORDER BY position""",(job_id,))
    pages=db.execute("""SELECT page_index,CASE WHEN length(page_json)<=? THEN page_json ELSE NULL END AS page_json,page_sha256
                        FROM production_manifest_pages WHERE job_id=? ORDER BY page_index""",(MAX_PAGE_BYTES,job_id))
    raw_pages=hashlib.sha256()
    def factory():
        position=0
        for i,row in enumerate(pages):
            raw=row["page_json"]
            if (type(raw) is not str or len(raw)>MAX_PAGE_BYTES or not raw.isascii() or
                    row["page_index"]!=i or hashlib.sha256(raw.encode("ascii")).hexdigest()!=row["page_sha256"]):
                raise RuntimeError("Original production page identity changed")
            raw_pages.update(bytes.fromhex(row["page_sha256"]))
            page=json.loads(raw)
            if (type(page) is not dict or set(page)!={"page_index","segments"} or
                    page["page_index"]!=i or canon(page)!=raw.encode("ascii") or
                    type(page["segments"]) is not list or not 1<=len(page["segments"])<=PAGE_SIZE):
                raise RuntimeError("Invalid original production page")
            inputs=[]
            for item in page["segments"]:
                if type(item) is not dict or set(item)!={"position","start_tick","end_tick",
                        "source_path","source_sha256","source_bytes"}:
                    raise RuntimeError("Invalid original production source row")
                if type(item["position"]) is not int or item["position"]!=position:
                    raise RuntimeError("Original production positions changed")
                position+=1
                actual=cursor.fetchone()
                if actual is None or dict(actual)!={**{k:item[k] for k in
                    ("position","start_tick","end_tick","source_path")},
                    "expected_sha256":item["source_sha256"],"expected_bytes":item["source_bytes"]}:
                    raise RuntimeError("Original production checkpoint source changed")
                inputs.append({k:v for k,v in item.items() if k!="position"})
            yield inputs
    try:
        actual=scan(factory,lambda path:path)
    except (KeyError,TypeError,ValueError) as exc:
        raise RuntimeError("Invalid original paged production manifest") from exc
    if (cursor.fetchone() is not None or actual!=expected or
            raw_pages.hexdigest()!=expected["pages_sha256"]):
        raise RuntimeError("Original production manifest root or row coverage changed")
    return actual
