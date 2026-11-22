"""R3 NVP-only native-protocol and Windows source gates; NOT installed acceptance."""
from __future__ import annotations
from pathlib import Path
import copy,ctypes,json,subprocess,sys,tempfile,types,unittest
from unittest import mock
from ctypes import wintypes

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import nvp_lu_ipc_v0 as lu
from backend import nvp_lu_win32_client as win
from backend import nvp_lu_readonly_policy as policy
from tools import nvp_native_protoc_qualification as native

from tools.nvp_native_protoc_path import find_native_protoc, require_test_protoc
PROTOC=find_native_protoc()
PROTO=ROOT/'contracts/nvp/film/v1/nvp_film_v1.proto'
CAT=ROOT/'contracts/nvp/film/v1/capabilities.json'
MAP=ROOT/'contracts/nvp/film/v1/native_effect_alignment.json'
RUST=ROOT/'native/nvp_lu_ipc_client'


class NativeDomainSchema(unittest.TestCase):
    def test_real_protoc_against_nvp_owned_schema(self):
        protoc=require_test_protoc(self)
        with tempfile.TemporaryDirectory() as tmp:
            result=native.qualify(protoc,PROTO,CAT,Path(tmp)/'domain.pb')
            self.assertEqual(result['message_count'],16)
            self.assertEqual(result['enum_count'],1)
            self.assertEqual(result['services'],0)
            self.assertEqual(result['catalog_capabilities'],8)
    def test_rust_prost_build_is_exact_upstream_pinned_not_copied(self):
        build=(RUST/'build.rs').read_text()
        manifest=(RUST/'Cargo.toml').read_text()
        rust=(RUST/'src/lib.rs').read_text()
        self.assertIn(lu.LU_WORKSPACE_PROTO_BLOB_SHA,build)
        self.assertIn('LU_WORKSPACE_PROTO',build)
        self.assertIn('compile_protos',build)
        self.assertIn('prost-build = "0.14"',manifest)
        self.assertIn('nvp.film.v1.rs',rust)
        self.assertIn('lu.workspace.v0.rs',rust)
        self.assertNotIn('TcpStream',rust)
        self.assertNotIn('reqwest',manifest)
    def test_no_production_rust_health_until_installed_broker(self):
        rust=(RUST/'src/lib.rs').read_text()
        self.assertIn('Err(Refusal::MissingInstaller)',rust)
        self.assertIn('sha2', (RUST/'Cargo.toml').read_text())
        self.assertNotIn('unsafe{std::mem::transmute',rust)
    def test_upstream_contract_limits_match_native_catalog(self):
        native_map=json.loads(MAP.read_text())
        self.assertEqual(native_map['constraints']['max_parallel_core_dlc_calls'],4)
        self.assertEqual(lu.MAX_FRAME_BYTES,262144)
        self.assertEqual(lu.MAX_TYPED_BYTES,65536)
        self.assertEqual(lu.MAX_OBJECT_REFS,16)
        self.assertEqual(lu.MAX_STREAM_CREDIT,64)


