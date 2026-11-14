"""DA-05 derivative 2D packaging acceptance (test raster stub only).

Real OpenUSD frozen source, exact authored camera timeline, approved and
denied output, sample-addressable PCM WAV, original SHA and explicit
picture gaps. A tiny deterministic Python PNG fixture is NOT evidence of
the production 3D raster renderer or accepted cinema master.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave
import zlib

import test_nvp_data_av_native as fixture
from backend.nvp_exact_time_shots import ExactTimeShotSequence
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_final_2d_native import Approved2DPackage

T=fixture.T


def png(r=0,g=0,b=0):
    def chunk(tag, data):
        return struct.pack(">I",len(data))+tag+data+struct.pack(
            ">I",zlib.crc32(tag+data))
    raw=b"".join(b"\x00"+bytes([r,g,b])*8 for _ in range(8))
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",
            struct.pack(">IIBBBBB",8,8,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress(raw))+
            chunk(b"IEND",b""))


class NativeDataFirstOutputTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        self.tmp=tempfile.TemporaryDirectory(prefix="nvp-2d-derived-")
        self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        self.events=[]
        self.grants=[]
        self.exporter=Approved2DPackage(
            self.index,native_creator_approval=lambda scope:
                self.grants.append(scope) is None and self.allow,
            render_png=lambda *,scope,tick,camera_path,source_snapshot:
                self._render(tick,camera_path,source_snapshot))
        self.allow=True

    def _render(self,tick,camera_path,snapshot):
        self.events.append((tick,camera_path,snapshot["scene_document_sha256"]))
        return png(0 if camera_path is None else (tick//(T//24))%255,10,40)

    def create(self,*,with_gap=False):
        camera="/World/ListenerLeft"
        duration=T
        observations=([
            {"shot_id":"Shot1","camera_path":camera,"pattern":"single",
             "start_tick":"0","end_tick":str(T//3)},
            {"shot_id":"Shot2","camera_path":camera,"pattern":"single",
             "start_tick":str((T*2)//3),"end_tick":str(T)}
        ] if with_gap else [{
            "shot_id":"Shot1","camera_path":camera,"pattern":"continuous",
            "start_tick":"0","end_tick":str(T)}
        ])
        ExactTimeShotSequence(self.index).publish(
            self.pid,"OutputCuts",scene_id="spatial_world",scene_revision=1,
            shots=observations,duration_tick=str(duration))
        taken=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
                event=="native_approved").freeze(
                self.pid,"OutputTake",scene_id="spatial_world",
                scene_revision=1,timeline_id="OutputCuts",timeline_revision=1,
                sample_ticks=[0],creator_event="native_approved")
        return taken["document_sha256"]

    def test_exact_camera_samples_pcm_and_gaps_are_only_derived_output(self):
        sha=self.create(with_gap=True)
        result=self.exporter.export(
            self.pid,"OutputTake",sha,"FinalTestA",self.out,
            listener_path="/World/ListenerLeft",fps_num=24,fps_den=1)
        self.assertEqual(result["status"],"DERIVED_2D_PACKAGE")
        self.assertFalse(result["single_file_master"])
        folder=Path(result["directory"])
        manifest=json.loads((folder/"manifest.json").read_text())
        self.assertEqual(manifest["original_take_sha256"],sha)
        self.assertEqual(manifest["output_picture_count"],24)
        self.assertEqual(manifest["audio_samples"],48000)
        self.assertTrue(any(x["camera_path"] is None for x in manifest["pictures"]))
        self.assertEqual(len(self.events),24)
        self.assertEqual(hashlib.sha256(
            (folder/"soundtrack.wav").read_bytes()).hexdigest(),
            manifest["audio_sha256"])
        with wave.open(str(folder/"soundtrack.wav"),"rb") as audio:
            self.assertEqual(audio.getnframes(),48000)
            self.assertEqual(audio.getframerate(),48000)
        self.assertEqual(self.index.read_revision(
            self.pid,"OutputTake",1)["document_sha256"],sha)
        self.assertEqual(self.grants[0]["listener_path"],"/World/ListenerLeft")
        with self.assertRaises(FileExistsError):
            self.exporter.export(
                self.pid,"OutputTake",sha,"FinalTestA",self.out,
                listener_path="/World/ListenerLeft",fps_num=24,fps_den=1)

    def test_denied_export_never_creates_derived_or_mutates_take(self):
        sha=self.create()
        self.allow=False
        with self.assertRaises(PermissionError):
            self.exporter.export(self.pid,"OutputTake",sha,"Denied",self.out,
                                 listener_path="/World/ListenerLeft")
        self.assertEqual(list(self.out.iterdir()),[])
        self.assertEqual(self.index.read_revision(
            self.pid,"OutputTake",1)["document_sha256"],sha)

    def test_invalid_authoritative_sources_and_listener_fail_closed(self):
        sha=self.create()
        with self.assertRaises(ValueError):
            self.exporter.export(
                self.pid,"OutputTake",sha,"BadListener",self.out,
                listener_path="/World/Actor")
        with self.assertRaises(RuntimeError):
            self.exporter.export(
                self.pid,"OutputTake","0"*64,"WrongSHA",self.out,
                listener_path="/World/ListenerLeft")


if __name__=="__main__":
    unittest.main()
