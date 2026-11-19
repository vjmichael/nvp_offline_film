"""Additive audio publication checkpoints in the existing native journal.

No worker queue or lease of its own. Native caller must hold its existing
SingletonSupervisor and supply the protected source/producer/verifier.
"""
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

HEX = re.compile(r'[0-9a-f]{64}\Z')
ID = re.compile(r'[0-9a-f]{32}\Z')
MAX_JSON = 32 * 1024
FORMAT = 'nvp.wo4.partitioned_pcm24_candidate.v1'


def canonical(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
    if len(raw) > MAX_JSON:
        raise ValueError('Audio publication metadata too large')
    return raw.decode('ascii')


def digest(raw):
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS production_audio_sets(
      audio_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, project_db TEXT NOT NULL,
      approval_json TEXT NOT NULL, approval_sha256 TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('RUNNING','PREPARED','REVIEW_REQUIRED','VERIFIED')),
      manifest_sha256 TEXT, receipt_json TEXT, receipt_sha256 TEXT)''')
    db.execute('CREATE INDEX IF NOT EXISTS production_audio_recovery ON production_audio_sets(state,audio_id)')
    db.execute('CREATE INDEX IF NOT EXISTS production_audio_catalog ON production_audio_sets(project_id,project_db,audio_id)')


def paths(scope, uid):
    if type(uid) is not str or not ID.fullmatch(uid):
        raise ValueError('Invalid audio set identity')
    root = Path(scope['output_root'])
    if not root.is_absolute() or '..' in root.parts:
        raise PermissionError('Trusted absolute audio root required')
    return root / ('.nvp-pcm-reels-' + uid), root / ('PCM24_REELS_' + uid)


def _load(db, uid, pid=None, project_db=None):
    row = db.execute('SELECT * FROM production_audio_sets WHERE audio_id=?', (uid,)).fetchone()
    if row is None or (pid is not None and (row['project_id'] != pid or row['project_db'] != project_db)):
        raise PermissionError('Audio set outside project scope')
    row = dict(row)
    if digest(row['approval_json']) != row['approval_sha256']:
        raise PermissionError('Audio approval changed')
    plan = json.loads(row['approval_json'])
    if plan['audio_id'] != uid or plan['project_id'] != row['project_id'] or plan['project_db'] != row['project_db']:
        raise PermissionError('Audio approval identities changed')
    if row['receipt_json'] is not None and digest(row['receipt_json']) != row['receipt_sha256']:
        raise PermissionError('Audio receipt changed')
    return row, plan


def _insert(journal, uid, pid, project_db, scope, approve):
    stage, target = paths(scope, uid)
    plan = {**scope, 'audio_id': uid, 'project_id': pid, 'project_db': project_db,
            'staging_path': str(stage), 'destination': str(target)}
    raw = canonical(plan)
    if approve(json.loads(raw)) is not True:
        return False
    with journal._tx() as db:
        if stage.exists() or stage.is_symlink() or target.exists() or target.is_symlink():
            raise FileExistsError('Audio staging or destination already exists')
        db.execute('INSERT INTO production_audio_sets VALUES(?,?,?,?,?,\'RUNNING\',NULL,NULL,NULL)',
                   (uid,pid,project_db,raw,digest(raw)))
    return True


def _prepare(journal, uid, root_sha):
    if type(root_sha) is not str or not HEX.fullmatch(root_sha):
        raise ValueError('Invalid prepared root digest')
    with journal._tx() as db:
        row,_ = _load(db,uid)
        if row['state'] != 'RUNNING' or row['manifest_sha256'] is not None:
            raise PermissionError('Audio preparation state changed')
        db.execute("UPDATE production_audio_sets SET state='PREPARED',manifest_sha256=? WHERE audio_id=?",(root_sha,uid))


def _validate_receipt(row, plan, receipt):
    if (type(receipt) is not dict or receipt.get('format') != FORMAT or
        receipt.get('status') != 'PARTITIONED_PCM24_CANDIDATE_PUBLISHED' or
        receipt.get('manifest_sha256') != row['manifest_sha256'] or
        receipt.get('destination') != plan['destination'] or
        receipt.get('original_take_sha256') != plan['original_take_sha256'] or
        receipt.get('source_pcm_sha256') != plan['source_sha256']):
        raise PermissionError('Audio receipt differs from approved publication')
    # All layout/gain metadata from producer consent is immutable.
    for key in ('frame_count','reel_count','channel_order','sample_rate','sample_count','gain','max_reel_frames'):
        if key in plan and receipt.get(key) != plan[key]:
            raise PermissionError('Prepared audio layout differs: '+key)


def _finalize(journal, uid, receipt, *, verify, allowed, cancelled):
    with journal._read() as db:
        row,plan = _load(db,uid)
    if row['state'] not in allowed:
        raise PermissionError('Audio set not eligible for verification')
    _validate_receipt(row,plan,receipt)
    if cancelled(): raise InterruptedError('Audio verification cancelled')
    result = verify(receipt,cancelled=cancelled)
    if (result.get('manifest_sha256') != row['manifest_sha256'] or
        result.get('production_audio_accepted') is not False):
        raise PermissionError('Independent audio verification failed')
    if cancelled(): raise InterruptedError('Audio verification cancelled')
    raw=canonical(receipt)
    with journal._tx() as db:
        current,_ = _load(db,uid)
        if current != row or cancelled():
            raise PermissionError('Audio publication state changed during verification')
        db.execute("UPDATE production_audio_sets SET state='VERIFIED',receipt_json=?,receipt_sha256=? WHERE audio_id=?",(raw,digest(raw),uid))
    return {**receipt,'audio_set_id':uid,'production_audio_accepted':False}


def run(journal,pid,project_db,*,approve,produce,verify,cancelled=lambda:False,source_ref=None,**parameters):
    """Run within original host lease; register approval before staged writes."""
    uid=uuid4().hex
    try:
        receipt=produce(**parameters,approve=lambda scope:_insert(journal,uid,pid,project_db,{**scope,**(source_ref or {})},approve),
                        publication_id=uid,before_publish=lambda sha:_prepare(journal,uid,sha),cancelled=cancelled)
        if receipt.get('status')=='DENIED':return receipt
        return _finalize(journal,uid,receipt,verify=verify,allowed={'PREPARED'},cancelled=cancelled)
    except BaseException:
        with journal._tx() as db:
            db.execute("UPDATE production_audio_sets SET state='REVIEW_REQUIRED' WHERE audio_id=? AND state IN ('RUNNING','PREPARED')",(uid,))
        raise


def reconcile(journal):
    """Held exclusive native lease: no replay, no deletion, no scan allocation."""
    with journal._tx() as db:
        return db.execute("UPDATE production_audio_sets SET state='REVIEW_REQUIRED' WHERE state IN ('RUNNING','PREPARED')").rowcount


def adopt(journal,uid,pid,project_db,*,approve,reopen,verify,cancelled=lambda:False):
    """Explicit review of a promoted, digest-pinned set, never an unknown stage."""
    with journal._read() as db:
        row,plan=_load(db,uid,pid,project_db)
    if row['state']!='REVIEW_REQUIRED' or not row['manifest_sha256']:
        raise PermissionError('Audio set lacks a durable prepared digest')
    stage,target=paths(plan,uid)
    if stage.exists() or stage.is_symlink() or not target.is_dir() or target.is_symlink():
        raise PermissionError('Ambiguous or missing audio publication')
    receipt=reopen(plan,row['manifest_sha256'],cancelled=cancelled)
    _validate_receipt(row,plan,receipt)
    scope={'operation':'nvp.wo4.adopt_partitioned_audio.v1','audio_id':uid,'project_id':pid,
           'project_db':project_db,'approval_sha256':row['approval_sha256'],
           'manifest_sha256':row['manifest_sha256'],'destination':str(target)}
    if approve(scope) is not True:return {'status':'DENIED','audio_set_id':uid}
    if reopen(plan,row['manifest_sha256'],cancelled=cancelled)!=receipt:
        raise PermissionError('Audio set changed during recovery consent')
    return _finalize(journal,uid,receipt,verify=verify,allowed={'REVIEW_REQUIRED'},cancelled=cancelled)


def page(journal,pid,project_db,*,after=None,limit=32):
    """Only metadata; no private paths or unverified receipt exposed."""
    if type(limit) is not int or not 1<=limit<=64 or (after is not None and (type(after) is not str or not ID.fullmatch(after))):
        raise ValueError('Bounded audio recovery page required')
    with journal._read() as db:
        if after is not None:_load(db,after,pid,project_db)
        ids=[r[0] for r in db.execute('''SELECT audio_id FROM production_audio_sets WHERE project_id=? AND project_db=?
                                         AND audio_id>? ORDER BY audio_id LIMIT ?''',(pid,project_db,after or '',limit+1))]
        items=[]
        for uid in ids[:limit]:
            row,plan=_load(db,uid,pid,project_db)
            items.append({'audio_set_id':uid,'state':row['state'],'frame_count':plan['frame_count'],
                          'reel_count':plan['reel_count'],'prepared_manifest_recorded':row['manifest_sha256'] is not None,
                          'production_audio_accepted':False})
    return {'items':items,'next_after':ids[limit-1] if len(ids)>limit else None}


def verified_receipt(journal,uid,pid,project_db,*,verify,cancelled=lambda:False):
    """Scoped, durable verified candidate; originally authorized delivery still checks it."""
    with journal._read() as db:
        row,plan=_load(db,uid,pid,project_db)
    if row['state']!='VERIFIED' or row['receipt_json'] is None:raise PermissionError('Unverified audio set')
    receipt=json.loads(row['receipt_json']);_validate_receipt(row,plan,receipt)
    result=verify(receipt,cancelled=cancelled)
    if result.get('manifest_sha256')!=row['manifest_sha256'] or result.get('production_audio_accepted') is not False:
        raise PermissionError('Audio receipt verification changed')
    return receipt
