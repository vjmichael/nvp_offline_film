"""Separate bootstrap and payload fence: actual guest kernel, not a mocked receipt."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from backend.nvp_worker_private_sandbox import sandbox_command_with_landlock
from backend.nvp_worker_containment import launch_contained

class BootstrapContract(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux','Linux namespace argv')
    def test_fixed_bootstrap_precedes_reviewed_payload(self):
        with tempfile.TemporaryDirectory() as d, patch('backend.nvp_worker_private_sandbox._pinned_linux_bwrap',return_value='a'*64):
            cmd=sandbox_command_with_landlock(['/usr/bin/python3','-V'],d)
            self.assertEqual(cmd[0],'/usr/bin/bwrap')
            for x in ('--unshare-user','--unshare-net','--unshare-mnt' if '--unshare-mnt' in cmd else '--unshare-pid','--clearenv','--die-with-parent','--cap-drop'):
                self.assertIn(x,cmd)
            self.assertEqual(cmd[cmd.index('--cap-drop')+1],'ALL')
            i=cmd.index('--');self.assertEqual(cmd[i+1:i+5],['/usr/bin/python3','-I','-S','-c'])
            self.assertIn('restrict_strict_worker_writes(Path.cwd(),inside_private_namespace=True)',cmd[i+5])
            self.assertEqual(cmd[-2:],['/usr/bin/python3','-V'])
            self.assertNotIn('--share-net',cmd)
    def test_private_and_device_spool_cannot_mix(self):
        with self.assertRaisesRegex(PermissionError,'distinct policies'):
            launch_contained(['/usr/bin/python3','-V'],cwd='/tmp',stdout=None,stderr=None,memory_mb=1024,linux_cgroup_tree_required=True,private_isolation_required=True,linux_write_spool='/tmp')

@unittest.skipUnless(sys.platform=='linux' and os.getenv('NVP_REQUIRE_REAL_P1F_KERNEL')=='1','Explicit real kernel required')
class ActualPayloadFence(unittest.TestCase):
    def test_kernel_denies_payload_proc_and_outside_job_writes(self):
        with tempfile.TemporaryDirectory(prefix='nvp-p1f-fence-') as d:
            job=Path(d)/'job';job.mkdir(); script=r'''
import json,os
from pathlib import Path
out={}
Path('allowed').write_text('yes');out['job_write']=Path('allowed').read_text()=='yes'
for name,p in [('outside','/tmp/unauthorized-write'),('proc','/proc/self/oom_score_adj')]:
    try:
        with open(p,'w') as f:f.write('0')
    except OSError as exc:out[name]=exc.errno
    else:out[name]=0
out['cgroup_hidden']=not Path('/sys/fs/cgroup').exists()
status=Path('/proc/self/status').read_text().splitlines()
out['nnp']=next(x.split()[1] for x in status if x.startswith('NoNewPrivs:'))
out['capeff']=next(x.split()[1] for x in status if x.startswith('CapEff:'))
print(json.dumps(out))
'''
            with (job/'out').open('wb') as o,(job/'err').open('wb') as e:
                p=launch_contained(['/usr/bin/python3','-I','-S','-c',script],cwd=str(job),stdout=o,stderr=e,memory_mb=1024,linux_cgroup_tree_required=True,private_isolation_required=True)
                try:self.assertEqual(p.wait(timeout=15),0,(job/'err').read_text())
                finally:p.close()
            report=json.loads((job/'out').read_text())
            self.assertTrue(report['job_write']);self.assertTrue(report['cgroup_hidden'])
            self.assertIn(report['outside'],(1,13,30));self.assertIn(report['proc'],(1,13,30))
            self.assertEqual(report['nnp'],'1');self.assertEqual(int(report['capeff'],16),0)
