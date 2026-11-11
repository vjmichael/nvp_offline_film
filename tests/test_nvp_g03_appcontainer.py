"""Actual Windows G03 AppContainer kernel/ACL/network/Job acceptance.

Never mocks win32 launch, SID, DACL, TCP or child process. The native C++
probe is compiled independently with MSVC in the Windows Actions gate.
Private film execution must not be enabled on a host that lacks this proof.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from backend.nvp_worker_containment import launch_contained

_PROBE=os.environ.get("NVP_G03_NATIVE_SANDBOX_PROBE","")
_WIN=sys.platform=="win32"

def _running(pid):
    if not _WIN:return False
    import pywintypes,win32api,win32con,win32event
    try:
        h=win32api.OpenProcess(win32con.SYNCHRONIZE|win32con.PROCESS_QUERY_LIMITED_INFORMATION,
                               False,int(pid))
    except pywintypes.error:return False
    try:return win32event.WaitForSingleObject(h,0)==win32event.WAIT_TIMEOUT
    finally:h.Close()

def _run(command,work,code_root,*,timeout=20):
    paths=[os.pipe(),os.pipe(),os.pipe()]
    files=[(os.fdopen(read,"rb",buffering=0),os.fdopen(write,"wb",buffering=0))
           for read,write in paths]
    stdin_read,stdin_write=files[0]
    stdout_read,stdout_write=files[1]
    stderr_read,stderr_write=files[2]
    proc=None
    try:
        proc=launch_contained(command,cwd=work,stdin=stdin_read,
             stdout=stdout_write,stderr=stderr_write,memory_mb=512,
             windows_appcontainer_required=True,appcontainer_code_roots=[code_root],
             env={"SYSTEMROOT":os.environ["SYSTEMROOT"],"WINDIR":os.environ["WINDIR"],
                  "PATH":os.environ["PATH"]})
        stdin_read.close();stdin_write.close();stdout_write.close();stderr_write.close()
        result=proc.wait(timeout=timeout)
        proc.close()
        proc=None
        return result,stdout_read.read().decode("utf8","replace"),stderr_read.read().decode("utf8","replace")
    finally:
        if proc is not None:
            if proc.poll() is None:proc.terminate_tree()
            proc.close()
        for pair in files:
            for file in pair:
                try:file.close()
                except OSError:pass

@unittest.skipUnless(_WIN and _PROBE,"MSVC compiled native Windows AppContainer probe required")
class AppContainerNativeKernelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="g03-real-appcontainer-")
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.private=root/"creator-originals"
        self.private.mkdir()
        self.canary=self.private/"original-actor-voice.pcm"
        self.canary.write_bytes(b"G03-PRIVATE-ORIGINAL-PCM-NEVER-READ-BY-WORKER")
        self.binaries=root/"reviewed-binary"
        self.binaries.mkdir()
        self.probe=self.binaries/"g03-kernel-probe.exe"
        shutil.copy2(_PROBE,self.probe)
        self.work=root/"disposable-worker"
        self.work.mkdir()

    def test_kernel_token_denies_real_ungranted_file_and_listening_network(self):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1",0))
            listener.listen(1)
            listener.settimeout(.5)
            port=listener.getsockname()[1]
            # A live regular host connection proves this is not a dead port.
            with socket.create_connection(("127.0.0.1",port),timeout=2):
                accepted,_=listener.accept()
                accepted.close()
            code,stdout,stderr=_run(
                [str(self.probe),str(self.canary),str(port)],
                self.work,self.binaries)
        self.assertEqual(code,0,(stdout,stderr))
        for marker in ("G03_NATIVE_KERNEL_APPCONTAINER_TOKEN_PASS",
                       "G03_NATIVE_UNGRANTED_FILE_DENIED_PASS",
                       "G03_NATIVE_UNGRANTED_NETWORK_DENIED_PASS"):
            self.assertIn(marker,stdout,(stdout,stderr))
        self.assertEqual(self.canary.read_bytes(),
                         b"G03-PRIVATE-ORIGINAL-PCM-NEVER-READ-BY-WORKER")
        self.assertFalse(any(self.work.iterdir()),
                         "Untrusted child wrote persistent plaintext to cwd")

    def test_sandbox_is_not_a_user_claim_or_uncontained_fallback(self):
        with self.assertRaisesRegex(Exception,"AppContainer"):
            _run([sys.executable,"-V"],self.work,self.binaries)

    def test_real_hard_host_crash_kills_appcontainer_descendant(self):
        root=Path(self.tmp.name)
        marker=root/"kernel-owned-worker.json"
        # Host has a real named Job Object only; os._exit deliberately prevents
        # Python cleanup to test kernel kill-on-close after genuine supervisor loss.
        host_code=r'''
import json,os,sys,time
from pathlib import Path
from backend.nvp_worker_containment import launch_contained
probe=Path(sys.argv[1]);work=Path(sys.argv[2]);marker=Path(sys.argv[3])
fds=[os.pipe(),os.pipe(),os.pipe()]
pairs=[(os.fdopen(a,"rb",buffering=0),os.fdopen(b,"wb",buffering=0)) for a,b in fds]
p=launch_contained([str(probe),"--sleep"],cwd=work,stdin=pairs[0][0],
 stdout=pairs[1][1],stderr=pairs[2][1],memory_mb=512,
 windows_appcontainer_required=True,appcontainer_code_roots=[probe.parent],
 env={"SYSTEMROOT":os.environ["SYSTEMROOT"],"WINDIR":os.environ["WINDIR"],
      "PATH":os.environ["PATH"]})
pairs[0][0].close();pairs[1][1].close();pairs[2][1].close()
line=pairs[1][0].read(512)
assert b"G03_NATIVE_KERNEL_APPCONTAINER_TOKEN_PASS" in line,line
marker.write_text(json.dumps({"pid":p.pid,"sid":p._sid,"profile":p._profile,
    "grants":[[str(a),b] for a,b in p._grants]}))
os._exit(19)
'''
        env=dict(os.environ)
        env["PYTHONPATH"]=str(Path(__file__).resolve().parents[1])+os.pathsep+env.get("PYTHONPATH","")
        host=subprocess.Popen([sys.executable,"-c",host_code,
                str(self.probe),str(self.work),str(marker)],
                env=env,cwd=self.tmp.name,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        try:
            _,error=host.communicate(timeout=55)
            self.assertEqual(host.returncode,19,error.decode("utf8","replace"))
            record=json.loads(marker.read_text())
            for _ in range(80):
                if not _running(record["pid"]):break
                time.sleep(.1)
            self.assertFalse(_running(record["pid"]),
                             "AppContainer Job child survived a real host crash")
        finally:
            if host.poll() is None:host.kill();host.wait()
            if marker.exists():
                from backend.nvp_g03_windows_appcontainer import _acl,_api
                record=json.loads(marker.read_text())
                for path,recursive in reversed(record["grants"]):
                    try:_acl(Path(path),record["sid"],"",recursive,remove=True)
                    except Exception:pass
                _,userenv,_=_api()
                userenv.DeleteAppContainerProfile(record["profile"])

if __name__=="__main__":
    unittest.main()
