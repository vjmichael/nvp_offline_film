"""Installed *qualification-only* service: real native worker and double-loss tests.

Not an NVP desktop entrypoint or production service. Never handles creator media.
Run only from the root-owned package's fixed systemd unit in the disposable lab.
"""
from __future__ import annotations
import hashlib, json, os, sys, time, threading, struct, wave
from pathlib import Path
# Installed entrypoint is invoked with -I; imports from the root-owned exact tree.
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.nvp_w1g_protected_native_worker import ProtectedNativeWorker
from backend.nvp_w1g_first_party_result_verifier import verify_bounded_first_party_role
from backend.nvp_worker_linux_cgroup import current_delegated_parent
from backend.nvp_worker_containment import launch_contained
from backend.nvp_audio01e3_native_host import NativeAudioHost
from backend.nvp_linux_service_recovery import SystemdRecoveryAuthority, ROOT as AUTHORITY_ROOT, digest as authority_digest
from backend.nvp_resource_ledger import TaskLedger
from backend.nvp_resource_guard import ResourceSnapshot
from backend.nvp_audio01d_chunked_recovery import RATE
from tools.nvp_w1g_worker_package import verify_native_workers

PACKAGE=Path('/opt/nvp-sec06-qualification')

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def atomic(path,doc):
    temp=path.with_suffix('.new')
    with temp.open('x') as f:
        json.dump(doc,f,sort_keys=True);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def native_roles(state):
    runtime=state/'roles';runtime.mkdir()
    verified=verify_native_workers(PACKAGE/'bundle',expected_platform='linux-amd64')
    assert len(verified['roles'])==5
    seen=set(); approvals=[]
    def approve(scope):
        # This consent is limited to generated qualification media, never creator data.
        assert scope['project_id']=='SEC06GeneratedFixture' and scope['job_id'] not in seen
        seen.add(scope['job_id']);approvals.append(scope);return True
    def kernel(scope,receipt):
        return (scope in approvals and receipt['os_provenance']=='linux-cgroup-v2' and
            receipt['process_tree_custody_verified'] is True and receipt['guardian_exit_verified'] is True and
            receipt['cgroup_leaf_removed'] is True)
    worker=ProtectedNativeWorker(PACKAGE/'bundle',runtime,platform='linux-amd64',native_approve=approve,
        independent_verify=verify_bounded_first_party_role,independent_os_custody=kernel)
    pcm=struct.pack('<6h',0,1,500,-500,30000,-30000)
    inputs={'original_capture':{'source.pcm':pcm},'scene_render':{'scene.txt':b'64 48\n'},
            'editorial':{'source.pcm':pcm,'edit.txt':b'1 3\n'},'audio':{'source.pcm':pcm,'gain.txt':b'2 1\n'}}
    outputs={};results=[]
    for role in ('original_capture','scene_render','editorial','audio','delivery'):
        if role=='delivery':inputs[role]={'render.ppm':outputs['scene_render'],'mix.pcm':outputs['audio']}
        receipt=worker.run(role,'SEC06GeneratedFixture',{'project_id':'SEC06GeneratedFixture','role':role},
                           sealed_inputs=inputs[role],memory_mb=512,timeout_s=30)
        assert receipt['state']=='SUCCEEDED_VERIFIED' and receipt['process_tree_custody_verified'] is True
        folder=runtime/receipt['job_id'];result=json.loads((folder/'result.json').read_text());out=(folder/result['output_name']).read_bytes()
        assert all((folder/name).read_bytes()==data for name,data in inputs[role].items())
        outputs[role]=out;results.append({'role':role,'worker_sha256':receipt['worker_sha256'],'output_sha256':hashlib.sha256(out).hexdigest(),'output_bytes':len(out),'kernel':receipt['os_custody_receipt']})
    assert outputs['audio']==struct.pack('<6h',0,2,1000,-1000,32767,-32768)
    assert outputs['delivery'][24:]==outputs['scene_render']+outputs['audio']
    atomic(state/'roles-complete.json',{'roles':results,'release_accepted':False,'qualification_only':True})

