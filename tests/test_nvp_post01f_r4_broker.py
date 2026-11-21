"""R4 portable contract/integration tests; does not run LTX or a Windows service."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.nvp_post01f_ltx_broker import (
    LOCK_NAME, LOCK_FORMAT, read_pinned_install, conform_picture_only,
    _probe_media, run_installed_broker, verify_derived_inputs_before_generation,
)
from backend.nvp_post01f_picture_verify import verify_picture_frames

H=lambda b:hashlib.sha256(b).hexdigest()
FFMPEG=shutil.which('ffmpeg')
FFPROBE=shutil.which('ffprobe')

class RealMediaBoundary(unittest.TestCase):
    @unittest.skipUnless(FFMPEG and FFPROBE,'external test media binaries unavailable')
    def test_121_frame_generated_audio_to_120_silent_picture(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            input=root/'picture.native.mp4'
            subprocess.run([FFMPEG,'-v','error','-f','lavfi','-i',
                'testsrc2=size=128x64:rate=24','-f','lavfi','-i',
                'sine=frequency=700:sample_rate=48000','-frames:v','121',
                '-c:v','libx264','-preset','ultrafast','-c:a','aac',
                '-shortest',str(input)],check=True,timeout=30)
            plan={'display_frames':120,'model_frames':121,'width':128,'height':64}
            media={'ffmpeg':FFMPEG,'ffprobe':FFPROBE}
            pre=_probe_media(Path(FFPROBE),input)
            self.assertEqual(pre['frames'],121)
            self.assertGreater(pre['audio_streams'],0)
            fake_efs=types.ModuleType('backend.nvp_w1g_encrypted_source')
            fake_efs.verify_efs_inputs=lambda *a,**kw:True
            with patch.dict(sys.modules,{'backend.nvp_w1g_encrypted_source':fake_efs}):
                result=conform_picture_only(stage=root,plan=plan,installed=media)
            self.assertFalse(input.exists())
            self.assertEqual(result['frames'],120)
            self.assertEqual(result['audio_streams'],0)
            output=root/'picture.mp4'
            self.assertEqual(result['sha'],H(output.read_bytes()))
            receipt=verify_picture_frames(output,plan,result['sha'],
                ffmpeg=Path(FFMPEG),ffmpeg_sha256=H(Path(FFMPEG).read_bytes()),
                ffprobe=Path(FFPROBE),ffprobe_sha256=H(Path(FFPROBE).read_bytes()))
            self.assertTrue(receipt['independently_decoded'])
            self.assertTrue(receipt['pts_verified'])
            self.assertEqual(receipt['audio_streams'],0)
            with self.assertRaises(PermissionError):
                verify_picture_frames(output,dict(plan,display_frames=121),result['sha'],
                    ffmpeg=Path(FFMPEG),ffmpeg_sha256=H(Path(FFMPEG).read_bytes()),
                    ffprobe=Path(FFPROBE),ffprobe_sha256=H(Path(FFPROBE).read_bytes()))

class NativeGuideContract(unittest.TestCase):
    @unittest.skipUnless(FFMPEG and FFPROBE,'external test media binaries unavailable')
    def test_121_frame_source_guide_validates_before_model_loading(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            guide=root/'layout.mp4'
            subprocess.run([FFMPEG,'-v','error','-f','lavfi','-i',
                'testsrc2=size=128x64:rate=24','-frames:v','121',
                '-c:v','libx264','-preset','ultrafast',str(guide)],check=True,timeout=30)
            (root/'look.png').write_bytes(b'\x89PNG\r\n\x1a\n'+
                b'\x00\x00\x00\rIHDR'+(128).to_bytes(4,'big')+(64).to_bytes(4,'big')+
                b'not-decoded-only-header')
            plan={'model_frames':121,'width':128,'height':64}
            roster={'ffprobe':FFPROBE}
            row=verify_derived_inputs_before_generation(stage=root,plan=plan,installed=roster)
            self.assertEqual(row['model_guide_frames'],121)
            with self.assertRaises(PermissionError):
                verify_derived_inputs_before_generation(stage=root,
                    plan=dict(plan,model_frames=120),installed=roster)
            (root/'look.png').write_bytes(b'not a real look')
            with self.assertRaises(PermissionError):
                verify_derived_inputs_before_generation(stage=root,plan=plan,installed=roster)


class LockContract(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.exe=self.root/'broker.exe'
        self.exe.write_bytes(b'reviewed-entry')
        self.files={}
        for name in ('checkpoint','spatial_upsampler','lora','ffmpeg','ffprobe'):
            file=self.root/(name+'.bin')
            file.write_bytes(name.encode())
            self.files[name]={'path':str(file),'sha256':H(file.read_bytes())}
        self.files['python']={'path':str(self.exe),'sha256':H(self.exe.read_bytes())}
        self.dirs={}
        for name in ('gemma_root','ltx_package'):
            folder=self.root/name
            folder.mkdir()
            (folder/'model.bin').write_bytes(name.encode())
            self.dirs[name]={'path':str(folder),'files':{'model.bin':H((folder/'model.bin').read_bytes())}}
        self.doc={'format':LOCK_FORMAT,'install_root':str(self.root),
                  'upstream_commit':'d'*40,'files':self.files,'directories':self.dirs}
        self.write()

    def write(self):
        self.raw=json.dumps(self.doc,sort_keys=True,separators=(',',':')).encode()
        (self.root/LOCK_NAME).write_bytes(self.raw)

    def test_full_installed_lock_verifies(self):
        got=read_pinned_install(self.exe,H(self.raw))
        self.assertEqual(Path(got['python']),self.exe)
        self.assertEqual(Path(got['lora']),Path(self.files['lora']['path']))

    def test_license_model_asset_drift_refuses(self):
        (self.root/'lora.bin').write_bytes(b'tamper')
        with self.assertRaises(PermissionError):
            read_pinned_install(self.exe,H(self.raw))

    def test_model_directory_extra_file_refuses(self):
        (self.root/'gemma_root'/'surprise.txt').write_bytes(b'mismatch')
        with self.assertRaises(PermissionError):
            read_pinned_install(self.exe,H(self.raw))

    def test_manifest_change_refuses(self):
        self.doc['upstream_commit']='c'*40
        self.write()
        with self.assertRaises(PermissionError):
            read_pinned_install(self.exe,H(b'old-byte-pin'))

    def test_direct_unsandboxed_broker_execution_refuses(self):
        with self.assertRaises(PermissionError):
            run_installed_broker(stage=self.root,installed_executable=self.exe,
                expected_lock_sha256=H(self.raw))
