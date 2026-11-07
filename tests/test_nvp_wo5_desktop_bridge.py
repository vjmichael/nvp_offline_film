"""WO5 trusted WebView2 creator approval and FilmIndex desktop binding."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_wo4_feature_journal import ASSEMBLY_FORMAT, FRAME_TICKS
from backend.nvp_wo5_desktop_bridge import TrustedDesktopWO5Bridge


class TestNativeWindow:
    def __init__(self, url, approvals=()):
        self.url = url
        self.approvals = list(approvals)
        self.prompts = []

    def get_current_url(self):
        return self.url

    def create_confirmation_dialog(self, title, message):
        self.prompts.append((title, message))
        return self.approvals.pop(0) if self.approvals else False


class NativeDirectorWindowTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name).resolve()
        self.studio=Studio(root/"nvp.sqlite3")
        self.project=self.studio.create_project("Human film review","Original film")["id"]
        self.index=FilmIndex(self.studio)
        self.cut=self.index.register_revision(
            self.project,"OriginalCut01","edit",
            {"format":ASSEMBLY_FORMAT,
             "ordered_reel_job_ids":["reel-one","reel-two"],
             "start_tick":0,"end_tick":48*FRAME_TICKS},
            expected_revision=0,dependencies=[])
        self.bridge=TrustedDesktopWO5Bridge(
            self.index,origin="http://127.0.0.1:51213",
            production_root=root/".native-production-runtime",
            host_factory=lambda _:None)
        self.addCleanup(self.bridge._close)
        self.win=TestNativeWindow("http://127.0.0.1:51213/")
        self.bridge._attach_window(self.win)
        self.shots=[{
            "shot_id":"Shot01","start_tick":0,
            "end_tick":48*FRAME_TICKS,
            "expected_action":"Actor enters","expected_camera":"Wide, slow pan",
            "expected_sound":"Audible footsteps",
        }]

    def intent_request(self):
        return {"project_id":self.project,
                "assembly_id":"OriginalCut01","assembly_revision":1,
                "intent_id":"OriginalIntent01","shots":self.shots}

    def test_real_native_catalog_exposes_only_project_scoped_film_metadata(self):
        view=self.bridge.wo5_review_catalog(self.project)
        self.assertEqual(view["status"],"NATIVE_PROJECT_SCOPED_READ_ONLY")
        self.assertTrue(view["host_native_only"])
        self.assertFalse(view["full_finished_dcp_playback_verified"])
        self.assertEqual(view["assemblies"][0]["assembly_id"],"OriginalCut01")
        self.assertEqual(view["features"],[])
        self.assertEqual(view["director_intents"],[])
        self.assertNotIn(str(self.studio.db_path),repr(view))

    def test_creator_can_deny_then_approve_native_source_bound_intention(self):
        self.win.approvals=[False,True]
        denied=self.bridge.wo5_review_save_intent(self.intent_request())
        self.assertEqual(denied["status"],"DENIED")
        self.assertEqual(self.index.history(self.project,"OriginalIntent01"),[])
        saved=self.bridge.wo5_review_save_intent(self.intent_request())
        self.assertEqual(saved["status"],"DIRECTOR_INTENT_FROZEN_NOT_FILM_ACCEPTED")
        self.assertEqual(len(self.win.prompts),2)
        self.assertIn(self.cut["document_sha256"],self.win.prompts[1][1])
        self.assertIn("not",self.win.prompts[1][1].lower())
        original=self.bridge.wo5_review_read_intent(self.project,"OriginalIntent01")
        self.assertEqual(original["data"]["shots"],self.shots)
        self.assertFalse(original["data"]["film_created"])
        listing=self.bridge.wo5_review_catalog(self.project)
        self.assertEqual(listing["director_intents"][0]["intent_id"],"OriginalIntent01")
        with self.assertRaises(FileExistsError):
            self.bridge.wo5_review_save_intent(self.intent_request())

    def test_host_refuses_untrusted_web_origin_and_browser_approval_boolean(self):
        self.win.url="http://127.0.0.1:51213/evil"
        with self.assertRaises(PermissionError):
            self.bridge.wo5_review_catalog(self.project)
        with self.assertRaises(PermissionError):
            self.bridge.wo5_review_save_intent(self.intent_request())
        self.assertEqual(self.win.prompts,[])
        self.win.url="http://127.0.0.1:51213/"
        with self.assertRaises(PermissionError):
            self.bridge.wo5_review_save_intent(
                {**self.intent_request(),"creator_approved":True})
        self.assertEqual(self.win.prompts,[])

    def test_no_cross_project_read_and_observation_requires_real_feature(self):
        other=self.studio.create_project("Other film","Other story")["id"]
        with self.assertRaises(KeyError):
            self.bridge.wo5_review_read_intent(other,"OriginalCut01")
        self.win.approvals=[True]
        self.bridge.wo5_review_save_intent(self.intent_request())
        with self.assertRaises(KeyError):
            self.bridge.wo5_review_inspect_feature(self.project,"not-a-feature")
        with self.assertRaises((KeyError,PermissionError)):
            self.bridge.wo5_review_save_observations({
                "project_id":self.project, "feature_id":"not-a-feature",
                "intent_id":"OriginalIntent01","review_id":"Viewing01",
                "observations":[{
                    "shot_id":"Shot01","observed_action":"Actor enters",
                    "observed_camera":"Wide","observed_sound":"Footsteps",
                    "judgment":"MATCHED","review_note":""}],
                "watched_entire_film":True,"heard_entire_sound":True,
            })
        self.assertEqual(self.index.history(self.project,"Viewing01"),[])

    def test_read_only_native_review_receives_source_bound_feature_report(self):
        evidence={"status":"SOURCE_CUSTODY_READY_FOR_HUMAN_FILM_REVIEW_NOT_ACCEPTED",
                  "project_id":self.project,"feature_id":"real-job",
                  "production_acceptance":False,
                  "source_reels_for_native_take_audition":[
                      {"take_id":"FrozenTakeA","reel_number":1,
                       "source_playback_only":True,
                       "finished_dcp_playback_verified":False}]}
        with patch("backend.nvp_wo5_desktop_bridge.inspect_original_feature_readiness",
                   return_value=evidence) as verify:
            result=self.bridge.wo5_review_inspect_feature(self.project,"real-job")
        self.assertEqual(result["source_reels_for_native_take_audition"][0][
            "take_id"],"FrozenTakeA")
        self.assertFalse(result["production_acceptance"])
        verify.assert_called_once()


if __name__=="__main__":
    unittest.main()
