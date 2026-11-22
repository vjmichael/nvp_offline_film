"""Read-only ADC preflight cannot be used as physical recording acceptance."""
import unittest

from tools.nvp_p1a_physical_device_preflight import classify_native_adc_catalog
from backend.nvp_device_producer_custody import scope_sha256


class PhysicalADCPrefightContracts(unittest.TestCase):
    def setUp(self):
        self.catalog = [
            {"device_id": 2, "name": "USB ADC A", "host_api": "WASAPI", "max_input_channels": 2},
            {"device_id": 4, "name": "USB ADC B", "host_api": "WASAPI", "max_input_channels": 2},
        ]

    def test_exact_two_distinct_sealed_portaudio_descriptors_cannot_promote_hardware(self):
        proof = classify_native_adc_catalog(self.catalog, selected_ids=(2,4))
        self.assertEqual(proof["status"], "TWO_PORTAUDIO_ENDPOINTS_ENUMERATED_ONLY")
        self.assertEqual(proof["selected_input_descriptor_sha256"],
                         [scope_sha256(self.catalog[0]),scope_sha256(self.catalog[1])])
        self.assertFalse(proof["possible_same_physical_adc_alias"])
        for key in ("stream_opened","physical_sound_samples_recorded",
                    "independent_hardware_adcs_verified",
                    "per_buffer_adc_clock_and_drift_verified",
                    "creator_one_use_approval_obtained",
                    "native_os_custody_verified_by_this_probe",
                    "efs_protected_original_take_verified",
                    "production_microphone_gate_accepted"):
            self.assertFalse(proof[key],key)

    def test_duplicate_or_disconnected_selection_and_forged_catalog_denied(self):
        for selected in ((2,2),(2,999),(4,3),(2,),("2",4)):
            with self.subTest(selected=selected),self.assertRaises(ValueError):
                classify_native_adc_catalog(self.catalog,selected_ids=selected)
        with self.assertRaises(ValueError):
            classify_native_adc_catalog([self.catalog[0],self.catalog[0]])
        with self.assertRaises(ValueError):
            classify_native_adc_catalog([{**self.catalog[0],"max_input_channels":0}])

    def test_repeated_name_host_api_flags_possible_virtual_alias(self):
        duplicate = {**self.catalog[1],"name":self.catalog[0]["name"]}
        proof = classify_native_adc_catalog(
            [self.catalog[0],duplicate],selected_ids=[2,4])
        self.assertTrue(proof["possible_same_physical_adc_alias"])
        self.assertFalse(proof["independent_hardware_adcs_verified"])

    def test_no_selection_is_only_a_portaudio_catalog(self):
        proof=classify_native_adc_catalog(self.catalog)
        self.assertEqual(proof["status"],"PORTAUDIO_CATALOG_ONLY_NO_DEVICE_SELECTED")
        self.assertEqual(proof["selected_input_descriptor_sha256"],[])
        self.assertFalse(proof["production_microphone_gate_accepted"])


if __name__=="__main__":
    unittest.main()
