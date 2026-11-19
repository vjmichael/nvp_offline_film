"""Native bounded working-review reels from the protected paged active edit.

Separate native consent and immutable encrypted output, exact source and
readback hashes. Uses existing G09E renderer, not an independent private
worker, final master or full-feature delivery. No legacy G08 fallback.
"""
import hashlib
import io
import json
import struct
import tempfile
import shutil
import uuid
import re
from pathlib import Path

from PIL import Image
from backend.nvp_g06_filming import _json,_sha
from backend.nvp_g07_paged_media import delivery_plan, native_source_window, window, admit
from backend.nvp_g08_native_avi import TICKS_FRAME,TICKS_SAMPLE,WIDTH,HEIGHT,_riff_head,verify_movie
from backend.nvp_g09e_chunk import render_reel,source_audio_window,_worlds,_pcm_mixer,MAX_CHUNK_BYTES,MAX_TAKES_PER_WINDOW,MAX_FRAMES
from backend.nvp_g09e_audio import plan_gain,finish_window
from backend.nvp_g03_windows_vault import VaultError,_token,_no_link,_encrypt_file,_decrypt_file
from backend.nvp_wo3_atomic_publish import atomic_publish_directory

FORMAT='nvp.g07.protected_review_reel.v1'
HEX=re.compile(r'[a-f0-9]{32}\Z')
MAX_FRAMES_PER_REEL=240


