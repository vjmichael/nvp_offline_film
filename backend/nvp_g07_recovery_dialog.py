"""Narrow protected editorial backup picker, separate from native camera IPC.

Only installed host code attaches a real window. No JS/HTTP supplied paths,
keys, approval boolean, or arbitrary callbacks. Existing live-store session,
exact current edit, index digest and original page recovery remain authoritative.
"""
from contextlib import contextmanager
from pathlib import Path
import json
import os
import threading
from urllib.parse import urlsplit,parse_qs
from backend.nvp_g07_sections import _number,_check_sha,_project,FORMAT,_digest,HEX
from backend.nvp_g03_windows_vault import VaultError,_no_link
from backend import nvp_g07_section_pages as pages


class NativeRecoveryDialog:
    def __init__(self,window,origin):
        u=urlsplit(origin)
        if u.scheme!='http' or u.hostname!='127.0.0.1' or u.port is None or u.path not in ('','/') or u.query or u.fragment or u.username:
            raise ValueError('Exact installed loopback origin required')
        for name in ('get_current_url','create_file_dialog','create_confirmation_dialog'):
            if not callable(getattr(window,name,None)):raise TypeError('Native recovery window required')
        self._window=window;self._origin=f'http://127.0.0.1:{u.port}';self._lock=threading.Lock();self._closed=False
        self._feature_lock=threading.Lock();self._feature=None;self._feature_ids=set()

    def close(self):
        with self._feature_lock:
            self._closed=True
            if self._feature:self._feature[4].set()

    @contextmanager
    def feature_operation(self,pid,origin,guard,token,operation_id):
        if type(operation_id) is not str or not HEX.fullmatch(operation_id) or not isinstance(token,str) or not token:
            raise PermissionError("Exact movie operation required")
        self._check(pid,origin,guard)
        event=threading.Event();done=threading.Event();record=(pid,origin,token,operation_id,event,{"phase":"preparing","saved_frames":0,"total_frames":0},done)
        with self._feature_lock:
            if self._closed or self._feature is not None:raise RuntimeError("A working movie action is already running")
            if operation_id in self._feature_ids or len(self._feature_ids)>=4096:raise PermissionError("Use a new working movie operation")
            self._feature_ids.add(operation_id);self._feature=record
        try:yield event
        finally:
            with self._feature_lock:
                if self._feature is record:self._feature=None
                done.set()

    def wait_feature_closed(self,timeout=60):
        with self._feature_lock:done=self._feature[6] if self._feature else None
        return done is None or done.wait(timeout)

    def feature_progress(self,operation_id,phase,saved,total):
        with self._feature_lock:
            if self._feature is None or self._feature[3]!=operation_id:raise RuntimeError("Working movie action lost")
            self._feature[5].update(phase=phase,saved_frames=saved,total_frames=total)

    def stop_feature(self,pid,origin,guard,token,operation_id):
        # The stop path does not acquire the live movie writer mutex or wait
        # for a native modal, backend operation or renderer response.
        guard()
        import hmac
        with self._feature_lock:
            active=self._feature
            if self._closed or origin!=self._origin or active is None or active[:2]!=(pid,origin) or not isinstance(token,str) or not hmac.compare_digest(active[2],token) or active[3]!=operation_id:
                return False
            active[4].set();return True

    def feature_status(self,pid,origin,guard,token,operation_id):
        guard()
        with self._feature_lock:
            active=self._feature
            if self._closed or origin!=self._origin or active is None or active[:4]!=(pid,origin,token,operation_id):return {"active":False}
            return {"active":True,**active[5],"stop_requested":active[4].is_set()}

    def _check(self,pid,origin,guard):
        if self._closed or origin!=self._origin:raise PermissionError('Native recovery origin denied')
        guard()
        current=self._window.get_current_url()
        if type(current) is not str:raise PermissionError('Native recovery window unavailable')
        u=urlsplit(current)
        if (u.scheme!='http' or u.netloc!=self._origin.removeprefix('http://') or u.fragment or
            not ((u.path=='/' and not u.query) or (u.path=='/postproduction.html' and parse_qs(u.query,keep_blank_values=True)=={'project':[pid],'encrypted':['1']}))):
            raise PermissionError('Native recovery window is not the selected movie')

    @contextmanager
    def operation(self,pid,origin,guard):
        self._check(pid,origin,guard)
        if not self._lock.acquire(blocking=False):raise RuntimeError('Another backup selection is open')
        try:
            self._check(pid,origin,guard)
            yield
        finally:self._lock.release()

    def pick(self,pid,origin,guard):
        self._check(pid,origin,guard)
        from webview import FileDialog
        selection=self._window.create_file_dialog(FileDialog.FOLDER,allow_multiple=False)
        self._check(pid,origin,guard)
        if not selection:return None
        if type(selection) not in (tuple,list) or len(selection)!=1 or type(selection[0]) is not str:
            raise PermissionError('Choose one local protected movie backup folder')
        return Path(selection[0])

    def confirm(self,pid,origin,guard,scope):
        self._check(pid,origin,guard)
        # Title is from the authenticated backup page, not browser text.
        yes=self._window.create_confirmation_dialog('NVP — Recover saved section',
            'Restore the missing saved section “'+scope['title']+'” from this verified backup?\n\nExisting material and your current edit will not be replaced.') is True
        self._check(pid,origin,guard)
        return yes


