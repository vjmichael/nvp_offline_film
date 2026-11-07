"""WO3-02..04: genuine typed J2K parsing and honest DCP structural output.

These fixtures intentionally use synthetic bytes only to exercise negative
checks and the immutable FilmIndex package ledger. They NEVER claim actual
codec, MXF-essence or cinema playback acceptance.
"""
import hashlib
from io import BytesIO
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid

from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_temporal_ledger import TemporalLedger,TICKS_PER_SECOND as T
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_wo3_j2k_audit import inspect_j2k_header
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,_ppm_xyz12
from backend.nvp_wo3_mxf_native import _frame_receipts,FORMAT as MXF_FORMAT
from backend.nvp_wo3_dcp_package import publish_dcp_candidate
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure


def synthetic_header(*,width=1998,height=1080,bits=12,progression=4,rsiz=3):
    # Real JPEG2000 marker byte grammar but NOT a real encoded picture.
    siz=(struct.pack(">HH8IH",47,rsiz,width,height,0,0,
                     width,height,0,0,3)+
         bytes([bits-1,1,1])*3)
    cod=b"\x00"+bytes([progression])+b"\x00\x01"+bytes([0,5,4,4,0,0])
    return (b"\xff\x4f\xff\x51"+siz+b"\xff\x52"+
            struct.pack(">H",len(cod)+2)+cod+
            b"\xff\x90\x00\x0a"+b"\x00"*24)


def fake_track(kind,asset_id,take_sha,frames=3):
    # Deliberately not valid MXF; the resulting candidate MUST refuse
    # to certify real essence, DCI or projector acceptance.
    raw=(b"NOT_REAL_ASDCP_"+kind.encode("ascii"))*12
    return {
        "format":MXF_FORMAT,"kind":kind,"asset_uuid":asset_id,
        "bytes":raw,"sha256":hashlib.sha256(raw).hexdigest(),
        "frame_count":frames,"edit_rate":[24,1],
        "original_approved_presentation_sha256":take_sha,
        "dci_compliance_verified":False,
        "independent_essence_decode_verified":False,
        "ffmpeg_used":False,"source_modified":False,
    }


