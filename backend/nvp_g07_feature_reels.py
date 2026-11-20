"""Host-private resumable segmented working-film production.

One native-reviewed reel per call, no automatic jobs or browser authority.
Keeps the legacy bounded host renderer and a separate reviewed installed
Windows AppContainer worker path. No protected-worker fallback. A verified
encrypted working reel is not final distribution or cinema master.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import stat
import struct
from pathlib import Path

from backend.nvp_g03_payloads import _context
from backend.nvp_g03_windows_vault import VaultError, _token, _no_link, _encrypt_file, _decrypt_file
from backend.nvp_g06_filming import _json
from backend.nvp_g07_feature_finish import _review, _digest, verify_index as verify_analysis
from backend.nvp_g07_paged_media import _native_source_window
from backend.nvp_g07_review_reels import inspect
from backend.nvp_g08_native_avi import TICKS_FRAME, _riff_head, WIDTH, HEIGHT
from backend.nvp_g09e_audio import finish_window
from backend.nvp_g09e_chunk import FRAMES_PER_CHUNK, MAX_CHUNK_BYTES, MAX_TAKES_PER_WINDOW, MAX_FRAMES, render_reel, check_assembly
from backend.nvp_wo3_atomic_publish import atomic_publish_directory, _fsync_directory

FORMAT = 'nvp.g07.protected_feature_reels.v1'
MAX_REELS_PER_JOB = 4096
MAX_JOBS = 32
HEX = re.compile(r'[0-9a-f]{64}\Z')


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS g07_feature_reel_jobs(
        project_id TEXT NOT NULL, job_id TEXT NOT NULL, analysis_sha256 TEXT NOT NULL,
        specification TEXT NOT NULL, completion TEXT,
        PRIMARY KEY(project_id,job_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS g07_feature_reel_parts(
        project_id TEXT NOT NULL, job_id TEXT NOT NULL, part INTEGER NOT NULL,
        attempt INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','verified')),
        receipt TEXT, PRIMARY KEY(project_id,job_id,part))''')


def _hex(value):
    if type(value) is not str or not HEX.fullmatch(value):
        raise ValueError('Choose an exact saved finishing analysis or production')
    return value


def _analysis(db, pid, digest):
    _hex(digest)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='g07_feature_finish_analysis'").fetchone():
        raise PermissionError('Measure and approve the current film finishing first')
    row = db.execute('SELECT receipt_json FROM g07_feature_finish_analysis WHERE project_id=? AND receipt_sha256=?',(pid,digest)).fetchone()
    if row is None: raise PermissionError('Saved finishing analysis missing')
    data=json.loads(row[0]); body=dict(data)
    if body.pop('receipt_sha256',None)!=digest or _digest(body)!=digest or data['review']['project_id']!=pid:
        raise VaultError('Finishing receipt changed')
    if not 1<=data['review']['frame_count']<=MAX_FRAMES or data['sample_count']!=data['review']['frame_count']*2000:
        raise VaultError('Finishing clock changed')
    return data


def _current(service,db,pid,analysis):
    reviewed=analysis['review']; fresh,approved=_review(service,db,pid,reviewed['revision'],reviewed['active_digest'])
    # Sealing the analysis/journal necessarily advances HEAD. All other
    # creative and source bindings must be exactly those originally measured.
    def binding(review):return {k:v for k,v in review.items() if k not in ('snapshot','review_sha256')}
    if binding(fresh)!=binding(reviewed):raise PermissionError('Review and measure the changed film finishing again')
    return approved


def _spec(pid,analysis,frames_per_reel):
    if type(frames_per_reel) is not int or not 1<=frames_per_reel<=FRAMES_PER_CHUNK:
        raise ValueError('One reel cannot exceed ten seconds')
    if (analysis['review']['frame_count']+frames_per_reel-1)//frames_per_reel>MAX_REELS_PER_JOB:
        raise ValueError('Choose a longer bounded reel window for this film')
    return {'format':FORMAT,'project_id':pid,'analysis_sha256':analysis['receipt_sha256'],
            'total_frames':analysis['review']['frame_count'],'frames_per_reel':frames_per_reel,
            'gain_plan_sha256':_digest(analysis['gain_plan']), 'working_delivery_only':True,
            'independent_worker_verified':False,'final_movie_exported':False}


def _bounds(spec,part):
    size=spec['frames_per_reel']; start=part*size; end=min(start+size,spec['total_frames'])
    if type(part) is not int or not 0<=start<end:raise VaultError('Reel outside approved film')
    return start,end


def _job(db,pid,job):
    return db.execute('SELECT * FROM g07_feature_reel_jobs WHERE project_id=? AND job_id=?',(pid,job)).fetchone()


def _parts(db,pid,job):
    return db.execute('SELECT * FROM g07_feature_reel_parts WHERE project_id=? AND job_id=? ORDER BY part',(pid,job))


def _cursor(db,pid,job,spec):
    part=0; pending=None
    for row in _parts(db,pid,job):
        if row['part']!=part or pending is not None or type(row['attempt']) is not int or row['attempt']<1:
            raise VaultError('Reel journal is not a contiguous prefix')
        _bounds(spec,part)
        if row['state']=='pending':
            if row['receipt'] is not None:raise VaultError('Pending reel has uncommitted receipt')
            pending=row['attempt']
        elif row['state']=='verified' and row['receipt'] is not None:
            part+=1
        else:raise VaultError('Invalid reel state')
    if part*spec['frames_per_reel']>=spec['total_frames']:return part,None,True
    return part,pending,False


def _next(service,db,pid,analysis_sha,frames_per_reel):
    if service.access_guard is None:raise PermissionError('Open the movie in the trusted native host')
    verify_analysis(db,pid,service.access_guard)
    analysis=_analysis(db,pid,analysis_sha);_current(service,db,pid,analysis)
    spec=_spec(pid,analysis,frames_per_reel);job=_digest(spec);_schema(db)
    row=_job(db,pid,job)
    if row is not None and (row['analysis_sha256']!=analysis_sha or json.loads(row['specification'])!=spec):raise VaultError('Production identity changed')
    part,pending,done=_cursor(db,pid,job,spec)
    if row is None and (part or pending is not None):raise VaultError('Orphan reel journal')
    _,_,_,head=_context(db,pid)
    action='complete' if row is not None and row['completion'] is not None else ('finalize' if done else 'resume' if pending else 'render')
    result={'format':FORMAT,'project_id':pid,'job_id':job,'analysis_sha256':analysis_sha,'spec':spec,
            'snapshot':head,'part':part,'pending_attempt':pending,'action':action,
            'window':None if done else list(_bounds(spec,part)),'worker_authorized':False}
    return {**result,'review_sha256':_digest(result)}


def review_next(service,pid,analysis_sha256,*,frames_per_reel=FRAMES_PER_CHUNK):
    return service._run(pid,lambda db,movie:_next(service,db,pid,analysis_sha256,frames_per_reel))


def _assembly(service,db,pid,analysis,approved,start,end):
    from backend.nvp_g09_environment import G09Environment
    from backend.nvp_g09_actor import G09Actors
    from backend.nvp_g09c_acoustics import G09CAcoustics
    reviewed=analysis['review'];source=_native_source_window(service,db,pid,reviewed['revision'],reviewed['active_digest'],start*TICKS_FRAME,end*TICKS_FRAME,plan_sha256=reviewed['plan_sha256'])
    if len(source['original_takes'])>MAX_TAKES_PER_WINDOW:raise ValueError('Choose a smaller reel')
    maps=[{},{},{}]
    for tid in source['original_takes']:
        service.access_guard();row,take,_=service.editor._take(db,pid,tid,{},metadata_only=True)
        for target,reader in zip(maps,(G09Environment.approved_source,G09Actors.approved_source,G09CAcoustics.approved_source)):
            val=reader(db,pid,tid,row['take_sha256'],take)
            if val is not None: target[tid]=val
    if maps[2]:raise PermissionError('Continuous approved room sound is not yet supported')
    bindings={k:reviewed['source'][k] for k in ('production_looks_sha256','actor_performances_sha256','acoustic_looks_sha256')}
    return {**source,**bindings,'format':'nvp.g07.non_destructive_edit.v1','source_media_modified':False,
            'edit_revision':reviewed['revision'],'edit_document_sha256':reviewed['active_digest'],
            'production_looks':maps[0],'actor_performances':maps[1],'acoustic_looks':maps[2],
            'approved_finishing':approved,'finishing_sha256':approved['sha256']}


def _name(job,part):return 'feature-reel/'+_hex(job)+'/'+str(part)


def _location(folder,key,job,part,*,create=False):
    root=folder/'feature-reels';_no_link(folder)
    if create:root.mkdir(exist_ok=True)
    if not stat.S_ISDIR(_no_link(root).st_mode):raise VaultError('Invalid feature storage root')
    return root/_token(_name(job,part),key)


def _read_body(folder,key,pid,job,part,size):
    return _read_at(_location(folder,key,job,part),key,pid,job,part,size)


def _read_at(target,key,pid,job,part,size):
    if not stat.S_ISDIR(_no_link(target).st_mode):raise VaultError('Invalid protected reel directory')
    if set(p.name for p in target.iterdir())!={'body.nvpsealed'}:raise VaultError('Unexpected protected reel entries')
    body=target/'body.nvpsealed';info=_no_link(body)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise VaultError('Invalid protected reel file')
    sink=io.BytesIO();audit=_decrypt_file(body,sink,key=key,project_id=pid,name=_name(job,part),max_plain_bytes=size)
    return sink.getvalue(),audit


def _pcm(data,frames):
    # Called only after strict inspect() checks exact RIFF, index and order.
    at=12+len(_riff_head(frames,frames*2000,WIDTH,HEIGHT,WIDTH*HEIGHT*3))+12
    for _ in range(frames):
        size=struct.unpack_from('<I',data,at+4)[0];at+=8+size+(size&1)
        size=struct.unpack_from('<I',data,at+4)[0];yield data[at+8:at+8+size];at+=8+size+(size&1)


def _part_receipt(job,part,start,end,verified,native=None):
    result={'format':FORMAT,'job_id':job,'part':part,'start_frame':start,'end_frame':end,
            'start_sample':start*2000,'end_sample':end*2000,'media':verified}
    if native is not None:
        if (type(native) is not dict or set(native)!={'identity','request_sha256','media_sha256','job_and_profile_cleanup_verified'} or
            type(native['identity']) is not dict or set(native['identity'])!={'role','executable_sha256','os'} or
            native['identity']['role']!='protected_feature_reel' or native['identity']['os']!='windows-appcontainer-job' or
            native['media_sha256']!=verified['sha256'] or native['job_and_profile_cleanup_verified'] is not True):
            raise VaultError('Invalid private worker receipt')
        _hex(native['request_sha256']);_hex(native['identity']['executable_sha256'])
        result['native_execution']=native
    return result


def _reopen(folder,key,pid,job,spec,row,guard=None):
    part=row['part'];start,end=_bounds(spec,part)
    if row['state']!='verified':raise VaultError('Reel is not published')
    receipt=json.loads(row['receipt']);media=receipt['media'];size=media['bytes']
    if type(size) is not int or not 0<size<=MAX_CHUNK_BYTES:raise VaultError('Invalid reel size')
    data,audit=_read_body(folder,key,pid,job,part,size)
    if audit!={'sha256':media['sha256'],'size_bytes':size}:raise VaultError('Encrypted reel changed')
    verified=inspect(data,end-start,expected_sha=media['sha256'],expected_pcm=media['pcm_sha256'],guard=guard)
    if receipt!=_part_receipt(job,part,start,end,verified,receipt.get('native_execution')):raise VaultError('Reel receipt changed')
    return data,receipt


def _publish(folder,key,pid,job,part,data,guard):
    target=_location(folder,key,job,part,create=True);digest=hashlib.sha256(data).hexdigest()
    expected={'sha256':digest,'size_bytes':len(data)}
    # Split commit: only an explicit fresh resume may replay the original
    # deterministic render and authenticate an exact already-published body.
    stage=target.parent/('.stage-'+target.name)
    if target.exists() or target.is_symlink():
        if stage.exists() or stage.is_symlink():raise VaultError('Conflicting interrupted reel storage')
        old,audit=_read_body(folder,key,pid,job,part,len(data))
        if audit!=expected or old!=data:raise VaultError('Interrupted reel differs; manual recovery required')
        return
    # The keyed stage name binds this specific project/job/part. A new
    # review may adopt only a complete authenticated stage matching an
    # exact fresh deterministic render. Unknown or partial bytes are retained.
    if stage.exists() or stage.is_symlink():
        old,audit=_read_at(stage,key,pid,job,part,len(data))
        if audit!=expected or old!=data:raise VaultError('Interrupted stage differs; manual recovery required')
        guard();_fsync_directory(stage);atomic_publish_directory(stage,target);return
    stage.mkdir(mode=0o700)
    try:
        _fsync_directory(stage.parent)
        body=stage/'body.nvpsealed';_encrypt_file(io.BytesIO(data),body,key=key,project_id=pid,name=_name(job,part))
        old,audit=_read_at(stage,key,pid,job,part,len(data))
        if audit!=expected or old!=data:raise VaultError('Sealed reel readback changed')
        guard();_fsync_directory(stage);atomic_publish_directory(stage,target)
    finally:
        if stage.exists():shutil.rmtree(stage)


def _complete(db,folder,key,pid,job,spec,analysis,guard):
    count,pending,done=_cursor(db,pid,job,spec)
    if not done or pending is not None:raise VaultError('Movie reels are incomplete')
    pcm=hashlib.sha256();chain=hashlib.sha256();frames=0;all_native=True
    for row in _parts(db,pid,job):
        guard();data,receipt=_reopen(folder,key,pid,job,spec,row,guard)
        if receipt['start_frame']!=frames:raise VaultError('Reel gap or overlap')
        all_native=all_native and 'native_execution' in receipt
        n=receipt['end_frame']-frames
        for block in _pcm(data,n):pcm.update(block)
        chain.update(bytes.fromhex(_digest(receipt)));frames+=n
    if frames!=spec['total_frames'] or pcm.hexdigest()!=analysis['derived_pcm_sha256']:
        raise VaultError('Whole-film PCM does not match the original finishing analysis')
    body={'format':FORMAT,'job_id':job,'project_id':pid,'analysis_sha256':analysis['receipt_sha256'],
          'frames':frames,'samples':frames*2000,'reel_count':count,'ordered_receipts_sha256':chain.hexdigest(),
          'pcm_sha256':pcm.hexdigest(),'working_reels_complete':True,'independent_worker_verified':all_native,'final_movie_exported':False}
    return {**body,'completion_sha256':_digest(body)}


def review_native_next(service,pid,analysis_sha256,*,frames_per_reel=FRAMES_PER_CHUNK):
    """Host-only exact separate worker review; never a renderer-supplied executable."""
    from backend.nvp_g07_feature_native import installed_identity
    identity=installed_identity()
    review=review_next(service,pid,analysis_sha256,frames_per_reel=frames_per_reel)
    body={'review':review,'native_renderer':identity}
    return {**body,'native_review_sha256':_digest(body)}


def execute_native_approved(service,pid,expected,*,human_approved=False,cancel=None,worker_started=None,worker_finished=None):
    from backend.nvp_g07_feature_native import installed_identity
    if human_approved is not True or type(expected) is not dict or set(expected)!={'review','native_renderer','native_review_sha256'}:
        raise PermissionError('Native worker confirmation required')
    identity=installed_identity()
    if expected['native_renderer']!=identity or _digest({'review':expected['review'],'native_renderer':identity})!=expected['native_review_sha256']:
        raise PermissionError('Native worker review changed')
    return _execute(service,pid,expected['review'],human_approved=True,cancel=cancel,native_identity=identity,worker_started=worker_started,worker_finished=worker_finished)


def execute_approved(service,pid,expected,*,human_approved=False,cancel=None):
    return _execute(service,pid,expected,human_approved=human_approved,cancel=cancel)


def _execute(service,pid,expected,*,human_approved=False,cancel=None,native_identity=None,worker_started=None,worker_finished=None):
    """Explicit per-reel host approval. Pending state never auto-restarts."""
    if human_approved is not True or service.access_guard is None or type(expected) is not dict or expected.get('project_id')!=pid:
        raise PermissionError('Native confirmation of exact production review required')
    if cancel is not None and not callable(cancel):raise ValueError('Invalid host cancellation')
    if worker_started is not None and not callable(worker_started):raise ValueError('Invalid host start notification')
    if worker_finished is not None and not callable(worker_finished):raise ValueError('Invalid host completion notification')
    def guard():
        service.access_guard()
        if cancel and cancel():raise InterruptedError('Movie production cancelled')
    guard();job=_hex(expected['job_id']);analysis_sha=_hex(expected['analysis_sha256']);size=expected['spec']['frames_per_reel'];part=expected['part']
    def claim(db,movie):
        actual=_next(service,db,pid,analysis_sha,size)
        if actual!=expected or actual['action']=='complete':raise PermissionError('Production review changed; review again')
        guard();spec=actual['spec'];_schema(db)
        if _job(db,pid,job) is None:
            if db.execute('SELECT COUNT(*) FROM g07_feature_reel_jobs').fetchone()[0]>=MAX_JOBS:
                raise VaultError('Retained reel-production capacity requires review')
            db.execute('INSERT INTO g07_feature_reel_jobs VALUES(?,?,?,?,NULL)',(pid,job,analysis_sha,_json(spec)))
        if actual['action']=='finalize':
            folder,_,key,_=_context(db,pid);result=_complete(db,folder,key,pid,job,spec,_analysis(db,pid,analysis_sha),guard)
            guard();db.execute('UPDATE g07_feature_reel_jobs SET completion=? WHERE project_id=? AND job_id=?',(_json(result),pid,job));return result
        attempt=(actual['pending_attempt'] or 0)+1
        if actual['pending_attempt'] is None:db.execute("INSERT INTO g07_feature_reel_parts VALUES(?,?,?,?,'pending',NULL)",(pid,job,part,attempt))
        else:db.execute('UPDATE g07_feature_reel_parts SET attempt=? WHERE project_id=? AND job_id=? AND part=?',(attempt,pid,job,part))
        return attempt
    attempt=service._run(pid,claim,write=True)
    if isinstance(attempt,dict):return attempt
    # Hold the existing host writer mutex through source read, render, and
    # publish. An overlapping resume can supersede an unclaimed attempt but
    # never concurrently publish the same journal row.
    def render(db,movie):
        guard();analysis=_analysis(db,pid,analysis_sha);approved=_current(service,db,pid,analysis);spec=_spec(pid,analysis,size)
        row=db.execute('SELECT * FROM g07_feature_reel_parts WHERE project_id=? AND job_id=? AND part=?',(pid,job,part)).fetchone()
        if row is None or row['state']!='pending' or row['attempt']!=attempt or _cursor(db,pid,job,spec)!=(part,attempt,False):raise PermissionError('Production attempt superseded')
        start,end=_bounds(spec,part);source=_assembly(service,db,pid,analysis,approved,start,end)
        reviewed=analysis['review'];binding=reviewed['source']
        digests={k:binding[k] for k in ('production_looks_sha256','actor_performances_sha256','acoustic_looks_sha256')}
        digests.update(edit_document_sha256=reviewed['active_digest'],finishing_sha256=reviewed['finishing_sha256'])
        check_assembly(source,spec['total_frames'],start,end,digests)
        native=None
        if native_identity is None:
            dest=io.BytesIO()
            def check_cancel():guard();return False
            render_reel(source,start,end,analysis['gain_plan'],dest,cancel=check_cancel)
            data=dest.getvalue()
        else:
            from backend.nvp_g07_feature_native import render as render_private
            data,native=render_private(source,start,end,analysis['gain_plan'],native_identity,guard,started=worker_started)
            if worker_finished is not None:worker_finished()
        digest=hashlib.sha256(data).hexdigest()
        # Independently recompute the original window's finished PCM, using
        # global sample offsets and the saved whole-film gain, not per-reel gain.
        from backend.nvp_g08_native_avi import _audio_frame
        pcm=hashlib.sha256()
        for frame in range(start,end):
            guard();raw=_audio_frame(source,source['original_takes'],frame*2000,2000)
            pcm.update(finish_window(raw,analysis['gain_plan'],start_sample=frame*2000,total_samples=analysis['sample_count']))
        verified=inspect(data,end-start,expected_sha=digest,expected_pcm=pcm.hexdigest(),guard=guard);receipt=_part_receipt(job,part,start,end,verified,native)
        folder,_,key,_=_context(db,pid);guard();_publish(folder,key,pid,job,part,data,guard)
        db.execute("UPDATE g07_feature_reel_parts SET state='verified',receipt=? WHERE project_id=? AND job_id=? AND part=?",(_json(receipt),pid,job,part))
        _reopen(folder,key,pid,job,spec,db.execute('SELECT * FROM g07_feature_reel_parts WHERE project_id=? AND job_id=? AND part=?',(pid,job,part)).fetchone(),guard);guard()
        return receipt
    return service._run(pid,render,write=True)



def _saved_job(db,pid,job):
    _hex(job)
    row=_job(db,pid,job)
    if row is None:raise KeyError('Saved reel production missing')
    analysis=_analysis(db,pid,row['analysis_sha256']);spec=json.loads(row['specification'])
    if spec!=_spec(pid,analysis,spec['frames_per_reel']) or _digest(spec)!=job:raise VaultError('Saved production identity changed')
    return row,spec,analysis


def verify_complete(service,pid,job):
    """Reopen every saved reel in order; do not assert status from metadata."""
    if service.access_guard is None:raise PermissionError('Native movie access required')
    def read(db,movie):
        verify_analysis(db,pid,service.access_guard);_schema(db)
        row,spec,analysis=_saved_job(db,pid,job)
        if row['completion'] is None:raise PermissionError('Finish production review first')
        folder,_,key,_=_context(db,pid)
        result=_complete(db,folder,key,pid,job,spec,analysis,service.access_guard)
        if json.loads(row['completion'])!=result:raise VaultError('Saved completion changed')
        return result
    return service._run(pid,read)


def open_verified_reel(service,pid,job,part):
    """One verified derivative only, no browser path or external file export."""
    if service.access_guard is None or type(part) is not int:raise PermissionError('Native movie access required')
    def read(db,movie):
        _schema(db);_,spec,_=_saved_job(db,pid,job);_bounds(spec,part)
        row=db.execute('SELECT * FROM g07_feature_reel_parts WHERE project_id=? AND job_id=? AND part=?',(pid,job,part)).fetchone()
        if row is None or row['state']!='verified':raise KeyError('Reel has not been verified')
        folder,_,key,_=_context(db,pid);return _reopen(folder,key,pid,job,spec,row)[0]
    return service._run(pid,read)


def verify_index(db,folder,pid,key,guard):
    root=folder/'feature-reels';known=set()
    has_jobs=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='g07_feature_reel_jobs'").fetchone()
    if has_jobs:
        if db.execute('SELECT COUNT(*) FROM g07_feature_reel_jobs').fetchone()[0]>MAX_JOBS:raise VaultError('Too many retained productions')
        for row in db.execute('SELECT * FROM g07_feature_reel_jobs'):
            guard();job=row['job_id'];spec=json.loads(row['specification']);analysis=_analysis(db,pid,row['analysis_sha256'])
            if row['project_id']!=pid or spec!=_spec(pid,analysis,spec['frames_per_reel']) or _digest(spec)!=job:raise VaultError('Foreign or changed feature reel job')
            _cursor(db,pid,job,spec)
            for part in _parts(db,pid,job):
                guard();opaque=_token(_name(job,part['part']),key)
                if part['state']=='verified':
                    if opaque in known:raise VaultError('Duplicate protected reel')
                    known.add(opaque)
                    if row['completion'] is None:_reopen(folder,key,pid,job,spec,part,guard)
                else:
                    # A split-commit artifact must not be silently adopted by backup.
                    if root.exists() and (root/opaque).exists():raise VaultError('Interrupted reel needs explicit reconciliation before backup')
            if row['completion'] is not None and json.loads(row['completion'])!=_complete(db,folder,key,pid,job,spec,analysis,guard):raise VaultError('Feature completion changed')
        if db.execute('SELECT 1 FROM g07_feature_reel_parts p LEFT JOIN g07_feature_reel_jobs j ON p.project_id=j.project_id AND p.job_id=j.job_id WHERE j.job_id IS NULL LIMIT 1').fetchone():raise VaultError('Orphan feature reel index')
    if root.exists() or root.is_symlink():
        if not stat.S_ISDIR(_no_link(root).st_mode):raise VaultError('Invalid feature reel storage')
        for entry in root.iterdir():
            guard()
            if entry.name not in known:raise VaultError('Unindexed feature reel storage; explicit reconciliation required')
            known.remove(entry.name)
    if known:raise VaultError('Indexed feature reels missing')
