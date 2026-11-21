"""NVP IPC R2: native-protoc, host-effect alignment, inert Windows probe and Health fixture.

All positive native observations are Linux/source-only or synthetic and NEVER
produce installed Lu/NVP package or filmmaker approval evidence.
"""
import hashlib
import hmac
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import nvp_lu_ipc_v0 as wire
from backend import nvp_lu_windows_pipe_probe as probe
from tools import nvp_native_protoc_qualification as native

from tools.nvp_native_protoc_path import require_test_protoc
SCHEMA=ROOT/'contracts/nvp/film/v1/nvp_film_v1.proto'
CATALOG=ROOT/'contracts/nvp/film/v1/capabilities.json'
MAP=ROOT/'contracts/nvp/film/v1/native_effect_alignment.json'
KEY=b'K'*32  # controlled fixture only
PACKAGE=b'P'*32


def serve_health(s, *,bad_session=False,bad_module=False,bad_status=False,wrong_type=False):
    try:
        hello=wire.read_frame(s)
        request_id=hello.request_id
        hello_wire=hello.SerializeToString(deterministic=True)
        server_nonce=b'\x55'*32
        challenge=wire.LU['WorkspaceFrame'](protocol_major=1,request_id=request_id,
            auth_challenge=wire.LU['AuthChallenge'](server_nonce=server_nonce))
        wire.write_frame(s,challenge)
        proof=wire.read_frame(s)
        if proof.auth_proof.client_hmac_sha256!=hmac.new(KEY,b'lu.workspace.client.v0\0'+hello_wire+server_nonce,
                                                        hashlib.sha256).digest():
            return
        session='session-r2'
        unsigned=wire.LU['Welcome'](selected_major=1,selected_minor=0,
            core_epoch_ref='core-epoch-r2')
        expected=hmac.new(KEY,b'lu.workspace.server.v0\0'+hello_wire+server_nonce+
                          session.encode()+unsigned.SerializeToString(deterministic=True),
                          hashlib.sha256).digest()
        welcome=wire.LU['Welcome']();welcome.CopyFrom(unsigned)
        welcome.server_hmac_sha256=expected
        wire.write_frame(s,wire.LU['WorkspaceFrame'](protocol_major=1,
            request_id=request_id,session_ref=session,welcome=welcome))
        request=wire.read_frame(s)
        if request.WhichOneof('body')!='health':return
        if wrong_type:
            response=wire.LU['WorkspaceFrame'](protocol_major=1,request_id=request.request_id,
                session_ref=session,health=wire.LU['HealthRequest']())
        else:
            report=wire.LU['HealthReport'](module_id='forged.core' if bad_module else 'lu.core',
                connected=not bad_status,status_code='ready',epoch=1)
            response=wire.LU['WorkspaceFrame'](protocol_major=1,request_id=request.request_id,
                session_ref='fake-session' if bad_session else session,health_report=report)
        wire.write_frame(s,response)
    except (PermissionError,TimeoutError,ValueError,ConnectionError,OSError):
        return
    finally:s.close()


