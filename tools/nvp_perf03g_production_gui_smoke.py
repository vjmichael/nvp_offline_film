"""Generated-only installed WebView2 working-movie acceptance.
No test automation or consent substitution is reachable from ordinary startup.
The test clicks real React controls and this process's actual native dialogs.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def _click_native_choice(title,answer,timeout=45):
    # Bound to this isolated installed test process and the standard native
    # confirmation's exact title/ID. Never click an unrelated dialog/window.
    import ctypes as C
    from ctypes import wintypes as W
    user=C.WinDLL('user32',use_last_error=True)
    user.FindWindowW.argtypes=[W.LPCWSTR,W.LPCWSTR];user.FindWindowW.restype=W.HWND
    user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]
    user.GetDlgItem.argtypes=[W.HWND,C.c_int];user.GetDlgItem.restype=W.HWND
    user.IsWindowEnabled.argtypes=[W.HWND];user.IsWindowEnabled.restype=W.BOOL
    user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];user.PostMessageW.restype=W.BOOL
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        hwnd=user.FindWindowW('#32770',title)
        if hwnd:
            pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,C.byref(pid))
            if pid.value==os.getpid():
                button=user.GetDlgItem(hwnd,1 if answer else 2) # IDOK/IDCANCEL (pinned pywebview 6.2.1)
                if button and user.IsWindowEnabled(button):
                    if not user.PostMessageW(button,0xf5,0,0):raise RuntimeError('Native test button not delivered')
                    return
        time.sleep(.1)
    raise RuntimeError('Expected installed confirmation dialog unavailable')


def run(*,create_app,serve,start_private,await_loaded,checkpoint):
    if sys.platform!='win32' or not getattr(sys,'frozen',False) or os.environ.get('GITHUB_ACTIONS')!='true':
        raise PermissionError('Installed generated Windows qualification only')
    import webview
    from backend.nvp_g07_recovery_dialog import NativeRecoveryDialog
    from backend.nvp_g07_edit import G07Editor
    from backend.nvp_g07_feature_finish import current_analysis
    from backend import nvp_g07_feature_reels as reels
    from tools.nvp_perf03g_worker_smoke import seed_feature
    previous=os.environ.get('NVP_HOME');server=worker=sock=dialog=None
    with tempfile.TemporaryDirectory(prefix='nvp-r8-public-window-') as tmp:
        root=Path(tmp);os.environ['NVP_HOME']=str(root)
        result={'passed':False,'phase':'setup'}
        try:
            app=create_app()
            from backend.nvp_api import studio,live_films,film_access
            if not Path(studio.db_path).resolve().is_relative_to(root.resolve()):raise RuntimeError('Disposable workspace not selected')
            secret='PERF03G disposable public graphical fixture'
            pid=studio.create_project('Generated working movie','','')['id'];store=live_films();access=film_access()
            store.create(pid,'Generated working movie','','',secret);access.protect(pid,secret);token=access.unlock(pid,secret);store.authorize(pid,secret,token)
            service=seed_feature(G07Editor(studio,live=store,token=token),pid,count=32)
            revision=service.editor.view(pid)
            access.lock(pid,token);store.revoke(pid)
            server,worker,port,sock=serve(app);origin=f'http://127.0.0.1:{port}'
            window=webview.create_window('NVP working movie acceptance',origin+f'/postproduction.html?project={pid}&encrypted=1',width=1100,height=760)
            dialog=NativeRecoveryDialog(window,origin);app.state.nvp_editorial_recovery_dialog=dialog
            def wait(expr,phase,timeout=60):
                result['phase']=phase;deadline=time.monotonic()+timeout
                while time.monotonic()<deadline:
                    try:
                        if window.evaluate_js(expr) is True:return
                    except Exception:pass
                    time.sleep(.1)
                raise RuntimeError('Working movie GUI assertion failed: '+phase)
            def click(caption):
                q=json.dumps(caption)
                if window.evaluate_js(f"(()=>{{const b=[...document.querySelectorAll('.film-working-movie button,.film-working-movie summary')].find(x=>x.textContent.trim()==={q}&&!x.disabled);if(!b)return false;b.click();return true}})()") is not True:raise RuntimeError('Expected movie control not available')
            def inspect():
                try:
                    if webview.renderer!='edgechromium':raise RuntimeError('Native WebView2 renderer unavailable')
                    await_loaded(window,server,worker)
                    wait("document.body.textContent.includes('This movie is locked')",'locked')
                    window.evaluate_js(f"fetch('/api/projects/{pid}/unlock',{{method:'POST',credentials:'same-origin',headers:{{'Content-Type':'application/json','x-nvp-director':'1'}},body:JSON.stringify({{passphrase:{json.dumps(secret)}}})}}).then(r=>{{if(r.ok)location.reload()}});true")
                    wait("Boolean(document.querySelector('.film-working-movie'))",'unlocked_working_movie')
                    click('Working movie');click('Review picture and sound')
                    wait("document.querySelector('.film-working-movie')?.textContent.includes('Approved for this film')===true",'confirmed_finishing_ui')
                    click('Close picture and sound')
                    # Observe the actual HTTP response without intercepting its
                    # arguments, changing decisions or injecting session data.
                    window.evaluate_js("(()=>{const f=window.fetch;window.__nvpWorkingReceipt=null;window.fetch=async (...args)=>{const r=await f(...args);if(typeof args[0]==='string'&&args[0].endsWith('/feature-step'))r.clone().json().then(v=>window.__nvpWorkingReceipt=v);return r};return true})()")
                    click('Prepare or continue working movie');_click_native_choice('NVP — Prepare working movie',False)
                    wait("window.__nvpWorkingReceipt?.state==='refused'&&document.querySelector('.film-working-movie').textContent.includes('Not started')",'real_native_refusal')
                    click('Prepare or continue working movie');_click_native_choice('NVP — Prepare working movie',True)
                    wait("window.__nvpWorkingReceipt?.state==='prepared'&&document.querySelector('.film-working-movie').textContent.includes('Sound preparation complete')",'real_native_preparation',120)
                    click('Continue working movie');_click_native_choice('NVP — Working movie',True)
                    wait("document.querySelector('.film-working-movie')?.dataset.productionPhase==='rendering'",'active_native_worker_observed',120)
                    click('Stop')
                    wait("window.__nvpWorkingReceipt?.state==='stopped'&&document.querySelector('.film-working-movie').textContent.includes('Stopped. Verified parts')",'graphical_stop',120)
                    if window.evaluate_js("window.__nvpWorkingReceipt?.active_render_stopped===true") is not True:raise RuntimeError('Stop did not terminate an active protected worker')
                    checkpoint('perf03g_r8_actual_graphical_worker_stop_verified')
                    click('Continue working movie');_click_native_choice('NVP — Working movie',True)
                    wait("window.__nvpWorkingReceipt?.state==='complete'&&window.__nvpWorkingReceipt.saved_frames===756&&document.querySelector('.film-working-movie').textContent.includes('Working movie verified and saved')",'resumed_multi_reel_movie',600)
                    # Get the live key only from the native store, not JS.
                    # Read the unique host session for this disposable movie;
                    # no test cookie or approval is added to the browser.
                    tokens=[key for key,value in store._keys.items() if value[0]==pid]
                    if len(tokens)!=1:raise RuntimeError('Expected one live movie session')
                    from backend.nvp_g07_sections import EditorialSections
                    token=tokens[0];read=EditorialSections(G07Editor(studio,live=store,token=token),access_guard=lambda:store._session(pid,token))
                    _,analysis_sha=current_analysis(read,pid,revision['revision'],revision['active_digest']);step=reels.review_native_next(read,pid,analysis_sha)['review'];complete=reels.verify_complete(read,pid,step['job_id'])
                    if complete['frames']!=1524 or complete['reel_count']!=7 or complete['independent_worker_verified'] is not True or complete['final_movie_exported'] is not False:raise RuntimeError('Verified native film receipt differs')
                    checkpoint('perf03g_r8_actual_graphical_resume_and_native_reels_verified')
                    # Playback uses the actual installed React player, WebView2
                    # AudioContext and protected HTTP reader. No media or clock
                    # substitution; a stall/error is an acceptance failure.
                    click('Watch working movie')
                    wait("document.querySelector('.director-reel-player')?.textContent.includes('Film ready to watch')===true",'playback_open',120)
                    click('Play Film')
                    wait("document.querySelector('.director-reel-player')?.textContent.includes('Playing in sync')===true",'playback_started',120)
                    start=time.monotonic();last=0.;furthest=0.;seen=set();crossings=set()
                    result['phase']='continuous_native_playback'
                    while time.monotonic()-start<100:
                        sample=window.evaluate_js("(()=>{const p=document.querySelector('.director-reel-player');const r=p?.querySelector('input[type=range]');return JSON.stringify({position:Number(r?.value),duration:Number(r?.max),picture:Boolean(p?.querySelector('img')?.complete&&p?.querySelector('img')?.naturalWidth===640),playing:p?.textContent.includes('Playing in sync')===true,ended:p?.textContent.includes('The finished film has ended.')===true,error:p?.querySelector('[role=alert]')?.textContent||''})})()")
                        state=json.loads(sample)
                        if state['error'] or state['duration']!=63.5 or state['position']<last or (not state['playing'] and not state['ended']):raise RuntimeError('Playback paused, drifted or changed identity')
                        pos=state['position'];last=pos;furthest=max(furthest,pos)
                        if state['picture']:
                            seen.add(int(pos*24));crossings.add(min(6,int(pos//10)))
                        if state['ended']:
                            if furthest<63.498 or len(crossings)!=7 or len(seen)<100 or time.monotonic()-start<61:raise RuntimeError('Incomplete real-time playback observation')
                            break
                        time.sleep(.12)
                    else:raise RuntimeError('Continuous playback deadline exceeded')
                    checkpoint('perf03g_r10_actual_graphical_playback_complete')
                    click('Close playback')
                    result['passed']=True
                except Exception as exc:result['failure']=type(exc).__name__
                finally:dialog.close();window.destroy()
            start_private(webview,func=inspect)
            dialog.close()
            if not dialog.wait_feature_closed(timeout=60) or not result['passed']:raise RuntimeError('Installed working movie gate failed: '+result['phase']+' / '+result.get('failure','unknown'))
            server.should_exit=True;worker.join(timeout=30)
            if worker.is_alive():raise RuntimeError('Installed movie API did not shut down')
            socket_to_close=sock;sock=None;socket_to_close.close();worker=None;server=None
            checkpoint('perf03g_r8_actual_graphical_clean_exit')
            return 0
        finally:
            if dialog:dialog.close()
            if server:server.should_exit=True
            if worker:worker.join(timeout=12)
            if sock:sock.close()
            if previous is None:os.environ.pop('NVP_HOME',None)
            else:os.environ['NVP_HOME']=previous
