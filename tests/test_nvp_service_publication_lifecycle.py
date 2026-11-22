"""Real filesystem publication fault tests; no OS-stop authority inferred here."""
import os
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend import nvp_linux_service_recovery as r


@unittest.skipUnless(sys.platform=='linux' and os.geteuid()==0,
                     'Root-owned disposable filesystem required; not service custody acceptance')
class PublicationLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/var/lib')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.unit='nvp-test@root.service'
        self.scope=r.CGROUP/'system.slice'/self.unit
        self.machine='a'*32;self.boot='b'*32
        self.patch=patch.object(r,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)
        r._ensure_unit(self.unit)
    def start(self,i,prev=None,boot=None):
        return dict(format=r.PERSISTENT_FORMAT,kind='start',unit=self.unit,invocation=f'{i:032x}',
                    boot=boot or self.boot,scope=str(self.scope),time_ns=i,machine=self.machine,
                    sequence=i,previous_start_sha256=r.digest(prev) if prev else '0'*64)
    def child_crash(self,doc,after_link):
        code="""import os,sys,json
from pathlib import Path
from backend import nvp_linux_service_recovery as r
r.ROOT=Path(sys.argv[1]);r.MAX_GENERATIONS=int(sys.argv[2]);doc=json.loads(sys.argv[3]);after=sys.argv[4]=='1'
real=os.link
def die(*a,**kw):
    if after: real(*a,**kw)
    os._exit(79)
os.link=die
r._write(doc['unit'],doc['kind'],doc)
os._exit(81)
"""
        proc=subprocess.run([sys.executable,'-c',code,str(self.root),str(r.MAX_GENERATIONS),json.dumps(doc),str(int(after_link))],timeout=15)
        self.assertEqual(proc.returncode,79)
    def test_before_link_does_not_publish_evidence(self):
        doc=self.start(1);self.child_crash(doc,False)
        with self.assertRaises(FileNotFoundError):r._read(self.unit,doc['invocation'],'start')
        r._repair_pending(self.unit)
        self.assertEqual(list((self.root/self.unit).iterdir()),[])
        r._write(self.unit,'start',doc);self.assertEqual(r._read(self.unit,doc['invocation'],'start'),doc)
    def test_after_link_repair_and_exact_replay(self):
        doc=self.start(1);self.child_crash(doc,True)
        with self.assertRaises(PermissionError):r._read(self.unit,doc['invocation'],'start')
        r._repair_pending(self.unit);r._write(self.unit,'start',doc)
        self.assertEqual(r._read(self.unit,doc['invocation'],'start'),doc)
        with self.assertRaises(PermissionError):r._write(self.unit,'start',dict(doc,time_ns=99))
    def test_interrupted_stop_link_keeps_exact_digest(self):
        doc=self.start(1);r._write(self.unit,'start',doc)
        stop=dict(doc,kind='stop',time_ns=2,start_sha256=r.digest(doc),service_result='signal',prior_subtree_empty=True)
        self.child_crash(stop,True)
        with self.assertRaises(PermissionError):r._read(self.unit,doc['invocation'],'stop')
        r._repair_pending(self.unit)
        with patch.dict(os.environ,SERVICE_RESULT='signal'):
            r._publish_hook('stop',self.unit,doc['invocation'],self.scope,self.boot,self.machine)
        self.assertEqual(r._read(self.unit,doc['invocation'],'stop'),stop)

    def test_foreign_link_refused(self):
        doc=self.start(1);self.child_crash(doc,True)
        pending=next((self.root/self.unit).glob('.pending-*'))
        os.link(pending,self.root/'foreign')
        with self.assertRaises(PermissionError):r._repair_pending(self.unit)
        self.assertTrue(pending.exists())
    def test_segment_rollover_and_recovery_after_hook_start_commit(self):
        with patch.object(r,'MAX_GENERATIONS',2):
            first=self.start(1);second=self.start(2,first);third=self.start(3,second,'c'*32)
            for doc in (first,second):r._write(self.unit,'start',doc)
            # Publish later boot's start, then die before publishing its cold stops.
            self.child_crash(third,True);r._repair_pending(self.unit)
            r._publish_hook('start',self.unit,third['invocation'],self.scope,third['boot'],self.machine)
            chain=r._persistent_chain(self.unit,self.machine);self.assertEqual(chain,[first,second,third])
            self.assertEqual(r._read(self.unit,third['invocation'],'start'),third)
            for old in (first,second):
                witness=r._read(self.unit,old['invocation'],'stop')
                self.assertEqual(witness['witness_start_sha256'],r.digest(third))
            before=r._read(self.unit,first['invocation'],'stop')
            r._publish_hook('start',self.unit,third['invocation'],self.scope,third['boot'],self.machine)
            self.assertEqual(r._read(self.unit,first['invocation'],'stop'),before)
            with patch.dict(os.environ,SERVICE_RESULT='success'):
                r._publish_hook('stop',self.unit,third['invocation'],self.scope,third['boot'],self.machine)
                stop=r._read(self.unit,third['invocation'],'stop')
                r._publish_hook('stop',self.unit,third['invocation'],self.scope,third['boot'],self.machine)
                self.assertEqual(stop,r._read(self.unit,third['invocation'],'stop'))
            with patch.dict(os.environ,SERVICE_RESULT='signal'),self.assertRaises(PermissionError):
                r._publish_hook('stop',self.unit,third['invocation'],self.scope,third['boot'],self.machine)
            with self.assertRaises(PermissionError):r._publish_hook('start',self.unit,third['invocation'],self.scope,third['boot'],self.machine)
            # Old evidence remains readable, even when its witness is in a later segment.
            authority=r.SystemdRecoveryAuthority(self.unit)
            with patch.object(authority,'current',return_value=third),patch.object(r,'_machine',return_value=self.machine):
                self.assertEqual(authority.stopped(first['invocation'],r.digest(first)),before)
            # Any duplicate or removed interior start must fail closed.
            folder=self.root/self.unit;name=third['invocation']+'.start.json'
            (folder/name).write_bytes((folder/'segment-0001'/name).read_bytes())
            with self.assertRaises(PermissionError):r._persistent_chain(self.unit,self.machine)
            (folder/name).unlink();(folder/(second['invocation']+'.start.json')).unlink()
            with self.assertRaises(PermissionError):r._persistent_chain(self.unit,self.machine)

if __name__=='__main__':unittest.main()