class NativeCompilerR2(unittest.TestCase):
    def test_real_native_protoc_compiles_and_matches_review_parser(self):
        protoc=require_test_protoc(self)
        with tempfile.TemporaryDirectory() as tmp:
            r=native.qualify(protoc,SCHEMA,CATALOG,Path(tmp)/'native.pb')
            self.assertEqual(r['message_count'],16)
            self.assertEqual(r['services'],0)
            self.assertEqual(len(r['native_tool_descriptor_single_effect_gaps']),2)
            self.assertFalse(r['lu_native_rust_prost_compiled'])
    def test_native_protoc_rejects_duplicate_field_number(self):
        protoc=require_test_protoc(self)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'contracts/nvp/film/v1/nvp_film_v1.proto'
            p.parent.mkdir(parents=True)
            p.write_text(SCHEMA.read_text().replace('uint64 minimum_revision = 2;',
                'uint64 minimum_revision = 1;',1))
            with self.assertRaises(RuntimeError):
                native.qualify(protoc,p,CATALOG,root/'bad.pb')
    def test_native_protoc_compiles_proposal_without_generating_service(self):
        protoc=require_test_protoc(self)
        with tempfile.TemporaryDirectory() as tmp:
            result=native.qualify(protoc,SCHEMA,CATALOG,Path(tmp)/'good.pb')
            self.assertTrue(result['protoc_version'].startswith('libprotoc'))
            self.assertFalse(result['windows_pipe_connected'])
    def test_native_effect_alignment_matches_lu_single_tool_effect(self):
        catalog=json.loads(CATALOG.read_text())['capabilities']
        data=json.loads(MAP.read_text())
        self.assertEqual(data['status'],'DRAFT_UNREGISTERED_NOT_EFFECT_AUTHORIZED')
        by_id={x['id']:x for x in data['mappings']}
        self.assertEqual(set(by_id),{x['id'] for x in catalog})
        self.assertEqual(len(by_id),8)
        effectmap={'READ_WORKSPACE':'ReadWorkspace','WRITE_WORKSPACE':'WriteWorkspace',
                   'EXECUTE':'ExecuteCode'}
        for cap in catalog:
            entry=by_id[cap['id']]
            self.assertEqual(entry['core_tool_effect'],effectmap[cap['effect_classes'][0]])
            if len(cap['effect_classes'])>1:
                self.assertEqual(entry['core_registration_status'],'BLOCKED_EFFECT_BRIDGE_APPROVAL')
                self.assertIn('NVP_write_grant',entry['domain_guards'])
            else:self.assertEqual(entry['core_registration_status'],'PENDING')
        self.assertFalse(data['constraints']['input_refs_supported_by_current_core_host_gate'])
        self.assertTrue(data['constraints']['trusted_exact_typed_input_verifier_required'])

class InertWindowsPipeR2(unittest.TestCase):
    def test_refuses_all_non_windows_probe_calls(self):
        if sys.platform=='win32':self.skipTest('Linux-only refusal test')
        with self.assertRaises(PermissionError):probe.observe_local_lu_pipe_server(
            r'\\.\pipe\lu-ipc-'+'a'*32)
    def test_refuses_non_lu_remote_and_unsafe_pipe_names(self):
        for name in [r'\\evil\pipe\lu-ipc-'+'a'*32,r'\\.\pipe\else-'+ 'a'*32,
                     r'\\.\pipe\lu-ipc-'+'A'*32]:
            with self.subTest(name=name),self.assertRaises(PermissionError):
                probe.observe_local_lu_pipe_server(name)
    def test_authenticated_windows_exchange_remains_closed(self):
        with self.assertRaises(PermissionError):
            probe.open_authenticated_read_only_session(object(),signed=True)

class HostHealthFixtureR2(unittest.TestCase):
    def invoke(self,**kw):
        client,server=socket.socketpair()
        t=threading.Thread(target=serve_health,args=(server,),kwargs=kw,daemon=True)
        t.start()
        try:
            enrolled=wire.EnrolledClient('nvp.film',PACKAGE,KEY)
            session=wire.handshake(client,enrolled)
            return wire.read_only_health(client,session)
        finally:
            client.close();t.join(timeout=4)
    def test_health_exchange_after_mutual_hmac_fixture(self):
        r=self.invoke()
        self.assertEqual(r['module_id'],'lu.core')
        self.assertEqual(r['status_code'],'ready')
        self.assertTrue(r['transport_only'])
        self.assertFalse(r['user_effect_authorized'])
        self.assertFalse(r['installed_host_verified'])
    def test_reject_unrelated_host_epoch_or_session(self):
        with self.assertRaises(PermissionError):self.invoke(bad_session=True)
    def test_reject_forged_report_module(self):
        with self.assertRaises(PermissionError):self.invoke(bad_module=True)
    def test_reject_disconnected_host_status(self):
        with self.assertRaises(PermissionError):self.invoke(bad_status=True)
    def test_reject_instead_of_accept_non_health_response(self):
        with self.assertRaises(PermissionError):self.invoke(wrong_type=True)
    def test_reject_user_constructed_invalid_session(self):
        a,b=socket.socketpair()
        try:
            with self.assertRaises(PermissionError):
                wire.read_only_health(a,wire.LuSession('bad!ref','epoch','nvp.film',()))
        finally:a.close();b.close()

if __name__=='__main__':unittest.main()
