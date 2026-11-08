"""WO6-07F real native OpenUSD surface pixel + 48k PCM AV window checks.

These are authentic USD mesh/render/audio source tests, not mocked images.
No claim of 24 fps physical display, calibrated Hydra light transport or
sustained feature movie playback is made by CPU source pixel tests.
"""
from __future__ import annotations

import base64
from hashlib import sha256
from io import BytesIO
import unittest
import wave

import test_nvp_openusd_reusable_assets as fixture
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_digital_slate_branches import DigitalSlateBranches
from backend.nvp_slate_edit_assembly import SlateSequenceAssembly
from backend.nvp_wo6_07f_rendered_av import (
    rendered_source_window,FORMAT,SAMPLES_PER_FRAME,MAX_FRAMES)
from backend.nvp_temporal_ledger import TICKS_PER_SECOND
from PIL import Image

T=TICKS_PER_SECOND


class NativeOriginalAVRenderedFrames(unittest.TestCase):
    def setUp(self):
        fixture.NativeUSD02Integration.setUp(self)
        self.scene.publish(
            self.pid,"render_source",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                {"path":"/World/KeyLight","role":"light","position":[2,3,4]},
            ],curves=[{"path":"/World/Actor","samples":[
                {"tick":0,"position":[0,0,0]},
                {"tick":2*T,"position":[0.8,0,0]},
            ]}],asset_bindings=[
                {"path":"/World/Actor","asset_id":"body_geometry",
                 "asset_revision":1},
            ],native_schemas=True)
        self.sound=RecordedSoundSources(self.index)
        self.recording=self.sound.publish(
            self.pid,"authentic_foley",[bytes([0xE8,0x03])*48000,
                                      bytes([0xD0,0x07])*48000])
        self.ledger.publish(
            self.pid,"render_timeline",[
                {"event_id":"actor_moves","event_kind":"action",
                 "subject_id":"Actor","start_tick":0,"end_tick":2*T,
                 "source_id":"performance_authority","source_revision":1,
                 "payload":{"usd_prim_path":"/World/Actor"}},
                {"event_id":"authentic_footstep","event_kind":"sound",
                 "subject_id":"Actor","start_tick":0,"end_tick":2*T,
                 "source_id":"authentic_foley","source_revision":1,
                 "payload":{"gain":0.5}},
            ],duration_tick=2*T)
        self.take=self.takes.freeze(
            self.pid,"render_take",scene_id="render_source",
            scene_revision=1,timeline_id="render_timeline",
            timeline_revision=1,sample_ticks=[0,T],
            creator_event="director_confirms")
        self.slate=DigitalSlateBranches(
            self.index,verify_editor_action=lambda *_:False)
        self.graph=self.slate.publish_graph(
            self.pid,"render_graph",scene_id="render_source",
            scene_label="RenderSet",nodes=[{
                "branch_id":"authored_take_branch","kind":"performance",
                "parent_id":None,"fork_tick":None,
                "group_id":"OriginalDirector","primary":True,
                "take_id":"render_take",
                "source_start_tick":0,"source_end_tick":2*T,
                "shot_id":None,"shot_revision":None,
                "slate":{"scene":"RenderSet","setup":"KeyA","shot":"Master",
                         "camera":"Original","take_number":1,
                         "wild":False,"script_revision":"1",
                         "notes":"Original unmodified camera/actor and key"},
            }])
        self.editor=SlateSequenceAssembly(
            DigitalSlateBranches(self.index,verify_editor_action=lambda *_:False),
            verify_editor_action=lambda event,scope:event=="explicit_test_director")
        self.edit=self.editor.commit(
            self.pid,"render_edit",graph_id="render_graph",
            graph_revision=1,segments=[
                {"segment_id":"first_take_part","branch_id":"authored_take_branch",
                 "source_in_tick":0,"source_out_tick":T},
                {"segment_id":"second_take_part","branch_id":"authored_take_branch",
                 "source_in_tick":T,"source_out_tick":2*T},
            ],editor_event="explicit_test_director",expected_revision=0)
        self.original_sound_bytes=self.sound.read(
            self.pid,"authentic_foley",1,0,8192)

    def sample(self,first,count=2,**overrides):
        opts=dict(camera_path="/World/Camera")
        opts.update(overrides)
        return rendered_source_window(
            self.index,self.pid,"render_edit",1,self.edit["document_sha256"],
            first,count,**opts)

    def test_real_camera_light_geometry_png_and_first_party_pcm_window(self):
        r=self.sample(0,3)
        self.assertEqual(r["format"],FORMAT)
        self.assertTrue(r["real_original_usd_pixels_rendered"])
        self.assertTrue(r["source_rasterizer_only_not_hydra"])
        self.assertFalse(r["continuous_24fps_installed_acceptance"])
        self.assertFalse(r["film_delivered"])
        self.assertEqual(r["count"],3)
        self.assertEqual(r["actual_audio_sample_count"],3*SAMPLES_PER_FRAME)
        self.assertEqual(len(r["images"]),3)
        self.assertEqual(r["images"][0]["source_segment_id"],"first_take_part")
        hashes=[]
        for j,image in enumerate(r["images"]):
            self.assertEqual(image["output_frame_zero"],j)
            self.assertGreater(image["actual_rasterized_triangles"],0)
            self.assertGreater(image["real_source_mesh_triangles"],0)
            self.assertEqual(image["source_take_sha256"],self.take["document_sha256"])
            raw=base64.b64decode(image["frame_image_data_url"].split(",",1)[1])
            self.assertEqual(sha256(raw).hexdigest(),image["frame_png_sha256"])
            with Image.open(BytesIO(raw)) as frame:
                self.assertEqual(frame.size,(640,360))
                self.assertEqual(frame.mode,"RGB")
                self.assertGreater(max(frame.getextrema()[0]),0)
            hashes.append(image["frame_png_sha256"])
        audio=base64.b64decode(
            r["source_audio_wav_data_url"].split(",",1)[1])
        self.assertEqual(sha256(audio).hexdigest(),r["source_audio_wav_sha256"])
        with wave.open(BytesIO(audio),"rb") as wav:
            self.assertEqual(wav.getnchannels(),1)
            self.assertEqual(wav.getsampwidth(),2)
            self.assertEqual(wav.getframerate(),48000)
            self.assertEqual(wav.getnframes(),3*SAMPLES_PER_FRAME)
            sound=wav.readframes(3*SAMPLES_PER_FRAME)
        self.assertEqual(sound[:8],bytes([0xF4,0x01])*4)
        self.assertEqual(self.sound.read(
            self.pid,"authentic_foley",1,0,8192),self.original_sound_bytes)
        self.assertEqual(self.index.read_revision(
            self.pid,"render_take",1)["document_sha256"],self.take["document_sha256"])

    def test_true_hard_cut_frame_23_to_24_changes_source_segment_without_audio_gap(self):
        r=self.sample(23,2)
        self.assertEqual([x["source_segment_id"] for x in r["images"]],
                         ["first_take_part","second_take_part"])
        self.assertEqual(r["images"][0]["original_source_tick"],str(23*T//24))
        self.assertEqual(r["images"][1]["original_source_tick"],str(T))
        with wave.open(BytesIO(base64.b64decode(
                r["source_audio_wav_data_url"].split(",",1)[1])),"rb") as wavefile:
            self.assertEqual(wavefile.getnframes(),2*SAMPLES_PER_FRAME)
        self.assertTrue(all(x["actual_rasterized_triangles"]>0 for x in r["images"]))

    def test_denies_wrong_source_camera_invalid_count_outside_cut_and_subframe_hard_cut(self):
        with self.assertRaises(PermissionError):
            self.sample(0,camera_path="/World/Actor")
        with self.assertRaises(ValueError):
            self.sample(0,MAX_FRAMES+1)
        with self.assertRaises(ValueError):
            self.sample(48,1)
        with self.assertRaises(PermissionError):
            rendered_source_window(self.index,self.pid,"render_edit",1,
                                   "0"*64,0,1)
        # Existing editorial engine permits arbitrary exact Film Time trims;
        # frame-synchronized raster playback must NOT round them.
        uneven=self.editor.commit(
            self.pid,"unaligned_edit",graph_id="render_graph",
            graph_revision=1,segments=[
                {"segment_id":"odd_trim","branch_id":"authored_take_branch",
                 "source_in_tick":0,"source_out_tick":T+1},
            ],editor_event="explicit_test_director",expected_revision=0)
        with self.assertRaises(PermissionError):
            rendered_source_window(
                self.index,self.pid,"unaligned_edit",1,
                uneven["document_sha256"],0,1)

    def test_original_source_not_modified_when_capture_frame_uses_default_camera(self):
        r=self.sample(0,1,camera_path=None)
        self.assertEqual(r["images"][0]["original_camera_path"],"/World/Camera")
        self.assertEqual(r["images"][0]["source_take_sha256"],
                         self.take["document_sha256"])
        self.assertFalse(r["source_modified"])


if __name__=="__main__":
    unittest.main()