class NativeWindowsSource(unittest.TestCase):
    def test_non_windows_denies_native_trust_lookup(self):
        if sys.platform=='win32':self.skipTest('non-Windows native restriction')
        with self.assertRaises(PermissionError):win.read_installed_peer_pin()
        with self.assertRaises(PermissionError):win.observe_installed_lu_pipe()
    def test_no_caller_bypass_to_enrolled_windows_health(self):
        with self.assertRaises(PermissionError):win.connect_authenticated_read_only(
            signed=True,endpoint=r'\\.\pipe\lu-ipc-'+'0'*32,
            package=b'A'*32,secret=b'B'*32)
    def test_installed_image_pin_rejects_uncanonical_value(self):
        good=r'C:\Program Files\Lu\lu-core.exe'
        obj=win.InstallerPinnedLuCore(good,'a'*64,'S-1-5-18')
        self.assertEqual(obj.service_sid,'S-1-5-18')
        for image,sha,sid in [
            ('lu.exe','a'*64,'S-1-5-18'),
            (r'C:\Users\x\..\lu.exe','a'*64,'S-1-5-18'),
            (good,'0'*7,'S-1-5-18'),
            (good,'a'*64,'bad')]:
            with self.subTest(image=image,sha=sha),self.assertRaises(PermissionError):
                win.InstallerPinnedLuCore(image,sha,sid)
    def test_host_hash_filter_refuses_wrong_pin_without_signing_claim(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'lu.exe';path.write_bytes(b'fake-lu-signed-no')
            # The byte hash test is NOT an Authenticode signer verification.
            pin=win.InstallerPinnedLuCore(str(path),'f'*64,'S-1-5-18') if sys.platform=='win32' else None
            if pin is not None:
                with self.assertRaises(PermissionError):win._pinned_image_hash(str(path),pin)
    def test_win32_timeout_and_cancel_source_guards(self):
        code=(ROOT/'backend/nvp_lu_win32_client.py').read_text()
        for fragment in ['FILE_FLAG_OVERLAPPED','SECURITY_SQOS_PRESENT',
                         'SECURITY_IDENTIFICATION','GetNamedPipeServerProcessId',
                         'GetProcessTimes','GetNamedPipeServerSessionId',
                         'CancelIoEx','GetOverlappedResult',
                         'read_installed_peer_pin()']:
            self.assertIn(fragment,code)
        self.assertNotIn('subprocess.',code)
    def _mock_kernel_observation(self,*,sid='S-1-5-18',pid_change=False):
        class FakeKey:
            def __enter__(self):return self
            def __exit__(self,*args):return False
        data={'PipeName':(r'\\.\pipe\lu-ipc-'+'a'*32,1)}
        fake_winreg=types.SimpleNamespace(HKEY_LOCAL_MACHINE=1,REG_SZ=1,
            KEY_READ=1,KEY_WOW64_64KEY=1,
            OpenKey=lambda *a:FakeKey(),
            QueryValueEx=lambda _h,name:data[name])
        class Api:
            invalid=-1
            closed=[]
            reads=0
            def _invalid(self,h):return h in (0,None,-1)
            def CreateFileW(self,*args):return 11
            def GetNamedPipeServerProcessId(self,_h,ptr):
                self.reads+=1
                ptr._obj.value=202 if pid_change and self.reads>1 else 101
                return 1
            def GetNamedPipeServerSessionId(self,_h,ptr):ptr._obj.value=1;return 1
            def OpenProcess(self,*args):return 13
            def WaitForSingleObject(self,_h,_ms):return win.WAIT_TIMEOUT
            def close(self,h):self.closed.append(h)
            def CancelIoEx(self,*args):return 1
        api=Api()
        pin=win.InstallerPinnedLuCore(r'C:\Program Files\Lu\lu-core.exe','f'*64,'S-1-5-18')
        stack=__import__('contextlib').ExitStack()
        stack.enter_context(mock.patch.dict(sys.modules,{'winreg':fake_winreg}))
        stack.enter_context(mock.patch.object(win,'_Win32',lambda:api))
        stack.enter_context(mock.patch.object(win,'read_installed_peer_pin',lambda:pin))
        stack.enter_context(mock.patch.object(win,'_creation_time',lambda *_:10))
        stack.enter_context(mock.patch.object(win,'_image_path',lambda *_:pin.image_path))
        stack.enter_context(mock.patch.object(win,'_sid_for_process',lambda *_:sid))
        stack.enter_context(mock.patch.object(win,'_pinned_image_hash',lambda *_:None))
        return api,stack
    def test_wrong_native_peer_sid_refused_before_send(self):
        api,context=self._mock_kernel_observation(sid='S-1-5-21-9999')
        with context, self.assertRaisesRegex(PermissionError,'service account'):
            win.observe_installed_lu_pipe()
        self.assertIn(11,api.closed)
        self.assertIn(13,api.closed)
    def test_native_pid_swap_refused_before_send(self):
        api,context=self._mock_kernel_observation(pid_change=True)
        with context, self.assertRaisesRegex(PermissionError,'changed while observed'):
            win.observe_installed_lu_pipe()
        self.assertIn(11,api.closed)
    def test_even_observed_correct_native_pid_is_not_authentication(self):
        api,context=self._mock_kernel_observation()
        with context:
            observed=win.observe_installed_lu_pipe()
            self.assertEqual(observed.server_pid,101)
            self.assertEqual(observed.user_sid,'S-1-5-18')
            with self.assertRaises(PermissionError):
                win.connect_authenticated_read_only(observed)
            observed.close()
        self.assertIn(11,api.closed)
    def test_fake_win32_overlapped_transport_bytes_not_authentication(self):
        class FakeKernel:
            invalid=-1
            closed=[]
            def _invalid(self,handle):return handle in (-1,0,None)
            def CreateEventW(self,*_):return 99
            def close(self,handle):self.closed.append(handle)
            def CancelIoEx(self,*_):return 1
            def ReadFile(self,_handle,buffer,size,out,ov):
                data=b'hello-world'[:size]
                ctypes.memmove(buffer,data,len(data));out._obj.value=len(data)
                return 1
            def WriteFile(self,_handle,buffer,size,out,ov):
                out._obj.value=size
                return 1
        native_api=FakeKernel();pipe=win.WinPipeStream(native_api,123)
        self.assertEqual(pipe.recv(5),b'hello')
        self.assertEqual(pipe.send(b'abc'),3)
        pipe.settimeout(0.2)
        with self.assertRaises(ValueError):pipe.settimeout(10.0)
        pipe.close();self.assertIn(123,native_api.closed)
        with self.assertRaises(ConnectionError):pipe.recv(1)


class DomainRegistrationPolicy(unittest.TestCase):
    def test_review_catalog_stays_unregistered_and_read_only(self):
        result=policy.review_catalog(CAT,MAP)
        self.assertFalse(result['registration_enabled'])
        self.assertFalse(result['effect_authorized'])
        self.assertFalse(result['input_object_refs_supported_by_lu_host'])
        self.assertEqual(len(result['read_only_candidates']),3)
        self.assertEqual(len(result['blocked_composite_effects']),2)
    def test_refuses_even_caller_claimed_enrollment_and_all_effects(self):
        for name in [*policy.READ_ONLY_IDS,'nvp.film.render.shot',
                     'nvp.film.edit.export','nvp.film.project.commit','unapproved']:
            with self.subTest(name=name),self.assertRaises(PermissionError):
                policy.authorize_readonly_request(name,installed_enrollment_proven=True)
    def test_refuses_input_object_refs_until_lu_core_resolver(self):
        with self.assertRaisesRegex(PermissionError,'ObjectRef'):
            policy.authorize_readonly_request('nvp.film.project.read',input_refs=('fake',))
    def test_edited_catalog_effect_downgrade_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);a=json.loads(CAT.read_text());b=json.loads(MAP.read_text())
            for cap in a['capabilities']:
                if cap['id']=='nvp.film.render.shot':cap['effect_classes']=['READ_WORKSPACE']
            p=root/'cat.json';q=root/'map.json'
            p.write_text(json.dumps(a));q.write_text(json.dumps(b))
            with self.assertRaises(PermissionError):policy.review_catalog(p,q)
    def test_prohibition_of_legacy_json_fallback(self):
        rust=(RUST/'src/lib.rs').read_text()
        win_code=(ROOT/'backend/nvp_lu_win32_client.py').read_text()
        for code in [rust,win_code]:
            self.assertNotIn('nvp_lu_status_socket',code)
            self.assertNotIn('http://127.0.0.1',code)
            self.assertNotIn('socket.create_connection(',code)

if __name__=='__main__':unittest.main()
