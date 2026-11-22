"""R3-R1 NVP-only exact source and Win32 negative tests; not native Windows."""
from __future__ import annotations
import contextlib
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import nvp_lu_win32_client as win
from backend import nvp_lu_ipc_v0 as lu
from tools.nvp_native_protoc_path import require_test_protoc

NATIVE=ROOT/'native/nvp_lu_ipc_client'
PIN='747b7472ab7e4bdfd7d646dd629b2c45a9c63dd1'


class NativeProtobufBuildContracts(unittest.TestCase):
    def test_real_native_protoc_nvp_schema_and_descriptor(self):
        protoc=require_test_protoc(self)
        from tools.nvp_native_protoc_qualification import qualify
        schema=ROOT/'contracts/nvp/film/v1/nvp_film_v1.proto'
        catalog=ROOT/'contracts/nvp/film/v1/capabilities.json'
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'nvp.pb'
            status=qualify(protoc,schema,catalog,out)
            self.assertEqual(status['message_count'],16)
            self.assertEqual(status['catalog_capabilities'],8)
            self.assertGreater(out.stat().st_size,300)

    def test_rust_build_pins_lu_proto_blob_instead_of_copied_core(self):
        build=(NATIVE/'build.rs').read_text()
        self.assertIn(PIN,build)
        self.assertIn('LU_WORKSPACE_PROTO',build)
        self.assertIn('compile_protos(',build)
        self.assertNotIn('lu-core =', (NATIVE/'Cargo.toml').read_text())

    def test_native_fixture_has_no_production_installer_bypass(self):
        source=(NATIVE/'src/lib.rs').read_text()
        self.assertIn('mod independent_wire_tests',source)
        self.assertIn('source_only_health_roundtrip_with_matching_session_mac',source)
        self.assertIn('forged_welcome_does_not_enable_health',source)
        self.assertIn('forged_health_module_refused_after_valid_mac',source)
        self.assertIn('wrong_hmac_enrollment_refused',source)
        self.assertIn('Err(Refusal::MissingInstaller)',source)
        self.assertNotIn('TcpStream',source)
        self.assertNotIn('http://',source)

    def test_compilation_state_explicit(self):
        # A Rust source fixture is not evidence that rustc/prost ran.
        self.assertFalse((ROOT/'receipts/RUST_NATIVE_ACCEPTANCE_PASS.json').exists())

