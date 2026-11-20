"""Fixed synthetic installed-linux smoke; never handles creator media.

The actual production host and fixed worker entrypoint execute. Only the
resource-admission sample is a synthetic fixture because the VM is intended
for kernel qualification, not native RAM/throughput benchmarking.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import sys


def require_audio_worker_cgroup():
    from backend.nvp_worker_linux_cgroup import current_cgroup_relative, CGROUP_MOUNT
    path=CGROUP_MOUNT/current_cgroup_relative().lstrip('/')
    if not re.fullmatch(r'nvp-worker-[0-9a-f]{32}',path.name):
        raise PermissionError('Frozen audio worker requires its dedicated kernel leaf')
    if os.getxattr(path.parent,'user.delegate')!=b'1':
        raise PermissionError('Frozen audio worker has no delegated parent')
    status=Path('/proc/self/status').read_text('ascii').splitlines()
    if not any(line.split()==['NoNewPrivs:','1'] for line in status):
        raise PermissionError('Frozen audio worker lacks the inherited write fence')
    # This is a context check, not a replacement for the original host's
    # grant/plan admission, guardian or kernel Landlock enforcement.


def run_audio_smoke():
    if sys.platform!='linux' or not getattr(sys,'frozen',False) or os.geteuid()==0:
        raise PermissionError('Installed non-root Linux runtime required')
    import tempfile, wave, struct, hashlib, json
    from backend.nvp_worker_linux_cgroup import current_delegated_parent
    from backend.nvp_audio01e3_native_host import NativeAudioHost
    from backend.nvp_audio01d_chunked_recovery import RATE
    from backend.nvp_resource_ledger import TaskLedger
    from backend.nvp_resource_guard import ResourceSnapshot
    delegated=current_delegated_parent()
    before={p.name for p in delegated.glob('nvp-worker-*')}
    with tempfile.TemporaryDirectory(prefix='nvp-frozen-audio-smoke-') as tmp:
        root=Path(tmp)
        src=root/'generated.wav';frames=RATE*2
        with wave.open(str(src),'wb') as stream:
            stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(RATE)
            stream.writeframes(struct.pack('<hh',1000,-1000)*frames)
        sha=hashlib.sha256(src.read_bytes()).hexdigest()
        ledger=TaskLedger(root/'ledger',sampler=lambda:ResourceSnapshot(0,16000,12000,0.,()))
        host=NativeAudioHost(ledger,root/'jobs',verify_creator_action=lambda event,scope:event=='synthetic-smoke' and scope['final_master'] is False)
        plan={'stems':[{'stem_id':'voice','kind':'dialogue','clips':[{'out_start':0,'out_end':frames,'source_start':0,'fade_in':0,'fade_out':0,'gain_milli':1000}]}]}
        job=host.stage_and_approve(plan,{'voice':src},frames,root/'output','synthetic-smoke')['job_id']
        result=host.run_next(timeout_seconds=180)
        if not result or result.get('state')!='SUCCEEDED':
            # Preserve fixed failure diagnostics in the separate fixture log.
            for name in ('stderr.log','stdout.log'):
                p=root/'jobs'/job/name
                if p.is_file():print(p.read_text(errors='replace')[-4000:],file=sys.stderr)
            raise RuntimeError('Frozen strict audio worker did not complete')
        if ledger.get_task(job)['reserved']!=0 or hashlib.sha256(src.read_bytes()).hexdigest()!=sha:
            raise RuntimeError('Frozen audio reservation/source integrity failed')
        if {p.name for p in delegated.glob('nvp-worker-*')}!=before:
            raise RuntimeError('Frozen worker cgroup was not reaped')
        print(json.dumps({'status':'FROZEN_LINUX_AUDIO_VERIFIED','samples':frames,'strict_kernel':True,'source_unchanged':True,'synthetic_resource_sample':True}),flush=True)
    return 0
