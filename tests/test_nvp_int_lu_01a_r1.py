"""Source-only native Linux socket + Protobuf descriptor/HMAC wire regression.

No mock or test key is release admission. No production Lu service is started.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import nvp_lu_ipc_v0 as wire
from tools import nvp_compile_domain_descriptor as compiler

SCHEMA=ROOT/'contracts/nvp/film/v1/nvp_film_v1.proto'
CATALOG=ROOT/'contracts/nvp/film/v1/capabilities.json'
FIXTURE_SECRET=b'k'*32  # TEST-ONLY NEVER INSTALL THIS KEY
FIXTURE_PACKAGE=b'p'*32  # TEST-ONLY, NOT A SIGNED EXECUTABLE


def fixture_host(s, *,wrong_mac=False, wrong_session=False, bad_nonce=False, unexpected_features=False):
    try:
        h=wire.read_frame(s)
        if h.WhichOneof('body')!='hello':return
        challenge=wire.LU['WorkspaceFrame'](protocol_major=1,request_id=h.request_id,
            auth_challenge=wire.LU['AuthChallenge'](server_nonce=b'\x00'*32 if bad_nonce else b'\x55'*32))
        wire.write_frame(s,challenge)
        if bad_nonce:return
        proof=wire.read_frame(s)
        raw=h.SerializeToString(deterministic=True)
        expected=hmac.new(FIXTURE_SECRET,b'lu.workspace.client.v0\x00'+raw+b'\x55'*32,
            hashlib.sha256).digest()
        if proof.auth_proof.client_hmac_sha256!=expected:return
        session='other-session' if wrong_session else 'host-session-one'
        features=['unexpected-feature'] if unexpected_features else []
        wel=wire.LU['Welcome'](selected_major=1,selected_minor=0,
            core_epoch_ref='core-epoch-one',enabled_features=features)
        transcript=(b'lu.workspace.server.v0\x00'+raw+b'\x55'*32+
                    session.encode()+wel.SerializeToString(deterministic=True))
        mac=hmac.new(FIXTURE_SECRET,transcript,hashlib.sha256).digest()
        wel.server_hmac_sha256= b'\x00'*32 if wrong_mac else mac
        frame=wire.LU['WorkspaceFrame'](protocol_major=1,request_id=h.request_id,
            session_ref=session,welcome=wel)
        wire.write_frame(s,frame)
    except (ConnectionError,TimeoutError,OSError,PermissionError,ValueError):pass
    finally:s.close()


class ProtobufDescriptorTests(unittest.TestCase):
    def test_compiles_all_exact_messages_with_real_protobuf_runtime(self):
        desc,messages=compiler.compile_file(SCHEMA)
        self.assertEqual(len(messages),16)
        self.assertEqual(desc.package,'nvp.film.v1')
        self.assertTrue(all(messages[k].DESCRIPTOR.full_name=='nvp.film.v1.'+k for k in messages))
    def test_film_message_round_trip(self):
        _,m=compiler.compile_file(SCHEMA)
        obj=m['SceneReadResult'](scene_ref='scene-1',revision=2,scene_sha256=b'\xaa'*32,
            take_refs=['take-1','take-2'],production_bible_ref='bible-1')
        raw=obj.SerializeToString(deterministic=True)
        parsed=m['SceneReadResult'].FromString(raw)
        self.assertEqual(parsed,obj)
    def test_export_does_not_contain_original_audio_bytes(self):
        _,m=compiler.compile_file(SCHEMA)
        f=set(m['FilmExportRequest'].DESCRIPTOR.fields_by_name)
        self.assertEqual(f,{'project_ref','exact_edit_revision','edit_manifest_sha256','installed_export_profile_ref'})
    def test_reject_duplicate_message_field_numbers(self):
        text=SCHEMA.read_text().replace('string project_ref = 1;\n  uint64 minimum_revision = 2;',
            'string project_ref = 1;\n  uint64 minimum_revision = 1;')
        with self.assertRaises(ValueError): compiler.compile_schema(text)
    def test_reject_extra_protobuf_service(self):
        with self.assertRaises(ValueError):compiler.compile_schema(SCHEMA.read_text()+ '\nservice Unsafe {}\n')
    def test_reject_unknown_field_type(self):
        with self.assertRaises(ValueError):compiler.compile_schema(
            SCHEMA.read_text().replace('string project_ref = 1;','arbitrary project_ref = 1;',1))
    def test_catalog_exact_8_proposals_no_grants(self):
        _,messages=compiler.compile_file(SCHEMA)
        j=json.loads(CATALOG.read_text())
        self.assertEqual(j['schema_status'],'draft_unregistered_no_permissions')
        self.assertEqual(len(j['capabilities']),8)
        self.assertEqual(len({v['id'] for v in j['capabilities']}),8)
        for v in j['capabilities']:
            self.assertTrue(v['id'].startswith('nvp.film.'))
            self.assertIn(v['input'],messages);self.assertIn(v['output'],messages)
            self.assertNotIn('PURE_COMPUTE',v['effect_classes'])
            self.assertTrue(set(v['effect_classes'])<=set(['READ_WORKSPACE','WRITE_WORKSPACE','EXECUTE']))
    def test_descriptor_has_no_service(self):
        desc,_=compiler.compile_file(SCHEMA)
        self.assertEqual(len(desc.service),0)

class LuFrameTests(unittest.TestCase):
    def frame(self):
        return wire.LU['WorkspaceFrame'](protocol_major=1,request_id='request-one',
            hello=wire.LU['Hello'](claimed_module_id='nvp.film',claimed_role=1,
            claimed_package_sha256=b'\x77'*32,minimum_major=1,maximum_major=1,
            requested_features=['typed-calls'],client_nonce=b'\x66'*32))
    def test_lu_fixture_hello_roundtrip_exact_binary(self):
        src=self.frame();data=wire._canonical(src)
        self.assertEqual(wire._decode(data),src)
        self.assertEqual(data[:2],bytes.fromhex('0801'))
        self.assertIn(b'nvp.film',data)
    def test_4_byte_framing_roundtrip(self):
        a,b=socket.socketpair()
        try:
            wire.write_frame(a,self.frame())
            actual=wire.read_frame(b)
            self.assertEqual(actual,self.frame())
        finally:a.close();b.close()
    def test_zero_frame_denial_without_body_allocation(self):
        a,b=socket.socketpair()
        try:
            a.sendall(b'\x00'*4)
            with self.assertRaises(ValueError):wire.read_frame(b)
        finally:a.close();b.close()
    def test_oversized_frame_denial_without_body_allocation(self):
        a,b=socket.socketpair()
        try:
            a.sendall(struct.pack('!I',wire.MAX_FRAME_BYTES+1))
            with self.assertRaises(ValueError):wire.read_frame(b)
        finally:a.close();b.close()
    def test_short_frame_denied(self):
        a,b=socket.socketpair()
        try:
            a.sendall(struct.pack('!I',8)+b'\x08\x01');a.shutdown(socket.SHUT_WR)
            with self.assertRaises(ConnectionError):wire.read_frame(b)
        finally:a.close();b.close()
    def test_incompatible_wire_version_refused(self):
        msg=self.frame();msg.protocol_major=9
        with self.assertRaises(PermissionError):wire._canonical(msg)
    def test_unknown_field_is_rejected(self):
        raw=wire._canonical(self.frame())+b'\xb8\x3e\x01'
        with self.assertRaises(PermissionError):wire._decode(raw)
    def test_unrecognized_body_variant_is_rejected(self):
        bad=wire.LU['WorkspaceFrame'](protocol_major=1,request_id='other')
        with self.assertRaises(PermissionError):wire._canonical(bad)
    def test_no_anonymous_enrollment(self):
        for key,digest in [(b'',FIXTURE_PACKAGE),(b'\x00'*32,FIXTURE_PACKAGE),
                           (FIXTURE_SECRET,b''),(FIXTURE_SECRET,b'\x00'*32)]:
            with self.subTest(key=key[:2],digest=digest[:2]),self.assertRaises(PermissionError):
                wire.EnrolledClient('nvp.film',digest,key)
    def run_handshake(self,*,override_key=None,**kw):
        a,b=socket.socketpair();
        t=threading.Thread(target=fixture_host,args=(b,),kwargs=kw,daemon=True)
        t.start()
        try:
            enrollment=wire.EnrolledClient('nvp.film',FIXTURE_PACKAGE,
                FIXTURE_SECRET if override_key is None else override_key,
                ('typed-calls',))
            return wire.handshake(a,enrollment)
        finally:a.close();t.join(timeout=5)
    def test_fixture_mutual_hmac_positive_not_installation(self):
        sess=self.run_handshake()
        self.assertEqual(sess.ref,'host-session-one')
        self.assertEqual(sess.epoch,'core-epoch-one')
    def test_wrong_enrolled_key_no_session(self):
        with self.assertRaises((ConnectionError,PermissionError)):
            self.run_handshake(override_key=b'\x11'*32)
    def test_forged_host_mac_rejected(self):
        with self.assertRaises(PermissionError):self.run_handshake(wrong_mac=True)
    def test_zero_server_nonce_denied(self):
        with self.assertRaises(PermissionError):self.run_handshake(bad_nonce=True)
    def test_unnegotiated_feature_denied(self):
        with self.assertRaises(PermissionError):self.run_handshake(unexpected_features=True)
    def test_health_is_inert_non_authorizing_message(self):
        s=wire.LuSession('session-1','epoch-1','nvp.film',())
        health=wire.health_request(s)
        self.assertEqual(health.WhichOneof('body'),'health')
        self.assertEqual(health.session_ref,s.ref)
    def test_reject_unenrolled_other_module(self):
        with self.assertRaises(PermissionError):
            wire.EnrolledClient('other-module',FIXTURE_PACKAGE,FIXTURE_SECRET)
    def test_windows_unqualified_connection_is_denied(self):
        with self.assertRaises(PermissionError):wire.windows_connect()
    def test_reject_malformed_windows_pipe_name(self):
        for name in ('\\\\.\\pipe\\else',r'\\server\pipe\lu-ipc-'+'a'*32,
                     r'\\.\pipe\lu-ipc-../other',r'\\.\pipe\lu-ipc-'+'G'*32):
            with self.subTest(name=name),self.assertRaises(PermissionError):
                wire.validate_windows_pipe_name(name)
        name=r'\\.\pipe\lu-ipc-'+'a'*32
        self.assertEqual(wire.validate_windows_pipe_name(name),name)

@unittest.skipUnless(sys.platform=='linux','Linux SO_PEERCRED only')
class NativeLinuxPeerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.path.chmod(0o700)
        self.endpoint=self.path/'lu.sock'
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.listener.bind(str(self.endpoint))
        self.endpoint.chmod(0o600)
        self.listener.listen()
        self.addCleanup(self.listener.close)
    def test_actual_linux_peer_creds_and_independent_policy(self):
        evidence=[]
        def server():
            client,_=self.listener.accept()
            try:client.recv(1)
            finally:client.close()
        t=threading.Thread(target=server,daemon=True);t.start()
        s=wire.linux_connect(self.endpoint,peer_policy=lambda uid,gid,pid:
                             evidence.append((uid,gid,pid)) or pid==os.getpid())
        try:
            self.assertEqual(evidence[0][0],os.getuid())
            self.assertEqual(evidence[0][2],os.getpid())
            s.sendall(b'X')
        finally:s.close();t.join(timeout=5)
    def test_missing_peer_policy_denied(self):
        with self.assertRaises(PermissionError):wire.linux_connect(self.endpoint,peer_policy=None)
    def test_rejected_real_kernel_peer_identity_denied(self):
        with self.assertRaises(PermissionError):wire.linux_connect(self.endpoint,
                                    peer_policy=lambda uid,gid,pid:False)
    def test_world_readable_runtime_dir_denied(self):
        self.path.chmod(0o755)
        with self.assertRaises(PermissionError):wire.linux_connect(self.endpoint,
                                       peer_policy=lambda *args:True)
    def test_world_readable_endpoint_denied(self):
        self.endpoint.chmod(0o666)
        with self.assertRaises(PermissionError):wire.linux_connect(self.endpoint,
                                       peer_policy=lambda *args:True)
    def test_socket_symlink_denied(self):
        link=self.path/'fake.sock';link.symlink_to(self.endpoint)
        with self.assertRaises(PermissionError):wire.linux_connect(link,
                                       peer_policy=lambda *args:True)

if __name__=='__main__':unittest.main()
