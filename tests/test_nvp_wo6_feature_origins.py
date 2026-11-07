"""WO6-02 adapter/authorization contract tests.

The expensive WO5 original-feature SHA/media/native USD auditor is MOCKED
here only to isolate trusted dispatch and exact-source mapping behavior.
These are not a substitute for WO5's genuine native DCP/PCM/J2K tests.
"""
from __future__ import annotations
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.nvp_ai_read_host import NativeAiReadHost, TrustedReadScope
from backend.nvp_film_index import FilmIndex
from backend.nvp_studio import Studio
from backend.nvp_wo4_feature_journal import FeatureJournal
from backend.nvp_wo6_creator_plan import USD_TAKE_FORMAT
from backend.nvp_wo6_feature_origins import (
    FORMAT, resolve_published_feature_origins)


class FeatureOriginalSourcePlanContract(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix="nvp-wo6-origins-")
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.studio=Studio(root/"film.sqlite3")
        self.pid=self.studio.create_project("Film", "Original movie")["id"]
        self.index=FilmIndex(self.studio)
        self.journal=FeatureJournal(root/"native_journal")
        self.scope=TrustedReadScope("filmmaker",self.pid,"turn-wo6-feature")
        scene=self.index.register_revision(
            self.pid,"OriginalUSD","scene",
            {"format":"scene","actor":"original"})
        timeline=self.index.register_revision(
            self.pid,"ActingEvents","temporal",
            {"format":"source.time","duration":800})
        self.take=self.index.register_revision(
            self.pid,"FrozenTake001","take",{
                "format":USD_TAKE_FORMAT,
                "frozen":True,
                "scene_id":"OriginalUSD",
                "scene_revision":1,
                "scene_document_sha256":scene["document_sha256"],
                "timeline_id":"ActingEvents",
                "timeline_revision":1,
                "timeline_document_sha256":timeline["document_sha256"],
            },dependencies=[
                {"object_id":"OriginalUSD","revision":1,"role":"scene"},
                {"object_id":"ActingEvents","revision":1,"role":"temporal"},
            ])
        self.feature={
            "project_id":self.pid,
            "state":"INDEXED",
            "cancel_requested":0,
            "filmindex_sha256":"a"*64,
        }
        self.audit={
            "status":"SOURCE_CUSTODY_READY_FOR_HUMAN_FILM_REVIEW_NOT_ACCEPTED",
            "filmindex_feature_receipt_sha256":"a"*64,
            "project_id":self.pid,
            "feature_id":"OriginalFeature",
            "cpl_uuid":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "duration_ticks":24*294000000,
            "frame_count":24,
            "reel_count":2,
            "source_reels_for_native_take_audition":[{
                "reel_number":i+1,
                "take_id":"FrozenTake001",
                "take_document_sha256":self.take["document_sha256"],
                "approved_frame_count":12,
                "take_start_tick":i*12*294000000,
                "take_end_tick":(i+1)*12*294000000,
                "cut_start_tick":i*12*294000000,
                "cut_end_tick":(i+1)*12*294000000,
                "source_playback_only":True,
                "finished_dcp_playback_verified":False,
            } for i in range(2)],
            "production_acceptance":False,
        }
        self.request={
            "capability_id":"nvp.film.resolve_published_sources.v1",
            "project_id":self.pid,
            "feature_id":"OriginalFeature",
        }

    def with_mocked_native_evidence(self):
        return patch(
            "backend.nvp_wo6_feature_origins.inspect_original_feature_readiness",
            return_value=self.audit)

    def test_source_mapping_requires_verified_feature_and_real_take_identity(self):
        with (patch.object(self.journal,"feature",return_value=self.feature),
              self.with_mocked_native_evidence()):
            result=resolve_published_feature_origins(
                self.index,self.journal,self.pid,"OriginalFeature")
        self.assertEqual(result["format"],FORMAT)
        self.assertEqual(result["status"],
                         "PUBLISHED_ORIGINAL_SOURCES_REOPENED_NOT_RETAKEN")
        self.assertEqual(result["distinct_original_take_count"],1)
        self.assertEqual([x["reel_number"] for x in result["source_reels"]],[1,2])
        self.assertEqual(
            result["source_reels"][0]["original_scene"]["object_id"],
            "OriginalUSD")
        self.assertEqual(
            result["source_reels"][1]["original_temporal_events"]["object_id"],
            "ActingEvents")
        self.assertFalse(result["standalone_dcp_reverse_engineered_into_usd"])
        self.assertFalse(result["new_take_created"])
        self.assertFalse(result["native_creator_approval_granted"])
        self.assertFalse(result["model_executed"])
        self.assertFalse(result["independent_dcp_bv21_theater_validation"])
        self.assertEqual(len(self.index.history(self.pid,"FrozenTake001")),1)

    def test_feature_source_can_only_be_read_with_injected_native_journal_and_turn_grant(self):
        calls=[]
        def authorize(scope,cap,digest,spec):
            calls.append((scope,cap,digest,spec))
            return scope.actor_id=="filmmaker"
        host=NativeAiReadHost(
            self.studio,authorize_read=authorize,feature_journal=self.journal)
        capids={x["id"] for x in host.catalog()["capabilities"]}
        self.assertIn("nvp.film.resolve_published_sources.v1",capids)
        self.assertFalse(host.catalog()["authorization_provided"])
        with (patch.object(self.journal,"feature",return_value=self.feature),
              self.with_mocked_native_evidence()):
            result=host.execute_read(self.scope,self.request)
        self.assertEqual(result["result"]["format"],FORMAT)
        self.assertEqual(result["capability_id"],
                         "nvp.film.resolve_published_sources.v1")
        self.assertFalse(result["authority_granted_to_model"])
        self.assertFalse(result["creator_approval_granted"])
        self.assertEqual(len(calls),1)
        self.assertEqual(result["request_sha256"],calls[0][2])
        with self.assertRaises(PermissionError):
            host.execute_read(self.scope,{**self.request,
                                          "project_id":"different"})
        with self.assertRaises(ValueError):
            host.execute_read(self.scope,{**self.request,
                                          "creator_approval":True})
        self.assertEqual(len(calls),1)
        unconfigured=NativeAiReadHost(
            self.studio,authorize_read=lambda *_:True)
        self.assertNotIn(
            "nvp.film.resolve_published_sources.v1",
            {x["id"] for x in unconfigured.catalog()["capabilities"]})
        with self.assertRaises(ValueError):
            unconfigured.execute_read(self.scope,self.request)

    def test_declined_trusted_scope_prevents_native_feature_audit(self):
        host=NativeAiReadHost(
            self.studio,authorize_read=lambda *_:False,
            feature_journal=self.journal)
        with patch.object(self.journal,"feature") as feature:
            with self.assertRaises(PermissionError):
                host.execute_read(self.scope,self.request)
            feature.assert_not_called()

    def test_other_project_and_replaced_or_cancelled_published_feature_fail(self):
        other=self.studio.create_project("Other", "")["id"]
        with patch.object(self.journal,"feature",return_value=self.feature):
            with self.assertRaises(PermissionError):
                resolve_published_feature_origins(
                    self.index,self.journal,other,"OriginalFeature")
        aborted={**self.feature,"cancel_requested":1}
        with patch.object(self.journal,"feature",return_value=aborted):
            with self.assertRaises(PermissionError):
                resolve_published_feature_origins(
                    self.index,self.journal,self.pid,"OriginalFeature")
        changed={**self.feature,"filmindex_sha256":"b"*64}
        with (patch.object(self.journal,"feature",
                          side_effect=[self.feature,changed]),
              self.with_mocked_native_evidence()):
            with self.assertRaises(PermissionError):
                resolve_published_feature_origins(
                    self.index,self.journal,self.pid,"OriginalFeature")

    def test_fake_reel_take_sha_is_denied_even_if_auditor_claims_valid(self):
        modified={**self.audit,
                  "source_reels_for_native_take_audition":[
                      {**item,"take_document_sha256":"f"*64}
                      for item in self.audit[
                          "source_reels_for_native_take_audition"]]}
        with (patch.object(self.journal,"feature",return_value=self.feature),
              patch("backend.nvp_wo6_feature_origins.inspect_original_feature_readiness",
                    return_value=modified)):
            with self.assertRaises(PermissionError):
                resolve_published_feature_origins(
                    self.index,self.journal,self.pid,"OriginalFeature")

if __name__=="__main__":
    unittest.main()
