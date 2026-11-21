"""NVP R3-R2: real Debian Linux kernel UDS peer + fixture-only Lu 1.0 Health.

The separate process is an unprivileged local protocol fixture, NOT Lu Core.
No executable package, signed enrollment, Windows named pipe, Rust/prost, or
real Core Health dispatcher is authenticated by this test.
"""
from __future__ import annotations

import hashlib
import hmac
import multiprocessing
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import nvp_lu_ipc_v0 as wire

_PACKAGE=b'P'*32
_KEY=b'K'*32


def _local_fixture_server(endpoint: str, control, mode: str) -> None:
    """Actual OS subprocess; deliberately no installer or effect authority."""
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
            listener.bind(endpoint)
            os.chmod(endpoint,0o600)
            listener.listen(1)
            listener.settimeout(5)
            control.send(('ready',os.getpid()))
            with listener.accept()[0] as s:
                s.settimeout(3)
                # Actual Linux kernel peer witness, not a self-declared PID.
                credentials=s.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12)
                import struct
                client_pid,client_uid,_=struct.unpack('3i',credentials)
                if client_pid<=0 or client_uid!=os.getuid():
                    raise RuntimeError('wrong kernel peer credentials')
                msg=wire.read_frame(s)
                if msg.WhichOneof('body')!='hello' or msg.hello.claimed_module_id!='nvp.film':
                    raise RuntimeError('unexpected client Hello')
                if msg.hello.claimed_package_sha256 != _PACKAGE or len(msg.hello.client_nonce)!=32:
                    raise RuntimeError('invalid fixture package or nonce')
                original=wire._canonical(msg)
                request_id=msg.request_id
                nonce=b'N'*32
                wire.write_frame(s,wire.LU['WorkspaceFrame'](protocol_major=1,
                    protocol_minor=0,request_id=request_id,
                    auth_challenge=wire.LU['AuthChallenge'](server_nonce=nonce)))
                proof=wire.read_frame(s)
                expected=hmac.new(_KEY,b'lu.workspace.client.v0\0'+original+nonce,
                                  hashlib.sha256).digest()
                if proof.WhichOneof('body')!='auth_proof' or not hmac.compare_digest(
                        expected,proof.auth_proof.client_hmac_sha256):
                    # Never issue a Welcome to a caller with an invalid key.
                    control.send(('invalid_client_proof',client_pid))
                    return
                session='host-session-nvp'
                welcome=wire.LU['Welcome'](selected_major=1,selected_minor=0,
                    core_epoch_ref='core-epoch-fixture',enabled_features=[])
                unsigned=welcome.SerializeToString(deterministic=True)
                signature=hmac.new(_KEY,b'lu.workspace.server.v0\0'+original+nonce+
                                   session.encode()+unsigned,hashlib.sha256).digest()
                if mode=='forged_welcome':signature=b'\x00'*32
                welcome.server_hmac_sha256=signature
                wire.write_frame(s,wire.LU['WorkspaceFrame'](protocol_major=1,
                    protocol_minor=0,request_id=request_id,session_ref=session,
                    welcome=welcome))
                if mode=='forged_welcome':
                    control.send(('forged_welcome_sent',client_pid))
                    return
                health=wire.read_frame(s)
                if health.WhichOneof('body')!='health' or health.session_ref!=session:
                    raise RuntimeError('health request not in signed session')
                result_session='incorrect-session' if mode=='wrong_session' else session
                wire.write_frame(s,wire.LU['WorkspaceFrame'](protocol_major=1,
                    protocol_minor=0,request_id=health.request_id,
                    session_ref=result_session,
                    health_report=wire.LU['HealthReport'](
                        module_id='lu.core',connected=True,status_code='READY',epoch=8)))
                control.send(('fixture_health_replied',client_pid))
    except Exception as exc:
        try:control.send(('fixture_error',type(exc).__name__,str(exc)))
        except Exception:pass
    finally:
        control.close()


@unittest.skipUnless(sys.platform=='linux' and hasattr(socket,'SO_PEERCRED'),
                     'genuine Linux AF_UNIX SO_PEERCRED only')
