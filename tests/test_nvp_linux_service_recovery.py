"""Portable parser and authority boundary tests; actual trust is installed guest-tested."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import nvp_linux_service_recovery as recovery


class SystemdGenerationBinding(unittest.TestCase):
    def setUp(self):
        self.unit='nvp-sec06-qualification@nvptest.service'
        self.scope='/sys/fs/cgroup/system.slice/'+self.unit
        self.old='1'*32; self.new='2'*32; self.boot='3'*32
        self.start=dict(format=recovery.FORMAT,kind='start',unit=self.unit,invocation=self.old,boot=self.boot,scope=self.scope,time_ns=10)
        self.stop=dict(self.start,kind='stop',time_ns=20,start_sha256=recovery.digest(self.start),service_result='signal',prior_subtree_empty=True)
        self.current=dict(self.start,invocation=self.new,time_ns=30)
        self.authority=recovery.SystemdRecoveryAuthority(self.unit)

    def check(self,start=None,stop=None,current=None,sha=None,inv=None):
        with patch.object(self.authority,'current',return_value=current or self.current), patch.object(recovery,'_read',side_effect=[start or self.start,stop or self.stop]):
            return self.authority.stopped(inv or self.old,sha or recovery.digest(self.start))

    def test_exact_binding(self):
        self.assertEqual(self.check(),self.stop)

    def test_wrong_digest_and_generation(self):
        for args in ({'sha':'0'*64},{'inv':self.new},{'stop':dict(self.stop,start_sha256='0'*64)},{'stop':dict(self.stop,prior_subtree_empty=False)}):
            with self.subTest(args=args),self.assertRaises(PermissionError):self.check(**args)

    def test_cross_boot_scope_and_reverse_time(self):
        for args in ({'current':dict(self.current,boot='f'*32)},{'stop':dict(self.stop,scope='/sys/fs/cgroup')},{'stop':dict(self.stop,time_ns=40)},{'start':dict(self.start,time_ns=21)}):
            with self.subTest(args=args),self.assertRaises(PermissionError):self.check(**args)

    def test_missing_stop_does_not_invent_witness(self):
        with patch.object(self.authority,'current',return_value=self.current),patch.object(recovery,'_read',side_effect=[self.start,FileNotFoundError()]):
            with self.assertRaises(FileNotFoundError):self.authority.stopped(self.old,recovery.digest(self.start))

    def persistent(self):
        old=dict(self.start,format=recovery.PERSISTENT_FORMAT,machine='4'*32,sequence=1,previous_start_sha256='0'*64)
        current=dict(old,invocation=self.new,boot='5'*32,sequence=2,previous_start_sha256=recovery.digest(old),time_ns=1)
        stop=dict(old,kind='stop',time_ns=2,start_sha256=recovery.digest(old),service_result='cold-reboot',prior_subtree_empty=True,
                  witness_invocation=self.new,witness_start_sha256=recovery.digest(current),witness_boot=current['boot'])
        return old,current,stop

    def test_persistent_cold_boot_requires_exact_later_start(self):
        old,current,stop=self.persistent()
        with patch.object(recovery,'_persistent_chain',return_value=[old,current]),patch.object(recovery,'_machine',return_value=old['machine']):
            self.assertEqual(self.check(old,stop,current,recovery.digest(old)),stop)
            for changed in (dict(stop,witness_boot=old['boot']),dict(stop,witness_invocation=self.old),dict(stop,witness_start_sha256='f'*64),dict(stop,machine='f'*32)):
                with self.assertRaises(PermissionError):self.check(old,changed,current,recovery.digest(old))

    def test_persistent_reboot_hook_does_not_infer_same_boot_stop(self):
        old,current,stop=self.persistent()
        with patch.object(recovery,'_read',side_effect=FileNotFoundError),patch.object(recovery,'_write') as write:
            recovery._cold_stops([old],dict(current,boot=old['boot']))
            write.assert_not_called()
            recovery._cold_stops([old],current)
            actual=write.call_args.args[2]
            self.assertEqual(actual['witness_start_sha256'],recovery.digest(current))
            self.assertEqual(actual['service_result'],'cold-reboot')

    def test_persistent_missing_interior_or_machine_change_denied(self):
        old,current,_=self.persistent()
        with patch.object(recovery,'_trusted_directory',return_value=99),patch.object(recovery.os,'close'),patch.object(recovery.os,'listdir',return_value=[self.new+'.start.json']),patch.object(recovery,'_read_at',return_value=current):
            with self.assertRaises(PermissionError):recovery._persistent_chain(self.unit,old['machine'])
        with patch.object(recovery,'_trusted_directory',return_value=99),patch.object(recovery.os,'close'),patch.object(recovery.os,'listdir',return_value=[self.old+'.start.json']),patch.object(recovery,'_read_at',return_value=old):
            with self.assertRaises(PermissionError):recovery._persistent_chain(self.unit,'f'*32)

    def test_invalid_traversal_and_untrusted_directory(self):
        for name in ('../nvp-x@root.service','nvp-x@../root.service','other@root.service'):
            with self.assertRaises(ValueError):recovery.SystemdRecoveryAuthority(name)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PermissionError):recovery._trusted_directory(Path(tmp))

    def test_control_hook_refuses_other_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            scope=Path(tmp); control=scope/'.control'; control.mkdir()
            (scope/'cgroup.procs').write_text('987654\n')
            (control/'cgroup.procs').write_text(str(__import__('os').getpid()))
            with self.assertRaisesRegex(RuntimeError,'other processes'):recovery._exclusive_hook(scope,control)

if __name__=='__main__':unittest.main()
