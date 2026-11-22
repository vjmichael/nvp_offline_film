"""CI-only installed Windows worker acceptance on generated disposable sources."""
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading


def seed_feature(editor,pid,count=4):
    """Generated fixture only, not an alternate creator approval path."""
    if type(count) is not int or not 2<=count<=32:raise ValueError('Bounded fixture')
    from backend.nvp_g07_edit import _blank,_default_grade,RATE
    from backend.nvp_g06_filming import _json,_sha,TAKE_FORMAT
    from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
    from backend.nvp_g07_sections import EditorialSections
    from backend.nvp_g09d_finishing import G09DFinishing,DEFAULT_AUDIO
    host=editor.filming.g05.g04;studio=host.studio;store=host.live;token=host.token
    guard=lambda:store._session(pid,token)
    def seed(db,movie):
        doc=_blank();doc['title']='Generated native movie';scene='SC_abcdef012345'
        for n in range(1,count+1):
            tid=f'{n:032x}';cid=f'{9000+n:032x}';pcm=struct.pack('<h',((n*2000+32768)%65536)-32768)*(2*RATE);pcm_sha=_sha(pcm)
            db.execute('INSERT INTO g06_original_pcm VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cid,pid,scene,'actor_fixture','native_microphone_pcm16le',pcm,pcm_sha,RATE,1,2*RATE,'2026-11-19'))
            source=(f'#usda 1.0\n( defaultPrim = "World" )\ndef Xform "World" {{\n def Scope "Objects" {{\n  def Xform "Actor" {{\n   double3 xformOp:translate = ({n}, 0, 0)\n   uniform token[] xformOpOrder = ["xformOp:translate"]\n  }}\n }}\n}}\n').encode();sha=_sha(source)
            audio=[{'clip_id':cid,'actor_id':'actor_fixture','pcm_sha256':pcm_sha,'sample_count':2*RATE,'start_tick':0,'duration_tick':2*T,'emitter_position':[0,0,0]}]
            manifest={'format':TAKE_FORMAT,'scene_id':scene,'duration_tick':2*T,'original_usd_sha256':sha,'performance_usd_sha256':sha,'audio':audio,'events':[],'stage_setting':{},'stage_objects':[{'id':'Actor','name':'Actor','role':'actor','actor_id':'actor_fixture','shape':'box','rotation':[0,0,0],'scale':[1,1,1],'color':'#aaaaaa'}]}
            raw=_json(manifest);digest=_sha(raw.encode());db.execute('INSERT INTO g06_frozen_takes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(tid,pid,scene,1,sha,sha,source,sha,source,raw,_json(audio),digest,'2026-11-19'))
            doc['clips'].append({'id':f'{100000+n:032x}','take_id':tid,'take_sha256':digest,'source_in_tick':0,'source_out_tick':2*T,'camera':{'name':'Wide','position':[-4.,-4.,2.],'look_at':[2.,0.,0.],'focal_mm':50},'grade':_default_grade(),'audio':[{'clip_id':cid,'enabled':True,'gain':1.,'pan':-1.,'spatial':False,'offset_tick':0}],'transition':{'kind':'dissolve','duration_tick':T//2} if n==2 else {'kind':'cut','duration_tick':0},'note':''})
        editor._validate(db,pid,doc);editor._save(db,pid,doc,0,0)
    editor._execute(pid,seed,mutate=True);service=EditorialSections(editor,access_guard=guard)
    entry=service.directory(pid,'edits')['items'][0];refs=[{'kind':'edit','revision':entry['revision'],'digest':entry['digest'],'first':0,'count':count}]
    proposed=service.preview(pid,'Generated feature',refs);root_doc=service.publish(pid,'Generated feature',refs,proposed['digest'])['selection'];args=(pid,root_doc['section_id'],root_doc['digest'],1);activate=service.preview_paged(*args);service.activate_paged(*args,activate['approval_digest'])
    finishing=G09DFinishing(studio,live=store,token=token);decision=finishing.change(pid,0,'audio',{**DEFAULT_AUDIO,'fade_in_seconds':.25,'fade_out_seconds':.5});finishing.approve(pid,decision['revision'])
    return service


def run(checkpoint):
    if sys.platform!='win32' or not getattr(sys,'frozen',False) or os.environ.get('GITHUB_ACTIONS')!='true':
        raise PermissionError('Installed synthetic CI worker qualification only')
    from backend.nvp_g03_live_store import LiveFilmStore
    from backend.nvp_studio import Studio
    from backend.nvp_g07_edit import G07Editor
    from backend.nvp_g07_feature_finish import review,analyze_approved
    from backend import nvp_g07_feature_reels as reels
    with tempfile.TemporaryDirectory(prefix='nvp-r7-public-ci-') as tmp:
        root=Path(tmp);studio=Studio(root/'studio.sqlite3');pid=studio.create_project('Generated acceptance movie','','')['id'];store=LiveFilmStore(root/'sealed')
        secret='PERF03G disposable public test passphrase';token='ci-generated-feature-fixture-'+'x'*32
        store.create(pid,'Generated acceptance movie','','',secret);store.authorize(pid,secret,token)
        editor=G07Editor(studio,live=store,token=token)
        service=seed_feature(editor,pid)
        revision=editor.view(pid);analysis=analyze_approved(service,pid,review(service,pid,revision['revision'],revision['active_digest']),human_approved=True)
        def next():return reels.review_native_next(service,pid,analysis['receipt_sha256'],frames_per_reel=90)
        event=threading.Event();first=next();checkpoint('perf03g_native_fixture_prepared')
        try:
            reels.execute_native_approved(service,pid,first,human_approved=True,cancel=event.is_set,worker_started=event.set)
        except InterruptedError as exc:
            from backend.nvp_g07_feature_native import NativeReelInterrupted
            if not event.is_set() or type(exc) is not NativeReelInterrupted or not exc.active_worker_stopped:raise RuntimeError('Active worker termination was not verified')
        else:raise RuntimeError('Active native cancellation did not interrupt')
        resumed=next()
        if resumed['review']['action']!='resume' or resumed['review']['part']!=0:raise RuntimeError('Cancelled native reel incorrectly advanced')
        checkpoint('perf03g_native_active_worker_cancelled')
        for end in (90,180):
            receipt=reels.execute_native_approved(service,pid,next(),human_approved=True)
            if receipt['end_frame']!=end or receipt['native_execution']['job_and_profile_cleanup_verified'] is not True:raise RuntimeError('Native worker result not independently reopened')
        complete=reels.execute_native_approved(service,pid,next(),human_approved=True)
        if complete['independent_worker_verified'] is not True or complete['pcm_sha256']!=analysis['derived_pcm_sha256'] or reels.verify_complete(service,pid,complete['job_id'])!=complete:raise RuntimeError('Native reel coverage differs')
        checkpoint('perf03g_native_reels_and_pcm_verified');store.revoke(pid)
    checkpoint('perf03g_native_worker_clean_exit');return 0
