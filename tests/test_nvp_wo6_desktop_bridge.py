"""WO6 installed desktop pywebview actor, creative and native permission checks."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

from backend.nvp_film_index import FilmIndex
from backend.nvp_openusd_scene import OpenUSDSceneBridge
from backend.nvp_studio import Studio
from backend.nvp_temporal_ledger import TemporalLedger, TICKS_PER_SECOND
from backend.nvp_wo6_desktop_bridge import TrustedDesktopWO6Bridge


class Window:
    def __init__(self):
        self.url="http://127.0.0.1:43231/"
        self.answers=[]
        self.prompts=[]
    def get_current_url(self):
        return self.url
    def create_confirmation_dialog(self,title,message):
        self.prompts.append((title,message))
        return self.answers.pop(0) if self.answers else False


class NativeWO6CreatorDesktop(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name).resolve()
        self.patch=patch.dict(os.environ,{"NVP_HOME":str(root/"Projects")})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.studio=Studio(root/"film.sqlite3")
        self.pid=self.studio.create_project(
            "Native human director test","No automatic AI grants")["id"]
        self.index=FilmIndex(self.studio)
        self.scene=OpenUSDSceneBridge(self.index).publish(
            self.pid,"original_world",prims=[
                {"path":"/World/Actor","role":"actor","position":[0,0,0]},
                {"path":"/World/Camera","role":"camera","position":[0,2,-3]},
            ],curves=[])
        self.index.register_revision(
            self.pid,"actor_source","performance",{"format":"nvp.wo6.actor.test.v1"})
        self.timeline=TemporalLedger(self.index).publish(
            self.pid,"film_time",[{
                "event_id":"walk","event_kind":"action","subject_id":"Actor",
                "start_tick":0,"end_tick":TICKS_PER_SECOND,
                "source_id":"actor_source","source_revision":1,
                "payload":{"usd_prim_path":"/World/Actor"},
            }],duration_tick=2*TICKS_PER_SECOND)
        self.bridge=TrustedDesktopWO6Bridge(
            self.index,origin="http://127.0.0.1:43231",
            host_factory=lambda _:None)
        self.addCleanup(self.bridge._close)
        self.window=Window()
        self.bridge._attach_window(self.window)

    def _request(self):
        preview=self.bridge.wo6_source_impact({
            "project_id":self.pid,"source_id":"original_world",
            "source_revision":1,"source_sha256":self.scene["document_sha256"],
            "change_kind":"retake"})
        return {
            "project_id":self.pid,"scene_id":"original_world",
            "scene_revision":1,"scene_sha256":self.scene["document_sha256"],
            "timeline_id":"film_time","timeline_revision":1,
            "timeline_sha256":self.timeline["document_sha256"],
            "new_take_id":"human_new_take","sample_ticks":[0],
            "preview_sha256":preview["preview_sha256"],
        }

    def test_native_catalog_read_preview_never_issues_authorization(self):
        data=self.bridge.wo6_source_catalog(self.pid)
        self.assertEqual(data["format"],"nvp.wo6.director_desktop_native_consent.v1")
        self.assertFalse(data["model_execute_enabled"])
        self.assertFalse(data["finished_film_accepted"])
        self.assertEqual(data["scenes"][0]["sha256"],self.scene["document_sha256"])
        self.assertEqual(data["timelines"][0]["sha256"],self.timeline["document_sha256"])
        self.assertEqual(len(self.window.prompts),0)
        self.assertEqual(self._request()["scene_sha256"],self.scene["document_sha256"])

    def test_two_independent_real_native_prompts_and_queued_no_film(self):
        request=self._request()
        self.window.answers=[False]
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_take(request)
        self.assertEqual(len(self.window.prompts),1)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"human_new_take")

        self.window.answers=[True,False]
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_take(request)
        self.assertEqual(len(self.window.prompts),3)
        self.assertIn("Separate native worker",self.window.prompts[-1][0])
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"human_new_take")

        self.window.answers=[True,True]
        self.bridge._wo6_host()
        with patch.object(self.bridge._wo6_take,"run_next",return_value=None):
            queued=self.bridge.wo6_create_take(request)
        self.assertEqual(queued["state"],"QUEUED_NOT_ADMITTED")
        task=queued["task_id"]
        evidence=self.bridge.wo6_task_status(self.pid,task)
        self.assertEqual(evidence["state"],"QUEUED")
        self.assertFalse(evidence["film_delivered"])
        self.assertEqual(len(self.window.prompts),5)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"human_new_take")
        self.window.answers=[True]
        cancelled=self.bridge.wo6_cancel_native_task(self.pid,task)
        self.assertEqual(cancelled["state"],"CANCELLED")
        self.assertTrue(cancelled["cancel_intent_durable"])

    def test_foreign_origin_model_supplied_consent_and_bad_project_denied(self):
        request=self._request()
        with self.assertRaises(ValueError):
            self.bridge.wo6_create_take({
                **request,"creator_approved":True,"arbitrary_executable":"python"})
        self.assertFalse(self.window.prompts)
        self.window.url="http://127.0.0.1:43231/attacker"
        with self.assertRaises(PermissionError):
            self.bridge.wo6_source_catalog(self.pid)
        with self.assertRaises(PermissionError):
            self.bridge.wo6_create_take(request)
        self.window.url="http://127.0.0.1:43231/"
        with self.assertRaises(KeyError):
            self.bridge.wo6_source_catalog("f"*32)
        self.assertFalse(self.window.prompts)


if __name__=="__main__":
    unittest.main()
