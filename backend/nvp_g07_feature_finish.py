"""Protected paged-film sound finishing preparation (not a final exporter).

Uses the existing G09D creator decision and G09E continuous filter/gain
implementation. Two passes reopen exact original media inside one protected
snapshot. An authenticated receipt records measured source and derived PCM
hashes, not a saved soundtrack, worker acceptance, or cinema compliance.
Room-tail/acoustic finishing remains fail-closed until the continuous renderer.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3

from backend.nvp_g06_filming import _json,_sha
from backend.nvp_g07_paged_active import FORMAT as PAGED,build,MAX_IDENTITY_BYTES
from backend.nvp_g07_paged_media import _scope,_plan_record,_native_source_window
from backend.nvp_g08_native_avi import TICKS_FRAME,TICKS_SAMPLE,_audio_frame
from backend.nvp_g09e_chunk import FRAMES_PER_CHUNK,MAX_FRAMES
from backend.nvp_g09e_audio import FilmMeter,plan_gain,finish_window,RATE
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g03_payloads import _context

FORMAT='nvp.g07.protected_feature_finish_analysis.v1'


def _digest(v):return _sha(_json(v).encode('utf8'))


def _stream_digest(rows,*,mapping=False):
    """Same canonical JSON identity as the finite G09D binding, no full map."""
    h=hashlib.sha256();h.update(b'{' if mapping else b'[');first=True
    for key,value in rows:
        if not first:h.update(b',')
        first=False
        raw=(_json(key)+':'+_json(value)) if mapping else _json([key,value])
        h.update(raw.encode('utf8'))
    h.update(b'}' if mapping else b']')
    return h.hexdigest()


def binding(db,pid,editor,version,doc,*,guard=None):
    """Complete ordered paged edit and existing per-Take approved decisions."""
    if doc.get('format')!=PAGED or editor.filming.g05.g04.live is None:
        raise ValueError('Protected chapter timeline required')
    from backend.nvp_g07_sections import EditorialSections,_schema
    from backend.nvp_g09_environment import G09Environment
    from backend.nvp_g09_actor import G09Actors
    from backend.nvp_g09c_acoustics import G09CAcoustics
    service=EditorialSections(editor,access_guard=guard or (lambda:_context(db,pid)));_schema(db)
    root,sha=service._paged_root(db,pid,version,doc)
    if build(service,db,pid,root,sha)!=doc:raise VaultError('Original arrangement changed')
    seen=sqlite3.connect(':memory:')
    try:
        seen.execute('PRAGMA temp_store=MEMORY');seen.execute('PRAGMA page_size=4096');seen.execute(f'PRAGMA max_page_count={MAX_IDENTITY_BYTES//4096}')
        seen.execute('CREATE TABLE refs(tid TEXT PRIMARY KEY,sha TEXT,look TEXT,actor TEXT,acoustic TEXT) WITHOUT ROWID')
        for _,seg in service._walk_cuts(db,pid,root,0,root['clip_count']):
            service.access_guard();tid=seg['take_id']
            if any(seg[k]%TICKS_FRAME or seg[k]%TICKS_SAMPLE for k in ('start_tick','end_tick','source_in_tick','source_out_tick')):raise ValueError('Review whole-frame finishing timing')
            old=seen.execute('SELECT sha FROM refs WHERE tid=?',(tid,)).fetchone()
            if old is not None:
                if old[0]!=seg['take_sha256']:raise VaultError('Original Take identity differs')
                continue
            row,original,_=editor._take(db,pid,tid,{},metadata_only=True)
            if row['take_sha256']!=seg['take_sha256']:raise VaultError('Original Take changed')
            values=[]
            for reader in (G09Environment.approved_source,G09Actors.approved_source,G09CAcoustics.approved_source):
                result=reader(db,pid,tid,row['take_sha256'],original)
                values.append(None if result is None else _json({'revision':result['revision'],'sha256':result['sha256']}))
            try:seen.execute('INSERT INTO refs VALUES(?,?,?,?,?)',(tid,row['take_sha256'],*values))
            except sqlite3.OperationalError as exc:raise ValueError('Finishing identity index exceeds its bounded budget') from exc
        return {'edit_revision':version,'edit_sha256':_digest(doc),
            'production_looks_sha256':_stream_digest(((tid,json.loads(v)) for tid,v in seen.execute('SELECT tid,look FROM refs WHERE look IS NOT NULL ORDER BY tid')),mapping=True),
            'actor_performances_sha256':_stream_digest(((tid,json.loads(v)) for tid,v in seen.execute('SELECT tid,actor FROM refs WHERE actor IS NOT NULL ORDER BY tid')),mapping=True),
            'acoustic_looks_sha256':_stream_digest(((tid,json.loads(v)) for tid,v in seen.execute('SELECT tid,acoustic FROM refs WHERE acoustic IS NOT NULL ORDER BY tid')),mapping=True),
            'original_takes_sha256':_stream_digest(seen.execute('SELECT tid,sha FROM refs ORDER BY tid'))}
    finally:seen.close()


def _review(service,db,pid,revision,digest):
    if service.access_guard is None:raise PermissionError('Open protected movie in the native host')
    service.access_guard();_,_,_,head=_context(db,pid)
    doc,_,_=_scope(service,db,pid,revision,digest);plan=_plan_record(pid,revision,digest,doc)
    if not 1<=plan['frame_count']<=MAX_FRAMES or plan['frame_count']*TICKS_FRAME!=doc['duration_tick']:raise ValueError('Finishing exceeds the current three-hour native profile')
    from backend.nvp_g09d_finishing import G09DFinishing,_head
    source=binding(db,pid,service.editor,revision,doc,guard=service.access_guard)
    approved=G09DFinishing.approved_source(db,pid,source)
    if approved is None or _head(db,pid)!=(approved['revision'],approved['revision']):raise PermissionError('Review and approve the current movie finishing first')
    if source['acoustic_looks_sha256']!=_digest({}):raise ValueError('Continuous approved room sound is not supported by this finishing operation')
    record={'format':FORMAT,'project_id':pid,'revision':revision,'active_digest':digest,'snapshot':head,'plan_sha256':plan['plan_sha256'],'frame_count':plan['frame_count'],'source':source,'finishing_revision':approved['revision'],'finishing_sha256':approved['sha256'],'render_approved':False,'final_movie_exported':False}
    return {**record,'review_sha256':_digest(record)},approved


def review(service,pid,revision,digest):
    return service._run(pid,lambda db,movie:_review(service,db,pid,revision,digest)[0])


def _pcm(service,db,pid,reviewed):
    total=reviewed['frame_count'];next_sample=0
    for start in range(0,total,FRAMES_PER_CHUNK):
        service.access_guard();end=min(start+FRAMES_PER_CHUNK,total)
        window=_native_source_window(service,db,pid,reviewed['revision'],reviewed['active_digest'],start*TICKS_FRAME,end*TICKS_FRAME,plan_sha256=reviewed['plan_sha256'])
        if window['window']!=[start*TICKS_FRAME,end*TICKS_FRAME]:raise VaultError('Original source window changed')
        # Source PCM is evaluated at global sample positions. Includes both
        # sides of intersecting dissolves; one-second blocks do not reset DSP.
        begin=start*2000;stop=end*2000
        for at in range(begin,stop,RATE):
            service.access_guard();n=min(RATE,stop-at)
            data=_audio_frame(window,window['original_takes'],at,n)
            if len(data)!=n*4 or at!=next_sample:raise VaultError('Protected whole-film sound clock changed')
            next_sample+=n
            yield at,data
        del window
    if next_sample!=total*2000:raise VaultError('Incomplete protected film sound')


def analyze_approved(service,pid,expected,*,human_approved=False):
    """Native host only. Real two-pass PCM evaluation; no final bytes published.

    A future worker must independently reproduce the source and mastering
    receipts. No per-reel gain, no automated signing or continuation.
    """
    if human_approved is not True:raise PermissionError('Native finishing analysis approval required')
    if type(expected) is not dict or expected.get('project_id')!=pid:raise PermissionError('Review exact movie finishing')
    def analyze(db,movie):
        actual,approved=_review(service,db,pid,expected['revision'],expected['active_digest'])
        if actual!=expected:raise PermissionError('Finishing review changed')
        samples=actual['frame_count']*2000;source=FilmMeter(duration_samples=samples);h=hashlib.sha256()
        for _,raw in _pcm(service,db,pid,actual):source.feed(raw);h.update(raw)
        measured=source.finish();plan=plan_gain(measured,approved)
        check=hashlib.sha256();derived=hashlib.sha256();out=FilmMeter(duration_samples=samples)
        for at,raw in _pcm(service,db,pid,actual):
            check.update(raw);finished=finish_window(raw,plan,start_sample=at,total_samples=samples);derived.update(finished);out.feed(finished)
        if h.digest()!=check.digest():raise VaultError('Original sound changed between finishing passes')
        receipt={'format':FORMAT,'review':actual,'source_pcm_sha256':h.hexdigest(),'derived_pcm_sha256':derived.hexdigest(),'sample_count':samples,'source_measurement':measured,'gain_plan':plan,'derived_measurement':out.finish(),'derived_bytes_saved':False,'worker_verified':False,'render_approved':False,'final_movie_exported':False}
        return {**receipt,'receipt_sha256':_digest(receipt)}
    receipt=service._run(pid,analyze)
    # Revalidate the same full authority and immutable snapshot at publication.
    def record(db,movie):
        actual,_=_review(service,db,pid,expected['revision'],expected['active_digest'])
        if actual!=expected:raise PermissionError('Movie changed during finishing analysis')
        db.execute('''CREATE TABLE IF NOT EXISTS g07_feature_finish_analysis(
            project_id TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,receipt_json TEXT NOT NULL,
            PRIMARY KEY(project_id,receipt_sha256))''')
        db.execute('INSERT INTO g07_feature_finish_analysis VALUES(?,?,?)',(pid,receipt['receipt_sha256'],_json(receipt)))
        return receipt
    return service._run(pid,record,write=True)


def verify_index(db,pid,guard):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='g07_feature_finish_analysis'").fetchone():return
    for row in db.execute('SELECT project_id,receipt_sha256,receipt_json FROM g07_feature_finish_analysis'):
        guard();data=json.loads(row['receipt_json']);digest=data.pop('receipt_sha256',None)
        if (row['project_id']!=pid or digest!=row['receipt_sha256'] or _digest(data)!=digest or data['review']['project_id']!=pid or data['derived_bytes_saved'] is not False or data['final_movie_exported'] is not False):raise VaultError('Protected finishing analysis receipt changed')
        reviewed=data['review'];scope=dict(reviewed);review_digest=scope.pop('review_sha256',None)
        if scope.get('format')!=FORMAT or _digest(scope)!=review_digest or data['sample_count']!=reviewed['frame_count']*2000 or data['worker_verified'] is not False or data['render_approved'] is not False:raise VaultError('Protected finishing scope changed')
        if not db.execute('SELECT 1 FROM g07_edit_versions WHERE project_id=? AND revision=? AND document_sha256=?',(pid,reviewed['revision'],reviewed['active_digest'])).fetchone():raise VaultError('Finishing analysis edit missing')
        if not db.execute('SELECT 1 FROM g09d_finish_versions WHERE project_id=? AND revision=? AND document_sha256=?',(pid,reviewed['finishing_revision'],reviewed['finishing_sha256'])).fetchone():raise VaultError('Finishing analysis decision missing')
        folder,_,_,_=_context(db,pid)
        snap=reviewed['snapshot'];seq=snap['sequence']
        from backend.nvp_g03_windows_vault import _no_link
        if type(seq) is not int or seq<0 or snap['name']!=f'db.{seq:012d}.nvpsealed':raise VaultError('Invalid finishing snapshot identity')
        path=folder/'revisions'/snap['name'];_no_link(path)
        h=hashlib.sha256()
        with path.open('rb') as source:
            while block:=source.read(512*1024):guard();h.update(block)
        if h.hexdigest()!=snap['sha256']:raise VaultError('Finishing analysis snapshot changed')


def current_analysis(service,pid,revision,digest):
    """Discover a saved, authenticated analysis for the exact current edit.

    Snapshot/index revisions advance when saving results; creative bindings do
    not. Prefer the existing first matching analysis to retain its reel cursor.
    No client-supplied receipt or implicit approval is accepted.
    """
    def read(db,movie):
        fresh,_=_review(service,db,pid,revision,digest)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='g07_feature_finish_analysis'").fetchone():return fresh,None
        verify_index(db,pid,service.access_guard)
        def scope(review):return {k:v for k,v in review.items() if k not in ('snapshot','review_sha256')}
        for row in db.execute('SELECT receipt_sha256,receipt_json FROM g07_feature_finish_analysis WHERE project_id=? ORDER BY rowid',(pid,)):
            service.access_guard();record=json.loads(row['receipt_json'])
            if scope(record['review'])==scope(fresh):return fresh,row['receipt_sha256']
        return fresh,None
    return service._run(pid,read)
