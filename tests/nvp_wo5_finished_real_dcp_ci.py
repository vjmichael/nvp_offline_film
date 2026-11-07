"""WO5 actual native published final DCP playback across a reel boundary.

This is an integration test using REAL OpenJPEG encode, CineCert picture
and PCM24 MXF wrapping, multi-reel SMPTE XML publication and native
asdcplib unwrap + OpenJPEG decode. It is 6 real distinct-pattern frames,
not a creator-made 30-minute original or continuous realtime playback.
FilmIndex source approval is covered by different tests; this integration
keeps the hash-bound real native essences and projector claims distinct.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_wo4_feature_journal import FeatureJournal,FRAME_TICKS
from backend.nvp_wo3_native_codecs import ApprovedCodecBinary,digest_file
from backend.nvp_wo3_j2k_audit import PROFILES
from backend.nvp_wo3_dcp_structure import inspect_dcp_structure
from backend.nvp_wo4_picture_spool import (
    encode_disk_xyz12,wrap_disk_j2k_picture)
from backend.nvp_wo4_supervised_sound import wrap_supervised_sound
from backend.nvp_wo4_pcm_stream import stream_master_pcm24_candidate
from backend.nvp_wo4_multireel import publish_multireel_dcp
from backend.nvp_wo5_finished_playback import (
    Reel,FinishedFilmPlayer,_fingerprint)

ENV={
  "NVP_NATIVE_OPENJPEG":"OpenJPEG-opj_compress",
  "NVP_NATIVE_OPENJPEG_DECODE":"OpenJPEG-opj_decompress",
  "NVP_NATIVE_ASDCP_WRAP":"ASDCP-asdcp_wrap",
  "NVP_NATIVE_ASDCP_INFO":"ASDCP-asdcp_info",
  "NVP_NATIVE_ASDCP_UNWRAP":"ASDCP-asdcp_unwrap",
}
@unittest.skipUnless(all(os.environ.get(x) for x in ENV),
                    "Native real OpenJPEG/CineCert toolchain required")
class NativePublishedMultiReelViewing(unittest.TestCase):
    def codec(self,key):
        f=Path(os.environ[key]).resolve(strict=True)
        return ApprovedCodecBinary(f,sha256=digest_file(f),product=ENV[key])

    def test_reopen_actual_final_picture_and_sound_on_both_sides_of_real_reel_boundary(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            artifacts=root/"dcp"
            artifacts.mkdir()
            studio=Studio(root/"film.sqlite3")
            project=studio.create_project("Published picture sound","native proof")["id"]
            index=FilmIndex(studio)
            journal=FeatureJournal(root/"production")
            encode=self.codec("NVP_NATIVE_OPENJPEG")
            wrap=self.codec("NVP_NATIVE_ASDCP_WRAP")
            info=self.codec("NVP_NATIVE_ASDCP_INFO")
            unwrap=self.codec("NVP_NATIVE_ASDCP_UNWRAP")
            decode=self.codec("NVP_NATIVE_OPENJPEG_DECODE")
            profile="2K_FLAT_24"
            width,height,_=PROFILES[profile]
            take_sha=sha256(b"CI-owned sealed example identity").hexdigest()
            hashes={}
            receipts=[]
            original_files=[]
            for reel_i in range(2):
                folder=root/f"reel_{reel_i}"
                folder.mkdir()
                sources=folder/"approved_original_xyz12"
                sources.mkdir()
                frames=folder/"j2k"
                frames.mkdir()
                picture_stage=folder/"picture"
                picture_stage.mkdir()
                sounds=folder/"sound"
                sounds.mkdir()
                master_stage=folder/"master"
                master_stage.mkdir()
                codestream_hashes=[]
                for local in range(3):
                    global_index=reel_i*3+local
                    level=(180+global_index*360)
                    original=sources/f"{local:06d}.xyz12"
                    original.write_bytes(level.to_bytes(2,"big")*3*(width*height))
                    original_files.append((original,digest_file(original)))
                    work=folder/f"work_{local}"
                    work.mkdir()
                    encoded=encode_disk_xyz12(
                        encode,profile=profile,source_path=str(original),
                        source_sha256=digest_file(original),
                        private_work=work,check_cancel=lambda:False,
                        timeout=180)
                    codestream_hashes.append(encoded["codestream_sha256"])
                    (work/"frame.j2c").replace(frames/f"{local:06d}.j2c")
                hashes[reel_i]=codestream_hashes
                picture=wrap_disk_j2k_picture(
                    wrap,info,frames_dir=frames,stage_dir=picture_stage,
                    frame_count=3,profile=profile,asset_uuid=str(uuid4()),
                    check_cancel=lambda:False,timeout=180)
                # True native signed PCM24 in the published sound MXF.
                # Different average amplitude on each reel, to catch
                # accidentally continuing the previous sound track.
                amplitude=0x100000+reel_i*0x100000
                raw=(amplitude.to_bytes(3,"little",signed=True) +
                     (-amplitude).to_bytes(3,"little",signed=True))*6000
                raw_path=folder/"original_pcm24.pcm"
                raw_path.write_bytes(raw)
                original_files.append((raw_path,digest_file(raw_path)))
                master=stream_master_pcm24_candidate(
                    raw_path,source_sha256=digest_file(raw_path),
                    original_take_sha256=take_sha,cinema_frames=3,
                    channel_layout="stereo",output_root=master_stage,
                    approve=lambda _:True)
                sound=wrap_supervised_sound(
                    wrap,info,candidate=master,source_take_sha=take_sha,
                    frames=3,sound_uuid=str(uuid4()),
                    stage_dir=sounds,check_cancel=lambda:False)
                picture_file=picture_stage/"picture.mxf"
                sound_file=sounds/"sound.mxf"
                receipts.append({
                    "start_tick":reel_i*3*FRAME_TICKS,
                    "end_tick":(reel_i+1)*3*FRAME_TICKS,
                    "frames":3,"reel_uuid":str(uuid4()),
                    "picture":{"file_path":str(picture_file),
                               "file_sha256":picture["file_sha256"],
                               "file_bytes":picture["file_bytes"],
                               "asset_uuid":picture["asset_uuid"]},
                    "sound":{"file_path":str(sound_file),
                             "file_sha256":sound["file_sha256"],
                             "file_bytes":sound["file_bytes"],
                             "asset_uuid":sound["asset_uuid"]}})
            ids={x:str(uuid4()) for x in ("cpl","pkl","assetmap")}
            published=publish_multireel_dcp(
                reels=receipts,ids=ids,title="Real WO5 final DCP sample",
                profile=profile,output_root=artifacts,
                check_cancel=lambda:False)
            self.assertEqual(published["status"],"MULTIREEL_STRUCTURAL_DCP_PUBLISHED")
            folder=Path(published["destination"])
            dcp=inspect_dcp_structure(folder)
            self.assertEqual(dcp["reel_durations"],[3,3])
            self.assertEqual(dcp["status"],"STRUCTURE_AND_SHA_VERIFIED")
            tracks=dcp["tracks"]
            ordered=[]
            for r in range(2):
                by_kind={t["kind"]:t for t in tracks[r*2:r*2+2]}
                pic=folder/by_kind["picture"]["filename"]
                snd=folder/by_kind["sound"]["filename"]
                ordered.append(Reel(
                    r*3,3,pic,snd,digest_file(pic),digest_file(snd),
                    f"real_native_reel_{r}",("L","R"),
                    _fingerprint(pic),_fingerprint(snd)))
            audit={"filmindex_feature_receipt_sha256":"a"*64,
                   "ordered_picture_custody_sha256":"b"*64,
                   "frame_count":6}
            player=FinishedFilmPlayer(
                index,journal,unwrap=unwrap,decoder=decode,
                private_root=root/"work_native",
                native_window=lambda:True,ask_native=lambda scope:True)
            try:
                with patch("backend.nvp_wo5_finished_playback.load_published_reels",
                           return_value=(audit,tuple(ordered),profile)):
                    started=player.begin(project,"published_real_two_reel")
                self.assertEqual(started["status"],"FINISHED_DCP_READONLY_READY")
                token=started["session_id"]
                def expected_sha(_journal,job_id,local):
                    reel=int(job_id.rsplit("_",1)[1])
                    return hashes[reel][local]
                with patch("backend.nvp_wo5_finished_playback._expected_frame_sha",
                           side_effect=expected_sha):
                    a=player.frame(token,2)
                    b=player.frame(token,3)
                    one=player.window(token,2,4)
                    two=player.window(token,3,2)
                self.assertEqual(one["frame_count"],1)
                self.assertEqual(two["frame_count"],2)
                self.assertEqual(
                    [f["frame_index"] for f in two["frames"]],[3,4])
                self.assertEqual(
                    [f["audio_start_sample"] for f in two["frames"]],
                    [6000,8000])
                self.assertTrue(one["no_reel_crossing"])
                self.assertTrue(two["no_reel_crossing"])
                self.assertEqual((a["reel_index"],a["reel_frame_index"]),(0,2))
                self.assertEqual((b["reel_index"],b["reel_frame_index"]),(1,0))
                self.assertEqual(a["audio_start_sample"],4000)
                self.assertEqual(b["audio_start_sample"],6000)
                self.assertNotEqual(a["source_j2k_sha256"],b["source_j2k_sha256"])
                self.assertNotEqual(a["picture_png_base64"],b["picture_png_base64"])
                self.assertNotEqual(a["stereo_pcm16_base64"],b["stereo_pcm16_base64"])
                self.assertTrue(a["picture_and_sound_from_final_published_mxf"])
                self.assertTrue(b["picture_and_sound_from_final_published_mxf"])
                self.assertFalse(b["production_accepted"])
                player.stop(token)
            finally:
                player.close()
            for original,original_sha in original_files:
                self.assertEqual(digest_file(original),original_sha)

if __name__=="__main__":
    unittest.main()
