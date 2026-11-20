"""Bounded, host-scoped media windows for a reviewed G07 section timeline.

The legacy finite exporter cannot consume this contract. It is a source
window for later protected rendering, never an export or creator execution grant.
"""
from backend.nvp_g06_filming import _json, _sha
from backend.nvp_g07_edit import _project, TICKS_PER_SAMPLE
from backend.nvp_g07_paged_active import FORMAT, build
from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T

MAX_WINDOW_CUTS = 64
MAX_MEDIA_BYTES = 128 * 1024 * 1024
MAX_PCM_BYTES = 64 * 1024 * 1024
WINDOW_FORMAT = 'nvp.g07.paged_media_window.v1'
PLAN_FORMAT = 'nvp.g07.paged_delivery_source.v1'


def _scope(service, db, pid, revision, digest):
    from backend.nvp_g07_sections import _schema, _check_sha, _number, _digest
    _schema(db); _number(revision,1,15000); _check_sha(digest)
    current,doc = _project(db,pid,allow_paged=True)
    if current!=revision or doc.get('format')!=FORMAT or _digest(doc)!=digest:
        raise RuntimeError('The active edit changed; reopen it')
    root,sha=service._paged_root(db,pid,current,doc)
    return doc,root,sha


def window(service,db,pid,revision,digest,start,end):
    """Exact half-open global Film Time; visit only intersecting subtrees.

    A page is not a full-tree audit. Every selected leaf is revalidated by
    the original editor. Both sides of every intersecting dissolve survive.
    """
    doc,root,_=_scope(service,db,pid,revision,digest)
    if (type(start) is not int or type(end) is not int or not 0<=start<end<=doc['duration_tick'] or end-start>10*T):
        raise ValueError('Choose up to ten seconds of the current edit')
    out=[]
    def walk(group,base,tick,level):
        if level>3:raise RuntimeError('Invalid section depth')
        index=base
        for child in group['children']:
            a=tick+child['start_tick']; b=tick+child['end_tick']; ref=child['source']
            if a<end and b>start:
                if service.access_guard:service.access_guard()
                if ref['kind']=='section':
                    sub,_=service._verified(db,pid,ref['section_id'],ref['digest'])
                    walk(sub,index,a,level+1)
                else:
                    _,sha,_,segments=service._edit(db,pid,ref['revision'],ref['digest'])
                    origin=segments[ref['first']]['start_tick']
                    for k in range(ref['first'],ref['first']+ref['count']):
                        seg=segments[k];lo=a+seg['start_tick']-origin;hi=a+seg['end_tick']-origin
                        if lo<end and hi>start:
                            if len(out)>=MAX_WINDOW_CUTS:raise ValueError('Choose a smaller preview window')
                            out.append({**seg,'index':index+k-ref['first'],'source_revision':ref['revision'],'source_digest':sha,'start_tick':lo,'end_tick':hi})
            index+=child['clip_count']
    walk(root,0,0,1)
    if not out or out[0]['start_tick']>start or out[-1]['end_tick']<end:
        raise RuntimeError('Original cut coverage is incomplete')
    for a,b in zip(out,out[1:]):
        if b['index']!=a['index']+1 or b['start_tick']!=a['end_tick']-b['transition']['duration_tick']:
            raise RuntimeError('Original cut continuity changed')
    return doc,out


def admit(service,db,pid,segments):
    """Bound original payloads before existing native Take verification."""
    seen=set();budget=0
    for seg in segments:
        tid=seg['take_id']
        if tid in seen:continue
        seen.add(tid)
        row,_,audio=service.editor._take(db,pid,tid,{},metadata_only=True)
        if row['take_sha256']!=seg['take_sha256']:raise RuntimeError('Original Take changed')
        budget+=row['original_usd_size']+row['performance_usd_size']
        for item in audio:
            length=item['sample_count']*2
            if length>MAX_PCM_BYTES:raise ValueError('This long recording needs the incremental sound reader')
            budget+=length
        if budget>MAX_MEDIA_BYTES:raise ValueError('Choose a smaller source preview')
    return budget