def _candidate(service,db,pid,ident,revision):
    if type(ident) is not str or not HEX.fullmatch(ident):raise ValueError('Select a saved section')
    rev,_=_project(db,pid,allow_paged=True)
    if rev!=_number(revision,1,15000):raise RuntimeError('The active edit changed')
    row=db.execute('SELECT document_json,document_sha256 FROM g07_sections WHERE project_id=? AND section_id=?',(pid,ident)).fetchone()
    if row is None:raise KeyError('Saved section missing from the index')
    digest=_check_sha(row['document_sha256'])
    if json.loads(row['document_json'])!={'format':pages.FORMAT,'sha256':digest}:raise VaultError('No exact indexed sealed page to recover')
    context=service._page_context(pid)
    if not context:raise PermissionError('Unlock the protected movie first')
    target=pages._location(context['folder'],context['key'],digest,missing_directory=True)
    if target.exists() or target.is_symlink():raise VaultError('Existing page must be preserved for review')
    return digest,context


def _backup_path(backup,folder):
    backup=Path(backup)
    if not backup.is_absolute():raise VaultError('Choose an absolute local backup folder')
    # Do not probe a UNC/network path even to determine whether it exists.
    if os.name=='nt':
        import ctypes
        if len(backup.drive)!=2 or backup.drive[1]!=':' or ctypes.windll.kernel32.GetDriveTypeW(str(backup.anchor)) not in (2,3):raise VaultError('Choose a local backup drive')
    if any(part in ('.','..') or ':' in part for part in backup.parts[1:]):raise VaultError('Invalid backup folder')
    for entry in (*reversed(backup.parents),backup):_no_link(entry)
    if not backup.is_dir():raise VaultError('Choose an available local backup folder')
    if backup.resolve()==folder.resolve():raise ValueError('Choose a separate authenticated backup')
    return backup


def recovery_candidate(service,pid,ident,revision):
    """Private host preflight; return only the exact indexed digest."""
    return service._run(pid,lambda db,movie:_candidate(service,db,pid,ident,revision)[0])


