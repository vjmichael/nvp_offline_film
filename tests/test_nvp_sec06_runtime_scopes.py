"""SEC-06 real Linux permissions; no mocked worker/kernel receipts."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from backend.nvp_worker_containment import launch_contained
from backend.nvp_audio01e3_native_host import NativeAudioHost
from tests import test_audio_native_os_termination as prior

@unittest.skipUnless(sys.platform=='linux' and os.environ.get('NVP_REQUIRE_DELEGATED_CGROUP')=='1','Explicit real delegation required; skip is not acceptance')
class KernelWriteScopes(unittest.TestCase):
    def test_filesystem_mutation_denied_outside_exact_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);job=root/'job';job.mkdir();dest=root/'output';dest.mkdir();outside=root/'existing';outside.write_text('original')
            code=r'''import json,os,sys
from pathlib import Path
root=Path(sys.argv[1]);out=root/'output';victim=root/'existing'
Path('local').write_text('local');(out/'pcm').write_text('allowed')
ops={'write':lambda:victim.write_text('bad'),'unlink':victim.unlink,'mkdir':lambda:(root/'bad-dir').mkdir(),'create':lambda:(root/'new').touch(),'rename':lambda:victim.rename(out/'renamed'),'symlink':lambda:(root/'alias').symlink_to(victim),'hardlink':lambda:os.link(victim,out/'link')}
result={}
for name,op in ops.items():
    try:op();result[name]=False
    except OSError as e:result[name]=e.errno in (1,13,18,30)
print(json.dumps(result))'''
            with (job/'stdout').open('wb') as out,(job/'stderr').open('wb') as err:
                proc=launch_contained([str(Path(sys.executable).resolve()),'-c',code,str(root)],cwd=str(job),stdout=out,stderr=err,memory_mb=512,linux_cgroup_tree_required=True,linux_audio_output=str(dest))
                try:self.assertEqual(proc.wait(timeout=25),0,(job/'stderr').read_text())
                finally:proc.close()
            self.assertTrue(all(json.loads((job/'stdout').read_text()).values()),(job/'stdout').read_text());self.assertEqual(outside.read_text(),'original');self.assertEqual((dest/'pcm').read_text(),'allowed');self.assertEqual((job/'local').read_text(),'local')
            self.assertFalse((root/'new').exists());self.assertFalse((root/'bad-dir').exists());self.assertFalse((root/'alias').exists())

@unittest.skipUnless(sys.platform=='linux' and os.environ.get('NVP_REQUIRE_DELEGATED_CGROUP')=='1','Explicit real delegation required; skip is not acceptance')
class StrictAudioProduction(unittest.TestCase):
    def test_actual_audio_worker_cgroup_cancel_restart_and_completion(self):
        fixture=prior.ActualAudioContainment(methodName='test_real_os_terminate_tree_then_durable_recovery')
        fixture.setUp()
        try:
            fixture.host.strict_linux_tree=True
            job=fixture.prepare();thread,result=fixture.run_background();proc=fixture.started(job)
            leaf=proc.cgroup;self.assertIn(str(proc.pid),(leaf/'cgroup.procs').read_text().split());self.assertEqual((leaf/'memory.max').read_text().strip(),str(1024*1024*1024))
            proc.terminate_tree();thread.join(timeout=35);self.assertFalse(thread.is_alive());self.assertIn('error',result)
            self.assertEqual(fixture.ledger.get_task(job)['state'],'INTERRUPTED');self.assertFalse(leaf.exists())
            restarted=NativeAudioHost(fixture.ledger,fixture.root/'native',verify_creator_action=fixture.host.creator,strict_linux_tree=True)
            proof=restarted.recover_stopped(job);self.assertEqual(proof['state'],'reconciled');self.assertGreaterEqual(proof['next_sample'],prior.RATE)
            chunk=fixture.root/'rendered'/'mix_chunk_0000000.pcm';first=chunk.read_bytes()
            resumed=restarted.stage_and_approve(fixture.plan,{'voice':fixture.src},fixture.n,fixture.root/'rendered','creator_confirmed',ram_mb=1024,duration_s=3600,resume_from=job)
            self.assertNotEqual(resumed['job_id'],job);final=restarted.run_next(timeout_seconds=60)
            self.assertEqual(final['state'],'SUCCEEDED');self.assertEqual(chunk.read_bytes(),first);self.assertEqual(fixture.ledger.get_task(job)['state'],'INTERRUPTED')
        finally:fixture.tearDown()
