"""Read-only protected working-movie playback and bounded media inventory.
No filesystem names, keys, new grants or plaintext files leave the host.
Completion is checked in full at timeline open; each subsequent read reopens
its sealed reel, checks the exact byte digest, and extracts the paired clock.
"""
import base64
import hashlib
import io
import json
import struct
import wave
from backend import nvp_g07_feature_reels as reels
from backend.nvp_g03_payloads import _context, _has_table, take_sizes
from backend.nvp_g03_pcm_pages import inventory_metadata as pcm_inventory_metadata
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g08_native_avi import _riff_head, WIDTH, HEIGHT
from backend.nvp_g06_filming import HEX
from backend import nvp_g07_playback_projection as projection

MAX_WINDOW = 12
MAX_PAIRED_BYTES = 8 * 1024 * 1024


def _selected(service,db,pid,revision,digest,job):
    if service.access_guard is None or not service._page_context(pid):
        raise PermissionError('Protected movie access required')
    service.access_guard(); reels._schema(db)
    row,spec,analysis=reels._saved_job(db,pid,job)
    if (analysis['review']['revision']!=revision or analysis['review']['active_digest']!=digest or row['completion'] is None):
        raise PermissionError('Select the completed current working movie')
    reels._current(service,db,pid,analysis)
    done=json.loads(row['completion']);body=dict(done);sha=body.pop('completion_sha256',None)
    if (reels._digest(body)!=sha or done['job_id']!=job or done['project_id']!=pid or done['analysis_sha256']!=analysis['receipt_sha256'] or done['frames']!=spec['total_frames'] or done['samples']!=spec['total_frames']*2000 or done['pcm_sha256']!=analysis['derived_pcm_sha256'] or done['working_reels_complete'] is not True or done['final_movie_exported'] is not False):
        raise VaultError('Completed movie binding changed')
    count,pending,complete=reels._cursor(db,pid,job,spec)
    chain=hashlib.sha256()
    for part in reels._parts(db,pid,job):
        service.access_guard();chain.update(bytes.fromhex(reels._digest(json.loads(part['receipt']))))
    if not complete or pending is not None or count!=done['reel_count'] or chain.hexdigest()!=done['ordered_receipts_sha256']:
        raise VaultError('Completed reel sequence changed')
    return spec,analysis,done


def _projection(service,db,pid,revision,digest,job):
    folder,_,_,head=_context(db,pid)
    deps=projection.Dependencies(folder,pid)
    spec,analysis,done=deps.collect(lambda:_selected(service,db,pid,revision,digest,job))
    parts=[];size=4*(len(reels._json(spec).encode())+len(reels._json(done).encode()))
    # Account for Python object overhead as well as encoded receipt bytes.
    size+=4096+sum(len(k)*4+256 for k in deps.files)
    cached=None
    if deps.valid and size<=projection.MAX_PROJECTED_BYTES:
        for row in reels._parts(db,pid,job):
            service.access_guard();raw=row['receipt'];size+=len(raw)*4+128
            if size>projection.MAX_PROJECTED_BYTES:break
            parts.append(raw)
        if size<=projection.MAX_PROJECTED_BYTES and len(parts)==done['reel_count']:
            token=service.editor.filming.g05.g04.token
            cached=projection.Projection((pid,token,revision,digest,job),head,spec,done,parts,deps,size)
    return spec,analysis,done,cached


def _host(service,pid):
    host=service.editor.filming.g05.g04
    if service.access_guard is None or host.live is None:
        raise PermissionError('Protected movie access required')
    return host.live,host.token


def _read_window(service,pid,revision,digest,job,first,count):
    store,token=_host(service,pid);folder=store._folder(pid)
    scope=(pid,token,revision,digest,job)
    # Same lock and authorization as the original protected read. The cache
    # spans request-local EditorialSections instances, never director grants.
    with store._guard:
        def guard():
            service.access_guard();store._session(pid,token)
        try:
            guard();key=store._session(pid,token)
            cached=store._playback_projection
            if cached is not None and cached.scope==scope and cached.head==store._head(folder):
                cached.verify(store,folder,guard)
                result=_extract(service,folder,key,pid,job,cached.spec,cached.done,cached.row,first,count)
                if store._head(folder)!=cached.head:raise VaultError('Movie snapshot changed during playback')
            else:
                store._playback_projection=None
                def read(db,movie):
                    spec,_,done,verified=_projection(service,db,pid,revision,digest,job)
                    folder,_,key,head=_context(db,pid)
                    def row(part):return db.execute('SELECT * FROM g07_feature_reel_parts WHERE project_id=? AND job_id=? AND part=?',(pid,job,part)).fetchone()
                    result=_extract(service,folder,key,pid,job,spec,done,row,first,count)
                    if store._head(folder)!=head:raise VaultError('Movie snapshot changed during playback')
                    store._playback_projection=verified
                    return result
                result=service._run(pid,read)
            guard()
            return result
        except Exception:
            store._playback_projection=None
            raise


