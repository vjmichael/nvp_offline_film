"""PLAN-02: verify the repo records one data-first integration path.

This is a static contract/evidence integrity test, NOT a native integration
acceptance or a replacement for DA-00 and actual CI.
"""
import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"docs"/"NVP_PLAN02_INTEGRATION_MANIFEST.json"
SHA=re.compile(r"^[a-f0-9]{40}$")

class PLAN02IntegrationRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads(MANIFEST.read_text("utf8"))

    def test_one_authoritative_source_and_exact_baseline(self):
        d=self.report
        self.assertEqual(d["format"],"nvp.plan02.canonical_data_first_integration.v1")
        self.assertEqual(d["canonical"]["pr"],74)
        self.assertEqual(d["canonical"]["branch"],
                         "nvp/data-av01-native-scene-playback-20261106")
        self.assertTrue(SHA.fullmatch(d["canonical"]["inspected_source_sha256"]))
        self.assertEqual(d["status"],"PLAN02_EVIDENCE_ROUTE_RECORDED_PORTS_UNEXECUTED")
        self.assertTrue(d["canonical"]["draft"])

    def test_source_authority_never_moves_to_frames_or_ffmpeg(self):
        c=self.report["contract"]
        self.assertEqual(c["film_time_ticks_per_second"],7056000000)
        self.assertFalse(c["ffmpeg_in_any_active_path"])
        self.assertFalse(c["model_grants_native_authority"])
        self.assertTrue(c["creator_approval_required_for_mutations"])
        self.assertTrue(c["worker_custody_required_for_retry"])
        self.assertIn("sampled picture frames",c["derivative_only"])
        self.assertIn("integer Film Time events",c["authoritative_objects"])
        rejected=set(self.report["forbidden_actions"])
        self.assertIn("FFMPEG_ACTIVE_DELIVERY",rejected)
        self.assertIn("FRAME_INDEX_AS_TAKE_AUTHORITY",rejected)
        self.assertIn("WHOLE_STACK_MERGE",rejected)

    def test_no_donor_becomes_an_accepted_product_by_appearance(self):
        d=self.report
        ids=[x["id"] for x in d["sources"]]
        self.assertEqual(len(ids),len(set(ids)))
        allowed={"KEEP_CANONICAL","SELECTIVE_PORT","ADAPT_EXACT_TIME",
                 "ADAPT_UNTRUSTED_MODEL","EXTRACT_MECHANISMS_REWRITE_LEGACY",
                 "REPAIR_PRESENT_CANONICAL_PATH"}
        for source in d["sources"]:
            self.assertIn(source["decision"],allowed)
            self.assertRegex(source["head"],SHA)
        self.assertEqual(sum(x["decision"]=="KEEP_CANONICAL"
                             for x in d["sources"]),1)
        self.assertEqual(d["observed"]["data_av01"]["jobs_passed"],7)
        self.assertFalse(d["observed"]["data_av01"][
            "physical_creator_hardware_acceptance"])
        self.assertEqual(d["observed"]["legacy_01t"]["status"],
                         "FAILED_DIFFERENT_SOURCE")

    def test_groups_are_acyclic_and_next_is_canonical_repair(self):
        groups=self.report["groups"]
        ids={x["id"] for x in groups}
        self.assertEqual(ids,set("ABCDEF"))
        visited=set()
        for group in groups:
            self.assertTrue(set(group["requires"])<=visited)
            visited.add(group["id"])
        self.assertEqual(groups[0]["id"],"A")
        for source in self.report["sources"]:
            self.assertIn(source["group"],ids)

    def test_canonical_source_files_exist_not_donor_legacy(self):
        original=next(x for x in self.report["sources"]
                      if x["decision"]=="KEEP_CANONICAL")
        for name in original["modules"]:
            with self.subTest(module=name):
                self.assertTrue((ROOT/name).is_file(),name)

if __name__=="__main__":
    unittest.main()
