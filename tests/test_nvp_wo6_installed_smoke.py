"""WO6-07 real source tree, separate contained worker and durable receipt E2E.

This exercises the same smoke used by an NSIS-installed NVP.exe, but in
source test mode the workers run through python.exe and their .py scripts.
The report explicitly distinguishes these environments.
"""
from __future__ import annotations

import unittest
from tools.nvp_wo6_installed_action_smoke import run_wo6_installed_native_smoke


class WO6PackagedNativeSourceWorkerAcceptance(unittest.TestCase):
    def test_sequential_native_take_three_shots_color_and_film_time(self):
        evidence=run_wo6_installed_native_smoke()
        self.assertEqual(evidence["status"],
                         "INSTALLED_NATIVE_WORKER_SOURCES_VERIFIED_NO_FILM")
        self.assertEqual(evidence["worker_operation_count"],6)
        self.assertEqual(evidence["completed_operations"],[
            "new_frozen_take","camera_shot","blocking_shot",
            "lighting_shot","derived_color","exact_film_time_edit"])
        self.assertTrue(evidence["native_os_contained_actual_child_processes"])
        self.assertTrue(evidence["durable_task_status_reopened"])
        self.assertTrue(evidence["all_original_filminindex_revisions_preserved"])
        self.assertFalse(evidence["native_model_self_approval"])
        self.assertFalse(evidence["director_human_consent_verified"])
        self.assertFalse(evidence["cinema_picture_rendered"])
        self.assertFalse(evidence["DCP_released"])
        self.assertFalse(evidence["film_delivered"])


if __name__=="__main__":
    unittest.main()