def _plan_record(pid,revision,digest,doc):
    from backend.nvp_g08_native_avi import TICKS_FRAME
    receipt={'format':PLAN_FORMAT,'project_id':pid,'revision':revision,'active_digest':digest,'ordered_cuts_sha256':doc['ordered_cuts_sha256'],'duration_tick':str(doc['duration_tick']),'frame_count':doc['duration_tick']//TICKS_FRAME,'clip_count':doc['clip_count'],'window_frames':240,'render_approved':False,'media_verified':False,'final_movie_exported':False}
    return {**receipt,'plan_sha256':_sha(_json(receipt).encode('utf8'))}


def delivery_plan(service,pid,revision,digest):
    """Full ordered metadata and exact clock audit, without media or outputs.

    Not a publisher. Separate native creator consent, media admission,
    finishing and output receipts are still required by the production engine.
    """
    from backend.nvp_g08_native_avi import TICKS_FRAME
    def read(db,movie):
        doc,root,sha=_scope(service,db,pid,revision,digest)
        if build(service,db,pid,root,sha)!=doc:raise RuntimeError('Approved timeline changed')
        # Check the existing frame and sample clocks across every cut, not
        # merely the total (a fractional intermediate cut is not repaired).
        for _,seg in service._walk_cuts(db,pid,root,0,root['clip_count']):
            if service.access_guard:service.access_guard()
            if any(seg[k]%TICKS_FRAME for k in ('start_tick','end_tick','source_in_tick','source_out_tick')) or any(seg[k]%TICKS_PER_SAMPLE for k in ('start_tick','end_tick','source_in_tick','source_out_tick')):
                raise ValueError('Review cut timing before cinema delivery')
        return _plan_record(pid,revision,digest,doc)
    return service._run(pid,read)


def native_source_window(service,pid,revision,digest,start,end,*,plan_sha256):
    """Host-only verified original USD and PCM for one finite output window.

    Explicit distinct contract: do not give it to an old renderer expecting
    a complete film or approved finishing digests. No worker is launched.
    """
    from backend.nvp_g08_native_avi import TICKS_FRAME
    if type(start) is not int or type(end) is not int or start%TICKS_FRAME or end%TICKS_FRAME:
        raise ValueError('Choose whole-frame source windows')
    return service._run(pid,lambda db,movie:_native_source_window(service,db,pid,revision,digest,start,end,plan_sha256=plan_sha256))


def _native_source_window(service,db,pid,revision,digest,start,end,*,plan_sha256):
    """Host-only source read within a caller-owned immutable SQLite snapshot."""
    from backend.nvp_g08_native_avi import TICKS_FRAME
    if type(start) is not int or type(end) is not int or start%TICKS_FRAME or end%TICKS_FRAME:
        raise ValueError('Choose whole-frame source windows')
    doc,segments=window(service,db,pid,revision,digest,start,end)
    from backend.nvp_g07_sections import _check_sha
    if _check_sha(plan_sha256)!=_plan_record(pid,revision,digest,doc)['plan_sha256']:
        raise PermissionError('Review the exact delivery source again')
    budget=admit(service,db,pid,segments);sources={}
    for seg in segments:
        tid=seg['take_id']
        if tid in sources:continue
        if service.access_guard:service.access_guard()
        row,take,audio=service.editor._take(db,pid,tid,{})
        if row['take_sha256']!=seg['take_sha256']:raise RuntimeError('Original Take changed')
        sounds=[]
        for item in audio:
            pcm=service.editor.filming._pcm(db,pid,row['scene_id'],item['clip_id'])
            if pcm is None or _sha(pcm['pcm'])!=item['pcm_sha256'] or pcm['pcm_sha256']!=item['pcm_sha256']:raise RuntimeError('Original sound changed')
            sounds.append({**item,'pcm16le':bytes(pcm['pcm'])})
        sources[tid]={'scene_id':row['scene_id'],'take_sha256':row['take_sha256'],'original_usd':bytes(row['original_usd']),'performance_usd':bytes(row['performance_usd']),'original_sha256':row['original_usd_sha256'],'performance_sha256':row['performance_usd_sha256'],'duration_tick':take['duration_tick'],'stage_objects':take['stage_objects'],'stage_setting':take['stage_setting'],'events':take['events'],'audio':sounds}
    return {'format':WINDOW_FORMAT,'project_id':pid,'revision':revision,'active_digest':digest,'ordered_cuts_sha256':doc['ordered_cuts_sha256'],'plan_sha256':plan_sha256,'window':[start,end],'duration_tick':doc['duration_tick'],'segments':segments,'original_takes':sources,'source_payload_budget_bytes':budget,'master_gain':doc['master_gain'],'render_approved':False,'final_movie_exported':False}
