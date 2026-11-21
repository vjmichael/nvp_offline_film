import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from backend.nvp_diffusion_music_prompt import freeze_diffusion_conditioning
from backend.nvp_post01f_ltx_native_command import build_layout_to_render_argv


class LiveLtxPromptBridge(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.installed=root/'installed';self.installed.mkdir()
        self.stage=root/'stage';self.stage.mkdir()
        for name in ('python.exe','model.safetensors','upscale.safetensors','adapter.safetensors'):
            (self.installed/name).write_bytes(b'pinned')
        (self.installed/'gemma').mkdir()
        (self.stage/'layout.mp4').write_bytes(b'ftyp')
        (self.stage/'look.png').write_bytes(b'png')
        self.pin={'install_root':str(self.installed),'python':str(self.installed/'python.exe'),
                  'checkpoint':str(self.installed/'model.safetensors'),
                  'spatial_upsampler':str(self.installed/'upscale.safetensors'),
                  'lora':str(self.installed/'adapter.safetensors'),
                  'gemma_root':str(self.installed/'gemma')}
        self.plan={'format':'nvp.post01f.ltx_layout_request.v1','job_id':'ltx_'+'1'*24,
             'project_id':'a'*32,'take_sha256':'b'*64,
             'layout_sha256':'b'*64,'look_sha256':'b'*64,
             'conditioning_sha256':'b'*64,'model_stack_sha256':'b'*64,
             'display_frames':120,'model_frames':121,'fps':24,'width':768,'height':448,
             'seed':42,'camera_id':'cam1'}
        self.prompt='A cinematic forest at dawn with blue fog.'

    def make(self, enabled, *, raw=False):
        data,digest=freeze_diffusion_conditioning(positive_prompt=self.prompt,
            take_sha256=self.plan['take_sha256'],camera_id=self.plan['camera_id'],
            no_background_music=enabled)
        if raw:
            obj=json.loads(data)
            obj.pop('no_background_music')
            data=json.dumps(obj,sort_keys=True,separators=(',',':')).encode('ascii')
        self.plan['conditioning_sha256']=sha256(data).hexdigest()
        (self.stage/'conditioning.json').write_bytes(data)
        self.assertEqual(sha256((self.stage/'conditioning.json').read_bytes()).hexdigest(),
                         self.plan['conditioning_sha256'])
        argv=build_layout_to_render_argv(self.plan, job_root=self.stage, installed=self.pin)
        return argv[argv.index('--prompt')+1]

    def test_enabled_reaches_actual_ltx_argv(self):
        self.assertEqual(self.make(True),self.prompt+'\nNo background music.')

    def test_disabled_preserves_user_prompt(self):
        self.assertEqual(self.make(False),self.prompt)

    def test_old_conditioning_defaults_to_disabled(self):
        self.assertEqual(self.make(False,raw=True),self.prompt)

    def test_nonboolean_option_refused(self):
        self.make(True)
        path=self.stage/'conditioning.json'
        data=json.loads(path.read_text())
        data['no_background_music']='true'
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            build_layout_to_render_argv(self.plan,job_root=self.stage,installed=self.pin)

    def test_unknown_conditional_key_refused(self):
        self.make(True)
        path=self.stage/'conditioning.json'
        data=json.loads(path.read_text())
        data['unapproved_command']='some flag'
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            build_layout_to_render_argv(self.plan,job_root=self.stage,installed=self.pin)

if __name__=='__main__':unittest.main()
