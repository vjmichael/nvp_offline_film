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

    def close(self):self._closed=True

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