def timeline(service,pid,revision,digest,job):
    def read(db,movie):
        spec,analysis,done,cached=_projection(service,db,pid,revision,digest,job)
        folder,_,key,head=_context(db,pid)
        if reels._complete(db,folder,key,pid,job,spec,analysis,service.access_guard)!=done:
            raise VaultError('Completed picture or sound changed')
        if store._head(folder)!=head:raise VaultError('Movie snapshot changed during playback')
        service.access_guard();store._playback_projection=cached
        return {'format':'nvp.g07.working_movie_playback.v1','source_sha256':done['completion_sha256'],
                'picture_frames':done['frames'],'audio_samples':done['samples'],'duration_seconds':done['frames']/24,
                'fps':24,'sample_rate':48000,'channels':2,'reels':done['reel_count'],
                'independent_worker_verified':done['independent_worker_verified'],'final_movie_exported':False,
                'physical_gapless_device_acceptance_passed':False,
                'paired_windows':True}
    store,token=_host(service,pid)
    with store._guard:
        store._playback_projection=None
        try:return service._run(pid,read)
        except Exception:
            store._playback_projection=None
            raise


def _pairs(data,frames,first,end):
    # Exact sealed bytes already independently decoded during production and
    # matched to the immutable receipt before this bounded extraction.
    at=12+len(_riff_head(frames,frames*2000,WIDTH,HEIGHT,WIDTH*HEIGHT*3))+12
    for i in range(end):
        pair=[]
        for tag in (b'00dc',b'01wb'):
            if data[at:at+4]!=tag:raise VaultError('Reel stream order changed')
            size=struct.unpack_from('<I',data,at+4)[0];stop=at+8+size
            if stop>len(data) or (tag==b'01wb' and size!=8000):raise VaultError('Reel packet changed')
            if i>=first:pair.append(data[at+8:stop])
            at=stop+(size&1)
        if i>=first:yield pair


def _extract(service,folder,key,pid,job,spec,done,get_row,first,count):
    if type(first) is not int or type(count) is not int or not 0<=first<spec['total_frames'] or not 1<=count<=MAX_WINDOW+1:
        raise ValueError('Choose a bounded movie window')
    current=first;end=min(first+count,spec['total_frames']);pictures=[];pcm=bytearray()
    while current<end:
        service.access_guard();part=current//spec['frames_per_reel'];a,b=reels._bounds(spec,part)
        row=get_row(part)
        if row is None or row['state']!='verified':raise VaultError('Verified reel missing')
        # At most one bounded plaintext reel at a time. Do not decode all
        # RGB frames on every half-second request; authenticated exact bytes
        # bind the previously independently verified picture/audio receipt.
        receipt=json.loads(row['receipt']);media=receipt['media'];size=media['bytes']
        if type(size) is not int or not 0<size<=reels.MAX_CHUNK_BYTES or receipt!=reels._part_receipt(job,part,a,b,media,receipt.get('native_execution')):
            raise VaultError('Reel receipt changed')
        data,audit=reels._read_body(folder,key,pid,job,part,size)
        if audit!={'sha256':media['sha256'],'size_bytes':size} or hashlib.sha256(data).hexdigest()!=media['sha256']:
            raise VaultError('Protected reel changed')
        for jpg,sound in _pairs(data,b-a,current-a,min(end,b)-a):
            service.access_guard();pictures.append(jpg);pcm.extend(sound);current+=1
        del data
    return done['completion_sha256'],pictures,bytes(pcm)


def _response_guard(service,pid):
    store,token=_host(service,pid)
    with store._guard:
        try:
            service.access_guard();store._session(pid,token)
        except Exception:
            store._playback_projection=None
            raise


def pictures(service,pid,revision,digest,job,first,count):
    if type(count) is not int or not 1<=count<=MAX_WINDOW:raise ValueError('Choose a bounded picture window')
    sha,frames,_=_read_window(service,pid,revision,digest,job,first,count)
    result={'source_sha256':sha,'start_frame':first,'frames':[{'frame':first+i,'picture_base64':base64.b64encode(raw).decode('ascii')} for i,raw in enumerate(frames)]}
    _response_guard(service,pid)
    return result


def _wav(raw):
    out=io.BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000);w.writeframes(raw)
    return out.getvalue()


