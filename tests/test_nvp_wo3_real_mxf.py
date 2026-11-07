"""WO3-02..05 real OpenJPEG + asdcplib MXF integration (native Linux CI).

No fake MXF or mock decoder accepted in this test. A real source Take is
authored/frozen in OpenUSD, two XYZ12 frames are encoded in OpenJPEG cinema
mode, real picture and 24-bit 48kHz sound essence are wrapped by asdcplib,
CPL/PKL/AssetMap are written and audited, then MXF tracks are unpacked and
every J2K frame and all PCM samples actually decoded and checked.
No claim of licensed theatrical hardware calibration or DCI certification.
"""
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
import wave

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND as T
from backend.nvp_wo3_native_codecs import (
    ApprovedCodecBinary,encode_xyz12_frame)
from backend.nvp_wo3_mxf_native import wrap_cinema_picture,wrap_cinema_pcm
from backend.nvp_wo3_dcp_package import publish_dcp_candidate
from backend.nvp_wo3_independent_essence import decode_full_dcp_candidate


@unittest.skipUnless(
    all(os.environ.get(k) for k in (
        "NVP_NATIVE_OPENJPEG","NVP_NATIVE_ASDCP_WRAP",
        "NVP_NATIVE_ASDCP_INFO","NVP_NATIVE_ASDCP_UNWRAP",
        "NVP_NATIVE_OPENJPEG_DECODE")),
    "Native encoder, MXF wrap/read, decoder bundle not supplied")
class WO3RealASDCPIntegration(unittest.TestCase):
    def binary(self,var,product):
        executable=Path(os.environ[var]).resolve(strict=True)
        h=sha256()
        with executable.open("rb") as stream:
            for packet in iter(lambda:stream.read(1024*1024),b""):
                h.update(packet)
        return ApprovedCodecBinary(
            executable,sha256=h.hexdigest(),product=product)

    def test_real_three_frame_native_smpte_dcp_roundtrip(self):
        with TemporaryDirectory(prefix="nvp-wo3-real-") as tmp:
            root=Path(tmp)
            studio=Studio(root/"real_source.sqlite")
            pid=studio.create_project("Real WO3", "")["id"]
            index=FilmIndex(studio)
            OpenUSDSceneBridge(index).publish(
                pid,"CinemaScene",prims=[
                    {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                    {"path":"/World/Camera","role":"camera","position":[0,0,5]},
                ],curves=[],native_schemas=True)
            index.register_revision(pid,"EventSource","performance",
                                    {"format":"wo3.cinema.origin.v1"})
            TemporalLedger(index).publish(pid,"CinemaEvents",[{
                "event_id":"start","event_kind":"action","subject_id":"Actor",
                "start_tick":0,"end_tick":T,
                "source_id":"EventSource","source_revision":1,
                "payload":{"usd_prim_path":"/World/Actor","action":"present"},
            }],duration_tick=2*T)
            take=OpenUSDTakeCapture(
                index,verify_creator_action=lambda event,scope:
                event=="freeze" and scope["operation"]==
                "nvp.freeze.usd_temporal_take.v1").freeze(
                    pid,"CinemaTake",scene_id="CinemaScene",scene_revision=1,
                    timeline_id="CinemaEvents",timeline_revision=1,
                    sample_ticks=[0,T],creator_event="freeze")
            source=take["document_sha256"]
            encoder=self.binary("NVP_NATIVE_OPENJPEG","OpenJPEG-opj_compress")
            decoder=self.binary("NVP_NATIVE_OPENJPEG_DECODE",
                                "OpenJPEG-opj_decompress")
            wrapper=self.binary("NVP_NATIVE_ASDCP_WRAP","ASDCP-asdcp_wrap")
            info=self.binary("NVP_NATIVE_ASDCP_INFO","ASDCP-asdcp_info")
            unwrap=self.binary("NVP_NATIVE_ASDCP_UNWRAP",
                               "ASDCP-asdcp_unwrap")
            raw=b"\x08\x00\x08\x00\x08\x00"*(1998*1080)
            frames=[encode_xyz12_frame(
                encoder,raw,profile="2K_FLAT_24",
                source_presentation_sha256=source,
                creator_approved=True) for _ in range(3)]
            pic=wrap_cinema_picture(
                wrapper,info,frames,profile="2K_FLAT_24",
                asset_uuid=str(uuid.uuid4()))
            audio_bytes=b"\x00\x00\x00"*(6000*2)
            buffer=BytesIO()
            with wave.open(buffer,"wb") as wf:
                wf.setnchannels(2);wf.setsampwidth(3);wf.setframerate(48000)
                wf.writeframes(audio_bytes)
            sound=wrap_cinema_pcm(
                wrapper,info,buffer.getvalue(),
                asset_uuid=str(uuid.uuid4()),frame_count=3,
                origin_sha256=source)
            destination=root/"export";destination.mkdir()
            published=publish_dcp_candidate(
                index,pid,take_id="CinemaTake",take_revision=1,
                take_sha256=source,picture=pic,sound=sound,
                output_root=destination,title="Real Native Cinema Source",
                approve=lambda _:True)
            self.assertEqual(published["status"],
                             "STRUCTURAL_DCP_CANDIDATE_PUBLISHED")
            roundtrip=decode_full_dcp_candidate(
                published["destination"],unwrap=unwrap,decoder=decoder,
                expected_picture_codestream_sha256=[
                    x["codestream_sha256"] for x in frames],
                expected_sound_pcm_sha256=sha256(audio_bytes).hexdigest(),
                profile="2K_FLAT_24",expected_frames=3)
            self.assertEqual(roundtrip["frames_decoded"],3)
            self.assertTrue(roundtrip["picture_exact_codestream_sha_verified"])
            self.assertTrue(roundtrip["pcm24_48000_sample_exact"])
            self.assertFalse(roundtrip["production_dcp_accepted"])
            self.assertFalse(roundtrip["formal_independent_dci_validator_passed"])
            self.assertEqual(index.read_revision(pid,"CinemaTake",1)[
                "document_sha256"],source)
            print("WO3_NATIVE_REAL_MXF_ROUNDTRIP:",{
                "picture_mxf_sha256":pic["sha256"],
                "sound_mxf_sha256":sound["sha256"],
                "source_take_sha256":source,
                "decoded_all_frames":True,
                "pcm_exact":True,
                "production_dcp_accepted":False,
            },flush=True)


if __name__=="__main__":
    unittest.main()