def review_backup(service,pid,ident,revision,digest,folder):
    """Review the exact authenticated page before opening the OS confirmation."""
    def read(db,movie):
        actual,context=_candidate(service,db,pid,ident,revision)
        if actual!=digest:raise RuntimeError('The saved section changed')
        backup=_backup_path(folder,context['folder'])
        raw=pages.read_page(backup,pid,context['key'],actual);doc=json.loads(raw)
        if type(doc) is not dict or set(doc)!={'format','project_id','section_id','title','children','duration_tick','clip_count','depth'} or doc['format']!=FORMAT or doc['project_id']!=pid or doc['section_id']!=ident or _digest(doc)!=actual:
            raise VaultError('Backup section source changed')
        expected=service._compose(db,pid,doc['title'],[c['source'] for c in doc['children']])
        if any(doc[k]!=v for k,v in expected.items()):raise VaultError('Backup section dependencies changed')
        return {'project_id':pid,'section_id':ident,'revision':revision,'digest':actual,'title':doc['title']}
    return service._run(pid,read)


def recover_with_dialog(service,pid,ident,revision,origin,dialog):
    if type(dialog) is not NativeRecoveryDialog:raise PermissionError('Open NVP desktop to choose a protected backup')
    if service.access_guard is None:raise PermissionError('Live director request guard required')
    guard=service.access_guard
    with dialog.operation(pid,origin,guard):
        # Retain both the original request authorization and the exact native
        # dialog/window lease through the final atomic missing-page recovery.
        def current():dialog._check(pid,origin,guard)
        service.access_guard=current
        try:
            digest=recovery_candidate(service,pid,ident,revision)
            folder=dialog.pick(pid,origin,guard)
            if folder is None:return {'restored':False,'cancelled':True,'revision':revision,'render_approved':False}
            scope=review_backup(service,pid,ident,revision,digest,folder)
            if not dialog.confirm(pid,origin,guard,scope):return {'restored':False,'cancelled':True,'revision':revision,'render_approved':False}
            current()
            result=service.recover_missing_page(pid,ident,digest,folder,expected_revision=revision,human_approved=True)
            current()
            return {**result,'cancelled':False}
        finally:service.access_guard=guard


def _native_operation(service,pid,origin,dialog):
    if type(dialog) is not NativeRecoveryDialog or service.access_guard is None or not service._page_context(pid):raise PermissionError('Open the installed protected movie workspace')
    return dialog.operation(pid,origin,service.access_guard)


def review_clip_with_dialog(service,pid,revision,digest,first,count,origin,dialog):
    from backend.nvp_g07_review_reels import review,render_approved,FORMAT as REEL_FORMAT
    with _native_operation(service,pid,origin,dialog):
        previous=service.access_guard
        def check():dialog._check(pid,origin,previous)
        service.access_guard=check
        try:
            expected=review(service,pid,revision,digest,first,count)
            confirmed=dialog._window.create_confirmation_dialog('NVP — Save review clip',f'Save this {count/24:.2f}-second review clip from the current edit inside your protected movie?\n\nThis is a working clip, not the finished movie.') is True
            check()
            if not confirmed:return {'format':REEL_FORMAT,'project_id':pid,'revision':revision,'cancelled':True,'verified':False,'whole_movie_exported':False}
            return {**render_approved(service,pid,expected,human_approved=True),'cancelled':False}
        finally:service.access_guard=previous


def backup_with_dialog(service,pid,origin,dialog,*,restore=False):
    from backend.nvp_g03_live_backup import create_backup,restore_copy,_check_manifest,_verify_index,_root,FORMAT as BACKUP_FORMAT
    with _native_operation(service,pid,origin,dialog):
        guard=service.access_guard
        host=service.editor.filming.g05.g04;store=host.live;token=host.token
        def check():dialog._check(pid,origin,guard)
        cancel={'format':BACKUP_FORMAT,'project_id':pid,'cancelled':True,'original_unchanged':True}
        first=dialog.pick(pid,origin,guard)
        if first is None:return cancel
        if restore:
            with store._guard:
                key=store._session(pid,token);source=_root(first)
                inventory=_check_manifest(source,pid,key,check);_verify_index(store,source,pid,key,check)
            destination=dialog.pick(pid,origin,guard)
            if destination is None:return cancel
            yes=dialog._window.create_confirmation_dialog('NVP — Recover movie copy','Create a separate verified copy of this protected movie from the selected backup?\n\nThe current movie and existing folders will not be replaced.') is True
            check()
            if not yes:return cancel
            # Revalidate exact reviewed inventory after the picker and consent.
            with store._guard:
                if _check_manifest(source,pid,store._session(pid,token),check)!=inventory:raise VaultError('Backup changed during consent')
            return {**restore_copy(store,pid,token,source,destination,guard=check,human_approved=True,expected_inventory=inventory),'cancelled':False}
        with store._guard:
            check();head=store._head(store._folder(pid))
        yes=dialog._window.create_confirmation_dialog('NVP — Create movie backup','Save an encrypted backup of this movie, including the saved history and original material, in the selected folder?\n\nExisting backups are never replaced. Keep your Windows account and movie passphrase for recovery.') is True
        check()
        if not yes:return cancel
        return {**create_backup(store,pid,token,first,guard=check,human_approved=True,expected_head=head),'cancelled':False}