class WO3OriginalCinemaAuthoring(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.studio=Studio(root/"cinema.sqlite")
        self.pid=self.studio.create_project("WO3 Native DCP","")["id"]
        self.index=FilmIndex(self.studio)
        # A genuine pxr-authored scene and temporal ledger are frozen.
        # Only the test MXF essence is synthetic; it cannot pass WO3-05.
        OpenUSDSceneBridge(self.index).publish(
            self.pid,"CinemaScene",
            prims=[
                {"path":"/World/Actor","role":"actor",
                 "position":[0,0,0]},
                {"path":"/World/Camera","role":"camera",
                 "position":[0,0,5]},
            ],curves=[],native_schemas=True)
        self.index.register_revision(
            self.pid,"EventSource","performance",
            {"format":"nvp.wo3.test.event","source_modified":False})
        TemporalLedger(self.index).publish(
            self.pid,"CinemaEvents",[{
                "event_id":"begin","event_kind":"action","subject_id":"Actor",
                "start_tick":0,"end_tick":T,
                "source_id":"EventSource","source_revision":1,
                "payload":{"usd_prim_path":"/World/Actor","action":"present"},
            }],duration_tick=2*T)
        take=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
            event=="approved" and
            scope["operation"]=="nvp.freeze.usd_temporal_take.v1"
        ).freeze(self.pid,"FrozenFixture",
                 scene_id="CinemaScene",scene_revision=1,
                 timeline_id="CinemaEvents",timeline_revision=1,
                 sample_ticks=[0,T],creator_event="approved")
        self.sha=take["document_sha256"]
        self.output=root/"exports";self.output.mkdir()
        self.pic=fake_track("picture",str(uuid.uuid4()),self.sha)
        self.snd=fake_track("sound",str(uuid.uuid4()),self.sha)

    def test_real_smpte_package_metadata_is_written_and_reopened(self):
        requested=[]
        rec=publish_dcp_candidate(
            self.index,self.pid,take_id="FrozenFixture",take_revision=1,
            take_sha256=self.sha,picture=self.pic,sound=self.snd,
            output_root=self.output,title="Cinema Original",
            approve=lambda scope:(requested.append(scope) or True))
        self.assertEqual(rec["status"],"STRUCTURAL_DCP_CANDIDATE_PUBLISHED")
        self.assertTrue(requested)
        self.assertFalse(rec["production_dcp_accepted"])
        folder=Path(rec["destination"])
        self.assertTrue((folder/"VOLINDEX.xml").is_file())
        audit=inspect_dcp_structure(folder)
        self.assertEqual(audit["asset_count"],3)
        self.assertTrue(audit["metadata_and_asset_hashes_verified"])
        self.assertFalse(audit["mxf_essence_verified"])
        self.assertFalse(audit["production_dcp_accepted"])
        saved=self.index.read_revision(
            self.pid,"WO3DCP_"+audit["cpl_uuid"].replace("-",""),1)
        self.assertEqual(saved["data"]["original_take_sha256"],self.sha)
        self.assertEqual(saved["dependencies"][0]["role"],"source_take")
        self.assertEqual(self.index.read_revision(
            self.pid,"FrozenFixture",1)["document_sha256"],self.sha)

    def test_denied_and_tampered_source_never_publish(self):
        request=lambda **kw:publish_dcp_candidate(
            self.index,self.pid,take_id="FrozenFixture",take_revision=1,
            take_sha256=self.sha,picture=self.pic,sound=self.snd,
            output_root=self.output,title="Cinema Original",**kw)
        self.assertEqual(request(approve=lambda _:False)["status"],"DENIED")
        self.assertFalse(list(self.output.iterdir()))
        bad=dict(self.pic);bad["bytes"]=b"changed"
        with self.assertRaises(PermissionError):
            publish_dcp_candidate(
                self.index,self.pid,take_id="FrozenFixture",take_revision=1,
                take_sha256=self.sha,picture=bad,sound=self.snd,
                output_root=self.output,title="Cinema Original",
                approve=lambda _:True)
        with self.assertRaises(PermissionError):
            publish_dcp_candidate(
                self.index,self.pid,take_id="FrozenFixture",take_revision=1,
                take_sha256="0"*64,picture=self.pic,sound=self.snd,
                output_root=self.output,title="Cinema Original",
                approve=lambda _:True)
        self.assertFalse(list(self.output.iterdir()))

    def test_native_asset_sequence_edit_rate_requires_exact_match(self):
        bad=dict(self.snd);bad["frame_count"]=4
        with self.assertRaises(ValueError):
            publish_dcp_candidate(
                self.index,self.pid,take_id="FrozenFixture",take_revision=1,
                take_sha256=self.sha,picture=self.pic,sound=bad,
                output_root=self.output,title="Cinema Original",
                approve=lambda _:True)

    def test_j2k_marker_header_only_never_claims_actual_decode(self):
        header=inspect_j2k_header(synthetic_header(),"2K_FLAT_24")
        self.assertEqual(header["components"][0]["precision"],12)
        self.assertFalse(header["full_codestream_decoded"])
        self.assertFalse(header["dci_compliant"])
        for raw in (
            synthetic_header(bits=8),
            synthetic_header(progression=0),
            synthetic_header(rsiz=0),
            synthetic_header(width=2048),
            b"\x00"*120,
        ):
            with self.subTest(blob=raw[:10]):
                with self.assertRaises(ValueError):
                    inspect_j2k_header(raw,"2K_FLAT_24")

    def test_encoder_refuses_non_xyz_and_unknown_codec_binary(self):
        with self.assertRaises(ValueError):
            _ppm_xyz12(b"RGB", "2K_FLAT_24")
        false_binary=self.output/"fake_codec.exe"
        false_binary.write_bytes(b"not-a-licensed-codec")
        with self.assertRaises(PermissionError):
            ApprovedCodecBinary(
                false_binary,sha256="0"*64,
                product="OpenJPEG-opj_compress")
        with self.assertRaises(PermissionError):
            _frame_receipts([{
                "format":"nvp.wo3.native_openjpeg_frame.v1",
                "codestream":synthetic_header(),
                "codestream_sha256":"0"*64,
                "independent_header_constraints_verified":True,
                "original_approved_presentation_sha256":self.sha,
            }],"2K_FLAT_24")


if __name__=="__main__":
    unittest.main()
