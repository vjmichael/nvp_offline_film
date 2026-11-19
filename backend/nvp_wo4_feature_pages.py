"""Durable bounded feature manifest pages inside the existing protected journal.

Original creator-approved canonical manifest SHA remains authoritative. A
finite legacy publisher may materialize its existing bounded manifest; browse
and page integrity verification never materialize the entire reel table.
"""
from hashlib import sha256
import json
import re

from backend.nvp_production_journal import _canonical, _digest
from backend.nvp_wo4_resource_budget import MAX_REELS
from backend.nvp_feature_receipt_tree import ReceiptTree,output_header,check_output_header

FORMAT = "nvp.wo4.feature_pages.v2"
PAGE = 64
MAX_PAGE_BYTES = 256 * 1024
ARRAYS = ("ordered_reel_job_ids", "reels", "source_reel_authority")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS production_feature_pages(
        feature_id TEXT NOT NULL REFERENCES production_features(feature_id),
        kind TEXT NOT NULL CHECK(kind IN ('source','output')),
        page_index INTEGER NOT NULL, page_json TEXT NOT NULL, page_sha256 TEXT NOT NULL,
        PRIMARY KEY(feature_id,kind,page_index))""")


def exists(db, fid, kind):
    return (db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='production_feature_pages'").fetchone() is not None
            and db.execute("SELECT 1 FROM production_feature_pages WHERE feature_id=? AND kind=? LIMIT 1", (fid,kind)).fetchone() is not None)


def store(db, fid, kind, rows, manifest_sha, *, header=None):
    maximum = MAX_REELS if kind == 'source' else 2*MAX_REELS+4
    if not 1 <= len(rows) <= maximum or exists(db,fid,kind):
        raise PermissionError("Invalid or repeated immutable feature page publication")
    chain = sha256()
    for offset in range(0,len(rows),PAGE):
        index=offset//PAGE
        raw=_canonical({"index":index,"rows":rows[offset:offset+PAGE]})
        if len(raw)>MAX_PAGE_BYTES:
            raise ValueError("Feature manifest page exceeds bounded byte size")
        digest=_digest(raw);chain.update(bytes.fromhex(digest))
        db.execute("INSERT INTO production_feature_pages VALUES(?,?,?,?,?)",(fid,kind,index,raw.decode('ascii'),digest))
    return _canonical({"format":FORMAT,"kind":kind,"count":len(rows),
        "manifest_sha256":manifest_sha,"pages_sha256":chain.hexdigest(),"header":header}).decode('ascii')


def rows(db,fid,kind,root,manifest_sha):
    maximum=MAX_REELS if kind=='source' else 2*MAX_REELS+4
    if (type(root) is not dict or set(root)!={"format","kind","count","manifest_sha256","pages_sha256","header"}
            or root['format']!=FORMAT or root['kind']!=kind or root['manifest_sha256']!=manifest_sha
            or type(root['count']) is not int or not 1<=root['count']<=maximum
            or not SHA.fullmatch(str(root['pages_sha256']))):
        raise PermissionError("Feature page root differs from approved manifest")
    if not exists(db,fid,kind):
        raise PermissionError("Feature manifest pages missing")
    chain=sha256();offset=0;index=0
    for row in db.execute("SELECT page_index, page_json, page_sha256 FROM production_feature_pages WHERE feature_id=? AND kind=? ORDER BY page_index",(fid,kind)):
        raw=row['page_json'].encode('ascii')
        if (len(raw)>MAX_PAGE_BYTES or row['page_index']!=index or
                _digest(raw)!=row['page_sha256']):
            raise PermissionError("Feature page hash or order changed")
        page=json.loads(raw);n=min(PAGE,root['count']-offset)
        if (n<=0 or type(page) is not dict or set(page)!={'index','rows'} or
                type(page['index']) is not int or page['index']!=index or
                type(page['rows']) is not list or len(page['rows'])!=n or _canonical(page)!=raw):
            raise PermissionError("Feature page count or canonical bytes changed")
        chain.update(bytes.fromhex(row['page_sha256']))
        for item in page['rows']:
            yield item
        offset+=n;index+=1
    if offset!=root['count'] or chain.hexdigest()!=root['pages_sha256']:
        raise PermissionError("Incomplete or changed feature page chain")


def store_source(db,fid,m,digest):
    if _digest(_canonical(m))!=digest or len({len(m[k]) for k in ARRAYS})!=1:
        raise PermissionError("Approved feature source differs")
    header={k:v for k,v in m.items() if k not in ARRAYS}
    entries=[dict(zip(ARRAYS,values)) for values in zip(*(m[k] for k in ARRAYS))]
    return store(db,fid,'source',entries,digest,header=header)


def source(db,fid,encoded,digest,*,first=None,limit=PAGE):
    root=json.loads(encoded)
    if root.get('format')!=FORMAT:
        if exists(db,fid,'source') or _digest(_canonical(root))!=digest:
            raise PermissionError("Legacy feature manifest changed")
        if first is None:return root
        return root,len(root['reels']),[dict(zip(ARRAYS,x)) for x in zip(*(root[k][first:first+limit] for k in ARRAYS))]
    header=root.get('header')
    if type(header) is not dict or set(header)&set(ARRAYS):
        raise PermissionError("Feature source page header changed")
    # Preserve exact v1 canonical bytes without building the arrays during browsing.
    h=sha256();h.update(b'{');selected=[];materialized={} if first is None else None
    for ordinal,key in enumerate(sorted([*header,*ARRAYS])):
        if ordinal:h.update(b',')
        h.update(_canonical(key)+b':')
        if key not in ARRAYS:
            h.update(_canonical(header[key]));continue
        h.update(b'[')
        if materialized is not None:materialized[key]=[]
        for i,item in enumerate(rows(db,fid,'source',root,digest)):
            if type(item) is not dict or set(item)!=set(ARRAYS):
                raise PermissionError("Feature source row changed")
            if i:h.update(b',')
            h.update(_canonical(item[key]))
            if materialized is not None:materialized[key].append(item[key])
            elif key=='reels' and first<=i<first+limit:selected.append(item)
        h.update(b']')
    h.update(b'}')
    if h.hexdigest()!=digest:
        raise PermissionError("Paged source differs from exact creator-approved manifest")
    return {**header,**materialized} if materialized is not None else (header,root['count'],selected)


def store_output(db,fid,files,digest):
    if type(files) is not dict or not files:
        raise PermissionError("Exact verified output file hashes required")
    return store(db,fid,'output',[[k,files[k]] for k in sorted(files)],digest,
                 header=output_header(files,digest,_digest(_canonical(files))))


def output(db,fid,encoded,digest,*,first=None,limit=PAGE):
    if encoded is None:
        if exists(db,fid,'output'):raise PermissionError("Uncommitted output has page receipts")
        return None if first is None else (0,[])
    root=json.loads(encoded)
    if root.get('format')!=FORMAT:
        if exists(db,fid,'output'):raise PermissionError("Feature output page pointer changed")
        return root if first is None else (len(root),list(sorted(root.items()))[first:first+limit])
    h=sha256();h.update(b'{');previous=None;result={} if first is None else [];count=0
    tree=ReceiptTree(digest)
    for item in rows(db,fid,'output',root,digest):
        if (type(item) is not list or len(item)!=2 or type(item[0]) is not str or
                not re.fullmatch(r'(?:CPL|PKL|ASSETMAP|VOLINDEX)\.xml|(?:picture|sound)_[0-9]{4}\.mxf',item[0]) or
                not SHA.fullmatch(str(item[1])) or (previous is not None and item[0]<=previous)):
            raise PermissionError("Invalid output receipt order or identity")
        if count:h.update(b',')
        h.update(_canonical(item[0])+b':'+_canonical(item[1]))
        previous=item[0]
        tree.add(item[0],item[1])
        if first is None:result[item[0]]=item[1]
        elif first<=count<first+limit:result.append(item)
        count+=1
    h.update(b'}')
    check_output_header(root['header'],h.hexdigest(),tree)
    return result if first is None else (count,result)