def copy_clip_with_dialog(service,pid,revision,digest,ident,origin,dialog):
    from backend.nvp_g07_review_reels import open_reel,inspect,FORMAT as REEL_FORMAT
    from backend.nvp_g03_live_backup import _root
    from backend.nvp_wo3_atomic_publish import atomic_publish_directory
    import hashlib,tempfile,shutil
    with _native_operation(service,pid,origin,dialog):
        guard=service.access_guard
        def check():dialog._check(pid,origin,guard)
        raw=open_reel(service,pid,ident,revision,digest);sha=hashlib.sha256(raw).hexdigest()
        cancelled={'format':REEL_FORMAT,'project_id':pid,'reel_id':ident,'revision':revision,'cancelled':True,'copy_saved':False}
        choice=dialog.pick(pid,origin,guard)
        if choice is None:return cancelled
        parent=_root(choice);ctx=service._page_context(pid);folder=ctx['folder'].resolve()
        if parent==folder or folder in parent.parents or parent in folder.parents:raise VaultError('Choose a separate folder for the working clip')
        yes=dialog._window.create_confirmation_dialog('NVP — Save review clip copy','Save an AVI review copy outside the protected movie?\n\nThe copy will not be encrypted. Your protected original and saved edit remain unchanged.') is True
        check()
        if not yes:return cancelled
        if hashlib.sha256(open_reel(service,pid,ident,revision,digest)).hexdigest()!=sha:raise VaultError('Review clip changed during approval')
        target=parent/('NVP-review-'+ident);stage=Path(tempfile.mkdtemp(prefix='.nvp-review-',dir=parent))
        try:
            output=stage/'review.avi'
            with output.open('xb') as f:
                for at in range(0,len(raw),512*1024):
                    check();f.write(raw[at:at+512*1024])
                f.flush();os.fsync(f.fileno())
            with output.open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=sha:raise VaultError('Review copy changed')
            check();atomic_publish_directory(stage,target)
            return {**cancelled,'cancelled':False,'copy_saved':True,'original_unchanged':True}
        finally:
            if stage.exists():shutil.rmtree(stage)


def optimize_recording_with_dialog(service,pid,origin,dialog):
    from backend.nvp_g03_pcm_pages import migrate_recording
    with _native_operation(service,pid,origin,dialog):
        guard=service.access_guard
        def check():dialog._check(pid,origin,guard)
        def candidate(db,movie):
            return db.execute('SELECT id,scene_id,pcm_sha256,length(pcm) AS bytes FROM g06_original_pcm WHERE project_id=? AND length(pcm)>0 ORDER BY id LIMIT 1',(pid,)).fetchone()
        row=service._run(pid,candidate)
        if row is None:return {'project_id':pid,'migrated':False,'complete':True,'cancelled':False}
        confirmed=dialog._window.create_confirmation_dialog('NVP — Optimize recording storage','Move one original recording to independently protected storage pages?\n\nIts sound, timing, saved Takes and history will stay unchanged.') is True
        check()
        if not confirmed:return {'project_id':pid,'migrated':False,'complete':False,'cancelled':True}
        result=migrate_recording(service.editor.filming,pid,row['scene_id'],row['id'],row['pcm_sha256'],guard=check,human_approved=True)
        return {'project_id':pid,'migrated':result['migrated'],'complete':service._run(pid,candidate) is None,'cancelled':False,'original_unchanged':True}


