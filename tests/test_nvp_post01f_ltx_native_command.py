"""R1 documented CLI-to-R2-broker shape checks. No process/model is run."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from backend.nvp_post01f_ltx_native_command import build_layout_to_render_argv
from backend.nvp_post01f_ltx_native_handoff import WIRE


class LtxNativeCommand(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=pathlib.Path(self.tmp.name)
        self.installed=root/"installed"
        self.installed.mkdir()
        self.stage=root/"stage"
        self.stage.mkdir()
        for file in ("python.exe","model.safetensors","upscale.safetensors","adapter.safetensors"):
            (self.installed/file).write_bytes(b"pinned-test")
        (self.installed/"gemma").mkdir()
        (self.stage/"layout.mp4").write_bytes(b"test")
        (self.stage/"look.png").write_bytes(b"test")
        self.pin=dict(install_root=str(self.installed),python=str(self.installed/"python.exe"),
            checkpoint=str(self.installed/"model.safetensors"),
            spatial_upsampler=str(self.installed/"upscale.safetensors"),
            lora=str(self.installed/"adapter.safetensors"),
            gemma_root=str(self.installed/"gemma"))
        self.plan=dict(format=WIRE,job_id="ltx_"+"1"*24,
            project_id="a"*32,take_sha256="b"*64,layout_sha256="b"*64,
            look_sha256="b"*64,conditioning_sha256="b"*64,model_stack_sha256="b"*64,
            display_frames=120,model_frames=121,fps=24,
            width=768,height=448,seed=42,camera_id="cam1")
        self.guide=dict(positive_prompt="A cinematic live-action desert, golden light.",
            take_sha256="b"*64,camera_id="cam1")
        self.write_guide()

    def write_guide(self):
        (self.stage/"conditioning.json").write_text(json.dumps(self.guide), encoding="utf8")

    def test_native_r1_cli_exact_layout_to_render_recipe(self):
        argv=build_layout_to_render_argv(self.plan,job_root=self.stage,installed=self.pin)
        self.assertEqual(argv[1:3],["-m","ltx_pipelines.ic_lora"])
        self.assertIn("--stage-2-ic-lora",argv)
        self.assertEqual(argv[argv.index("--image")+2:argv.index("--image")+4],["-1","1.0"])
        self.assertEqual(argv[argv.index("--num-frames")+1],"121")
        self.assertEqual(argv[argv.index("--frame-rate")+1],"24")
        self.assertEqual(argv[argv.index("--video-conditioning")+2],"1.0")
        self.assertEqual(argv[argv.index("--output-path")+1],str(self.stage/"picture.native.mp4"))

    def test_foreign_take_or_camera_guide_refuses(self):
        self.guide["camera_id"]="other"
        self.write_guide()
        with self.assertRaises(ValueError):
            build_layout_to_render_argv(self.plan,job_root=self.stage,installed=self.pin)

    def test_model_escaped_installed_root_refuses(self):
        self.pin["lora"]=str(self.stage/"look.png")
        with self.assertRaises(PermissionError):
            build_layout_to_render_argv(self.plan,job_root=self.stage,installed=self.pin)

    def test_extra_command_and_manifest_fields_refuse(self):
        self.pin["extra"]="--network"
        with self.assertRaises(ValueError):
            build_layout_to_render_argv(self.plan,job_root=self.stage,installed=self.pin)

if __name__=="__main__":unittest.main()
