"""Installed Windows WebView2 creator workflow fixture.

Disposable, isolated synthetic scene and PCM: not a render/codec test. No test
source is ever written to the creator's workspace, and ordinary application
startup never loads this fixture. The normal HTTP-only session gate is used.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import struct
import tempfile
import time


def seed_fixture(editor,pid):
    from backend.nvp_g07_edit import _blank,_default_grade,RATE
    from backend.nvp_g06_filming import _json,_sha,TAKE_FORMAT
    from backend.nvp_g07_sections import EditorialSections
    from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
    # Only the last source has a genuine synthetic USD/PCM preview input.
    # No captured footage or final output is claimed.
    def seed(db,movie):
        for revision in range(2):
            doc=_blank();doc['title']=f'Saved act {revision+1}'
            for n in range(1+revision*140,141+revision*140):
                tid=f'{n:032x}';scene='SC_abcdef012345'
                payload=b'PERF03G public metadata fixture, not a rendered Take'
                sha=_sha(payload)
                manifest={'format':TAKE_FORMAT,'scene_id':scene,'duration_tick':2*T,
                    'original_usd_sha256':sha,'performance_usd_sha256':sha,'audio':[]}
                audio=[];clip_audio=[]
                if n==280:
                    payload=b'#usda 1.0\n( defaultPrim = "World" )\ndef Xform "World" {\n def Scope "Objects" {\n  def Xform "Actor" {\n   double3 xformOp:translate = (0, 0, 0)\n   uniform token[] xformOpOrder = ["xformOp:translate"]\n  }\n }\n}\n'
                    sha=_sha(payload);cid=f'{9000+n:032x}';pcm=struct.pack('<h',1200)*(2*RATE);pcm_sha=_sha(pcm)
                    db.execute('INSERT INTO g06_original_pcm VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cid,pid,scene,'actor_fixture','native_microphone_pcm16le',pcm,pcm_sha,RATE,1,2*RATE,'2026-11-19'))
                    audio=[{'clip_id':cid,'actor_id':'actor_fixture','pcm_sha256':pcm_sha,'sample_count':2*RATE,'start_tick':0,'duration_tick':2*T,'emitter_position':[0,0,0]}]
                    clip_audio=[{'clip_id':cid,'enabled':True,'gain':1.0,'pan':-1.0,'spatial':False,'offset_tick':0}]
                    manifest.update(original_usd_sha256=sha,performance_usd_sha256=sha,audio=audio,events=[],stage_setting={},stage_objects=[{'id':'Actor','name':'Actor','role':'actor','actor_id':'actor_fixture','shape':'cube','rotation':[0,0,0],'scale':[1,1,1],'color':'#aaaaaa'}])
                raw=_json(manifest);digest=_sha(raw.encode('utf8'))
                db.execute('INSERT INTO g06_frozen_takes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (tid,pid,scene,1,sha,sha,payload,sha,payload,raw,_json(audio),digest,'2026-11-19'))
                doc['clips'].append({'id':f'{100000+n:032x}','take_id':tid,'take_sha256':digest,
                    'source_in_tick':0,'source_out_tick':2*T,'camera':{'name':'Wide','position':[0,0,1],'look_at':[1,0,0],'focal_mm':50},
                    'grade':_default_grade(),'audio':clip_audio,'transition':{'kind':'cut','duration_tick':0},'note':''})
            editor._validate(db,pid,doc);editor._save(db,pid,doc,revision,revision)
    editor._execute(pid,seed,mutate=True)
    service=EditorialSections(editor)
    def save(title,refs):
        preview=service.preview(pid,title,refs)
        return service.publish(pid,title,refs,preview['digest'])['selection']
    first,last=service.directory(pid,'edits')['items']
    refs=[{'kind':'edit','revision':x['revision'],'digest':x['digest'],'first':0,'count':x['clip_count']} for x in (first,last)]
    a=save('First act',[refs[0]]);b=save('Second act',[refs[1]])
    a,b=({k:x[k] for k in ('kind','section_id','digest')} for x in (a,b))
    original=save('Chapter arrangement',[a,b]);alternate=save('Reordered feature',[b,a])
    args=(pid,original['section_id'],original['digest'],2)
    preview=service.preview_paged(*args);service.activate_paged(*args,preview['approval_digest'])
    return alternate


def run(*,create_app,serve,start_private,await_loaded,checkpoint):
    if sys.platform!='win32':raise RuntimeError('Genuine Windows WebView2 and DPAPI required')
    import webview
    root=Path(tempfile.mkdtemp(prefix='nvp-perf03g-window-'))
    previous=os.environ.get('NVP_HOME');os.environ['NVP_HOME']=str(root)
    server=worker=sock=window=None
    result={'passed':False,'phase':'setup'}
    try:
        app=create_app()
        from backend.nvp_api import studio,live_films,film_access
        from backend.nvp_g07_edit import G07Editor
        if not Path(studio.db_path).resolve().is_relative_to(root.resolve()):
            raise RuntimeError('Disposable native smoke workspace was not selected')
        password='PERF03G public disposable encrypted fixture passphrase'
        pid=studio.create_project('Chapter timeline acceptance','','')['id'];store=live_films();access=film_access()
        store.create(pid,'Chapter timeline acceptance','','',password)
        access.protect(pid,password);token=access.unlock(pid,password);store.authorize(pid,password,token)
        seed_fixture(G07Editor(studio,live=store,token=token),pid)
        access.lock(pid,token);store.revoke(pid)
        server,worker,port,sock=serve(app)
        api='/api/projects/'+pid
        window=webview.create_window('NVP Chapter Timeline Acceptance',f'http://127.0.0.1:{port}/postproduction.html?project={pid}&encrypted=1',width=1100,height=760)
        def wait(expr,phase,seconds=25):
            result['phase']=phase;until=time.monotonic()+seconds
            while time.monotonic()<until:
                # During a real reload the script target may temporarily be
                # unavailable. Only a later actual true DOM assertion passes.
                try:
                    if window.evaluate_js(expr) is True:return
                except Exception:
                    pass
                time.sleep(.2)
            raise RuntimeError('Protected chapter GUI assertion failed: '+phase)
        def click(selector,caption):
            selector=json.dumps(selector);caption=json.dumps(caption)
            if window.evaluate_js(f"(()=>{{const e=[...document.querySelectorAll({selector})].find(x=>x.textContent.trim()==={caption}&&!x.disabled);if(!e)return false;e.click();return true}})()") is not True:
                raise RuntimeError('Expected filmmaker control unavailable')
        def post(path,payload):
            # The installed browser uses the genuine cookie-based session; no
            # cookie, grant, database path or key is injected into JS.
            js=f"window.__nvpSmokeRequest='pending';fetch({json.dumps(api+path)},{{method:'POST',credentials:'same-origin',headers:{{'Content-Type':'application/json','x-nvp-director':'1'}},body:JSON.stringify({json.dumps(payload)})}}).then(r=>{{window.__nvpSmokeRequest=r.ok?'passed':'failed'}}).catch(()=>{{window.__nvpSmokeRequest='failed'}});true"
            window.evaluate_js(js);wait("window.__nvpSmokeRequest==='passed'",'protected_session_request')
        def inspect():
            try:
                if webview.renderer!='edgechromium':raise RuntimeError('Native WebView2 renderer unavailable')
                await_loaded(window,server,worker)
                wait("Boolean(document.body.textContent.includes('This movie is locked')&&!document.querySelector('.film-active-timeline'))",'locked_before_open')
                post('/unlock',{'passphrase':password});window.evaluate_js("setTimeout(()=>window.location.reload(),20);true")
                wait("Boolean(document.querySelector('.film-active-timeline')?.textContent.includes('Chapter arrangement')&&document.querySelectorAll('.film-active-cut-list li').length===32)",'unlocked_first_page')
                click('.film-active-timeline button','Next')
                wait("Boolean(document.querySelector('.film-active-timeline')?.textContent.includes('Cuts 33–64 of 280')&&document.querySelectorAll('.film-active-cut-list li').length===32)",'next_page')
                # Native WebView executes the actual React change/submit handlers.
                window.evaluate_js("(()=>{const e=document.querySelector('.film-active-jump input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'280');e.dispatchEvent(new Event('input',{bubbles:true}));return true})()")
                wait("Boolean(document.querySelector('.film-active-jump button')&&!document.querySelector('.film-active-jump button').disabled)",'jump_enabled')
                click('.film-active-jump button','Go')
                wait("Boolean(document.querySelector('.film-active-timeline')?.textContent.includes('Cuts 257–280 of 280')&&document.querySelectorAll('.film-active-cut-list li').length===24&&document.querySelector('.film-active-cut-target')?.dataset.cutIndex==='279')",'last_page')
                window.evaluate_js("document.querySelector('[aria-label=\"Preview cut 280\"]').click();true")
                wait("Boolean(document.querySelector('[data-source-sample=\"verified\"]'))",'native_sampled_scene')
                wait("Boolean(document.querySelector('.film-page-preview canvas'))",'native_sampled_display')
                click('.film-page-preview button','Listen to sound')
                wait("Boolean(document.querySelector('.film-page-preview audio')?.readyState>=1&&Math.abs(document.querySelector('.film-page-preview audio').duration-2)<.02)",'native_pcm_preview')
                click('.film-delivery-review button','Check cut timing')
                wait("Boolean(document.querySelector('.film-delivery-review')?.textContent.includes('Cut order and timing checked'))",'source_timing_review')
                click('.film-sections > summary','Movie recovery')
                click('.film-sections button','Check saved sections')
                wait("document.body.textContent.includes('All checked sections are available.')",'protected_storage_review')
                # Check the new filmmaker controls in the actual installed DOM.
                # The native R4 suite separately verifies real output and backup;
                # this window does not automate security/OS folder dialogs.
                click('.film-page-preview details > summary','Review clip')
                wait("[...document.querySelectorAll('.film-page-preview button')].some(x=>x.textContent.trim()==='Save review clip'&&!x.disabled&&x.getClientRects().length>0)",'review_clip_control')
                click('.film-delivery-review details > summary','Saved review clips')
                click('.film-delivery-review button','Show saved clips')
                wait("document.querySelector('.film-delivery-review')?.textContent.includes('No saved clips for this edit.')===true",'saved_clip_inventory')
                wait("['Create movie backup','Recover movie copy','Optimize recording storage'].every(c=>[...document.querySelectorAll('.film-sections button')].some(x=>x.textContent.trim()===c&&!x.disabled&&x.getClientRects().length>0))",'movie_backup_controls')
                checkpoint('perf03g_real_webview2_review_clip_and_backup_controls_verified')
                checkpoint('perf03g_real_webview2_sampled_media_recovery_review_verified')
                click('.film-sections > summary','Organize film sections')
                wait("[...document.querySelectorAll('.film-sections-open')].some(x=>x.textContent.trim()==='Reordered feature')",'browse_alternative')
                click('.film-sections-open','Reordered feature')
                wait("[...document.querySelectorAll('.film-sections button')].some(x=>x.textContent.trim()==='Review as active edit'&&!x.disabled)",'review_available')
                click('.film-sections button','Review as active edit')
                wait("Boolean(document.querySelector('.film-sections-review')?.textContent.includes('Sampled scene previews are available; final export is not yet available'))",'review_separate')
                click('.film-sections-review button','Use this edit')
                wait("Boolean(document.querySelector('.film-active-timeline')?.textContent.includes('Reordered feature')&&document.querySelector('.film-editor-save-state')?.textContent.includes('Version 4')&&document.querySelectorAll('.film-active-cut-list li').length===32)",'activated_and_reopened')
                post('/lock',{});window.evaluate_js("window.dispatchEvent(new Event('focus'));true")
                wait("Boolean(document.body.textContent.includes('This movie is locked')&&!document.querySelector('.film-active-timeline')&&!document.body.textContent.includes('Reordered feature'))",'relocked_no_content')
                checkpoint('perf03g_real_webview2_protected_paged_editor_verified');result['passed']=True
            except Exception as exc:
                result['failure']=type(exc).__name__
            finally:window.destroy()
        diagnostics={};start_private(webview,func=inspect,diagnostics=diagnostics)
        if not result['passed']:raise RuntimeError('Installed chapter editor failed: '+result['phase']+' / '+result.get('failure','unknown')+' / '+repr(diagnostics))
        checkpoint('perf03g_real_webview2_loop_exited')
        return 0
    finally:
        if server is not None:server.should_exit=True
        if worker is not None:worker.join(timeout=12)
        if sock is not None:sock.close()
        if previous is None:os.environ.pop('NVP_HOME',None)
        else:os.environ['NVP_HOME']=previous
        shutil.rmtree(root,ignore_errors=True)