def optimize_payloads_with_dialog(service,pid,origin,dialog,family):
    """Bounded movie-storage optimization, with native review of each batch."""
    from backend import nvp_g03_payloads as payloads
    if family not in ('edl','take'):raise ValueError('Choose movie edits or original scenes')
    with _native_operation(service,pid,origin,dialog):
        guard=service.access_guard
        def check():dialog._check(pid,origin,guard)
        host=service.editor.filming.g05.g04;store=host.live;token=host.token
        review=payloads.review(store,pid,token,family,pending_only=True,guard=check)
        count=len(review['entries'])
        if not count:return {'project_id':pid,'migrated':0,'complete':True,'cancelled':False,'original_unchanged':True}
        label='saved edits' if family=='edl' else 'original filmed scenes'
        yes=dialog._window.create_confirmation_dialog('NVP — Optimize movie storage',
            f'Move {count} {label} into separately protected storage?\n\nTheir original identities, current edit and saved history will remain unchanged.') is True
        check()
        if not yes:return {'project_id':pid,'migrated':0,'complete':False,'cancelled':True}
        result=payloads.migrate(store,pid,token,family,None,review['approval_digest'],human_approved=True,pending_only=True,guard=check)
        remaining=payloads.review(store,pid,token,family,pending_only=True,guard=check)
        return {'project_id':pid,'migrated':result['migrated'],'complete':not remaining['entries'],'cancelled':False,'original_unchanged':True}


def feature_reel_with_dialog(service,pid,analysis_sha256,origin,dialog,*,cancel=None,worker_started=None):
    """Trusted host integration only; caller owns cancellation and native window.

    No browser endpoint or arbitrary callback is exposed by this function.
    """
    from backend.nvp_g07_feature_reels import review_native_next,execute_native_approved
    with _native_operation(service,pid,origin,dialog):
        previous=service.access_guard
        def check():dialog._check(pid,origin,previous)
        service.access_guard=check
        try:
            review=review_native_next(service,pid,analysis_sha256)
            action=review['review']['action'];window=review['review']['window']
            if action=='complete':return {'cancelled':False,'already_complete':True}
            label='Verify the complete working movie?' if action=='finalize' else f'Render and save the next {((window[1]-window[0])/24):.2f} seconds of your working movie?'
            yes=dialog._window.create_confirmation_dialog('NVP — Working movie',label+'\n\nYour original recordings and current edit will stay unchanged.') is True
            check()
            if not yes:return {'cancelled':True}
            return {**execute_native_approved(service,pid,review,human_approved=True,cancel=cancel,worker_started=worker_started),'cancelled':False}
        finally:service.access_guard=previous