def _digest(obj):return _sha(_json(obj).encode())


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS g07_review_reels(
        project_id TEXT NOT NULL, reel_id TEXT NOT NULL, revision INTEGER NOT NULL,
        active_digest TEXT NOT NULL, review_sha256 TEXT NOT NULL, review_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('rendering','review_required','verified')),
        output_sha256 TEXT, output_bytes INTEGER, receipt_json TEXT,
        PRIMARY KEY(project_id,reel_id))''')


def _decisions(db,service,pid,segments):
    from backend.nvp_g09_environment import G09Environment
    from backend.nvp_g09_actor import G09Actors
    from backend.nvp_g09c_acoustics import G09CAcoustics
    from backend.nvp_g09d_finishing import _schema as finish_schema
    # Whole-film finishing decisions are source-bound and cannot be reused
    # from a different active edit or split into per-reel normalization.
    finish_schema(db)
    head=db.execute('SELECT approved_revision FROM g09d_finish_heads WHERE project_id=?',(pid,)).fetchone()
    if head and head[0]:raise ValueError('Review movie finishing before rendering chapter-based clips')
    maps=[{}, {}, {}];seen=set()
    for seg in segments:
        tid=seg['take_id']
        if tid in seen:continue
        seen.add(tid)
        if len(seen)>MAX_TAKES_PER_WINDOW:raise ValueError('Choose a smaller review clip')
        if service.access_guard:service.access_guard()
        row,take,_=service.editor._take(db,pid,tid,{},metadata_only=True)
        for target,reader in zip(maps,(G09Environment.approved_source,G09Actors.approved_source,G09CAcoustics.approved_source)):
            val=reader(db,pid,tid,row['take_sha256'],take)
            if val is not None:target[tid]=val
    # Existing spatial mixing depends on source context and whole-window
    # tail history. Do not substitute a dry track or restart room tails.
    if maps[2]:raise ValueError('Review clips with approved room sound need the continuous acoustic renderer')
    return maps


def _binding(maps):
    return {key:_digest({tid:{'revision':v['revision'],'sha256':v['sha256']} for tid,v in sorted(m.items())})
        for key,m in zip(('production_looks_sha256','actor_performances_sha256','acoustic_looks_sha256'),maps)}


def _review(service,db,pid,revision,digest,first,count,plan):
    if type(first) is not int or type(count) is not int or not 0<=first<first+count<=min(plan['frame_count'],MAX_FRAMES) or not 1<=count<=MAX_FRAMES_PER_REEL:raise ValueError('Choose up to ten seconds within the current review-render profile')
    start=first*TICKS_FRAME;end=(first+count)*TICKS_FRAME
    doc,segments=window(service,db,pid,revision,digest,start,end)
    budget=admit(service,db,pid,segments)
    maps=_decisions(db,service,pid,segments)
    review={'format':FORMAT,'project_id':pid,'revision':revision,'active_digest':digest,'plan_sha256':plan['plan_sha256'],'ordered_cuts_sha256':doc['ordered_cuts_sha256'],'start_frame':first,'frame_count':count,'duration_tick':str(doc['duration_tick']),'source_window_sha256':_digest(segments),'source_bytes':budget,'decisions':_binding(maps),'working_review_only':True,'final_movie_exported':False}
    return {**review,'review_sha256':_digest(review)},maps


def review(service,pid,revision,digest,first,count):
    if not service._page_context(pid) or service.access_guard is None:raise PermissionError('Unlock the protected movie in NVP desktop')
    plan=delivery_plan(service,pid,revision,digest)
    return service._run(pid,lambda db,movie:_review(service,db,pid,revision,digest,first,count,plan)[0])


def _same(service,db,pid,expected,*,verify_media=False):
    from backend.nvp_g07_paged_media import _scope,_plan_record
    doc,_,_=_scope(service,db,pid,expected['revision'],expected['active_digest'])
    plan=_plan_record(pid,expected['revision'],expected['active_digest'],doc)
    actual,maps=_review(service,db,pid,expected['revision'],expected['active_digest'],expected['start_frame'],expected['frame_count'],plan)
    if actual!=expected:raise PermissionError('Review the changed original cut again')
    if verify_media:
        # Reopen actual bytes in the final authoritative write snapshot, not
        # merely the declared Take identities used for metadata review.
        first=expected['start_frame'];end=first+expected['frame_count']
        _,segments=window(service,db,pid,expected['revision'],expected['active_digest'],first*TICKS_FRAME,end*TICKS_FRAME)
        seen=set()
        for seg in segments:
            tid=seg['take_id']
            if tid in seen:continue
            seen.add(tid);service.access_guard()
            row,_,_=service.editor._take(db,pid,tid,{})
            if row['take_sha256']!=seg['take_sha256']:raise VaultError('Original Take changed before clip commit')
    return maps


def _assembly(service,pid,expected):
    first=expected['start_frame'];end=first+expected['frame_count']
    source=native_source_window(service,pid,expected['revision'],expected['active_digest'],first*TICKS_FRAME,end*TICKS_FRAME,plan_sha256=expected['plan_sha256'])
    if _digest(source['segments'])!=expected['source_window_sha256'] or source['source_payload_budget_bytes']!=expected['source_bytes']:raise VaultError('Original window changed')
    maps=service._run(pid,lambda db,movie:_same(service,db,pid,expected))
    # This is an internal adapter to the *bounded* G09E reel engine. Do not
    # hand it to complete-film G08 because it contains only selected Takes.
    return {**source,'format':'nvp.g07.non_destructive_edit.v1','source_media_modified':False,'edit_revision':expected['revision'],'edit_document_sha256':expected['active_digest'],'production_looks':maps[0],'actor_performances':maps[1],'acoustic_looks':maps[2],**expected['decisions'],'approved_finishing':None,'finishing_sha256':_digest({})}


def inspect(data,frames,*,expected_sha,expected_pcm=None):
    """Independent reader: strict interleaved chunks, actual JPEG decode, PCM
    hash, every idx entry and exact native header. No renderer-provided counts."""
    if type(data) is not bytes or len(data)>MAX_CHUNK_BYTES or _sha(data)!=expected_sha:raise VaultError('Review reel integrity failed')
    base=verify_movie(data,frames,expected_sha=expected_sha)
    header=_riff_head(frames,frames*2000,WIDTH,HEIGHT,WIDTH*HEIGHT*3)
    if data[12:12+len(header)]!=header:raise VaultError('Review reel header changed')
    at=12+len(header)
    if data[at:at+4]!=b'LIST' or data[at+8:at+12]!=b'movi':raise VaultError('Review reel chunks missing')
    end=at+8+struct.unpack_from('<I',data,at+4)[0];origin=at+8;at+=12
    pic=hashlib.sha256();pcm=hashlib.sha256();entries=[]
    for i in range(frames):
        for tag in (b'00dc',b'01wb'):
            if at+8>end or data[at:at+4]!=tag:raise VaultError('Review reel frame order changed')
            size=struct.unpack_from('<I',data,at+4)[0];stop=at+8+size
            if stop>end or stop+(size&1)>end:raise VaultError('Review reel chunk incomplete')
            raw=data[at+8:stop]
            if tag==b'00dc':
                with Image.open(io.BytesIO(raw)) as raster:
                    raster.load();pic.update(raster.convert('RGB').tobytes())
            else:
                if size!=8000:raise VaultError('Review reel audio clock changed')
                pcm.update(raw)
            entries.append(struct.pack('<4sIII',tag,0x10 if tag==b'00dc' else 0,at-origin,size));at=stop+(size&1)
    index=b''.join(entries)
    if at!=end or data[at:]!=b'idx1'+struct.pack('<I',len(index))+index:raise VaultError('Review reel index changed')
    if expected_pcm is not None and pcm.hexdigest()!=expected_pcm:raise VaultError('Rendered sound does not match original edit mix')
    return {**base,'decoded_rgb_sha256':pic.hexdigest(),'pcm_sha256':pcm.hexdigest(),'exact_index_verified':True,'independent_process_verified':False,'whole_movie_exported':False}


def _location(folder,key,ident,*,create=False):
    if not HEX.fullmatch(ident):raise VaultError('Invalid review clip identity')
    _no_link(folder);root=folder/'review-reels'
    if create:root.mkdir(exist_ok=True)
    _no_link(root)
    return root/_token('review-reel/'+ident,key)


def _read(folder,key,pid,row):
    ident=row['reel_id'];receipt=json.loads(row['receipt_json']);expected=json.loads(row['review_json'])
    if (row['state']!='verified' or _digest({k:v for k,v in expected.items() if k!='review_sha256'})!=row['review_sha256'] or expected['review_sha256']!=row['review_sha256'] or expected['project_id']!=pid or expected['revision']!=row['revision'] or expected['active_digest']!=row['active_digest'] or not 0<row['output_bytes']<=MAX_CHUNK_BYTES):raise VaultError('Review clip index changed')
    p=_location(folder,key,ident);_no_link(p);body=p/'body.nvpsealed';_no_link(body)
    sink=io.BytesIO();audit=_decrypt_file(body,sink,key=key,project_id=pid,name='review-reel/'+ident,max_plain_bytes=row['output_bytes'])
    if audit!={'sha256':row['output_sha256'],'size_bytes':row['output_bytes']}:raise VaultError('Protected review clip changed')
    data=sink.getvalue();verified=inspect(data,expected['frame_count'],expected_sha=row['output_sha256'],expected_pcm=receipt['pcm_sha256'])
    if verified!=receipt:raise VaultError('Review clip receipt changed')
    return data,expected,verified


def verify_indexed_reels(db,folder,pid,key,guard):
    for row in db.execute("SELECT * FROM g07_review_reels WHERE state='verified'"):
        guard()
        if row['project_id']!=pid:raise VaultError('Foreign review clip')
        _read(folder,key,pid,row)


def render_approved(service,pid,expected,*,human_approved=False):
    if human_approved is not True or not service._page_context(pid) or service.access_guard is None:raise PermissionError('Separate native review rendering approval required')
    check=service.access_guard;check()
    if review(service,pid,expected['revision'],expected['active_digest'],expected['start_frame'],expected['frame_count'])!=expected:raise PermissionError('Review clip source changed')
    ident=uuid.uuid4().hex
    def intent(db,movie):
        _schema(db);_same(service,db,pid,expected)
        db.execute('INSERT INTO g07_review_reels VALUES(?,?,?,?,?,?,\'rendering\',NULL,NULL,NULL)',(pid,ident,expected['revision'],expected['active_digest'],expected['review_sha256'],_json(expected)))
    service._run(pid,intent,write=True)
    try:
        source=_assembly(service,pid,expected);check()
        first=expected['start_frame'];end=first+expected['frame_count'];sound_plan=plan_gain({'working_review':True,'loudness_measured':False},None)
        dest=io.BytesIO()
        def cancel():check();return False
        render_reel(source,first,end,sound_plan,dest,cancel=cancel)
        data=dest.getvalue();digest=_sha(data)
        # Independently reopen source worlds and recompute exact original edit
        # PCM over the same global frame/sample interval for output audit.
        worlds=_worlds(source);mixer=_pcm_mixer(source,worlds);pcm=hashlib.sha256()
        for frame in range(first,end):
            check();raw=source_audio_window(source,worlds,frame*2000,2000,mixer=mixer)
            pcm.update(finish_window(raw,sound_plan,start_sample=frame*2000,total_samples=source['duration_tick']//TICKS_SAMPLE))
        verified=inspect(data,expected['frame_count'],expected_sha=digest,expected_pcm=pcm.hexdigest())
        check()
        if review(service,pid,expected['revision'],expected['active_digest'],first,end-first)!=expected:raise PermissionError('Review clip source changed during rendering')
        def commit(db,movie):
            _same(service,db,pid,expected,verify_media=True);ctx=service._page_context(pid);folder,key=ctx['folder'],ctx['key'];target=_location(folder,key,ident,create=True)
            row=db.execute('SELECT state,review_sha256 FROM g07_review_reels WHERE project_id=? AND reel_id=?',(pid,ident)).fetchone()
            if row is None or row['state']!='rendering' or row['review_sha256']!=expected['review_sha256']:raise VaultError('Review clip intent changed')
            stage=Path(tempfile.mkdtemp(prefix='.review-reel-',dir=target.parent))
            try:
                _encrypt_file(io.BytesIO(data),stage/'body.nvpsealed',key=key,project_id=pid,name='review-reel/'+ident)
                sink=io.BytesIO();audit=_decrypt_file(stage/'body.nvpsealed',sink,key=key,project_id=pid,name='review-reel/'+ident,max_plain_bytes=len(data))
                if audit!={'sha256':digest,'size_bytes':len(data)} or inspect(sink.getvalue(),expected['frame_count'],expected_sha=digest,expected_pcm=pcm.hexdigest())!=verified:raise VaultError('Protected reel readback changed')
                check();atomic_publish_directory(stage,target)
                db.execute("UPDATE g07_review_reels SET state='verified',output_sha256=?,output_bytes=?,receipt_json=? WHERE project_id=? AND reel_id=?",(digest,len(data),_json(verified),pid,ident))
                _read(folder,key,pid,db.execute('SELECT * FROM g07_review_reels WHERE project_id=? AND reel_id=?',(pid,ident)).fetchone())
                check()
            finally:
                if stage.exists():shutil.rmtree(stage)
        service._run(pid,commit,write=True)
        return {'format':FORMAT,'project_id':pid,'reel_id':ident,'revision':expected['revision'],'start_frame':first,'frame_count':end-first,'verified':True,'protected':True,'whole_movie_exported':False}
    except BaseException:
        try:
            service._run(pid,lambda db,movie:db.execute("UPDATE g07_review_reels SET state='review_required' WHERE project_id=? AND reel_id=? AND state='rendering'",(pid,ident)),write=True)
        except Exception:pass
        raise


def list_reels(service,pid,revision,digest,after=None):
    if not service._page_context(pid):raise PermissionError('Unlock movie')
    if after is not None and (type(after) is not str or not HEX.fullmatch(after)):raise ValueError('Invalid page')
    def read(db,movie):
        from backend.nvp_g07_paged_media import _scope
        _scope(service,db,pid,revision,digest);_schema(db)
        rows=list(db.execute('SELECT reel_id,review_sha256,review_json,state FROM g07_review_reels WHERE project_id=? AND revision=? AND active_digest=? AND reel_id>? ORDER BY reel_id LIMIT 33',(pid,revision,digest,after or '')))
        items=[]
        for r in rows[:32]:
            info=json.loads(r['review_json'])
            if info['project_id']!=pid or info['revision']!=revision or info['active_digest']!=digest or info['review_sha256']!=r['review_sha256'] or _digest({k:v for k,v in info.items() if k!='review_sha256'})!=r['review_sha256']:raise VaultError('Saved clip identity changed')
            items.append({'reel_id':r['reel_id'],'start_frame':info['start_frame'],'frame_count':info['frame_count'],'state':'saved' if r['state']=='verified' else 'needs_review'})
        return {'format':FORMAT,'project_id':pid,'revision':revision,'items':items,'next_after':rows[31]['reel_id'] if len(rows)>32 else None,'whole_movie_exported':False,'reopened':False}
    return service._run(pid,read)


def open_reel(service,pid,ident,revision,digest):
    if type(ident) is not str or not HEX.fullmatch(ident):raise ValueError('Select a review clip')
    def read(db,movie):
        from backend.nvp_g07_paged_media import _scope
        _scope(service,db,pid,revision,digest);_schema(db)
        row=db.execute('SELECT * FROM g07_review_reels WHERE project_id=? AND reel_id=? AND revision=? AND active_digest=?',(pid,ident,revision,digest)).fetchone()
        if row is None or row['state']!='verified':raise KeyError('Verified review clip not found')
        ctx=service._page_context(pid)
        if not ctx:raise PermissionError('Unlock movie')
        return _read(ctx['folder'],ctx['key'],pid,row)[0]
    return service._run(pid,read)
