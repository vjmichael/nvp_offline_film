"""NVP Windows native named-pipe OS fixture, never installed Lu Core acceptance.

Runs only on a genuine Windows OS (not cross-compiled or mocked Win32). A
separate Python process hosts a TEST-ONLY pipe with normal account custody.
The client exercises real NVP Win32 overlapped byte I/O and kernel server
PID/SID/process-generation observations. Its trust pin is *test injected*, so
nothing here proves an installed Lu publisher, credential broker or HMAC.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import multiprocessing
import os
import secrets
import sys
import types
import unittest
from unittest import mock

from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import nvp_lu_win32_client as win


def _test_only_named_pipe_server(endpoint: str, control) -> None:
    handle=None
    try:
        k=ctypes.WinDLL('kernel32',use_last_error=True)
        H=wintypes.HANDLE;D=wintypes.DWORD;P=ctypes.c_void_p
        create=k.CreateNamedPipeW
        create.argtypes=[wintypes.LPCWSTR,D,D,D,D,D,D,P]
        create.restype=H
        connect=k.ConnectNamedPipe;connect.argtypes=[H,P];connect.restype=wintypes.BOOL
        read=k.ReadFile;read.argtypes=[H,P,D,ctypes.POINTER(D),P];read.restype=wintypes.BOOL
        write=k.WriteFile;write.argtypes=[H,P,D,ctypes.POINTER(D),P];write.restype=wintypes.BOOL
        close=k.CloseHandle;close.argtypes=[H];close.restype=wintypes.BOOL
        # Test-only current-user DACL. NOT the protected installed Lu Core pipe.
        handle=create(endpoint,0x00000003,0x00000000,1,4096,4096,0,None)
        invalid=ctypes.c_void_p(-1).value
        if handle in (None,0,invalid):
            raise OSError('test-only native CreateNamedPipeW failed')
        control.send(('ready',os.getpid()))
        if not connect(handle,None) and ctypes.get_last_error()!=535:
            raise OSError('native test pipe ConnectNamedPipe failed')
        received=ctypes.create_string_buffer(4);n=D(0)
        if not read(handle,received,4,ctypes.byref(n),None) or n.value!=4 or received.raw!=b'ping':
            raise OSError('native test server expected four-byte ping')
        reply=ctypes.create_string_buffer(b'pong',4)
        if not write(handle,reply,4,ctypes.byref(n),None) or n.value!=4:
            raise OSError('native test server failed four-byte pong')
        control.send(('replied',os.getpid()))
    except Exception as exc:
        try:control.send(('test_server_error',type(exc).__name__,str(exc)))
        except Exception:pass
    finally:
        if handle not in (None,0,ctypes.c_void_p(-1).value):
            k.CloseHandle(handle)
        control.close()


@unittest.skipUnless(sys.platform=='win32','genuine Windows native named-pipe test only')
class NativeWindowsPipeFixture(unittest.TestCase):
    def test_real_separate_process_pipe_and_nvp_observer(self):
        ctx=multiprocessing.get_context('spawn')
        parent,child=ctx.Pipe(duplex=False)
        endpoint=r'\\.\pipe\lu-ipc-'+secrets.token_hex(16)
        proc=ctx.Process(target=_test_only_named_pipe_server,
                         args=(endpoint,child),daemon=True)
        proc.start();child.close()
        observed=None
        try:
            self.assertTrue(parent.poll(10),'Win32 pipe fixture did not initialize')
            self.assertEqual(parent.recv(),('ready',proc.pid))
            api=win._Win32()
            process=api.OpenProcess(win.PROCESS_QUERY_LIMITED_INFORMATION|win.SYNCHRONIZE,
                                    False,proc.pid)
            self.assertFalse(api._invalid(process))
            try:
                image=win._image_path(api,process)
                sid=win._sid_for_process(api,process)
            finally:api.close(process)
            with open(image,'rb') as f:
                digest=hashlib.file_digest(f,'sha256').hexdigest()
            # A test-local asserted checksum is NOT a signed PE image or an
            # installer pin. The production credential path stays disabled.
            pin=win.InstallerPinnedLuCore(image,digest,sid)
            class FakeKey:
                def __enter__(self):return self
                def __exit__(self,*_):return False
            fake_registry=types.SimpleNamespace(HKEY_LOCAL_MACHINE=1,REG_SZ=1,
                KEY_READ=1,KEY_WOW64_64KEY=1,
                OpenKey=lambda *_:FakeKey(),
                QueryValueEx=lambda _key,name:(endpoint,1) if name=='PipeName' else (None,0))
            with mock.patch.dict(sys.modules,{'winreg':fake_registry}), \
                 mock.patch.object(win,'read_installed_peer_pin',lambda:pin):
                observed=win.observe_installed_lu_pipe()
            with observed:
                self.assertEqual(observed.server_pid,proc.pid)
                self.assertEqual(observed.user_sid,sid)
                self.assertTrue(observed.assert_observed_process_alive())
                self.assertEqual(observed.stream.send(b'ping'),4)
                self.assertEqual(observed.stream.recv(4),b'pong')
            self.assertTrue(parent.poll(5))
            self.assertEqual(parent.recv(),('replied',proc.pid))
        finally:
            if observed is not None:observed.close()
            proc.join(timeout=3)
            if proc.is_alive():proc.terminate();proc.join(timeout=3)
            parent.close()
        self.assertEqual(proc.exitcode,0)


if __name__=='__main__':unittest.main()