def feature_step_with_dialog(service,pid,revision,digest,operation_id,origin,dialog):
    """Explicitly prepare or approve the remaining immutable production range.
    No browser-selected worker or receipt.

    Cancel is a separate, session-scoped intent; a cancelled result is only
    returned after the operation unwinds (including native worker cleanup).
    """
    from backend.nvp_g07_feature_native import installed_identity
    from backend.nvp_g07_feature_finish import analyze_approved,current_analysis
    from backend.nvp_g07_feature_reels import review_native_next,execute_native_approved
    if type(dialog) is not NativeRecoveryDialog or service.access_guard is None or not service._page_context(pid):raise PermissionError('Open the installed protected movie workspace')
    installed_identity()  # refuse unsupported/source-only hosts before confirmation
    token=service.editor.filming.g05.g04.token;previous=service.access_guard
    result={'project_id':pid,'revision':revision,'active_digest':digest,'operation_id':operation_id,'final_movie_exported':False}
    with dialog.feature_operation(pid,origin,previous,token,operation_id) as stop:
        with _native_operation(service,pid,origin,dialog):
            def check():
                if stop.is_set():raise InterruptedError('Working movie stopped')
                dialog._check(pid,origin,previous)
                if stop.is_set():raise InterruptedError('Working movie stopped')
            service.access_guard=check
            try:
                expected,saved=current_analysis(service,pid,revision,digest)
                total=expected['frame_count']
                dialog.feature_progress(operation_id,'preparing',0,total)
                if saved is None:
                    yes=dialog._window.create_confirmation_dialog('NVP — Prepare working movie','Measure the complete approved picture and sound arrangement?\n\nYour original recordings and current edit will stay unchanged.') is True
                    check()
                    if not yes:return {**result,'state':'refused'}
                    analyze_approved(service,pid,expected,human_approved=True)
                    return {**result,'state':'prepared','saved_frames':0,'total_frames':total}
                native=review_native_next(service,pid,saved)
                step=native['review'];action=step['action']
                if action=='complete':
                    # Do not infer native proof just from completed metadata.
                    from backend.nvp_g07_feature_reels import verify_complete
                    verified=verify_complete(service,pid,step['job_id'])
                    if verified['independent_worker_verified'] is not True:raise VaultError('Saved working movie lacks native verification')
                    return {**result,'state':'complete','saved_frames':total,'total_frames':total,'job_id':step['job_id']}
                # One native confirmation authorizes this exact remaining
                # range, including verification. Subsequent reel reviews must
                # retain the original job/worker identity and advance exactly.
                spec=step['spec'];job=step['job_id'];identity=native['native_renderer'];part=step['part']
                start_frame=min(part*spec['frames_per_reel'],total)
                dialog.feature_progress(operation_id,'reviewing',start_frame,total)
                label=('Verify the complete working movie?' if action=='finalize' else
                       f'Render and verify the remaining {(total-start_frame)/24:.2f} seconds of your working movie?')
                yes=dialog._window.create_confirmation_dialog('NVP — Working movie',label+'\n\nYour original recordings and current edit will stay unchanged. You can stop at any time; verified parts will be kept.') is True
                check()
                if not yes:return {**result,'state':'refused'}
                while True:
                    check()
                    step=native['review'];action=step['action']
                    if (step['job_id']!=job or step['analysis_sha256']!=saved or step['spec']!=spec or native['native_renderer']!=identity or step['part']!=part or action not in ('render','resume','finalize')):
                        raise VaultError('Approved working movie range changed')
                    dialog.feature_progress(operation_id,'verifying' if action=='finalize' else 'starting',start_frame,total)
                    receipt=execute_native_approved(service,pid,native,human_approved=True,cancel=stop.is_set,worker_started=lambda:dialog.feature_progress(operation_id,'rendering',start_frame,total),worker_finished=lambda:dialog.feature_progress(operation_id,'verifying',start_frame,total))
                    if action=='finalize':
                        if receipt['independent_worker_verified'] is not True or receipt['frames']!=total:raise VaultError('Saved working movie lacks native verification')
                        return {**result,'state':'complete','saved_frames':total,'total_frames':total,'job_id':step['job_id']}
                    if receipt['native_execution']['job_and_profile_cleanup_verified'] is not True or receipt['part']!=part or receipt['start_frame']!=start_frame or receipt['end_frame']!=min(total,start_frame+spec['frames_per_reel']):raise VaultError('Worker cleanup or range unverified')
                    start_frame=receipt['end_frame'];part+=1
                    dialog.feature_progress(operation_id,'starting',start_frame,total)
                    check()
                    native=review_native_next(service,pid,saved)
            except InterruptedError as exc:
                if not stop.is_set():raise
                from backend.nvp_g07_feature_native import NativeReelInterrupted
                active_stopped=type(exc) is NativeReelInterrupted and exc.active_worker_stopped is True
                return {**result,'state':'stopped','active_render_stopped':active_stopped}
            finally:service.access_guard=previous
