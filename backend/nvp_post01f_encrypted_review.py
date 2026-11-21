"""POST-01F R5: encrypted *derived* LTX presentation review, never original Take.

Only a trusted native host may call this class. It uses the *existing* live
film's DPAPI-unwrapped AES-GCM project key and does not mutate its original
asset table or introduce an unauthenticated plaintext index. Every artifact
is an immutable project/AAD-bound .nvpsealed file; a separate immutable review
record requires authenticated creator authorization. No automatic acceptance.

The authenticated SCM signer and physical Windows/GPU acceptance are separate
prerequisites to constructing trusted result provenance; a generic dict cannot
turn a synthetic witness into native acceptance.
"""
from __future__ import annotations

from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import threading

from backend.nvp_g03_live_store import LiveFilmStore
from backend.nvp_g03_windows_vault import _encrypt_file, _decrypt_file, _no_link
from backend.nvp_post01f_ltx_native_handoff import MAX_PICTURE, digest_file

FORMAT = 'nvp.post01f.encrypted_derived_picture.v1'
REVIEW = 'nvp.post01f.authenticated_creator_picture_review.v1'
JOB = re.compile(r'ltx_[0-9a-f]{24}\Z')
PROJECT = re.compile(r'[0-9a-f]{32}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
MAX_RECORD = 16 * 1024


def _canonical(doc):
    return json.dumps(doc, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def _windows_required():
    if os.name != 'nt':
        raise PermissionError('Encrypted native LTX publication requires Windows project key/EFS custody')


def _validate_job(pid, job):
    if (type(pid) is not str or not PROJECT.fullmatch(pid) or
        type(job) is not str or not JOB.fullmatch(job)):
        raise PermissionError('Invalid exact derived-picture project/job identity')


def _sealed_name(job, suffix):
    return 'derived-ltx/' + job + '/' + suffix


def _hash_sink():
    class Sink:
        def write(self, chunk):
            if type(chunk) is not bytes:
                raise TypeError('Only exact bytes are accepted')
    return Sink()


def _fsync_folder(path):
    # Windows has no portable Python fsync(directory); the encrypted file itself
    # is fsynced by _encrypt_file. The native installed recovery gate must verify
    # durability under power interruption separately.
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)


class EncryptedLtxReview:
    def __init__(self, store: LiveFilmStore, *, verify_original_take,
                 authenticate_creator_decision, confirm_native_admission,
                 quarantine_root: Path, authenticate_creator_preview=None):
        if (not isinstance(store, LiveFilmStore) or
            not callable(verify_original_take) or
            not callable(authenticate_creator_decision) or
            not callable(confirm_native_admission)):
            raise TypeError('Existing protected film vault and trusted creator authority required')
        self.store = store
        self.verify_original = verify_original_take
        self.authorize_decision = authenticate_creator_decision
        self.confirm_native_admission = confirm_native_admission
        # Read-only director preview authority is independent from approval.
        # Old R5 call sites do not receive preview permissions by default.
        self.authorize_preview = authenticate_creator_preview
        self.guard = threading.RLock()
        root=Path(quarantine_root)
        if (not root.is_absolute() or not root.is_dir() or root.is_symlink()):
            raise PermissionError('Only installed host-owned native quarantine root is acceptable')
        _no_link(root)
        self.quarantine_root=root.resolve(strict=True)

    def _root(self, pid):
        folder = self.store._folder(pid)
        if not folder.is_dir() or folder.is_symlink():
            raise PermissionError('Live film root unavailable or linked')
        _no_link(folder)
        root = folder / 'derived_ltx'
        if root.is_symlink():
            raise PermissionError('Derived presentation root is a link')
        if root.exists():_no_link(root)
        return root

    def _read_record(self, path, key, pid, name, limit=MAX_RECORD):
        _no_link(path)
        sink=io.BytesIO()
        result=_decrypt_file(path, sink, key=key, project_id=pid,
                             name=name, max_plain_bytes=limit)
        raw=sink.getvalue()
        if len(raw)>limit or sha256(raw).hexdigest()!=result['sha256']:
            raise PermissionError('Authenticated derived review record changed')
        obj=json.loads(raw)
        if type(obj) is not dict or _canonical(obj)!=raw:
            raise PermissionError('Review record is not exact canonical authenticated JSON')
        return obj

    def _anchor(self, pid, key, job, *, kind, cipher_path):
        """Only the existing encrypted SQLite HEAD may authorize derived records.

        A sealed folder left behind by a crash but never committed into the
        authenticated project index is an orphan, not a successful publication.
        """
        rid=('ltx-picture:' if kind=='picture' else 'ltx-review:')+job
        db,_=self.store._read_db(self.store._folder(pid),pid,key)
        try:
            rows=db.execute('SELECT asset_name, operation, digest FROM worker_receipts WHERE receipt_id=?',
                            (rid,)).fetchall()
        finally:
            db.close()
        if (len(rows)!=1 or rows[0]['asset_name']!='derived_ltx/'+job or
            rows[0]['operation']!=('derived_picture_sealed' if kind=='picture' else 'derived_review_sealed') or
            rows[0]['digest']!=digest_file(cipher_path,MAX_RECORD+1024)):
            raise PermissionError('Derived picture/review is not anchored to encrypted film HEAD')

    def _anchor_once(self,pid,token,job,*,kind,cipher_path):
        rid=('ltx-picture:' if kind=='picture' else 'ltx-review:')+job
        operation='derived_picture_sealed' if kind=='picture' else 'derived_review_sealed'
        digest=digest_file(cipher_path,MAX_RECORD+1024)
        def mutate(db,key,folder):
            if db.execute('SELECT 1 FROM worker_receipts WHERE receipt_id=?',(rid,)).fetchone():
                raise PermissionError('Immutable derived review receipt replay')
            from backend.nvp_studio import now
            db.execute('INSERT INTO worker_receipts '
                       '(receipt_id,asset_name,operation,digest,recorded_at) VALUES (?,?,?,?,?)',
                       (rid,'derived_ltx/'+job,operation,digest,now()))
        self.store._change(pid,token,mutate)

    def _review_anchor_present(self,pid,key,job):
        db,_=self.store._read_db(self.store._folder(pid),pid,key)
        try:
            row=db.execute('SELECT operation FROM worker_receipts WHERE receipt_id=?',
                           ('ltx-review:'+job,)).fetchone()
            return row is not None
        finally:
            db.close()

    def _unseal(self, pid, key, job):
        root=self._root(pid)
        target=root/job
        if (root/(job+'.partial')).exists() or (root/(job+'.partial')).is_symlink():
            raise PermissionError('Unreconciled partial native picture publication')
        if not target.is_dir() or target.is_symlink():
            raise PermissionError('No authenticated LTX derived result for job')
        _no_link(target)
        if set(p.name for p in target.iterdir()) not in ({'picture.nvpsealed','manifest.nvpsealed'},
                          {'picture.nvpsealed','manifest.nvpsealed','decision.nvpsealed'}):
            raise PermissionError('Derived result contains unreviewed extra or missing files')
        for item in target.iterdir():
            _no_link(item)
        self._anchor(pid,key,job,kind='picture',cipher_path=target/'manifest.nvpsealed')
        meta=self._read_record(target/'manifest.nvpsealed',key,pid,_sealed_name(job,'manifest'))
        expected={'format','project_id','job_id','picture_sha256','picture_size_bytes',
                  'take_sha256','model_stack_sha256','plan_sha256',
                  'scm_receipt_sha256','state'}
        if (set(meta)!=expected or meta['format']!=FORMAT or
            meta['project_id']!=pid or meta['job_id']!=job or
            meta['state']!='PICTURE_VERIFIED_UNAPPROVED' or
            any(type(meta[k]) is not str or not SHA.fullmatch(meta[k]) for k in
                ('picture_sha256','take_sha256','model_stack_sha256',
                 'plan_sha256','scm_receipt_sha256')) or
            type(meta['picture_size_bytes']) is not int or
            not 1<=meta['picture_size_bytes']<=MAX_PICTURE):
            raise PermissionError('Encrypted result metadata is foreign or malformed')
        readback=_decrypt_file(target/'picture.nvpsealed',_hash_sink(),key=key,
                 project_id=pid,name=_sealed_name(job,'picture'),
                 max_plain_bytes=MAX_PICTURE)
        if readback!={'sha256':meta['picture_sha256'],
                      'size_bytes':meta['picture_size_bytes']}:
            raise PermissionError('Encrypted derived picture differs from signed result')
        if self.verify_original({'project_id':pid,'take_sha256':meta['take_sha256']}) is not True:
            raise PermissionError('Original immutable Take no longer verifies')
        decision=None
        has_decision=(target/'decision.nvpsealed').exists() or (target/'decision.nvpsealed').is_symlink()
        if self._review_anchor_present(pid,key,job) and not has_decision:
            raise PermissionError('An indexed creator decision was deleted or rolled back')
        if has_decision:
            self._anchor(pid,key,job,kind='review',cipher_path=target/'decision.nvpsealed')
            decision=self._read_record(target/'decision.nvpsealed',key,pid,
                                       _sealed_name(job,'decision'))
            if (set(decision)!={'format','project_id','job_id','picture_sha256','take_sha256',
                               'action','creator_event_sha256'} or
                decision['format']!=REVIEW or decision['project_id']!=pid or
                decision['job_id']!=job or decision['picture_sha256']!=meta['picture_sha256'] or
                decision['take_sha256']!=meta['take_sha256'] or
                decision['action'] not in ('approve','reject') or
                type(decision['creator_event_sha256']) is not str or
                not SHA.fullmatch(decision['creator_event_sha256'])):
                raise PermissionError('Authenticated decision does not bind exact source and picture')
        return target,meta,decision

    def publish_pending(self, pid: str, token: str, *, result: dict):
        """Host-only result admission: re-encrypt reviewed picture, leave UNAPPROVED.

        Caller MUST have verified real native SCM/OS/GPU/decoder independently;
        it cannot be recovered from a worker-supplied success JSON alone.
        """
        _windows_required()
        if type(result) is not dict:
            raise PermissionError('Only trusted host result accepted')
        job=result.get('job_id'); _validate_job(pid,job)
        plan_sha256=result.get('plan_sha256')
        scm_receipt_sha256=result.get('scm_receipt_sha256')
        if (result.get('state')!='PICTURE_VERIFIED_UNAPPROVED' or
            result.get('project_id')!=pid or result.get('creator_approved') is not False or
            result.get('publishable') is not False or
            any(type(x) is not str or not SHA.fullmatch(x) for x in (
                 result.get('picture_sha256'),result.get('source_take_sha256'),
                 result.get('model_stack_sha256'),plan_sha256,scm_receipt_sha256))):
            raise PermissionError('Only verified unapproved native picture and SCM receipt eligible')
        source=Path(result.get('picture_location',''))
        if (not source.is_absolute() or source.is_symlink() or not source.is_file() or
            not JOB.fullmatch(source.parent.name) or source.name!='picture.mp4' or
            source.parent.resolve(strict=True).parent!=self.quarantine_root):
            raise PermissionError('Picture must remain in the exact protected quarantine job')
        _no_link(source.parent)
        _no_link(source)
        from backend.nvp_w1g_encrypted_source import verify_efs_inputs, require_efs_stage
        verify_efs_inputs(source.parent,('picture.mp4','result.json'))
        before=source.stat()
        size=before.st_size
        if not 1<=size<=MAX_PICTURE or digest_file(source,MAX_PICTURE)!=result['picture_sha256']:
            raise PermissionError('Quarantined picture bytes no longer match verified result')
        if self.verify_original({'project_id':pid,
                                  'take_sha256':result['source_take_sha256']}) is not True:
            raise PermissionError('Original Take was mutated before derived publication')
        proof_scope={'project_id':pid,'job_id':job,
                     'picture_sha256':result['picture_sha256'],
                     'take_sha256':result['source_take_sha256'],
                     'model_stack_sha256':result['model_stack_sha256'],
                     'plan_sha256':plan_sha256,
                     'scm_receipt_sha256':scm_receipt_sha256}
        if self.confirm_native_admission(dict(proof_scope)) is not True:
            raise PermissionError('SCM-signed native admission was not independently confirmed')
        with self.guard, self.store._guard:
            key=self.store._session(pid,token)  # Unwrapped by existing DPAPI user-session authority.
            root=self._root(pid)
            root.mkdir(mode=0o700,exist_ok=True)
            target=root/job; scratch=root/(job+'.partial')
            if (target.exists() or target.is_symlink() or
                scratch.exists() or scratch.is_symlink()):
                raise FileExistsError('Duplicate/uncertain derived result; never overwrite or auto-resume')
            scratch.mkdir(mode=0o700)
            require_efs_stage(scratch)
            try:
                with source.open('rb') as inp:
                    opened=os.fstat(inp.fileno())
                    if (opened.st_dev,opened.st_ino,opened.st_size)!=(before.st_dev,before.st_ino,size):
                        raise PermissionError('Quarantined picture changed between admission and open')
                    asset=_encrypt_file(inp,scratch/'picture.nvpsealed',key=key,
                           project_id=pid,name=_sealed_name(job,'picture'))
                    after=os.fstat(inp.fileno())
                    if (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)!=(
                            opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns):
                        raise PermissionError('Quarantined picture mutated during encrypted transfer')
                if asset!={'sha256':result['picture_sha256'],'size_bytes':size}:
                    raise PermissionError('Encrypted picture does not match the SCM-verified result')
                meta={'format':FORMAT,'project_id':pid,'job_id':job,
                      'picture_sha256':asset['sha256'],'picture_size_bytes':size,
                      'take_sha256':result['source_take_sha256'],
                      'model_stack_sha256':result['model_stack_sha256'],
                      'plan_sha256':plan_sha256,
                      'scm_receipt_sha256':scm_receipt_sha256,
                      'state':'PICTURE_VERIFIED_UNAPPROVED'}
                raw=_canonical(meta)
                if len(raw)>MAX_RECORD:
                    raise ValueError('Derived metadata exceeds bound')
                _encrypt_file(io.BytesIO(raw),scratch/'manifest.nvpsealed',key=key,
                              project_id=pid,name=_sealed_name(job,'manifest'))
                verify_efs_inputs(scratch,('picture.nvpsealed','manifest.nvpsealed'))
                # Authenticated ciphertext readback BEFORE publication.
                check=_decrypt_file(scratch/'picture.nvpsealed',_hash_sink(),key=key,
                                    project_id=pid,name=_sealed_name(job,'picture'),
                                    max_plain_bytes=MAX_PICTURE)
                if check!=asset or self._read_record(scratch/'manifest.nvpsealed',key,pid,
                            _sealed_name(job,'manifest'))!=meta:
                    raise PermissionError('Protected derived output failed seal/readback')
                if digest_file(source,MAX_PICTURE)!=asset['sha256']:
                    raise PermissionError('Quarantine changed during protected publication')
                _fsync_folder(scratch)
                os.replace(scratch,target)
                _fsync_folder(root)
                # Atomically pin ciphertext digest in the already authenticated
                # live film SQLite HEAD. Crash before HEAD = refusal on reopen.
                self._anchor_once(pid,token,job,kind='picture',
                                  cipher_path=target/'manifest.nvpsealed')
            except BaseException:
                # Keep the partial for explicit recovery, do NOT clear it or publish it.
                raise
            return {'status':'ENCRYPTED_PICTURE_UNAPPROVED','job_id':job,
                    'picture_sha256':asset['sha256'],'original_modified':False,
                    'creator_approved':False}

    def review(self, pid: str, token: str, job_id: str):
        """Authenticated reopening: full AES-GCM media audit and creator decision."""
        _windows_required(); _validate_job(pid,job_id)
        with self.guard, self.store._guard:
            key=self.store._session(pid,token)
            _,meta,decision=self._unseal(pid,key,job_id)
            return {'job_id':job_id,'project_id':pid,
                    'picture_sha256':meta['picture_sha256'],
                    'original_take_sha256':meta['take_sha256'],
                    'status': ('PICTURE_VERIFIED_UNAPPROVED' if decision is None
                               else ('CREATOR_APPROVED' if decision['action']=='approve'
                                     else 'CREATOR_REJECTED')),
                    'encrypted_at_rest':True,'source_mutated':False}

    def director_preview_bytes(self, pid: str, token: str, job_id: str, *,
                               creator_event: bytes):
        """Release full authenticated video-only bytes ONLY to trusted director UI.

        No URL, worker-selected path, preview disk cache, key or HTML endpoint
        is exposed. The UI integration still must bind the local event to its
        authenticated app session; this function alone is not a browser API.
        GCM content is buffered privately until *after* its final tag verifies.
        """
        _windows_required(); _validate_job(pid,job_id)
        if (not callable(self.authorize_preview) or
            type(creator_event) is not bytes or not 1<=len(creator_event)<=8192):
            raise PermissionError('Authenticated local director preview authority missing')
        with self.guard, self.store._guard:
            key=self.store._session(pid,token)
            target,meta,decision=self._unseal(pid,key,job_id)
            scope={'project_id':pid,'job_id':job_id,
                   'picture_sha256':meta['picture_sha256'],
                   'take_sha256':meta['take_sha256'],
                   'state': ('PENDING' if decision is None else decision['action'])}
            if self.authorize_preview(dict(scope),creator_event) is not True:
                raise PermissionError('Director preview not independently authenticated')
            sink=io.BytesIO()
            proof=_decrypt_file(target/'picture.nvpsealed',sink,key=key,
                project_id=pid,name=_sealed_name(job_id,'picture'),
                max_plain_bytes=MAX_PICTURE)
            if proof!={'sha256':meta['picture_sha256'],
                       'size_bytes':meta['picture_size_bytes']}:
                raise PermissionError('Protected director preview media changed after review')
            # No raw media must be returned after an expired/revoked session.
            self.store._session(pid,token)
            return {'media_type':'video/mp4','video_only':True,
                    'job_id':job_id,'picture_sha256':proof['sha256'],
                    'picture_bytes':sink.getvalue()}

    def decide(self, pid: str, token: str, job_id: str, *, action: str,
               creator_event: bytes):
        """Append-once authenticated creator decision. Never replace source/picture."""
        _windows_required(); _validate_job(pid,job_id)
        if action not in ('approve','reject') or type(creator_event) is not bytes or not 1<=len(creator_event)<=8192:
            raise PermissionError('Explicit bounded creator review event required')
        with self.guard, self.store._guard:
            key=self.store._session(pid,token)
            target,meta,decision=self._unseal(pid,key,job_id)
            if decision is not None or (target/'decision.nvpsealed').exists():
                raise PermissionError('Creator action is immutable; retry requires a new generation job')
            scope={'project_id':pid,'job_id':job_id,'picture_sha256':meta['picture_sha256'],
                   'take_sha256':meta['take_sha256'],'action':action,
                   'creator_event_sha256':sha256(creator_event).hexdigest()}
            if self.authorize_decision(dict(scope), bytes(creator_event)) is not True:
                raise PermissionError('Authenticated local filmmaker review not authorized')
            record={'format':REVIEW,**scope}
            _encrypt_file(io.BytesIO(_canonical(record)),target/'decision.nvpsealed',
                          key=key,project_id=pid,name=_sealed_name(job_id,'decision'))
            from backend.nvp_w1g_encrypted_source import verify_efs_inputs
            verify_efs_inputs(target,('decision.nvpsealed',))
            if self._read_record(target/'decision.nvpsealed',key,pid,
                                 _sealed_name(job_id,'decision'))!=record:
                raise PermissionError('Creator decision ciphertext readback failed')
            self._anchor_once(pid,token,job_id,kind='review',
                              cipher_path=target/'decision.nvpsealed')
            return {'status': 'CREATOR_APPROVED' if action=='approve' else 'CREATOR_REJECTED',
                    'job_id':job_id,'picture_sha256':meta['picture_sha256'],
                    'immutable_original':True}
