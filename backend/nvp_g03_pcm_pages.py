"""Immutable independently authenticated original microphone pages.

The existing G06 audio row and SHA remain authoritative. Only protected
stores may replace its inline PCM representation, atomically with an exact
page pointer. Historical sealed snapshots and frozen Takes remain intact.
"""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile

from backend.nvp_g03_windows_vault import VaultError,_no_link,_token,_encrypt_file,_decrypt_file
from backend.nvp_wo3_atomic_publish import atomic_publish_directory

PAGE=512*1024
# Existing readers remain deliberately finite; storage/migration is streaming.
MAX_BYTES=64*1024*1024
MAX_ROOT=128*1024
FORMAT='nvp.g03.original_pcm_pages.v1'
HEX=re.compile(r'[a-f0-9]{32}\Z');SHA=re.compile(r'[a-f0-9]{64}\Z')


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS g03_pcm_pages(
        project_id TEXT NOT NULL, clip_id TEXT NOT NULL, scene_id TEXT NOT NULL,
        pcm_sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, root_sha256 TEXT NOT NULL,
        PRIMARY KEY(project_id,clip_id))''')


def context(filming,pid):
    host=filming.g05.g04
    if host.live is None:return None
    return host.live._folder(pid),host.live._session(pid,host.token)


def _canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def _identity(cid,digest):
    if type(cid) is not str or not HEX.fullmatch(cid) or type(digest) is not str or not SHA.fullmatch(digest):raise VaultError('Invalid original recording identity')
    return 'original-pcm-pages/'+cid+'/'+digest


def _location(folder,key,cid,digest,*,create=False):
    _no_link(folder);root=folder/'pcm-pages'
    if create:root.mkdir(exist_ok=True)
    _no_link(root)
    if not root.is_dir():raise VaultError('Missing original recording storage')
    return root/_token(_identity(cid,digest),key)


def _open_page(path,key,pid,name,limit):
    _no_link(path);sink=io.BytesIO()
    receipt=_decrypt_file(path,sink,key=key,project_id=pid,name=name,max_plain_bytes=limit)
    return sink.getvalue(),receipt


def _root(folder,key,pid,cid,digest,size,root_sha):
    if type(size) is not int or not 2<=size<=MAX_BYTES or size%2 or type(root_sha) is not str or not SHA.fullmatch(root_sha):raise VaultError('Invalid original recording bounds')
    path=_location(folder,key,cid,digest);_no_link(path)
    raw,receipt=_open_page(path/'root.nvpsealed',key,pid,_identity(cid,digest)+'/root',MAX_ROOT)
    if receipt['sha256']!=root_sha:raise VaultError('Original recording root changed')
    root=json.loads(raw)
    if (type(root) is not dict or set(root)!={'format','clip_id','pcm_sha256','size_bytes','pages'} or root['format']!=FORMAT or root['clip_id']!=cid or root['pcm_sha256']!=digest or root['size_bytes']!=size or type(root['pages']) is not list or len(root['pages'])!=(size+PAGE-1)//PAGE or any(type(x) is not str or not SHA.fullmatch(x) for x in root['pages'])):raise VaultError('Original recording page index changed')
    return path,root


def _read_pages(folder,key,pid,cid,digest,size,root_sha,*,first=0,count=None,sink=None,guard=lambda:None,whole=False):
    path,root=_root(folder,key,pid,cid,digest,size,root_sha)
    count=size-first if count is None else count
    if type(first) is not int or type(count) is not int or not 0<=first<=first+count<=size or first%2 or count%2:raise ValueError('Original PCM range is invalid')
    checksum=hashlib.sha256();seen=0
    start=0 if whole else first//PAGE;end=len(root['pages']) if whole else (first+count+PAGE-1)//PAGE
    for i in range(start,end):
        guard();raw,receipt=_open_page(path/f'{i:08d}.nvpsealed',key,pid,_identity(cid,digest)+f'/{i}',PAGE)
        if receipt['sha256']!=root['pages'][i] or len(raw)!=min(PAGE,size-i*PAGE):raise VaultError('Original recording page changed')
        checksum.update(raw);seen+=len(raw)
        lo=max(first,i*PAGE)-i*PAGE;hi=min(first+count,(i+1)*PAGE)-i*PAGE
        if sink is not None and hi>lo:sink.write(raw[lo:hi])
    if whole and (seen!=size or checksum.hexdigest()!=digest):raise VaultError('Original recording identity changed')
    guard()


def _seal(folder,key,pid,cid,digest,size,reader,guard):
    if not 2<=size<=MAX_BYTES or size%2:raise VaultError('Original recording exceeds the current source limit')
    name=_identity(cid,digest);target=_location(folder,key,cid,digest,create=True)
    stage=Path(tempfile.mkdtemp(prefix='.pcm-page-',dir=target.parent))
    try:
        checksum=hashlib.sha256();hashes=[];left=size
        while left:
            guard();n=min(PAGE,left);data=reader.read(n)
            if type(data) is not bytes or len(data)!=n:raise VaultError('Original recording is incomplete')
            checksum.update(data);hashes.append(hashlib.sha256(data).hexdigest())
            _encrypt_file(io.BytesIO(data),stage/f'{len(hashes)-1:08d}.nvpsealed',key=key,project_id=pid,name=name+f'/{len(hashes)-1}')
            left-=n
        if reader.read(1) or checksum.hexdigest()!=digest:raise VaultError('Original PCM digest changed during migration')
        raw=_canonical({'format':FORMAT,'clip_id':cid,'pcm_sha256':digest,'size_bytes':size,'pages':hashes});root_sha=hashlib.sha256(raw).hexdigest()
        _encrypt_file(io.BytesIO(raw),stage/'root.nvpsealed',key=key,project_id=pid,name=name+'/root')
        # Verify stage before exposing it, including all independently opened pages.
        staged,receipt=_open_page(stage/'root.nvpsealed',key,pid,name+'/root',MAX_ROOT)
        if staged!=raw or receipt['sha256']!=root_sha:raise VaultError('Recording root readback changed')
        for i,h in enumerate(hashes):
            guard();chunk,receipt=_open_page(stage/f'{i:08d}.nvpsealed',key,pid,name+f'/{i}',PAGE)
            if receipt['sha256']!=h or len(chunk)!=min(PAGE,size-i*PAGE):raise VaultError('Recording page readback changed')
        guard()
        if not target.exists():atomic_publish_directory(stage,target)
        # Existing orphan can be adopted only on exact complete authenticated identity.
        _read_pages(folder,key,pid,cid,digest,size,root_sha,guard=guard,whole=True)
        return root_sha
    finally:
        if stage.exists():shutil.rmtree(stage)


def _row(db,pid,sid,cid):
    if type(cid) is not str or not HEX.fullmatch(cid):raise ValueError('Select an original recording')
    row=db.execute('''SELECT rowid AS source_rowid,id,scene_id,actor_id,pcm_sha256,sample_rate,channels,sample_count,length(pcm) AS pcm_bytes FROM g06_original_pcm WHERE project_id=? AND scene_id=? AND id=?''',(pid,sid,cid)).fetchone()
    if row is None:raise KeyError('Original recording unavailable')
    if row['sample_rate']!=48000 or row['channels']!=1 or type(row['sample_count']) is not int or not 2<=row['sample_count']*2<=MAX_BYTES:raise VaultError('Original recording clock changed')
    if not SHA.fullmatch(row['pcm_sha256']):raise VaultError('Original recording digest is invalid')
    pointer=db.execute('SELECT * FROM g03_pcm_pages WHERE project_id=? AND clip_id=?',(pid,cid)).fetchone()
    size=row['sample_count']*2
    if pointer is None:
        if row['pcm_bytes']!=size:raise VaultError('Original recording length changed')
    elif (row['pcm_bytes']!=0 or pointer['scene_id']!=sid or pointer['size_bytes']!=size or pointer['pcm_sha256']!=row['pcm_sha256'] or not SHA.fullmatch(pointer['root_sha256'])):raise VaultError('Original recording pointer changed')
    return row,pointer


def metadata(db,filming,pid,sid,cid):
    row,pointer=_row(db,pid,sid,cid)
    if pointer is not None and context(filming,pid) is None:raise VaultError('Protected recording is not available in this workspace')
    result=dict(row);result['pcm_bytes']=row['sample_count']*2
    return result


def read_pcm(db,filming,pid,sid,cid,*,first=0,count=None,verify_only=False):
    row,pointer=_row(db,pid,sid,cid);size=row['sample_count']*2;digest=row['pcm_sha256'];count=size-first if count is None else count
    if type(first) is not int or type(count) is not int or not 0<=first<=first+count<=size or first%2 or count%2:raise ValueError('Invalid recording range')
    sink=None if verify_only else io.BytesIO();ctx=context(filming,pid)
    if pointer is None:
        checksum=hashlib.sha256();offset=0
        with db.blobopen('g06_original_pcm','pcm',row['source_rowid'],readonly=True) as b:
            while offset<size:
                if ctx is not None:context(filming,pid)
                raw=b.read(min(PAGE,size-offset));checksum.update(raw)
                if not raw:raise VaultError('Original PCM truncated')
                a=max(first,offset)-offset;z=min(first+count,offset+len(raw))-offset
                if sink is not None and z>a:sink.write(raw[a:z])
                offset+=len(raw)
        if offset!=size or checksum.hexdigest()!=digest:raise VaultError('Original PCM digest changed')
    else:
        if ctx is None:raise VaultError('Protected recording not available')
        folder,key=ctx
        _read_pages(folder,key,pid,cid,digest,size,pointer['root_sha256'],first=first,count=count,sink=sink,guard=lambda:context(filming,pid),whole=True)
    out=dict(row);out.pop('source_rowid');out['pcm_bytes']=size
    if sink is not None:out['pcm']=sink.getvalue()
    return out


def migrate_recording(filming,pid,sid,cid,digest,*,guard,human_approved=False):
    if human_approved is not True or context(filming,pid) is None:raise PermissionError('Native recording migration approval required')
    host=filming.g05.g04;store=host.live
    # A repeat request verifies the existing representation without another
    # encrypted HEAD publication or compaction.
    with store._guard:
        key=store._session(pid,host.token);folder=store._folder(pid)
        db,_=store._read_db(folder,pid,key)
        try:
            filming._schema(db);guard();row,pointer=_row(db,pid,sid,cid)
            if row['pcm_sha256']!=digest:raise VaultError('Review original recording again')
            if pointer is not None:
                size=row['sample_count']*2
                _read_pages(folder,key,pid,cid,digest,size,pointer['root_sha256'],whole=True,guard=guard)
                return {'migrated':False,'size_bytes':size,'sha256':digest}
        finally:db.close()
    def tx(db,key,folder):
        filming._schema(db);guard();row,pointer=_row(db,pid,sid,cid)
        if row['pcm_sha256']!=digest:raise VaultError('Review original recording again')
        size=row['sample_count']*2
        if pointer is not None:
            _read_pages(folder,key,pid,cid,digest,size,pointer['root_sha256'],whole=True,guard=guard)
            return {'migrated':False,'size_bytes':size,'sha256':digest}
        with db.blobopen('g06_original_pcm','pcm',row['source_rowid'],readonly=True) as original:
            root_sha=_seal(folder,key,pid,cid,digest,size,original,guard)
        db.execute('PRAGMA secure_delete=ON')
        db.execute('INSERT INTO g03_pcm_pages VALUES(?,?,?,?,?,?)',(pid,cid,sid,digest,size,root_sha))
        if db.execute("UPDATE g06_original_pcm SET pcm=X'' WHERE project_id=? AND scene_id=? AND id=? AND pcm_sha256=? AND length(pcm)=?",(pid,sid,cid,digest,size)).rowcount!=1:raise VaultError('Original recording changed')
        guard();return {'migrated':True,'size_bytes':size,'sha256':digest,'original_identity_preserved':True}
    return store._change(pid,host.token,tx,compact=True)


def verify_all(db,folder,pid,key,guard):
    for row in db.execute('SELECT * FROM g03_pcm_pages'):
        guard()
        if row['project_id']!=pid:raise VaultError('Foreign recording pointer')
        source,pointer=_row(db,pid,row['scene_id'],row['clip_id'])
        if pointer is None:raise VaultError('Recording pointer missing')
        _read_pages(folder,key,pid,row['clip_id'],row['pcm_sha256'],row['size_bytes'],row['root_sha256'],guard=guard,whole=True)