class DebianNativeSocketRoundtrip(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nvp-r3r2-',dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.dir=Path(self.temp.name)
        self.dir.chmod(0o700)
        self.endpoint=self.dir/'host.sock'
        self.proc=None
        self.control=None

    def start(self,mode='ok'):
        ctx=multiprocessing.get_context('spawn')
        left,right=ctx.Pipe(duplex=False)
        self.proc=ctx.Process(target=_local_fixture_server,
                              args=(str(self.endpoint),right,mode),daemon=True)
        self.proc.start()
        right.close()
        self.control=left
        self.addCleanup(left.close)
        self.addCleanup(self.stop)
        self.assertTrue(left.poll(5),'separate server did not bind the kernel endpoint')
        ready=left.recv()
        self.assertEqual(ready[0],'ready',ready)
        self.assertEqual(ready[1],self.proc.pid)
        self.assertNotEqual(self.proc.pid,os.getpid())
        self.assertEqual(self.endpoint.stat().st_mode&0o777,0o600)
        self.assertEqual(self.dir.stat().st_mode&0o777,0o700)

    def stop(self):
        if self.proc is not None:
            self.proc.join(timeout=2)
            if self.proc.is_alive():
                self.proc.terminate()
                self.proc.join(timeout=3)
            self.assertFalse(self.proc.is_alive())

    def connect(self):
        pid=self.proc.pid
        return wire.linux_connect(self.endpoint,peer_policy=lambda uid,gid,p:
                                  uid==os.getuid() and p==pid)

    def test_actual_separate_process_kernel_peer_and_fixture_health(self):
        self.start()
        with self.connect() as stream:
            session=wire.handshake(stream,wire.EnrolledClient('nvp.film',_PACKAGE,_KEY))
            self.assertEqual(session.ref,'host-session-nvp')
            observed=wire.read_only_health(stream,session)
        self.assertEqual(observed['module_id'],'lu.core')
        self.assertEqual(observed['epoch'],8)
        self.assertTrue(observed['transport_only'])
        self.assertFalse(observed['installed_host_verified'])
        self.assertFalse(observed['user_effect_authorized'])
        self.assertTrue(self.control.poll(5))
        self.assertEqual(self.control.recv(),('fixture_health_replied',os.getpid()))

    def test_forged_host_mac_refused_before_health_request(self):
        self.start('forged_welcome')
        with self.connect() as stream:
            with self.assertRaisesRegex(PermissionError,'HMAC'):
                wire.handshake(stream,wire.EnrolledClient('nvp.film',_PACKAGE,_KEY))
        self.assertEqual(self.control.recv()[0],'forged_welcome_sent')

    def test_wrong_client_key_gets_no_welcome(self):
        self.start()
        with self.connect() as stream:
            with self.assertRaises((ConnectionError,TimeoutError,PermissionError)):
                wire.handshake(stream,wire.EnrolledClient('nvp.film',_PACKAGE,b'Q'*32))
        self.assertEqual(self.control.recv()[0],'invalid_client_proof')

    def test_cross_session_health_reply_is_refused(self):
        self.start('wrong_session')
        with self.connect() as stream:
            session=wire.handshake(stream,wire.EnrolledClient('nvp.film',_PACKAGE,_KEY))
            with self.assertRaisesRegex(PermissionError,'bound to the active session'):
                wire.read_only_health(stream,session)
        self.assertEqual(self.control.recv()[0],'fixture_health_replied')

    def test_wrong_real_kernel_pid_denied_before_hello(self):
        self.start()
        with self.assertRaisesRegex(PermissionError,'peer/package policy'):
            wire.linux_connect(self.endpoint,peer_policy=lambda uid,gid,p: p==os.getpid())
        # Refusal before Hello; fixture listener is still alive until teardown.


class SensitiveEnrollmentRepresentation(unittest.TestCase):
    def test_python_enrollment_repr_never_contains_secret(self):
        e=wire.EnrolledClient('nvp.film',_PACKAGE,b'SECRET'+b'X'*26)
        self.assertNotIn('SECRET_',repr(e))
        self.assertNotIn('secret=',repr(e))

    def test_rust_enrollment_debug_is_explicitly_redacted(self):
        source=(ROOT/'native/nvp_lu_ipc_client/src/lib.rs').read_text()
        self.assertIn('impl fmt::Debug for VerifiedEnrollment',source)
        self.assertIn('debug_output_never_leaks_handshake_key',source)
        self.assertNotIn('#[derive(Debug)]\npub struct VerifiedEnrollment',source)


if __name__=='__main__':unittest.main()
