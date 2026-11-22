"""R5: bounded sealed EDL and frozen OpenUSD payloads in the live film vault.

The authenticated SQLite snapshot remains the sole index and edit authority.
Explicit migration is scoped to a reviewed current snapshot and bounded batch.
No keys, paths, worker grants or plaintext files are exposed through this API.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile

from backend.nvp_g03_windows_vault import VaultError, _no_link, _token, _encrypt_file, _decrypt_file
from backend.nvp_wo3_atomic_publish import atomic_publish_directory

SHA = re.compile(r'[a-f0-9]{64}\Z')
ID = re.compile(r'[a-f0-9]{32}\Z')
EDL_LIMIT = 8 * 1024 * 1024
USD_LIMIT = 6_000_000
BATCH = 8
POINTER = 'nvp.g03.sealed_edl.v1'
FORMATS = ('nvp.g07.non_destructive_edit.v1', 'nvp.g07.paged_active_edit.v1')
KINDS = ('original_usd', 'performance_usd')


def _json(doc):
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class ProtectedConnection(sqlite3.Connection):
    """Private host context, never a SQL function or serializable key field."""
    _nvp_payload_context = None
    _nvp_payload_guard = None

    def close(self):
        self._nvp_payload_context = None
        self._nvp_payload_guard = None
        super().close()


def attach(db, folder, pid, key, head, guard=None):
    if not isinstance(db, ProtectedConnection):
        raise VaultError('Protected payload connection required')
    db._nvp_payload_context = (Path(folder), pid, key, dict(head))
    db._nvp_payload_guard = guard


def _context(db, pid):
    ctx = getattr(db, '_nvp_payload_context', None)
    if ctx is None or ctx[1] != pid:
        raise VaultError('Original payload requires its unlocked movie')
    guard = getattr(db, '_nvp_payload_guard', None)
    if guard is not None:
        guard()
    return ctx


def _guard(db):
    guard = getattr(db, '_nvp_payload_guard', None)
    if guard is not None:
        guard()


def _has_table(db, name):
    return db.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?', (name,)).fetchone() is not None


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS g03_r5_storage_mode(
        project_id TEXT NOT NULL, family TEXT NOT NULL CHECK(family IN ('edl','take')),
        PRIMARY KEY(project_id,family))''')
    db.execute('''CREATE TABLE IF NOT EXISTS g03_r5_take_payloads(
        project_id TEXT NOT NULL, take_id TEXT NOT NULL, kind TEXT NOT NULL
        CHECK(kind IN ('original_usd','performance_usd')),
        sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
        PRIMARY KEY(project_id,take_id,kind))''')


def enabled(db, pid, family):
    if not _has_table(db, 'g03_r5_storage_mode'):
        return False
    if not db.execute('SELECT 1 FROM g03_r5_storage_mode WHERE project_id=? AND family=?', (pid,family)).fetchone():
        return False
    _context(db,pid)
    return True


def _identity(family, ident, digest, kind=None):
    if type(digest) is not str or not SHA.fullmatch(digest):
        raise VaultError('Invalid original payload digest')
    if family == 'edl' and type(ident) is int and 1 <= ident <= 15000 and kind is None:
        return f'r5/edl/{ident}/{digest}', EDL_LIMIT
    if family == 'take' and type(ident) is str and ID.fullmatch(ident) and kind in KINDS:
        return f'r5/take/{ident}/{kind}/{digest}', USD_LIMIT
    raise VaultError('Invalid original payload identity')


def _path(folder,key,name,*,create=False):
    _no_link(folder)
    root = folder/'protected-objects'
    if create:
        root.mkdir(exist_ok=True)
    if not stat.S_ISDIR(_no_link(root).st_mode):
        raise VaultError('Invalid protected payload directory')
    return root/_token(name,key)


class _Reader:
    def __init__(self, db, source, limit):
        self.db, self.source, self.limit = db, source, limit
        self.count = 0
    def read(self,n):
        _guard(self.db)
        raw = self.source.read(n)
        self.count += len(raw)
        if self.count > self.limit:
            raise VaultError('Original payload exceeds approved size')
        return raw


class _Sink:
    def __init__(self, db, sink=None):
        self.db,self.sink=db,sink
    def write(self,data):
        _guard(self.db)
        if self.sink is not None:
            self.sink.write(data)


def _read_object(db,pid,name,limit,digest,size,*,materialize=False,path=None):
    folder,_,key,_ = _context(db,pid)
    if type(size) is not int or not 0<size<=limit:
        raise VaultError('Unapproved original payload size')
    try:
        target = _path(folder,key,name) if path is None else path
        if not stat.S_ISDIR(_no_link(target).st_mode):
            raise VaultError('Invalid sealed payload object')
        body = target/'body.nvpsealed'
        info = _no_link(body)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            raise VaultError('Invalid sealed payload file')
        if set(p.name for p in target.iterdir()) != {'body.nvpsealed'}:
            raise VaultError('Unexpected sealed payload entries')
        memory = io.BytesIO() if materialize else None
        receipt = _decrypt_file(body,_Sink(db,memory),key=key,project_id=pid,name=name,max_plain_bytes=size)
        if receipt != {'sha256':digest,'size_bytes':size}:
            raise VaultError('Original payload identity changed')
        _guard(db)
        return memory.getvalue() if memory is not None else None
    except OSError as exc:
        raise VaultError('Original protected payload unavailable') from exc


def _seal(db,pid,name,limit,digest,size,source):
    folder,_,key,_ = _context(db,pid)
    if type(size) is not int or not 0<size<=limit:
        raise VaultError('Original payload exceeds reviewed size')
    target = _path(folder,key,name,create=True)
    if target.exists() or target.is_symlink():
        # Still consume and verify the supplied original; never erase changed
        # inline bytes based solely on a reusable immutable object.
        reader = _Reader(db,source,size); checksum = hashlib.sha256()
        while block := reader.read(512*1024):checksum.update(block)
        if reader.count!=size or checksum.hexdigest()!=digest:
            raise VaultError('Original inline bytes changed')
        _read_object(db,pid,name,limit,digest,size)
        return
    stage = Path(tempfile.mkdtemp(prefix='.r5-object-',dir=target.parent))
    try:
        receipt = _encrypt_file(_Reader(db,source,size),stage/'body.nvpsealed',key=key,project_id=pid,name=name)
        if receipt != {'sha256':digest,'size_bytes':size}:
            raise VaultError('Approved original payload changed')
        _read_object(db,pid,name,limit,digest,size,path=stage)
        _guard(db)
        atomic_publish_directory(stage,target)
        _read_object(db,pid,name,limit,digest,size)
    finally:
        if stage.exists():shutil.rmtree(stage)


def _inline_edl(raw,digest):
    if type(raw) is not str or len(raw)>EDL_LIMIT:
        raise VaultError('Saved edit exceeds bounded document size')
    encoded=raw.encode('utf8')
    if len(encoded)>EDL_LIMIT or _sha(encoded)!=digest:
        raise VaultError('Saved edit source changed')
    doc=json.loads(raw)
    if type(doc) is not dict or doc.get('format') not in FORMATS or _json(doc)!=raw or 'storage' in doc:
        raise VaultError('Unknown or noncanonical saved edit')
    return doc,encoded


def resolve_edit(db,pid,rev,raw,digest):
    if type(raw) is not str or len(raw)>EDL_LIMIT:
        raise VaultError('Saved edit exceeds bounded document size')
    pointer=json.loads(raw)
    if type(pointer) is dict and 'storage' in pointer:
        if (set(pointer)!={'format','storage','sha256','size_bytes'} or pointer['storage']!=POINTER or
            pointer['sha256']!=digest or pointer['format'] not in FORMATS):
            raise VaultError('Invalid saved edit pointer')
        name,limit=_identity('edl',rev,digest)
        resolved=_read_object(db,pid,name,limit,digest,pointer['size_bytes'],materialize=True)
        doc,_=_inline_edl(resolved.decode('utf8'),digest)
        if doc['format']!=pointer['format']:
            raise VaultError('Protected edit format changed')
        return doc
    return _inline_edl(raw,digest)[0]


def seal_edit(db,pid,rev,raw,digest):
    doc,data=_inline_edl(raw,digest)
    name,limit=_identity('edl',rev,digest)
    _seal(db,pid,name,limit,digest,len(data),io.BytesIO(data))
    return _json({'format':doc['format'],'storage':POINTER,'sha256':digest,'size_bytes':len(data)})


def _take_pointer(db,pid,tid,kind):
    if not _has_table(db,'g03_r5_take_payloads'):return None
    return db.execute('SELECT sha256,size_bytes FROM g03_r5_take_payloads WHERE project_id=? AND take_id=? AND kind=?',(pid,tid,kind)).fetchone()


def take_sizes(db,pid,tid,row,*,pointers=None):
    """Bounded metadata-only; no media authentication claimed."""
    out={}
    for kind in KINDS:
        size=row[kind+'_size'];digest=row[kind+'_sha256']
        _identity('take',tid,digest,kind)
        pointer=_take_pointer(db,pid,tid,kind) if pointers is None else pointers.get((tid,kind))
        if pointer is not None:
            _context(db,pid)
            if size!=0 or pointer['sha256']!=digest:
                raise VaultError('Frozen Take pointer conflicts with original')
            size=pointer['size_bytes']
        if type(size) is not int or not 0<size<=USD_LIMIT:
            raise VaultError('Frozen Take source size invalid')
        out[kind+'_size']=size
    return out


def read_take_payloads(db,pid,tid):
    meta=db.execute('''SELECT original_usd_sha256,performance_usd_sha256,
        length(original_usd) AS original_usd_size,length(performance_usd) AS performance_usd_size
        FROM g06_frozen_takes WHERE project_id=? AND take_id=?''',(pid,tid)).fetchone()
    if meta is None:raise VaultError('Original frozen Take unavailable')
    sizes=take_sizes(db,pid,tid,meta)
    result={}
    for kind in KINDS:
        digest=meta[kind+'_sha256'];size=sizes[kind+'_size']
        if _take_pointer(db,pid,tid,kind) is None:
            raw=db.execute(f'SELECT {kind} FROM g06_frozen_takes WHERE project_id=? AND take_id=?',(pid,tid)).fetchone()[0]
            if len(raw)!=size or _sha(raw)!=digest:raise VaultError('Frozen original USD changed')
        else:
            name,limit=_identity('take',tid,digest,kind)
            raw=_read_object(db,pid,name,limit,digest,size,materialize=True)
        result[kind]=raw
    return result


def seal_new_take(db,pid,tid,original,performance):
    """Prepare original USD bodies before inserting a new frozen Take row.

    Caller inserts the matching immutable Take within the same live transaction.
    A failure leaves only unindexed encrypted objects, never a visible Take.
    """
    _schema(db)
    for kind,raw in zip(KINDS,(original,performance)):
        if type(raw) is not bytes:raise VaultError('Frozen OpenUSD bytes required')
        digest=_sha(raw);size=len(raw);name,limit=_identity('take',tid,digest,kind)
        _seal(db,pid,name,limit,digest,size,io.BytesIO(raw))
        db.execute('INSERT INTO g03_r5_take_payloads VALUES(?,?,?,?,?)',(pid,tid,kind,digest,size))
    return b'',b''


def seal_take(db,pid,tid):
    _schema(db)
    row=db.execute('''SELECT rowid,original_usd_sha256,performance_usd_sha256,
        length(original_usd) AS original_usd_size,length(performance_usd) AS performance_usd_size
        FROM g06_frozen_takes WHERE project_id=? AND take_id=?''',(pid,tid)).fetchone()
    if row is None:raise VaultError('Original frozen Take unavailable')
    sizes=take_sizes(db,pid,tid,row)
    for kind in KINDS:
        digest=row[kind+'_sha256'];size=sizes[kind+'_size'];name,limit=_identity('take',tid,digest,kind)
        if _take_pointer(db,pid,tid,kind) is not None:
            _read_object(db,pid,name,limit,digest,size)
            continue
        with db.blobopen('g06_frozen_takes',kind,row['rowid'],readonly=True) as blob:
            _seal(db,pid,name,limit,digest,size,blob)
        db.execute('INSERT INTO g03_r5_take_payloads VALUES(?,?,?,?,?)',(pid,tid,kind,digest,size))
        if db.execute(f"UPDATE g06_frozen_takes SET {kind}=X'' WHERE project_id=? AND take_id=? AND {kind}_sha256=? AND length({kind})=?",(pid,tid,digest,size)).rowcount!=1:
            raise VaultError('Frozen Take changed during migration')
    _guard(db)


def _review(db,pid,family,after,*,pending_only=False):
    _,_,_,head=_context(db,pid)
    entries=[]
    if family=='edl':
        if after is None:after=0
        if type(after) is not int or not 0<=after<=15000:raise ValueError('Invalid saved edit cursor')
        condition=" AND json_extract(document_json,'$.storage') IS NOT '"+POINTER+"'" if pending_only else ''
        rows=list(db.execute('SELECT revision,document_sha256,length(CAST(document_json AS BLOB)) AS size FROM g07_edit_versions WHERE project_id=? AND revision>?'+condition+' ORDER BY revision LIMIT ?',(pid,after,BATCH+1))) if _has_table(db,'g07_edit_versions') else []
        for row in rows[:BATCH]:
            _guard(db)
            rev=row['revision'];digest=row['document_sha256']
            if not 0<row['size']<=EDL_LIMIT:raise VaultError('Saved edit exceeds migration limit')
            raw=db.execute('SELECT document_json FROM g07_edit_versions WHERE project_id=? AND revision=?',(pid,rev)).fetchone()[0]
            resolve_edit(db,pid,rev,raw,digest)
            if json.loads(raw).get('storage')!=POINTER:entries.append({'id':rev,'sha256':digest,'size_bytes':row['size']})
        next_after=rows[BATCH-1]['revision'] if len(rows)>BATCH else None
    elif family=='take':
        if after is None:after=''
        if type(after) is not str or (after and not ID.fullmatch(after)):raise ValueError('Invalid original Take cursor')
        condition=' AND (length(original_usd)>0 OR length(performance_usd)>0)' if pending_only else ''
        rows=list(db.execute('''SELECT take_id,take_sha256,original_usd_sha256,performance_usd_sha256,
            length(original_usd) AS original_usd_size,length(performance_usd) AS performance_usd_size
            FROM g06_frozen_takes WHERE project_id=? AND take_id>?'''+condition+' ORDER BY take_id LIMIT ?',(pid,after,BATCH+1))) if _has_table(db,'g06_frozen_takes') else []
        for row in rows[:BATCH]:
            _guard(db)
            tid=row['take_id'];sizes=take_sizes(db,pid,tid,row)
            if any(_take_pointer(db,pid,tid,k) is None for k in KINDS):
                entries.append({'id':tid,'take_sha256':row['take_sha256'],**{k+'_sha256':row[k+'_sha256'] for k in KINDS},**sizes})
        next_after=rows[BATCH-1]['take_id'] if len(rows)>BATCH else None
    else:raise ValueError('Choose edits or original Takes')
    return {'format':'nvp.g03.r5_migration.v1','project_id':pid,'snapshot':head,'family':family,'after':after,'pending_only':pending_only,'entries':entries,'next_after':next_after}


def review(store,pid,token,family,after=None,*,pending_only=False,guard=None):
    with store._guard:
        key=store._session(pid,token);db,_=store._read_db(store._folder(pid),pid,key)
        def check():
            store._session(pid,token)
            if guard is not None:guard()
        db._nvp_payload_guard=check
        try:
            record=_review(db,pid,family,after,pending_only=pending_only)
            return {**record,'approval_digest':_sha(_json(record).encode('utf8'))}
        finally:db.close()


def migrate(store,pid,token,family,after,approval_digest,*,human_approved=False,pending_only=False,guard=None):
    """Trusted host operation. Once opted in, future writes use same custody."""
    if human_approved is not True:raise PermissionError('Native migration approval required')
    def tx(db,key,folder):
        previous=db._nvp_payload_guard
        def check():
            previous()
            if guard is not None:guard()
        db._nvp_payload_guard=check
        record=_review(db,pid,family,after,pending_only=pending_only)
        if _sha(_json(record).encode('utf8'))!=approval_digest:
            raise PermissionError('Review the current original payload batch again')
        _schema(db);db.execute('PRAGMA secure_delete=ON')
        for entry in record['entries']:
            _guard(db)
            if family=='edl':
                rev=entry['id'];digest=entry['sha256']
                raw=db.execute('SELECT document_json FROM g07_edit_versions WHERE project_id=? AND revision=?',(pid,rev)).fetchone()[0]
                pointer=seal_edit(db,pid,rev,raw,digest)
                if db.execute('UPDATE g07_edit_versions SET document_json=? WHERE project_id=? AND revision=? AND document_sha256=? AND document_json=?',(pointer,pid,rev,digest,raw)).rowcount!=1:raise VaultError('Edit changed during migration')
                resolve_edit(db,pid,rev,pointer,digest)
            else:seal_take(db,pid,entry['id'])
        db.execute('INSERT OR IGNORE INTO g03_r5_storage_mode VALUES(?,?)',(pid,family))
        _guard(db)
        return {'migrated':len(record['entries']),'next_after':record['next_after'],'family':family,'original_identity_preserved':True,'render_approved':False}
    return store._change(pid,token,tx,compact=True)


def verify_index(db,pid,guard):
    if _has_table(db,'g07_edit_versions'):
        for row in db.execute('SELECT project_id,revision,document_json,document_sha256 FROM g07_edit_versions'):
            guard()
            if row['project_id']!=pid:raise VaultError('Foreign edit in protected movie')
            resolve_edit(db,pid,row['revision'],row['document_json'],row['document_sha256'])
        for row in db.execute('SELECT project_id,revision,document_sha256 FROM g07_edit_heads'):
            if row['project_id']!=pid or not db.execute('SELECT 1 FROM g07_edit_versions WHERE project_id=? AND revision=? AND document_sha256=?',(pid,row['revision'],row['document_sha256'])).fetchone():raise VaultError('Protected edit head has no immutable revision')
    if _has_table(db,'g03_r5_take_payloads'):
        for p in db.execute('SELECT * FROM g03_r5_take_payloads'):
            guard()
            if p['project_id']!=pid:raise VaultError('Foreign original payload pointer')
            kind=p['kind'];name,limit=_identity('take',p['take_id'],p['sha256'],kind)
            row=db.execute(f'SELECT {kind}_sha256,length({kind}) FROM g06_frozen_takes WHERE project_id=? AND take_id=?',(pid,p['take_id'])).fetchone()
            if row is None or row[0]!=p['sha256'] or row[1]!=0:raise VaultError('Original payload index changed')
            _read_object(db,pid,name,limit,p['sha256'],p['size_bytes'])
