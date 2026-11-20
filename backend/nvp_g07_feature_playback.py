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
from backend.nvp_g03_payloads import _context, take_sizes
from backend.nvp_g03_pcm_pages import metadata as pcm_metadata
from backend.nvp_g03_windows_vault import VaultError
from backend.nvp_g08_native_avi import _riff_head, WIDTH, HEIGHT
from backend.nvp_g06_filming import HEX

MAX_WINDOW = 12


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


def timeline(service,pid,revision,digest,job):
    def read(db,movie):
        spec,analysis,done=_selected(service,db,pid,revision,digest,job)
        folder,_,key,_=_context(db,pid)
        if reels._complete(db,folder,key,pid,job,spec,analysis,service.access_guard)!=done:
            raise VaultError('Completed picture or sound changed')
        return {'format':'nvp.g07.working_movie_playback.v1','source_sha256':done['completion_sha256'],
                'picture_frames':done['frames'],'audio_samples':done['samples'],'duration_seconds':done['frames']/24,
                'fps':24,'sample_rate':48000,'channels':2,'reels':done['reel_count'],
                'independent_worker_verified':done['independent_worker_verified'],'final_movie_exported':False,
                'physical_gapless_device_acceptance_passed':False}
    return service._run(pid,read)


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


def _window(service,db,pid,revision,digest,job,first,count):
    spec,_,done=_selected(service,db,pid,revision,digest,job)
    if type(first) is not int or type(count) is not int or not 0<=first<spec['total_frames'] or not 1<=count<=MAX_WINDOW+1:
        raise ValueError('Choose a bounded movie window')
    folder,_,key,_=_context(db,pid);current=first;end=min(first+count,spec['total_frames']);pictures=[];pcm=bytearray()
    while current<end:
        service.access_guard();part=current//spec['frames_per_reel'];a,b=reels._bounds(spec,part)
        row=db.execute('SELECT * FROM g07_feature_reel_parts WHERE project_id=? AND job_id=? AND part=?',(pid,job,part)).fetchone()
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


def pictures(service,pid,revision,digest,job,first,count):
    if type(count) is not int or not 1<=count<=MAX_WINDOW:raise ValueError('Choose a bounded picture window')
    def read(db,movie):
        sha,frames,_=_window(service,db,pid,revision,digest,job,first,count)
        return {'source_sha256':sha,'start_frame':first,'frames':[{'frame':first+i,'picture_base64':base64.b64encode(raw).decode('ascii')} for i,raw in enumerate(frames)]}
    return service._run(pid,read)


def sound(service,pid,revision,digest,job,first,count):
    if type(first) is not int or first<0 or type(count) is not int or not 1<=count<=MAX_WINDOW*2000:raise ValueError('Choose a bounded sound window')
    frame,offset=divmod(first,2000)
    def read(db,movie):
        sha,_,pcm=_window(service,db,pid,revision,digest,job,frame,(offset+count+1999)//2000)
        raw=pcm[offset*4:(offset+count)*4]
        if not raw:raise ValueError('Sound outside movie')
        out=io.BytesIO()
        with wave.open(out,'wb') as w:
            w.setnchannels(2);w.setsampwidth(2);w.setframerate(48000);w.writeframes(raw)
        return out.getvalue(),{'X-NVP-Audio-Start-Sample':str(first),'X-NVP-Audio-Samples':str(len(raw)//4),'X-NVP-Source-SHA256':sha}
    return service._run(pid,read)


def inventory(service,pid,family,after=None,limit=32):
    if service.access_guard is None or not service._page_context(pid):raise PermissionError('Protected movie access required')
    if type(limit) is not int or not 1<=limit<=64 or (after is not None and (type(after) is not str or not HEX.fullmatch(after))):raise ValueError('Invalid inventory page')
    def read(db,movie):
        service.editor.filming._schema(db);items=[]
        if family=='takes':
            rows=list(db.execute('SELECT take_id,scene_id,take_sha256,original_usd_sha256,performance_usd_sha256,length(original_usd) AS original_usd_size,length(performance_usd) AS performance_usd_size FROM g06_frozen_takes WHERE project_id=? AND take_id>? ORDER BY take_id LIMIT ?',(pid,after or '',limit+1)))
            for row in rows[:limit]:
                service.access_guard();sizes=take_sizes(db,pid,row['take_id'],row);items.append({'id':row['take_id'],'scene_id':row['scene_id'],'source_bytes':sum(sizes.values())})
        elif family=='recordings':
            rows=list(db.execute('SELECT id,scene_id FROM g06_original_pcm WHERE project_id=? AND id>? ORDER BY id LIMIT ?',(pid,after or '',limit+1)))
            for row in rows[:limit]:
                service.access_guard();m=pcm_metadata(db,service.editor.filming,pid,row['scene_id'],row['id']);items.append({'id':row['id'],'scene_id':row['scene_id'],'source_bytes':m['pcm_bytes'],'sample_count':m['sample_count']})
        else:raise ValueError('Unknown production media family')
        return {'project_id':pid,'family':family,'items':items,'next_after':items[-1]['id'] if len(rows)>limit else None,'media_authenticated':False,'physical_disk_usage':False}
    return service._run(pid,read)