def sound(service,pid,revision,digest,job,first,count):
    if type(first) is not int or first<0 or type(count) is not int or not 1<=count<=MAX_WINDOW*2000:raise ValueError('Choose a bounded sound window')
    frame,offset=divmod(first,2000)
    sha,_,pcm=_read_window(service,pid,revision,digest,job,frame,(offset+count+1999)//2000)
    raw=pcm[offset*4:(offset+count)*4]
    if not raw:raise ValueError('Sound outside movie')
    wav=_wav(raw);_response_guard(service,pid)
    return wav,{'X-NVP-Audio-Start-Sample':str(first),'X-NVP-Audio-Samples':str(len(raw)//4),'X-NVP-Source-SHA256':sha}


def paired(service,pid,revision,digest,job,first,count):
    """One authenticated snapshot and one decryption per touched reel.

    The caller chooses a bounded sample range; its first sample may be
    unaligned. Only bounded authenticated metadata survives requests, not
    decrypted media or authorization. Independent picture/audio routes remain.
    """
    if type(first) is not int or first<0 or type(count) is not int or not 1<=count<=MAX_WINDOW*2000:raise ValueError('Choose a bounded playback window')
    frame,offset=divmod(first,2000)
    blocks=(offset+count+1999)//2000
    if blocks>MAX_WINDOW:raise ValueError('Choose a playback window within twelve frames')
    sha,frames,pcm=_read_window(service,pid,revision,digest,job,frame,blocks)
    raw=pcm[offset*4:(offset+count)*4]
    if not raw:raise ValueError('Sound outside movie')
    if sum(map(len,frames))+len(raw)>MAX_PAIRED_BYTES:raise ValueError('Playback window exceeds its media budget')
    result={'source_sha256':sha,'start_frame':frame,'start_sample':first,
            'sample_count':len(raw)//4,'audio_base64':base64.b64encode(_wav(raw)).decode('ascii'),
            'frames':[{'frame':frame+i,'picture_base64':base64.b64encode(jpg).decode('ascii')} for i,jpg in enumerate(frames)]}
    _response_guard(service,pid)
    return result


def inventory(service,pid,family,after=None,limit=32):
    if service.access_guard is None or not service._page_context(pid):raise PermissionError('Protected movie access required')
    if type(limit) is not int or not 1<=limit<=64 or (after is not None and (type(after) is not str or not HEX.fullmatch(after))):raise ValueError('Invalid inventory page')
    if family not in ('takes','recordings'):raise ValueError('Unknown production media family')
    def read_page(db,cursor):
        items=[]
        if family=='takes':
            rows=list(db.execute('SELECT take_id,scene_id,take_sha256,original_usd_sha256,performance_usd_sha256,length(original_usd) AS original_usd_size,length(performance_usd) AS performance_usd_size FROM g06_frozen_takes WHERE project_id=? AND take_id>? ORDER BY take_id LIMIT ?',(pid,cursor or '',limit+1)))
            selected=rows[:limit]; pointers={}
            if selected and _has_table(db,'g03_r5_take_payloads'):
                marks=','.join('?' for _ in selected)
                for pointer in db.execute(f'SELECT take_id,kind,sha256,size_bytes FROM g03_r5_take_payloads WHERE project_id=? AND take_id IN ({marks})',(pid,*(row['take_id'] for row in selected))):
                    pointers[(pointer['take_id'],pointer['kind'])]=pointer
            for row in selected:
                service.access_guard();sizes=take_sizes(db,pid,row['take_id'],row,pointers=pointers);items.append({'id':row['take_id'],'scene_id':row['scene_id'],'source_bytes':sum(sizes.values())})
            more=len(rows)>limit
        elif family=='recordings':
            rows,more=pcm_inventory_metadata(db,service.editor.filming,pid,cursor or '',limit,service.access_guard)
            items=[{'id':row['id'],'scene_id':row['scene_id'],'source_bytes':row['pcm_bytes'],'sample_count':row['sample_count']} for row in rows]
        else:raise ValueError('Unknown production media family')
        return {'project_id':pid,'family':family,'items':items,'next_after':items[-1]['id'] if more else None,'media_authenticated':False,'physical_disk_usage':False}
    store,token=_host(service,pid);folder=store._folder(pid);scope=(pid,token,family,limit)
    with store._guard:
        def guard():
            service.access_guard();store._session(pid,token)
        try:
            guard()
            cached=store._inventory_projection
            if (cached is not None and cached['scope']==scope and after in cached['pages'] and
                    cached['head']==store._head(folder)):
                projection.verify_snapshot(store,folder,cached['head'],guard)
                # Return new decoded values, never mutable references to the index.
                return json.loads(cached['pages'][after])
            store._inventory_projection=None
            def read(db,movie):
                service.editor.filming._schema(db)
                _,_,_,head=_context(db,pid)
                result=read_page(db,after);pages={};size=0;cursor=after;page=result
                for i in range(projection.INVENTORY_PAGES):
                    guard();raw=reels._json(page);size+=len(raw)*4+512
                    if size>projection.MAX_INVENTORY_BYTES:break
                    pages[cursor]=raw
                    cursor=page['next_after']
                    if cursor is None or i+1>=projection.INVENTORY_PAGES:break
                    # Do not let invalid unrelated prefetched rows prevent
                    # delivery of the page actually requested. They will be
                    # validated (and denied) when that page is requested.
                    try:page=read_page(db,cursor)
                    except VaultError:break
                if store._head(folder)!=head:raise VaultError('Movie snapshot changed during inventory retrieval')
                guard()
                if pages:store._inventory_projection={'scope':scope,'head':dict(head),'pages':pages,'bytes_used':sum(len(x)*4+512 for x in pages.values())}
                return result
            return service._run(pid,read)
        except Exception:
            store._inventory_projection=None
            raise
