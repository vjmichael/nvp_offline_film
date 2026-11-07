"""DATA-AV-01: actual native USD scene, frozen Take and sample-addressed audio.

No FFmpeg invocation, mocked scene evaluator, MP4 proxy or user BWF
conversion. Installed Windows audio-device acceptance is a separate gate.
"""
import hashlib
import math
from pathlib import Path
import struct
import tempfile
import unittest

from pxr import UsdMedia

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND
from backend.nvp_data_av_source import RecordedSoundSources,SAMPLE_RATE
from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_data_av_usd import spatial_audio_at
from backend.nvp_slate08b_native_camera_ipc import TrustedDesktopCameraBridge

T=TICKS_PER_SECOND
S=T//SAMPLE_RATE


class Window:
    def __init__(self):
        self.url="http://127.0.0.1:7777/"
        self.allow=True
        self.questions=[]
    def get_current_url(self):
        return self.url
    def create_confirmation_dialog(self,title,message):
        self.questions.append((title,message))
        return self.allow


class NativeDigitalTakeAudioTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="nvp-data-av-native-")
        self.addCleanup(temp.cleanup)
        self.studio=Studio(Path(temp.name)/"studio.sqlite3")
        self.pid=self.studio.create_project(
            "One frozen 3D performance","Data-first audio")["id"]
        self.index=FilmIndex(self.studio)
        self.sound=RecordedSoundSources(self.index)
        self.scene=OpenUSDSceneBridge(self.index)
        self.timeline=TemporalLedger(self.index)
        self.takes=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
            event=="approved" and scope["operation"]==
            "nvp.freeze.usd_temporal_take.v1")
        self.original=struct.pack("<"+"h"*48000,*(
            int(9000*math.sin(2*math.pi*330*i/48000))
            for i in range(48000)))
        self.audio=self.sound.publish(self.pid,"mic_signal",[
            self.original[:32000],self.original[32000:]])
        self.scene.publish(self.pid,"spatial_world",prims=[
            {"path":"/World/Actor","role":"actor","position":[5,0,0]},
            {"path":"/World/ListenerLeft","role":"camera","position":[0,0,0]},
            {"path":"/World/ListenerRight","role":"anchor","position":[10,0,0]},
        ],curves=[],native_schemas=True)
        self.timeline.publish(self.pid,"sound_events",[{
            "event_id":"actor_speaks","event_kind":"dialogue",
            "subject_id":"Actor","start_tick":0,"end_tick":2*T,
            "source_id":"mic_signal","source_revision":1,
            "payload":{"usd_prim_path":"/World/Actor","gain":1.0},
        }],duration_tick=3*T)
        self.take=self.takes.freeze(
            self.pid,"frozen_audio_take",scene_id="spatial_world",
            scene_revision=1,timeline_id="sound_events",
            timeline_revision=1,sample_ticks=[0,T,2*T],
            creator_event="approved")
        self.sha=self.take["document_sha256"]

    def engine(self,listener):
        return FrozenSceneAV(self.index,self.pid,"frozen_audio_take",
            expected_take_sha256=self.sha,listener_path=listener)

    def test_source_chunks_seek_forward_backward_and_cross_boundary(self):
        start=16000-32
        actual=self.sound.read(self.pid,"mic_signal",1,start,128)
        self.assertEqual(actual,self.original[start*2:(start+128)*2])
        a=self.sound.read(self.pid,"mic_signal",1,30000,256)
        b=self.sound.read(self.pid,"mic_signal",1,30000,256)
        self.assertEqual(a,b)
        with self.assertRaises(ValueError):
            self.sound.read(self.pid,"mic_signal",1,47999,3)
        with self.assertRaises(ValueError):
            self.sound.publish(self.pid,"bad_sound",[b"\x00"],expected_revision=0)

    def test_same_frozen_take_two_listeners_yield_different_pcm(self):
        near=self.engine("/World/ListenerLeft")
        far=self.engine("/World/ListenerRight")
        a=near.audio_window(12000,2048)
        b=far.audio_window(12000,2048)
        self.assertEqual(a["status"],"READY")
        self.assertEqual(a["actual_start_tick"],str(12000*S))
        self.assertEqual(a["next_tick"],str(14048*S))
        self.assertEqual(a["take_document_sha256"],b["take_document_sha256"])
        self.assertNotEqual(a["audio_sha256"],b["audio_sha256"])
        self.assertEqual(a["audible_event_ids"],["actor_speaks"])
        self.assertEqual(a["sample_encoding"],"signed_16_le")
        self.assertFalse(a["frame_based_playback"])
        self.assertFalse(a["source_modified"])
        self.assertFalse(a["film_master_approved"])
        self.assertEqual(self.index.read_revision(
            self.pid,"frozen_audio_take",1)["document_sha256"],self.sha)
        self.assertEqual(self.sound.read(
            self.pid,"mic_signal",1,0,2048),self.original[:4096])
        near.close()
        with self.assertRaises(PermissionError):
            near.audio_window(12000,128)

    def test_trailing_signal_silence_is_real_film_time_not_skipped(self):
        engine=self.engine("/World/ListenerLeft")
        tail=engine.audio_window(52000,2048)
        import base64
        self.assertEqual(base64.b64decode(tail["pcm_base64"]),
                         b"\x00"*(2048*4))

    def test_native_usd_spatial_audio_overlay_is_ephemeral_and_sha_bound(self):
        before=self.index.read_revision(
            self.pid,"spatial_world",1)["document_sha256"]
        result=spatial_audio_at(
            self.index,self.pid,"spatial_world",1,"sound_events",1,T//2)
        self.assertEqual(result["format"],"nvp.data_av.usd_spatial_bindings.v1")
        self.assertEqual(len(result["bindings"]),1)
        binding=result["bindings"][0]
        self.assertEqual(binding["usd_schema"],"UsdMediaSpatialAudio")
        self.assertEqual(binding["source_document_sha256"],
                         self.audio["document_sha256"])
        self.assertFalse(binding["revised_frozen_layer"])
        self.assertEqual(self.index.read_revision(
            self.pid,"spatial_world",1)["document_sha256"],before)

    def test_native_creator_permission_seek_and_stop_are_window_scoped(self):
        bridge=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:7777")
        self.addCleanup(bridge._close)
        window=Window()
        bridge._attach_window(window)
        catalog=bridge.data_av_catalog(self.pid)
        self.assertFalse(catalog["ffmpeg_runtime_required"])
        self.assertEqual(len(catalog["takes"]),1)
        request={
            "project_id":self.pid,"take_id":"frozen_audio_take",
            "take_document_sha256":self.sha,
            "listener_path":"/World/ListenerLeft","first_sample":0,
            "direction":"forward",
        }
        window.allow=False
        denied=bridge.data_av_begin(request)
        self.assertEqual(denied["status"],"DENIED")
        window.allow=True
        allowed=bridge.data_av_begin(request)
        self.assertEqual(allowed["status"],"READY")
        self.assertEqual(len(window.questions),2)
        ticket=allowed["session_id"]
        segment=bridge.data_av_audio_window(ticket,12345,512)
        self.assertEqual(segment["sample_count"],512)
        self.assertEqual(segment["session_id"],ticket)
        scene=bridge.data_av_scene_at(ticket,12345*S)
        self.assertEqual(scene["status"],"SCENE_READY")
        self.assertEqual(scene["spatial_audio"]["bindings"][0][
            "event_id"],"actor_speaks")
        with self.assertRaises(PermissionError):
            bridge.data_av_audio_window(ticket,-1,512)
        with self.assertRaises(PermissionError):
            bridge.data_av_audio_window(ticket,0,8192)
        with self.assertRaises(PermissionError):
            bridge.data_av_audio_window("foreign_ticket",0,256)
        window.url="http://evil.example/"
        with self.assertRaises(PermissionError):
            bridge.data_av_audio_window(ticket,0,256)
        window.url="http://127.0.0.1:7777/"
        self.assertEqual(bridge.data_av_stop(ticket)["status"],"STOPPED")
        with self.assertRaises(PermissionError):
            bridge.data_av_audio_window(ticket,0,256)

    def test_reverse_audio_permission_is_prior_to_selected_sample(self):
        bridge=TrustedDesktopCameraBridge(
            self.index,origin="http://127.0.0.1:7777")
        self.addCleanup(bridge._close)
        bridge._attach_window(Window())
        grant=bridge.data_av_begin({
            "project_id":self.pid,"take_id":"frozen_audio_take",
            "take_document_sha256":self.sha,
            "listener_path":"/World/ListenerLeft",
            "first_sample":24000,"direction":"reverse"})
        self.assertEqual(grant["status"],"READY")
        self.assertEqual(grant["last_sample_exclusive"],24000)
        self.assertEqual(grant["approved_first_sample"],0)
        receipt=bridge.data_av_audio_window(grant["session_id"],23900,100)
        self.assertEqual(receipt["sample_count"],100)
        with self.assertRaises(PermissionError):
            bridge.data_av_audio_window(grant["session_id"],24000,100)
        self.assertEqual(bridge.data_av_stop(grant["session_id"])[
            "status"],"STOPPED")

    def test_original_audio_chunk_tampering_fails_closed(self):
        chunk=self.index.read_revision(self.pid,"mic_signal",1)[
            "data"]["chunks"][0]["blob_sha256"]
        path=self.index._blob_path(self.pid,chunk)
        original=path.read_bytes()
        path.write_bytes(original[:-2]+b"\xff\x7f")
        try:
            with self.assertRaises(RuntimeError):
                self.engine("/World/ListenerLeft").audio_window(0,128)
        finally:
            path.write_bytes(original)


if __name__=="__main__":
    unittest.main()
