"""Whole protected movie ciphertext backup, explicit local host operations only.

No plaintext source staging, key export, live HEAD replacement or automatic
adoption. Preserve retained revisions and opaque assets; a signed inventory is
checked on the restored copy. Older retained snapshots are not garbage collected.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

from backend.nvp_g03_windows_vault import VaultError, _no_link, _decrypt_file, _token
from backend.nvp_g03_live_store import LiveFilmStore, _HashSink, MAX_DB_BYTES
from backend.nvp_wo3_atomic_publish import atomic_publish_directory

FORMAT = 'nvp.g03.live_movie_backup.v1'
BLOCK = 512 * 1024
MAX_FILES = 100_000
INVENTORY_LIMIT = 32 * 1024 * 1024
ENTRY = re.compile(r'(?:HEAD\.json|key\.nvpdpapi|revisions/db\.[0-9]{12}\.nvpsealed|assets/[a-f0-9]{64}\.nvpsealed|editorial-pages/[a-f0-9]{64}/body\.nvpsealed|pcm-pages/[a-f0-9]{64}/(?:root\.nvpsealed|[0-9]{8}\.nvpsealed)|(?:review-reels|protected-objects|feature-reels)/[a-f0-9]{64}/body\.nvpsealed)\Z')
MANIFEST = 'backup.nvpinventory'


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def _root(path):
    p=Path(path)
    if not p.is_absolute():raise VaultError('Choose a local absolute backup folder')
    if os.name=='nt':
        import ctypes
        if len(p.drive)!=2 or p.drive[1]!=':' or ctypes.windll.kernel32.GetDriveTypeW(str(p.anchor)) not in (2,3):raise VaultError('Choose a local backup drive')
    if any(x in ('.','..') or ':' in x for x in p.parts[1:]):raise VaultError('Invalid backup folder')
    for ancestor in (*reversed(p.parents),p):
        if not stat.S_ISDIR(_no_link(ancestor).st_mode):raise VaultError('Invalid backup folder')
    return p


def _entries(folder, *, backup=False):
    count=0
    for base,dirs,files in os.walk(folder,followlinks=False):
        dirs.sort();files.sort();base=Path(base)
        for d in dirs:
            p=base/d
            if not stat.S_ISDIR(_no_link(p).st_mode):raise VaultError('Unsafe backup directory')
            rel=p.relative_to(folder).as_posix()
            if rel not in ('revisions','assets','editorial-pages','pcm-pages','review-reels','protected-objects','feature-reels') and not re.fullmatch(r'(editorial-pages|pcm-pages|review-reels|protected-objects|feature-reels)/[a-f0-9]{64}',rel):
                raise VaultError('Unreviewed movie storage; finish interrupted writes before backup')
        for name in files:
            p=base/name;rel=p.relative_to(folder).as_posix()
            info=_no_link(p)
            if not stat.S_ISREG(info.st_mode):raise VaultError('Unsafe backup file')
            if rel=='.host-commit.lock' or (backup and rel==MANIFEST):continue
            if not ENTRY.fullmatch(rel):raise VaultError('Unreviewed movie storage file')
            count+=1
            if count>MAX_FILES:raise VaultError('Backup exceeds the reviewed file inventory capacity')
            yield rel,p


def _copy(source,target,guard):
    for part in reversed(source.parents):_no_link(part)
    info=_no_link(source)
    digest=hashlib.sha256();size=0
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)
    with os.fdopen(os.open(source,flags),'rb') as f:
        opened=os.fstat(f.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino):raise VaultError('Backup source changed')
        if target is not None:
            target.parent.mkdir(parents=True,exist_ok=True)
            out=target.open('xb')
        else:out=None
        try:
            while True:
                guard();block=f.read(BLOCK)
                if not block:break
                digest.update(block);size+=len(block)
                if out:out.write(block)
            if out:out.flush();os.fsync(out.fileno())
            after=os.fstat(f.fileno());current=_no_link(source)
            if size!=opened.st_size or (after.st_size,after.st_mtime_ns,after.st_ino)!=(opened.st_size,opened.st_mtime_ns,opened.st_ino) or (current.st_dev,current.st_ino,current.st_mtime_ns)!=(opened.st_dev,opened.st_ino,opened.st_mtime_ns):raise VaultError('Movie changed during backup')
        finally:
            if out:out.close()
    return {'size':size,'sha256':digest.hexdigest()}


def _inventory(folder,guard,*,target=None,backup=False):
    # Bounded manifest metadata, not bounded total movie bytes. No full media
    # allocation; maintain one row per retained file, strict reviewed cap.
    rows={}
    for rel,path in _entries(folder,backup=backup):
        rows[rel]=_copy(path,target/rel if target is not None else None,guard)
    return rows


def _check_manifest(folder,pid,key,guard):
    path=folder/MANIFEST
    if _no_link(path).st_size>INVENTORY_LIMIT:raise VaultError('Backup inventory is too large')
    data=json.loads(path.read_bytes())
    if type(data) is not dict or set(data)!={'inventory','mac'}:raise VaultError('Invalid movie backup inventory')
    inv=data['inventory']
    if type(inv) is not dict or set(inv)!={'format','project_id','head','files'} or inv['format']!=FORMAT or inv['project_id']!=pid or type(inv['files']) is not dict or len(inv['files'])>MAX_FILES:raise VaultError('Backup belongs to another movie')
    mac=hmac.new(key,b'nvp-live-backup-v1\0'+_canonical(inv),hashlib.sha256).hexdigest()
    if type(data['mac']) is not str or not hmac.compare_digest(data['mac'],mac):raise VaultError('Backup inventory is not authenticated')
    if _inventory(folder,guard,backup=True)!=inv['files'] or LiveFilmStore._head(folder)!=inv['head']:raise VaultError('Backup file inventory changed')
    return inv


def _verify_index(store,folder,pid,key,guard):
    """Independently verify current snapshot and indexed external sources."""
    # Every retained history object must authenticate to its exact immutable
    # revision identity. An incomplete orphan is a review condition, never
    # silently excluded from a backup advertised as complete.
    for file in (folder/'revisions').glob('db.*.nvpsealed'):
        guard();match=re.fullmatch(r'db\.([0-9]{12})\.nvpsealed',file.name)
        if not match:raise VaultError('Unexpected movie revision')
        _no_link(file);_decrypt_file(file,_HashSink(),key=key,project_id=pid,name='live-sqlite-v1/'+str(int(match.group(1))),max_plain_bytes=MAX_DB_BYTES)
    db,head=store._read_db(folder,pid,key)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise VaultError('Protected movie database is damaged')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for row in db.execute('SELECT name,opaque_id,sha256,size_bytes FROM source_assets'):
            guard();opaque=_token(row['name'],key)
            if row['opaque_id']!=opaque:raise VaultError('Original asset identity changed')
            path=folder/'assets'/ (opaque+'.nvpsealed');_no_link(path)
            r=_decrypt_file(path,_HashSink(),key=key,project_id=pid,name='original/'+row['name'],max_plain_bytes=row['size_bytes'])
            if r!={'sha256':row['sha256'],'size_bytes':row['size_bytes']}:raise VaultError('Original asset changed')
        if 'g07_sections' in tables:
            from backend.nvp_g07_section_pages import resolve
            for row in db.execute('SELECT project_id,document_json,document_sha256 FROM g07_sections'):
                guard()
                if row[0]!=pid:raise VaultError('Foreign saved section')
                raw=resolve(row[1],row[2],folder=folder,pid=pid,key=key)
                if hashlib.sha256(raw.encode()).hexdigest()!=row[2]:raise VaultError('Saved section changed')
        if 'g08_sealed_delivery_assets' in tables:
            for row in db.execute('SELECT job_id,opaque_id,digest,size_bytes FROM g08_sealed_delivery_assets'):
                guard();name='g08-delivery/'+row[0];opaque=_token(name,key)
                if opaque!=row[1]:raise VaultError('Finished asset identity changed')
                p=folder/'assets'/(opaque+'.nvpsealed');_no_link(p)
                if _decrypt_file(p,_HashSink(),key=key,project_id=pid,name=name,max_plain_bytes=row[3])!={'sha256':row[2],'size_bytes':row[3]}:raise VaultError('Finished asset changed')
        # Existing inline source records remain byte-identical through the
        # snapshot; also independently hash every original BLOB in bounded reads.
        from backend import nvp_g03_payloads as protected_payloads
        db._nvp_payload_guard=guard
        protected_payloads.verify_index(db,pid,guard)
        from backend.nvp_g07_feature_finish import verify_index as verify_finish_analysis
        verify_finish_analysis(db,pid,guard)
        for table,columns in (('g06_original_pcm',(('pcm','pcm_sha256'),)),('g06_frozen_takes',(('original_usd','original_usd_sha256'),('performance_usd','performance_usd_sha256')))):
            if table not in tables:continue
            for col,digest_col in columns:
                for row in db.execute(f'SELECT rowid,project_id,length({col}) AS n,{digest_col} AS digest FROM {table}'):
                    guard()
                    if row['project_id']!=pid:raise VaultError('Foreign movie source')
                    if table=='g06_original_pcm' and row['n']==0:
                        if 'g03_pcm_pages' not in tables or db.execute('SELECT 1 FROM g03_pcm_pages p JOIN g06_original_pcm a ON a.id=p.clip_id AND a.project_id=p.project_id WHERE a.rowid=?',(row['rowid'],)).fetchone() is None:raise VaultError('Missing indexed original PCM')
                        continue
                    if table=='g06_frozen_takes' and row['n']==0:
                        if 'g03_r5_take_payloads' not in tables or db.execute('SELECT 1 FROM g03_r5_take_payloads p JOIN g06_frozen_takes t ON p.project_id=t.project_id AND p.take_id=t.take_id WHERE t.rowid=? AND p.kind=?',(row['rowid'],col)).fetchone() is None:raise VaultError('Missing indexed original OpenUSD')
                        continue
                    if not 0<row['n']<=MAX_DB_BYTES:raise VaultError('Original media length changed')
                    h=hashlib.sha256();size=0
                    with db.blobopen(table,col,row['rowid'],readonly=True) as blob:
                        while True:
                            guard();data=blob.read(BLOCK)
                            if not data:break
                            h.update(data);size+=len(data)
                    if size!=row['n'] or h.hexdigest()!=row['digest']:raise VaultError('Original media digest changed')
        if 'g03_pcm_pages' in tables:
            from backend.nvp_g03_pcm_pages import verify_all
            verify_all(db,folder,pid,key,guard)
        if 'g07_review_reels' in tables:
            from backend.nvp_g07_review_reels import verify_indexed_reels
            verify_indexed_reels(db,folder,pid,key,guard)
        from backend.nvp_g07_feature_reels import verify_index as verify_feature_reels
        verify_feature_reels(db,folder,pid,key,guard)
    finally:db.close()
    return head


def create_backup(store,pid,token,parent,*,guard,human_approved=False,expected_head=None):
    if human_approved is not True:raise PermissionError('Native backup approval required')
    parent=_root(parent);folder=_root(store._folder(pid));target=parent/('NVP-'+pid+'-backup')
    if parent==folder or folder in parent.parents or parent in folder.parents:raise VaultError('Choose a separate backup location')
    if target.exists() or target.is_symlink():raise VaultError('Choose an empty backup location; existing backups are preserved')
    with store._guard,store._write_mutex(folder):
        key=store._session(pid,token)
        def check():guard();store._session(pid,token)
        check();head=_verify_index(store,folder,pid,key,check)
        if expected_head is not None and head!=expected_head:raise VaultError("Movie changed during backup approval")
        stage=Path(tempfile.mkdtemp(prefix='.nvp-backup-',dir=parent))
        try:
            for sub in ('revisions','assets'):(stage/sub).mkdir()
            rows=_inventory(folder,check,target=stage)
            if not {"key.nvpdpapi","HEAD.json","revisions/"+head["name"]}<=set(rows):raise VaultError("Incomplete protected key and revision inventory")
            if _inventory(folder,check)!=rows or store._head(folder)!=head:raise VaultError('Movie changed during backup')
            inv={'format':FORMAT,'project_id':pid,'head':head,'files':rows}
            material=_canonical({'inventory':inv,'mac':hmac.new(key,b'nvp-live-backup-v1\0'+_canonical(inv),hashlib.sha256).hexdigest()})
            if len(material)>INVENTORY_LIMIT:raise VaultError('Backup inventory exceeds the reviewed size')
            store._write_fsync(stage/MANIFEST,material)
            _check_manifest(stage,pid,key,check);_verify_index(store,stage,pid,key,check)
            check();atomic_publish_directory(stage,target)
            return {'format':FORMAT,'project_id':pid,'backup_created':True,'file_count':len(rows),'bytes':sum(r['size'] for r in rows.values()),'head_sequence':head['sequence'],'original_unchanged':True,'portable_to_other_windows_account':False}
        finally:
            if stage.exists():shutil.rmtree(stage)


def restore_copy(store,pid,token,backup,parent,*,guard,human_approved=False,expected_inventory=None):
    """Restore a separate copy only. Never replace an existing live movie."""
    if human_approved is not True:raise PermissionError('Native restore approval required')
    backup=_root(backup);parent=_root(parent);target=parent/pid
    if backup==parent or backup in parent.parents or parent==store.root or store.root in parent.parents or parent in store.root.parents or target.exists() or target.is_symlink():raise VaultError('Choose a new separate recovery folder')
    with store._guard:
        key=store._session(pid,token)
        def check():guard();store._session(pid,token)
        inv=_check_manifest(backup,pid,key,check);_verify_index(store,backup,pid,key,check)
        if expected_inventory is not None and inv!=expected_inventory:raise VaultError("Backup changed during recovery approval")
        stage=Path(tempfile.mkdtemp(prefix='.nvp-restore-',dir=parent))
        try:
            for sub in ('revisions','assets'):(stage/sub).mkdir()
            rows=_inventory(backup,check,target=stage,backup=True)
            if rows!=inv['files']:raise VaultError('Backup changed during restoration')
            if _inventory(stage,check)!=rows or _verify_index(store,stage,pid,key,check)!=inv['head']:raise VaultError('Restored copy cannot reopen')
            check();atomic_publish_directory(stage,target)
            return {'format':FORMAT,'project_id':pid,'restored_copy':True,'file_count':len(rows),'head_sequence':inv['head']['sequence'],'original_unchanged':True,'active_movie_replaced':False}
        finally:
            if stage.exists():shutil.rmtree(stage)


def restore_detached(pid,passphrase,backup,parent,*,guard,human_approved=False):
    """Host-only disaster recovery on the original Windows account.

    No live session or current film is needed. The wrapped original key and
    exact passphrase are required; this publishes a separate copy, not an
    active Studio registration. Never expose the password to a web route.
    """
    from backend.nvp_g03_windows_vault import _key_open,_project
    if human_approved is not True:raise PermissionError('Native recovery approval required')
    _project(pid);backup=_root(backup);parent=_root(parent);target=parent/pid
    if backup==parent or backup in parent.parents or target.exists() or target.is_symlink():raise VaultError('Choose an empty independent recovery folder')
    guard();metadata_path=backup/'key.nvpdpapi'
    if _no_link(metadata_path).st_size>16384:raise VaultError('Movie key metadata too large')
    key=_key_open(passphrase,pid,json.loads(metadata_path.read_bytes()))
    store=LiveFilmStore(parent)
    inv=_check_manifest(backup,pid,key,guard);_verify_index(store,backup,pid,key,guard)
    stage=Path(tempfile.mkdtemp(prefix='.nvp-restore-',dir=parent))
    try:
        for sub in ('revisions','assets'):(stage/sub).mkdir()
        rows=_inventory(backup,guard,target=stage,backup=True)
        if rows!=inv['files'] or _inventory(stage,guard)!=rows or _verify_index(store,stage,pid,key,guard)!=inv['head']:raise VaultError('Detached copy failed recovery verification')
        guard();atomic_publish_directory(stage,target)
        # The next installed host must independently unlock using DPAPI and
        # original project password. No active session is imported or leaked.
        return {'format':FORMAT,'project_id':pid,'restored_copy':True,'file_count':len(rows),'head_sequence':inv['head']['sequence'],'original_unchanged':True,'active_movie_replaced':False,'active_registration_created':False}
    finally:
        if stage.exists():shutil.rmtree(stage)
