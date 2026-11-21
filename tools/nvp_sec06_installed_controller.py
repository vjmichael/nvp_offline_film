"""Root-only controller for the disposable lab's exact installed qualification unit.
No arbitrary unit names, commands or process IDs accepted. Do not run on a user PC.
"""
import json,os,select,signal,subprocess,time,hashlib,stat
from pathlib import Path
CG=Path('/sys/fs/cgroup');root=Path('/var/lib');unitprefix='nvp-sec06-qualification@'
def run(*args): return subprocess.check_output(args,text=True).strip()
def show(unit,key):return run('systemctl','show',unit,'-p',key,'--value')
def until(check,desc,seconds=60):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if check():return
        time.sleep(.1)
    raise RuntimeError(desc)
def membership(pid):
    return (CG/Path('/proc',str(pid),'cgroup').read_text().strip().split('::',1)[1].lstrip('/')).resolve()
def run_fixture(user):
    unit=unitprefix+user+'.service';state=root/('nvp-sec06-'+user)
    assert show(unit,'FragmentPath')=='/usr/lib/systemd/system/nvp-sec06-qualification@.service'
    assert show(unit,'KillMode')=='control-group' and show(unit,'Delegate')=='yes' and show(unit,'Restart')=='no'
    assert not state.exists();fds={}
    try:
        run('systemctl','start',unit)
        until(lambda:(state/'ready.json').exists(),'Installed fixture failed to reach checkpoint',90)
        ready=json.loads((state/'ready.json').read_text());old_inv=show(unit,'InvocationID');assert ready['invocation']==old_inv
        assert int(show(unit,'MainPID'))==ready['host']
        scope=(CG/show(unit,'ControlGroup').lstrip('/')).resolve();assert scope==Path(ready['delegation'])
        assert ready['uid']==(0 if user=='root' else int(run('id','-u',user)))
        roles=json.loads((state/'roles-complete.json').read_text());assert len(roles['roles'])==5
        assert all(r['kernel']['process_tree_custody_verified'] for r in roles['roles'])
        for name in ['host','audio_guardian','audio_worker','detached_guardian','detached_worker','descendant']:
            pid=ready[name];assert type(pid) is int and pid>1 and pid!=os.getpid()
            fd=os.pidfd_open(pid);fds[name]=fd
            actual=membership(pid);assert actual.is_relative_to(scope) and actual!=scope
            if name.startswith('audio_worker'):assert actual==Path(ready['audio_leaf'])
            elif name in ('detached_worker','descendant'):assert actual==Path(ready['detached_leaf'])
            else:assert actual==scope/'nvp.host'
        assert len(set(ready[n] for n in fds))==6
        # No chance for the stopped main to perform normal cleanup. Only signal
        # exact pidfds taken from *this* installed fixture after kernel membership proof.
        signal.pidfd_send_signal(fds['host'],signal.SIGSTOP)
        until(lambda:Path('/proc',str(ready['host']),'status').read_text().split('State:')[1].lstrip().startswith('T'),'Host did not stop',5)
        for name in ('audio_guardian','detached_guardian','host'):signal.pidfd_send_signal(fds[name],signal.SIGKILL)
        until(lambda:show(unit,'ActiveState')=='failed','Installed unit did not enter failed state',30)
        assert show(unit,'Result')=='signal'
        for name,fd in fds.items():
            p=select.poll();p.register(fd,select.POLLIN);assert p.poll(10000),name+' remained alive after service stop'
        def empty():
            if not scope.exists():return True
            events=scope/'cgroup.events'
            return events.is_file() and 'populated 0' in events.read_text().splitlines()
        until(empty,'Systemd did not empty the full service subtree',20)
        authority=Path('/var/lib/nvp-service-recovery')/unit
        startfile=authority/(old_inv+'.start.json');stopfile=authority/(old_inv+'.stop.json')
        for record in (startfile,stopfile):
            info=record.lstat();assert info.st_uid==0 and not info.st_mode&0o022 and stat.S_ISREG(info.st_mode) and info.st_nlink==1
        stop=json.loads(stopfile.read_bytes());assert stop['prior_subtree_empty'] and stop['service_result']=='signal'
        assert stop['invocation']==old_inv and stop['scope']==str(scope)
        assert stop['start_sha256']==hashlib.sha256(startfile.read_bytes()).hexdigest()
        stop_digest=hashlib.sha256(stopfile.read_bytes()).hexdigest()
        assert not (state/'restart-complete.json').exists()
        run('systemctl','reset-failed',unit);run('systemctl','start',unit)
        until(lambda:(state/'restart-complete.json').exists(),'Service generation restart failed',90)
        report=json.loads((state/'restart-complete.json').read_text());assert report['old_invocation']==old_inv and report['new_invocation']!=old_inv
        assert report['authenticated_stop_verified'] and report['automatic_audio_recovery_completed']
        assert report['fresh_approval_required'] and report['split_commit_replayed'] and report['old_lease_replay_refused'] and report['changed_task_seal_refused']
        until(lambda:show(unit,'ActiveState')=='inactive','Restart service did not finish normally',20)
        fresh=json.loads((state/'fresh'/'roles-complete.json').read_text());assert len(fresh['roles'])==5
        print(json.dumps({'status':'INSTALLED_QUALIFICATION_SERVICE_PASSED','identity':user,'initial':roles,'restart':fresh,'recovery':report,'all_original_process_pidfds_exited':True,'original_service_subtree_empty':True,'root_stop_record_sha256':stop_digest,'full_desktop_install_accepted':False}),flush=True)
    finally:
        for fd in fds.values():os.close(fd)
        subprocess.run(['systemctl','stop',unit],check=False)
if __name__=='__main__':
    assert os.getuid()==0 and run('systemd-detect-virt')=='qemu'
    for user in ('nvptest','root'):run_fixture(user)