def audio_host(state):
    # Deterministic sensor is solely the original synthetic fixture's admission input.
    ledger=TaskLedger(state/'ledger',sampler=lambda:ResourceSnapshot(0,16000,12000,0.,tuple()))
    host=NativeAudioHost(ledger,state/'native',verify_creator_action=lambda event,scope:scope['final_master'] is False and ((event=='creator_confirmed' and 'action' not in scope) or (event=='creator_abandoned' and scope.get('action')=='abandon_interrupted_audio')),strict_linux_tree=True,systemd_recovery=SystemdRecoveryAuthority("nvp-sec06-qualification@"+state.parent.name.removeprefix("nvp-sec06-")+".service"))
    return host,ledger

def begin(state):
    native_roles(state)
    audio=state/'audio';audio.mkdir();host,ledger=audio_host(audio)
    src=audio/'dialogue.wav';n=RATE*3
    with wave.open(str(src),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(RATE);f.writeframes(struct.pack('<hh',1000,-1000)*n)
    plan={'stems':[{'stem_id':'voice','kind':'dialogue','clips':[{'out_start':0,'out_end':n,'source_start':0,'fade_in':0,'fade_out':0,'gain_milli':1000}]}]}
    # Reservation and generation binding must be durable together, even if
    # power is lost before the running journal transition or worker launch.
    prelaunch=host.stage_and_approve(plan,{'voice':src},n,audio/'never-started','creator_confirmed',ram_mb=1024,duration_s=3600)['job_id']
    claimed=host._claim_next();assert claimed['task_id']==prelaunch and claimed['admitted']
    assert host.journal.read(prelaunch)['state']=='approved' and not (audio/'never-started').exists()
    with ledger._db() as db:
        assert db.execute('SELECT invocation FROM audio_native_service_bindings WHERE job_id=?',(prelaunch,)).fetchone()==(os.environ['INVOCATION_ID'],)
    running_prelaunch=host.stage_and_approve(plan,{'voice':src},n,audio/'never-started-running','creator_confirmed',ram_mb=1024,duration_s=3600)['job_id']
    claimed=host._claim_next();assert claimed['task_id']==running_prelaunch and claimed['admitted']
    host.journal.transition(running_prelaunch,0,'running','native_os_worker_admitted')
    with ledger._db() as db:
        assert db.execute('SELECT phase FROM audio_native_launch_boundaries WHERE job_id=?',(running_prelaunch,)).fetchone()==('reserved',)
    uncertain=host.stage_and_approve(plan,{'voice':src},n,audio/'launch-intended-missing','creator_confirmed',ram_mb=1024,duration_s=3600)['job_id']
    claimed=host._claim_next();assert claimed['task_id']==uncertain and claimed['admitted']
    host.journal.transition(uncertain,0,'running','native_os_worker_admitted')
    host._mark_launch_intent(uncertain)
    # Host-owned initial publication cut points, before launch intent.
    from backend.nvp_audio_initial_output import initial_bytes
    stage_jobs={}
    for kind in ('empty','partial','linked'):
        target=audio/('initial-'+kind)
        stage_job=host.stage_and_approve(plan,{'voice':src},n,target,'creator_confirmed',ram_mb=1024,duration_s=3600)['job_id']
        assert host._claim_next()['task_id']==stage_job
        host.journal.transition(stage_job,0,'running','native_os_worker_admitted')
        sha=host._record_initial_output_intent(stage_job)
        raw=initial_bytes(host.journal.read(stage_job)['spec']);assert hashlib.sha256(raw).hexdigest()==sha
        target.mkdir(mode=0o700)
        if kind=='partial':(target/'checkpoint.json.new').write_bytes(raw[:len(raw)//2])
        if kind=='linked':
            (target/'checkpoint.json.new').write_bytes(raw)
            os.link(target/'checkpoint.json.new',target/'checkpoint.json')
        stage_jobs[kind]=stage_job
    job=host.stage_and_approve(plan,{'voice':src},n,audio/'rendered','creator_confirmed',ram_mb=1024,duration_s=3600)['job_id']
    os.environ['NVP_NATIVE_TERMINATION_TEST']='1'
    result={}
    def task():
        try:result['value']=host.run_next(timeout_seconds=100,test_hold=True)
        except BaseException as exc:result['error']=repr(exc)
    thread=threading.Thread(target=task,daemon=True);thread.start()
    limit=time.monotonic()+45
    while time.monotonic()<limit and not ((audio/'native'/job/'test_worker_ready').exists() and job in host._running):
        if result: raise RuntimeError(str(result))
        time.sleep(.05)
    proc=host._running[job];assert proc.poll() is None
    # Independent detached descendant fixture, separate leaf, same service.
    d=state/'detached';d.mkdir()
    code="import subprocess,json,sys,time,os;from pathlib import Path;p=subprocess.Popen([sys.executable,'-S','-c','import time;time.sleep(120)'],start_new_session=True);Path('child.json').write_text(json.dumps({'child':os.getpid(),'descendant':p.pid}));time.sleep(120)"
    with (d/'out').open('wb') as out,(d/'err').open('wb') as err:
        tree=launch_contained([sys.executable,'-S','-c',code],cwd=str(d),stdout=out,stderr=err,memory_mb=512,linux_cgroup_tree_required=True)
        limit=time.monotonic()+20
        while time.monotonic()<limit and not (d/'child.json').is_file():time.sleep(.05)
        child=json.loads((d/'child.json').read_text());assert child['child']==tree.pid
        chunk=audio/'rendered'/'mix_chunk_0000000.pcm';assert chunk.is_file()
        atomic(state/'ready.json',{'host':os.getpid(),'uid':os.getuid(),'invocation':os.environ['INVOCATION_ID'],
            'delegation':str(current_delegated_parent()),'audio_job':job,'prelaunch_job':prelaunch,'running_prelaunch_job':running_prelaunch,'uncertain_job':uncertain,'stage_jobs':stage_jobs,'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-',''),'audio_guardian':proc._guardian.pid,'audio_worker':proc.pid,'audio_leaf':str(proc.cgroup),
            'detached_guardian':tree._guardian.pid,'detached_worker':tree.pid,'detached_leaf':str(tree.cgroup),'descendant':child['descendant'],
            'first_chunk_sha256':digest(chunk),'source_sha256':digest(src)})
        # External systemd controller kills both guardians and the main process.
        # Never return a success receipt from this deliberately interrupted run.
        time.sleep(120)
        raise RuntimeError('Expected external double-loss fault was not delivered')

def restart(state):
    prior=json.loads((state/'ready.json').read_text());assert prior['invocation']!=os.environ['INVOCATION_ID']
    host,ledger=audio_host(state/'audio');job=prior['audio_job'];row=host.journal.read(job)
    assert ledger.get_task(job)['state']=='ACTIVE' and row['state']=='running'
    with ledger._db() as db:
        assert db.execute('SELECT worker_reaped FROM audio_native_os_stop_receipts WHERE job_id=?',(job,)).fetchone() is None
    try:host.recover_stopped(job)
    except RuntimeError as e:assert 'OS-cleaned interrupted admission' in str(e)
    else:raise AssertionError('A process-name or stale journal must not authorize recovery')
    assert ledger.get_task(job)['state']=='ACTIVE'
    assert digest(state/'audio'/'rendered'/'mix_chunk_0000000.pcm')==prior['first_chunk_sha256']
    assert digest(state/'audio'/'dialogue.wav')==prior['source_sha256']
    # Only the root-owned installed systemd hook can authorize the old admission.
    old_inv=prior['invocation']; authority=host.systemd_recovery
    prelaunch=prior['prelaunch_job']
    assert ledger.get_task(prelaunch)['state']=='ACTIVE' and host.journal.read(prelaunch)['state']=='approved'
    closed=host.recover_systemd_interrupted(prelaunch)
    assert closed['prelaunch_closed'] and not closed['worker_started'] and closed['next_sample']==0
    assert host.recover_systemd_interrupted(prelaunch)==closed
    assert ledger.get_task(prelaunch)['state']=='INTERRUPTED' and host.journal.read(prelaunch)['state']=='failed'
    assert host._grant(prelaunch)['revoked'] and not (state/'audio'/'never-started').exists()
    with ledger._db() as db:
        assert db.execute('SELECT job_id FROM audio_native_staging_leases WHERE job_id=?',(prelaunch,)).fetchone() is None

    running_prelaunch=prior['running_prelaunch_job']
    assert ledger.get_task(running_prelaunch)['state']=='ACTIVE' and host.journal.read(running_prelaunch)['state']=='running'
    closed_running=host.recover_systemd_interrupted(running_prelaunch)
    assert closed_running['prelaunch_closed'] and not closed_running['worker_started']
    assert host.recover_systemd_interrupted(running_prelaunch)==closed_running
    assert host.journal.read(running_prelaunch)['state']=='failed' and host._grant(running_prelaunch)['revoked']
    assert not (state/'audio'/'never-started-running').exists()
    with ledger._db() as db:
        assert db.execute('SELECT phase FROM audio_native_launch_boundaries WHERE job_id=?',(job,)).fetchone()==('launch-intent',)
        assert db.execute('SELECT job_id FROM audio_native_staging_leases WHERE job_id=?',(running_prelaunch,)).fetchone() is None

    uncertain=prior['uncertain_job']
    try:host.recover_systemd_interrupted(uncertain)
    except PermissionError as exc:assert 'Missing audio output' in str(exc)
    else:raise AssertionError('Missing output after launch intent must remain quarantined')
    assert ledger.get_task(uncertain)['state']=='ACTIVE' and not host._grant(uncertain)['revoked']
    for bad in ('creator_confirmed','not_approved'):
        try:host.abandon_systemd_missing_output(uncertain,creator_event=bad)
        except PermissionError:pass
        else:raise AssertionError('Old or denied approval resolved quarantine')
    assert ledger.get_task(uncertain)['state']=='ACTIVE'
    # Crash after the atomic abandonment commit, before journal closure.
    transition=host.journal.transition
    def stop_abandon(*args,**kwargs):raise RuntimeError('interrupted abandonment fixture')
    host.journal.transition=stop_abandon
    try:host.abandon_systemd_missing_output(uncertain,creator_event='creator_abandoned')
    except RuntimeError as exc:assert 'interrupted abandonment fixture' in str(exc)
    else:raise AssertionError('Expected interrupted abandonment')
    assert ledger.get_task(uncertain)['state']=='INTERRUPTED' and host._grant(uncertain)['revoked']
    host,ledger=audio_host(state/'audio')
    closed=host.recover_systemd_interrupted(uncertain)
    assert closed=={'state':'failed','abandoned':True,'worker_started':None,'next_sample':0}
    assert host.abandon_systemd_missing_output(uncertain,creator_event='creator_abandoned')==closed
    assert not (state/'audio'/'launch-intended-missing').exists()
    for kind,stage_job in prior['stage_jobs'].items():
        from backend.nvp_audio_initial_output import initial_bytes
        row=host.journal.read(stage_job);spec=row['spec'];target=Path(spec['directory']);raw=initial_bytes(spec)
        result=host.recover_systemd_interrupted(stage_job)
        assert result['state']=='reconciled' and result['next_sample']==0
        assert (target/'checkpoint.json').read_bytes()==raw and sorted(p.name for p in target.iterdir())==['checkpoint.json']
        if kind=='partial':
            residue=raw[:len(raw)//2];ev=host.root/stage_job/('initial-stage-'+hashlib.sha256(residue).hexdigest()+'.bin')
            assert ev.read_bytes()==residue
        assert host.recover_systemd_interrupted(stage_job)['already_reconciled'] is True

    with ledger._db() as db:
        binding=db.execute('SELECT invocation,start_sha FROM audio_native_service_bindings WHERE job_id=?',(job,)).fetchone()
    assert binding and binding[0]==old_inv
    # Same-generation and wrong-start hash are refused, no reservation release.
    for inv,sha in ((os.environ['INVOCATION_ID'],binding[1]),(old_inv,'0'*64)):
        try: authority.stopped(inv,sha)
        except PermissionError: pass
        else: raise AssertionError('Unbound generation was accepted')
    assert ledger.get_task(job)['state']=='ACTIVE'
    if os.getuid()!=0:
        witness=AUTHORITY_ROOT/authority.unit/(old_inv+'.stop.json')
        try:
            with witness.open('ab') as f: f.write(b'forgery')
        except PermissionError: pass
        else: raise AssertionError('Unprivileged host rewrote root stop authority')
    # Even with a genuine stop receipt, a changed immutable approval cannot
    # release the original reservation. Restore fixture data after denial.
    with ledger._db() as db:
        original=db.execute('SELECT spec_json FROM authorized_task_specs WHERE task_id=?',(job,)).fetchone()[0]
        db.execute('UPDATE authorized_task_specs SET spec_json=? WHERE task_id=?',(original+' ',job));db.commit()
    try:host.recover_systemd_interrupted(job)
    except PermissionError:pass
    else:raise AssertionError('Changed task seal authenticated')
    assert ledger.get_task(job)['state']=='ACTIVE'
    with ledger._db() as db:
        db.execute('UPDATE authorized_task_specs SET spec_json=? WHERE task_id=?',(original,job));db.commit()
    # Simulate second host loss after the genuine durable stop transaction by
    # interrupting before the separate journal transition. Reopening must replay.
    transition=host.journal.transition
    def interrupt(*args,**kwargs): raise RuntimeError('fixture interrupted after durable stop commit')
    host.journal.transition=interrupt
    try:host.recover_systemd_interrupted(job)
    except RuntimeError as e:assert 'fixture interrupted' in str(e)
    else:raise AssertionError('Recovery fault not injected')
    assert ledger.get_task(job)['state']=='INTERRUPTED' and host.journal.read(job)['state']=='running'
    host,ledger=audio_host(state/'audio')
    result=host.recover_systemd_interrupted(job);assert result['state']=='reconciled'
    assert host.recover_systemd_interrupted(job)['already_reconciled'] is True
    spec=host.journal.read(job)['spec']
    try:host.stage_and_approve(spec['plan'],spec['sources'],spec['total_samples'],spec['directory'],'not_approved',resume_from=job)
    except PermissionError:pass
    else:raise AssertionError('Stop witness was used as creator consent')
    continuation=host.stage_and_approve(spec['plan'],spec['sources'],spec['total_samples'],spec['directory'],'creator_confirmed',ram_mb=1024,duration_s=3600,resume_from=job)['job_id']
    assert continuation!=job
    complete=host.run_next(timeout_seconds=100);assert complete['state']=='SUCCEEDED' and complete['job_id']==continuation
    assert digest(state/'audio'/'rendered'/'mix_chunk_0000000.pcm')==prior['first_chunk_sha256']
    assert digest(state/'audio'/'dialogue.wav')==prior['source_sha256']
    try:host.recover_systemd_interrupted(job)
    except PermissionError:pass
    else:raise AssertionError('Old recovery replayed after lease transfer')
    # Fresh authorized role work must still be possible under the new service generation.
    fresh=state/'fresh';fresh.mkdir();native_roles(fresh)
    atomic(state/'restart-complete.json',{'new_invocation':os.environ['INVOCATION_ID'],'old_invocation':prior['invocation'],'old_audio_quarantined':False,'automatic_audio_recovery_completed':True,'authenticated_stop_verified':True,'fresh_approval_required':True,'split_commit_replayed':True,'old_lease_replay_refused':True,'changed_task_seal_refused':True,'continuation_job':continuation,'new_native_roles_pass':True,'source_and_checkpoint_preserved':True,'prelaunch_closed':True,'running_prelaunch_closed':True,'missing_after_launch_intent_quarantined':True,'explicit_quarantine_abandoned':True,'initial_stage_jobs_reconciled':len(prior['stage_jobs']),'old_boot':prior['boot'],'new_boot':authority.current()['boot'],'witness_kind':authority.stopped(binding[0],binding[1])['service_result']})

def main():
    assert ROOT==PACKAGE/'source' and os.environ.get('INVOCATION_ID') and Path.cwd()==Path(os.environ['STATE_DIRECTORY'])
    state=Path.cwd();assert current_delegated_parent()!=Path('/sys/fs/cgroup')
    if (state/'ready.json').exists():restart(state)
    else:begin(state)

if __name__=='__main__':main()
