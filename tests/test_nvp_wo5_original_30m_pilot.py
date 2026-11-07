"""WO5 original 30-minute native data-first authoring and immutable retake.

This test proves data/revisions and project reopen. It explicitly does NOT
claim that 43,200 XYZ12 frames were rendered, mastered or watched.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from tools.nvp_wo5_original_30m_pilot import (
    write_original_30minute_source,FRAMES,DURATION,T)
from backend.nvp_studio import Studio
from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_take import OpenUSDTakeCapture
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_temporal_ledger import TemporalLedger
from backend.nvp_data_av_source import RecordedSoundSources
from backend.nvp_exact_time_shots import ExactTimeShotSequence

class OriginalThirtyMinuteAuthoring(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dest=Path(self.temp.name).resolve()/"original_pilot"
        self.report=write_original_30minute_source(
            self.dest,approve_test_only=True)
        self.pid=self.report["project_id"]
        self.studio=Studio(self.dest/"pilot.sqlite3")
        self.index=FilmIndex(self.studio)

    def test_real_30minute_original_3d_take_six_reels_and_60_shots_survive_reopen(self):
        r=self.report
        self.assertEqual(r["status"],
            "ORIGINAL_30_MINUTE_NATIVE_SOURCE_AUTHORED_NOT_RENDERED")
        self.assertEqual(r["target_frames"],43200)
        self.assertEqual(r["duration_ticks"],1800*T)
        self.assertEqual(len(r["reel_plan"]),6)
        self.assertEqual(r["shot_count"],60)
        self.assertEqual(r["act_count"],6)
        self.assertEqual(len(r["original_audio_sources"]),6)
        self.assertFalse(r["real_43200_dci_xyz12_frames_rendered"])
        self.assertFalse(r["real_dcp_picture_and_sound_published"])
        saved=json.loads((self.dest/"source-evidence.json").read_text())
        self.assertEqual(saved["take_document_sha256"],
                         r["take_document_sha256"])
        frozen=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda *_:False)
        state=frozen.verify_take(self.pid,"RelayNineOriginalTake")
        self.assertEqual(state["status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.assertEqual(
            self.index.read_revision(self.pid,"RelayNineOriginalTake",1)[
                "document_sha256"],r["take_document_sha256"])
        shot=ExactTimeShotSequence(self.index).read(
            self.pid,"RelayNineShotEdit",1)
        self.assertEqual(len(shot["shots"]),60)
        self.assertEqual(shot["duration_tick"],str(1800*T))
        for entry in r["original_audio_sources"]:
            desc=RecordedSoundSources(self.index).describe(
                self.pid,entry["source_id"],1)
            self.assertEqual(desc["data"]["sample_count"],48000)
            self.assertEqual(desc["document_sha256"],
                             entry["source_document_sha256"])

    def test_director_can_create_new_take_from_original_scene_data_without_touching_final_take(self):
        pid=self.pid
        old=self.index.read_revision(pid,"RelayNineOriginalTake",1)
        old_scene=self.index.read_revision(pid,"RelayNineScene",1)
        # The editor chooses a fresh source scene revision and a fresh
        # recording ID; it must not attempt to reconstruct USD from a DCP.
        original_prims=[
            {"path":"/World/RelayCore","role":"prop","position":[0,0,0]},
            {"path":"/World/ServiceCraft","role":"actor","position":[-8,2,1]},
            {"path":"/World/Engineer","role":"actor","position":[-3,1,0]},
            {"path":"/World/WideCamera","role":"camera","position":[0,-20,8]},
            {"path":"/World/CloseCamera","role":"camera","position":[0,-8,2]},
            {"path":"/World/TravelCamera","role":"camera","position":[-8,-9,4]},
            {"path":"/World/RelayKey","role":"light","position":[2,1,7]},
        ]
        bindings=[{"path":"/World/"+name,"asset_id":name,
                   "asset_revision":1}
                  for name in ("RelayCore","ServiceCraft","Engineer")]
        rescene=OpenUSDSceneBridge(self.index).publish(
            pid,"RelayNineScene",expected_revision=1,
            prims=original_prims,
            curves=[{"path":"/World/Engineer","samples":[
                {"tick":0,"position":[-3,1,0]},
                {"tick":DURATION*T,"position":[4,1,0]}]}],
            native_schemas=True,asset_bindings=bindings)
        self.assertNotEqual(rescene["document_sha256"],
                            old_scene["document_sha256"])
        TemporalLedger(self.index).publish(pid,"RelayNineRetakeTimeline",[{
            "event_id":"RetakeWide",
            "event_kind":"camera","subject_id":"DirectorCamera",
            "start_tick":0,"end_tick":DURATION*T,
            "source_id":"RelayNineScene","source_revision":2,
            "payload":{"usd_prim_path":"/World/WideCamera",
                       "creator_changed_camera":True}}],
            duration_tick=DURATION*T)
        freezer=OpenUSDTakeCapture(
            self.index,verify_creator_action=lambda event,scope:
                event=="CI_RETAKE_SOURCE_PROOF_ONLY" and
                scope["scene_revision"]==2 and
                scope["duration_tick"]==DURATION*T)
        rerecord=freezer.freeze(
            pid,"RelayNineNewTake",
            scene_id="RelayNineScene",scene_revision=2,
            timeline_id="RelayNineRetakeTimeline",timeline_revision=1,
            sample_ticks=[0,150*T,900*T],
            creator_event="CI_RETAKE_SOURCE_PROOF_ONLY")
        self.assertNotEqual(rerecord["document_sha256"],
                            old["document_sha256"])
        self.assertEqual(freezer.verify_take(pid,"RelayNineNewTake")[
            "status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.assertEqual(freezer.verify_take(pid,"RelayNineOriginalTake")[
            "status"],"VERIFIED_FROZEN_DATA_TAKE")
        self.assertEqual(self.index.read_revision(
            pid,"RelayNineOriginalTake",1)["document_sha256"],
            old["document_sha256"])
        self.assertEqual(self.index.read_revision(
            pid,"RelayNineScene",1)["document_sha256"],
            old_scene["document_sha256"])
        self.assertFalse(self.report["real_dcp_picture_and_sound_published"])

if __name__=="__main__":unittest.main()