class WindowsPeerHandleLeaseFixture(unittest.TestCase):
    class FakeKey:
        def __enter__(self):return self
        def __exit__(self,*args):return False

    def factory(self,*,swap=False,wrong_session=False,exited=False):
        data={'PipeName':(r'\\.\pipe\lu-ipc-'+'a'*32,1)}
        fake_winreg=types.SimpleNamespace(HKEY_LOCAL_MACHINE=1,REG_SZ=1,
            KEY_READ=1,KEY_WOW64_64KEY=1,OpenKey=lambda *a:self.FakeKey(),
            QueryValueEx=lambda _h,n:data[n])
        class Api:
            closed=[]
            invalid=-1
            changes=0
            def _invalid(self,h):return h in (-1,0,None)
            def CreateFileW(self,*a):return 11
            def GetNamedPipeServerProcessId(self,_h,p):
                self.changes+=1
                p._obj.value=(202 if swap and self.changes>=3 else 101)
                return 1
            def GetNamedPipeServerSessionId(self,_h,p):p._obj.value=2 if wrong_session else 1;return 1
            def OpenProcess(self,*a):return 13
            def WaitForSingleObject(self,_h,_ms):return win.WAIT_OBJECT_0 if exited else win.WAIT_TIMEOUT
            def CancelIoEx(self,*a):return 1
            def close(self,h):
                if h is not None:self.closed.append(h)
        api=Api();api.closed=[]
        pin=win.InstallerPinnedLuCore(r'C:\Program Files\Lu\lu-core.exe','a'*64,'S-1-5-18')
        context=contextlib.ExitStack()
        context.enter_context(mock.patch.dict(sys.modules,{'winreg':fake_winreg}))
        context.enter_context(mock.patch.object(win,'_Win32',lambda:api))
        context.enter_context(mock.patch.object(win,'read_installed_peer_pin',lambda:pin))
        context.enter_context(mock.patch.object(win,'_creation_time',lambda *_:10))
        context.enter_context(mock.patch.object(win,'_image_path',lambda *_:pin.image_path))
        context.enter_context(mock.patch.object(win,'_sid_for_process',lambda *_:'S-1-5-18'))
        context.enter_context(mock.patch.object(win,'_pinned_image_hash',lambda *_:None))
        return api,context

    def test_pinned_process_handle_lifetime_matches_pipe(self):
        api,ctx=self.factory()
        with ctx:
            obs=win.observe_installed_lu_pipe()
            self.assertEqual(obs.server_pid,101)
            self.assertEqual(api.closed,[])
            self.assertTrue(obs.assert_observed_process_alive())
            self.assertEqual(api.closed,[])
            obs.close()
            self.assertCountEqual(api.closed,[11,13])
            with self.assertRaisesRegex(PermissionError,'closed'):
                obs.assert_observed_process_alive()
            obs.close()
            self.assertCountEqual(api.closed,[11,13])

    def test_swapped_server_pid_refused_on_rescan(self):
        api,ctx=self.factory(swap=True)
        with ctx:
            obs=win.observe_installed_lu_pipe()
            with self.assertRaisesRegex(PermissionError,'generation changed'):
                obs.assert_observed_process_alive()
            obs.close()
        self.assertCountEqual(api.closed,[11,13])

    def test_exited_process_refused_without_wire_exchange(self):
        api,ctx=self.factory(exited=True)
        with ctx:
            # New native pre-return test refuses a dead server before a lease
            # can be handed to any future authenticated broker.
            with self.assertRaisesRegex(PermissionError,'changed while observed'):
                win.observe_installed_lu_pipe()

    def test_wrong_pipe_session_denied_on_rescan(self):
        api,ctx=self.factory(wrong_session=True)
        with ctx:
            obs=win.observe_installed_lu_pipe()
            # The first probe captured session 2; a changed session is required.
            before=api.GetNamedPipeServerSessionId
            def alter(h,p):p._obj.value=3;return 1
            api.GetNamedPipeServerSessionId=alter
            with self.assertRaisesRegex(PermissionError,'generation changed'):
                obs.assert_observed_process_alive()
            obs.close()

    def test_untrusted_observation_never_triggers_production_health(self):
        api,ctx=self.factory()
        with ctx:
            obs=win.observe_installed_lu_pipe()
            self.assertTrue(obs.assert_observed_process_alive())
            with self.assertRaises(PermissionError):
                win.connect_authenticated_read_only(obs)
            obs.close()

class CoreInterfaceGates(unittest.TestCase):
    def test_lu_current_wire_pin_does_not_claim_package_enrollment(self):
        self.assertEqual(lu.LU_WORKSPACE_PROTO_BLOB_SHA,PIN)
        self.assertEqual(lu.LU_IPC_SOURCE_SHA,'60afe6908a6abe3408bb952869d85b43781313ca')
        self.assertEqual((lu.WIRE_MAJOR,lu.WIRE_MINOR),(1,0))
        self.assertEqual(lu.MAX_FRAME_BYTES,256*1024)
        self.assertEqual(lu.MAX_TYPED_BYTES,64*1024)

    def test_catalog_not_promoted_to_core_authorization(self):
        data=json.loads((ROOT/'contracts/nvp/film/v1/capabilities.json').read_text())
        self.assertEqual(data['schema_status'],'draft_unregistered_no_permissions')
        self.assertEqual(len(data['capabilities']),8)
        for cap in data['capabilities']:
            self.assertEqual(cap['version'],1)
        self.assertEqual([x['effect_classes'] for x in data['capabilities'] if x['id'] in
            ('nvp.film.render.shot','nvp.film.edit.export')],[['EXECUTE','WRITE_WORKSPACE']]*2)

if __name__=='__main__':unittest.main()
