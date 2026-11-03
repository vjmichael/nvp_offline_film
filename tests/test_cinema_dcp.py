"""NVP-CINEMA-01A: real-source preflight + strict DCP structure refusal.

Tests explicitly distinguish a *structural* XML/MXF check from verified
cinema essence, color, sound, SMPTE compliance or projector ingest.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.nvp_studio import Studio
from backend.nvp_cinema_dcp import (
    CinemaDCP,DCP_PROFILES,inspect_dcp_folder
)
from backend.nvp_film_index import FilmIndex


class CinemaDCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.studio=Studio(self.root/"nvp.db")
        self.project=self.studio.create_project("Theater","SMPTE projection test")["id"]
        self.film=FilmIndex(self.studio)
        self.cinema=CinemaDCP(self.studio,self.film)
        self.movie=self.root/"verified_picture.mov"
        self.movie.write_bytes(b"test-movie-bytes-no-codec-claim")
        blob=self.film.put_media_file(self.project,self.movie,"video/quicktime")
        self.src={
            "record":{"document_sha256":"a"*64},
            "media":{"sha256":blob["sha256"],"path":str(self.movie)},
            "audit":{"status":"verified_full_motion_unreviewed"},
        }
        self.src["record"]["data"]={
            "format":"nvp.presentation.motion.v1",
            "source_fps":24,"width":256,"height":144,
            "frame_count":16,
            "dialogue_timeline":[{"line_id":"line_1","start_sample":0}]
        }
        self.cinema.motion.reopen=lambda pid,motion_id: self.src

    def tearDown(self):
        self.tmp.cleanup()

    def test_2k_smpte_profile_contract(self):
        self.assertEqual(DCP_PROFILES["smpte_2k_flat_24"]["raster"],[1998,1080])
        self.assertEqual(DCP_PROFILES["smpte_2k_scope_24"]["raster"],[2048,858])
        self.assertEqual({x["fps"] for x in DCP_PROFILES.values()},{24})
        self.assertEqual({x["standard"] for x in DCP_PROFILES.values()},{"SMPTE"})

    def test_by_default_no_sound_blocks_cinema_export(self):
        plan=self.cinema.preflight(self.project,"motion_001")
        self.assertEqual(plan["status"],"blocked")
        self.assertTrue(any("approved" in x for x in plan["blockers"]))
        with self.assertRaisesRegex(RuntimeError,"preflight blocked"):
            self.cinema.package_technical_test(self.project,"motion_001","dcp_test",
                self.root/"dcp",audio_policy="require_approved_sound")
        self.assertEqual(self.film.list_objects(self.project,kind="presentation"),[])

    def test_silent_test_requires_explicit_director_intent_and_warns_on_dialogue(self):
        plan=self.cinema.preflight(self.project,"motion_001",
                                  profile="smpte_2k_scope_24",
                                  audio_policy="explicit_silent_test")
        self.assertEqual(plan["status"],"technical_test_only")
        self.assertEqual(plan["spec"]["raster"],[2048,858])
        self.assertTrue(any("dialogue" in x.lower() for x in plan["warnings"]))
        self.assertTrue(any("upscaled" in x for x in plan["warnings"]))
        with self.assertRaisesRegex(RuntimeError,"Explicit creator acceptance"):
            self.cinema.package_technical_test(self.project,"motion_001","dcp_test",
                self.root/"dcp",audio_policy="explicit_silent_test")
        self.assertFalse((self.root/"dcp").exists())

    def test_refuse_unknown_dcp_formats_or_audio_policies(self):
        for conf in ({"profile":"improvised_1920p"},
                     {"audio_policy":"fake_audiosync"},
                     {"profile":"dcp_4k_unsupported"}):
            with self.subTest(conf=conf),self.assertRaises(ValueError):
                self.cinema.preflight(self.project,"motion_001",**conf)
        with self.assertRaises(ValueError):
            self.cinema.package_technical_test(self.project,"motion_001",
                "dcp_test",self.root/"dcp",name="../bad",
                audio_policy="explicit_silent_test",
                director_silent_test_approval=True)

    def _make_folder(self):
        d=self.root/"test_dcp"
        d.mkdir()
        (d/"ASSETMAP.xml").write_text('<AssetMap xmlns="urn:smpte:429-9:2007"></AssetMap>')
        (d/"CPL.xml").write_text('<CompositionPlaylist></CompositionPlaylist>')
        (d/"PKL.xml").write_text('<PackingList></PackingList>')
        (d/"picture.mxf").write_bytes(b"pretend-container-for-structural-check-only")
        return d

    def test_dcp_requires_manifest_mxf_and_hashes(self):
        d=self._make_folder()
        report=inspect_dcp_folder(d)
        self.assertEqual(report["status"],"structural_only_not_cinema_conformance")
        self.assertEqual(report["asset_count"],4)
        self.assertEqual(set(report["components"]),
                         {"AssetMap","CompositionPlaylist","MXF","PackingList"})
        self.assertTrue(all(len(x["sha256"])==64 for x in report["files"]))
        (d/"picture.mxf").write_bytes(b"modified not-valid-essence")
        new=inspect_dcp_folder(d)
        self.assertNotEqual(report["files"],new["files"])
        (d/"CPL.xml").unlink()
        with self.assertRaisesRegex(RuntimeError,"incomplete"):
            inspect_dcp_folder(d)

    def test_dcp_folder_symlink_xml_and_empty_essence_refused(self):
        d=self._make_folder()
        (d/"picture.mxf").write_bytes(b"")
        with self.assertRaisesRegex(RuntimeError,"empty"):
            inspect_dcp_folder(d)
        (d/"picture.mxf").write_bytes(b"real-byte")
        (d/"PKL.xml").write_text("<PackingList")
        with self.assertRaisesRegex(RuntimeError,"Invalid DCP XML"):
            inspect_dcp_folder(d)
        (d/"PKL.xml").write_text("<PackingList/>")
        external=self.root/"external.dat"
        external.write_bytes(b"other project secret")
        link=d/"external.dat"
        try:
            link.symlink_to(external)
        except OSError:
            self.skipTest("File symlinks disabled on this platform")
        with self.assertRaisesRegex(RuntimeError,"symbolic link"):
            inspect_dcp_folder(d)

    def test_missing_dcpomatic_tools_refuse_without_creating_a_fake_package(self):
        with patch("backend.nvp_cinema_dcp.shutil.which",return_value=None):
            with self.assertRaisesRegex(RuntimeError,"executable unavailable"):
                self.cinema.package_technical_test(
                    self.project,"motion_001","dcp_missing",self.root/"out",
                    audio_policy="explicit_silent_test",
                    director_silent_test_approval=True)
        self.assertEqual(self.film.list_objects(self.project,kind="presentation"),[])

    def test_cannot_publish_incomplete_dcp_when_encoder_is_mocked(self):
        # Even a fake subprocess claiming success cannot publish a non-DCP.
        with patch("backend.nvp_cinema_dcp.shutil.which",
                   side_effect=lambda tool:tool),patch(
                       "backend.nvp_cinema_dcp._process",return_value="success"):
            with self.assertRaisesRegex(RuntimeError,"exactly one cinema package"):
                self.cinema.package_technical_test(
                    self.project,"motion_001","dcp_empty",self.root/"out",
                    audio_policy="explicit_silent_test",
                    director_silent_test_approval=True)
        self.assertEqual(self.film.list_objects(self.project,kind="presentation"),[])


    def test_structurally_plausible_dcp_without_real_decode_is_never_indexed(self):
        # A fake successful packager and valid-looking XML files are not
        # evidence that JPEG2000/MXF picture essence really decodes.
        def fake_process(args, timeout, purpose):
            if purpose == "DCP-o-matic film encode":
                d = Path(args[-1]) / "mock_dcp"
                d.mkdir(parents=True)
                (d / "ASSETMAP.xml").write_text("<AssetMap/>")
                (d / "CPL.xml").write_text("<CompositionPlaylist/>")
                (d / "PKL.xml").write_text("<PackingList/>")
                (d / "picture.mxf").write_bytes(b"not-jpeg2000")
            return "success"

        with patch("backend.nvp_cinema_dcp.shutil.which",
                   side_effect=lambda tool: tool), patch(
                       "backend.nvp_cinema_dcp._process",
                       side_effect=fake_process), patch(
                       "backend.nvp_cinema_dcp.audit_dcp_picture_essence",
                       side_effect=RuntimeError("independent picture decode rejected")):
            with self.assertRaisesRegex(RuntimeError, "decode rejected"):
                self.cinema.package_technical_test(
                    self.project, "motion_001", "dcp_fake_picture",
                    self.root / "out", audio_policy="explicit_silent_test",
                    director_silent_test_approval=True)
        self.assertEqual(self.film.list_objects(
            self.project, kind="presentation"), [])


if __name__=="__main__":
    unittest.main()
