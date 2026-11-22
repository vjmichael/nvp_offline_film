"""Bounded immutable hierarchy of separately approved P1-D/E editorial pages.

Each node keeps at most 64 exact child revision references. Legacy leaf edits
keep their own validation and approval. This is source planning, not execution.
"""
from backend.nvp_film_index import _id, _sha
from backend.nvp_temporal_ledger import TICKS_PER_SECOND, _int

FORMAT = "nvp.p1de.source_edit_manifest.v2"
LEAF_FORMAT = "nvp.p1de.source_edit_audio.v1"
MAX_CHILDREN = 64
MAX_DEPTH = 3
MAX_SOURCE_TICK = 2**53-1  # exact OpenUSD TimeCode integer range
SAMPLE_TICK = TICKS_PER_SECOND // 48000


def descriptor(record):
    doc = record["data"]
    if record["kind"] != "edit" or doc.get("format") not in (LEAF_FORMAT, FORMAT):
        raise RuntimeError("Only original P1-D/E edit revisions may be composed")
    if any(doc.get(k) is not False for k in ("source_modified", "flattened_soundtrack",
                                           "picture_rendered", "master_approved")):
        raise RuntimeError("Editorial page claims unauthorized output")
    if doc.get("ticks_per_second") != TICKS_PER_SECOND or doc.get("sample_rate") != 48000:
        raise RuntimeError("Editorial page has incompatible native clocks")
    duration = _int(doc["duration_tick"], "source duration", minimum=1, maximum=MAX_SOURCE_TICK)
    if duration % SAMPLE_TICK:
        raise ValueError("Editorial page must preserve exact sample clock")
    depth = 0 if doc["format"] == LEAF_FORMAT else _int(doc["depth"], "hierarchy depth", minimum=1, maximum=MAX_DEPTH)
    return duration, depth


def compose(children, read_child):
    if type(children) is not list or not 1 <= len(children) <= MAX_CHILDREN:
        raise ValueError("Choose 1 to 64 immutable child edit revisions per manifest")
    entries, deps, checked = [], {}, {}
    cursor = depth = 0
    for child in children:
        if type(child) is not dict or set(child) != {"edit_id", "revision", "document_sha256"}:
            raise ValueError("Exact editorial child revision and digest required")
        ident = _id(child["edit_id"], "editorial child")
        rev = _int(child["revision"], "editorial child revision", minimum=1)
        digest = _sha(child["document_sha256"])
        key = (ident, rev)
        if key not in checked:
            row = read_child(ident, rev)
            checked[key] = (row["document_sha256"], *descriptor(row))
        actual, duration, child_depth = checked[key]
        if actual != digest:
            raise RuntimeError("Editorial child source SHA changed")
        if cursor+duration > MAX_SOURCE_TICK or child_depth+1 > MAX_DEPTH:
            raise ValueError("Editorial manifest exceeds exact clock or bounded tree depth")
        entries.append({**child, "start_tick": cursor, "end_tick": cursor+duration,
                        "depth": child_depth})
        deps[(ident, rev)] = {"object_id": ident, "revision": rev, "role": "timeline"}
        cursor += duration
        depth = max(depth, child_depth+1)
    doc = {"format": FORMAT, "ticks_per_second": TICKS_PER_SECOND, "sample_rate": 48000,
           "children": entries, "duration_tick": cursor, "depth": depth,
           "source_modified": False, "flattened_soundtrack": False,
           "picture_rendered": False, "master_approved": False}
    return doc, sorted(deps.values(), key=lambda x: (x["object_id"], x["revision"], x["role"]))


def references(doc):
    children = doc.get("children")
    if type(children) is not list or not 1 <= len(children) <= MAX_CHILDREN:
        raise RuntimeError("Missing bounded editorial child table")
    return [{k: c[k] for k in ("edit_id", "revision", "document_sha256")} for c in children]


def slices_for_window(doc, start, count, plan_child):
    """Visit only overlapping children; child plans verify their own leaf sources."""
    result = []
    for child in doc["children"]:
        base = child["start_tick"]//SAMPLE_TICK
        end = child["end_tick"]//SAMPLE_TICK
        a, b = max(start, base), min(start+count, end)
        if a >= b:
            continue
        plan = plan_child(child["edit_id"], child["revision"], a-base, b-a)
        if plan["edit_document_sha256"] != child["document_sha256"]:
            raise RuntimeError("Editorial child differed from approved hierarchy")
        cursor = a
        for sl in plan["slices"]:
            view = {**sl, "output_first_sample": sl["output_first_sample"]+base}
            if view["output_first_sample"] != cursor or not 0 < view["sample_count"] <= b-cursor:
                raise RuntimeError("Editorial child returned disordered original sound")
            cursor += view["sample_count"]
            result.append(view)
        if cursor != b:
            raise RuntimeError("Editorial child has missing original sound samples")
    if sum(s["sample_count"] for s in result) != count:
        raise RuntimeError("Hierarchy does not cover requested exact original samples")
    return result
