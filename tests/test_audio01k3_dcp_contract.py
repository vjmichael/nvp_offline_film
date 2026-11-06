"""AUDIO-01K.3 fail-closed actual DCP packaging contracts (no fake green DCP).

Uses a deliberately invalid miniature package to prove strict independent
validator failure and unchanged source custody. Does not count as cinema
end-to-end acceptance: true DCP-o-matic and DcpDoctor binaries are required.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from backend.nvp_audio01k3_dcp import (
    PROFILE, FORMAT, plan_commands, inspect_dcp_directory,
    validate_strict_smpte, encode_candidate, inspect_cpl_timing)


class DCPContract(unittest.TestCase):
    def test_creator_profile_is_exact_and_unencrypted(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            create,encode=plan_commands(
                folder/"master.mov",folder/"film","Film_2026",
                folder/"dcpomatic2_create",folder/"dcpomatic2_cli")
            self.assertIn("--no-encrypt",create)
            self.assertIn("SMPTE",create)
            self.assertIn("--twok",create)
            self.assertIn("24",create)
            self.assertIn("rec709",create)
            self.assertIn("--audio-channels",create)
            self.assertEqual(create[create.index("--audio-channels")+1],"6")
            self.assertNotIn("--encrypt",create)
            self.assertEqual(encode[1:3],["--no-remote","--dcp-path"])
            for title in ("../bad","space in name","", "t"*82):
                with self.subTest(title=title),self.assertRaises(ValueError):
                    plan_commands(folder/"m.mov",folder,title,
                                  folder/"dcpomatic2_create",folder/"dcpomatic2_cli")

    def test_wrong_or_missing_assets_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            dcp=Path(temp)
            (dcp/"ASSETMAP.xml").write_text("<AssetMap/>")
            (dcp/"VOLINDEX.xml").write_text("<VolumeIndex/>")
            with self.assertRaises(RuntimeError):
                inspect_dcp_directory(dcp)
            (dcp/"CPL.xml").write_text("<CompositionPlaylist><Id>x</Id></CompositionPlaylist>")
            (dcp/"PKL.xml").write_text("<PackingList><Id>x</Id></PackingList>")
            (dcp/"picture.mxf").write_bytes(b"p"*2048)
            (dcp/"sound.mxf").write_bytes(b"s"*2048)
            with self.assertRaises(RuntimeError):
                inspect_dcp_directory(dcp)
            (dcp/"ASSETMAP.xml").write_text(
                "<AssetMap><Path>CPL.xml</Path><Path>PKL.xml</Path>"
                "<Path>picture.mxf</Path><Path>sound.mxf</Path></AssetMap>")
            proof=inspect_dcp_directory(dcp)
            self.assertTrue(proof["structure_only"])
            self.assertFalse(proof["independently_validated"])
            self.assertFalse(proof["dcp_delivered"])
            # Absent independent executable must block promotion.
            with self.assertRaises(RuntimeError):
                validate_strict_smpte(dcp,dcp/"missing-doctor")
            with self.assertRaises(RuntimeError):
                inspect_dcp_directory(dcp/"does_not_exist")
            (dcp/"picture.mxf").write_bytes(b"replacement")
            with self.assertRaises(RuntimeError):
                inspect_dcp_directory(dcp)

    def test_independent_validator_rejects_nonzero_and_skipped_checks(self):
        import os
        import sys
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            dcp=root/"dcp"
            dcp.mkdir()
            (dcp/"ASSETMAP.xml").write_text(
                "<AssetMap><Path>CPL.xml</Path><Path>PKL.xml</Path>"
                "<Path>picture.mxf</Path><Path>sound.mxf</Path></AssetMap>")
            (dcp/"VOLINDEX.xml").write_text("<VolumeIndex/>")
            (dcp/"CPL.xml").write_text(
                "<CompositionPlaylist><Id>id</Id></CompositionPlaylist>")
            (dcp/"PKL.xml").write_text(
                "<PackingList><Id>id</Id></PackingList>")
            (dcp/"picture.mxf").write_bytes(b"P"*2048)
            (dcp/"sound.mxf").write_bytes(b"S"*2048)
            # These intentionally fake validators only prove REJECTION
            # pathways; they NEVER count as a positive native DCP result.
            if os.name!="nt":
                bad=root/"dcpdoctor"
                bad.write_text("#!/bin/sh\\necho strict validation rejected >&2\\nexit 1\\n")
                bad.chmod(0o700)
                with self.assertRaises(RuntimeError):
                    validate_strict_smpte(dcp,bad)
                bad.write_text("#!/bin/sh\\necho check_skipped\\nexit 0\\n")
                bad.chmod(0o700)
                with self.assertRaises(RuntimeError):
                    validate_strict_smpte(dcp,bad)

    def test_smpte_reel_picture_and_sound_duration_must_match_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cpl=root/"CPL.xml"
            def xml(picture,sound):
                return ("<CompositionPlaylist><ReelList><Reel><AssetList>"
                    "<MainPicture><EditRate>24 1</EditRate><Duration>"
                    +str(picture)+"</Duration></MainPicture>"
                    "<MainSound><EditRate>24 1</EditRate><Duration>"
                    +str(sound)+"</Duration></MainSound>"
                    "</AssetList></Reel></ReelList></CompositionPlaylist>")
            cpl.write_text(xml(24,24))
            timing=inspect_cpl_timing(root,24)
            self.assertEqual(timing["frames"],24)
            self.assertEqual(timing["samples_per_channel"],48000)
            with self.assertRaises(RuntimeError):
                inspect_cpl_timing(root,25)
            cpl.write_text(xml(24,23))
            with self.assertRaises(RuntimeError):
                inspect_cpl_timing(root,24)
            cpl.write_text(xml(24,24).replace("24 1","25 1"))
            with self.assertRaises(RuntimeError):
                inspect_cpl_timing(root,24)

    def test_doctype_entities_and_unknown_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            dcp=Path(temp)
            (dcp/"ASSETMAP.xml").write_text(
                '<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///secret">]><AssetMap/>')
            (dcp/"VOLINDEX.xml").write_text("<VolumeIndex/>")
            with self.assertRaises(RuntimeError):
                inspect_dcp_directory(dcp)
            (dcp/"ASSETMAP.xml").write_text("<AssetMap/>")
            (dcp/"fake.pdf").write_bytes(b"not-a-cinema-asset")
            with self.assertRaises(RuntimeError):
                inspect_dcp_directory(dcp)


if __name__=="__main__":
    unittest.main()
