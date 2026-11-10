"""PLAN-02-B: immutable ADC clock evidence is not a permission or PCM rewrite."""
import hashlib
import unittest
import test_nvp_data_av_native as fixture
from backend.nvp_independent_device_sync import (
    FORMAT,SYNC_FORMAT,_digest)
from backend.nvp_original_clock_binding import verified_original_clock

DEN=1000000
COUNT=4000
TICK=147000*COUNT


class OriginalClockEvidenceTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        models=[{"device_id":10,"source_sample_count":COUNT},
                {"device_id":11,"source_sample_count":COUNT}]
        maps=[]
        for i,model in enumerate(models):
            start=i*147000
            maps.append({
                "format":SYNC_FORMAT,"device_id":model["device_id"],
                "first_tick":start,"last_tick_exclusive":start+TICK,
                "sample_period_tick_num":147000*DEN,
                "sample_period_tick_den":DEN,
                "source_sample_count":COUNT,
                "measured_drift_ppm":0,"adc_residual_ns":0,
                "source_clock_model_sha256":_digest(model),
                "original_pcm_unmodified":True,
                "synchronized_hardware_clock":False})
        self.hashes=[hashlib.sha256(bytes([i+1])*COUNT*2).hexdigest()
                     for i in range(2)]
        doc={"format":FORMAT,"original_pcm_unmodified":True,
             "hardware_genlocked":False,
             "timing_physically_certified":False,
             "creator_approved_recording":False,
             "source_ids":["MicClockA","MicClockB"],
             "sample_maps":maps,"clock_models":models,
             "original_mono_pcm_sha256":self.hashes}
        receipt=self.index.register_revision(
            self.pid,"OriginalDeviceClocks","audio",doc,expected_revision=0)
        self.evidence={"object_id":"OriginalDeviceClocks",
                       "document_sha256":receipt["document_sha256"]}
        self.maps=maps

    def bound(self,source="MicClockA",mapping=None,evidence=None,pcm=None,count=COUNT):
        idx=0 if source=="MicClockA" else 1
        chosen=mapping if mapping is not None else self.maps[idx]
        return verified_original_clock(
            self.index,self.pid,source,chosen["first_tick"],
            chosen["last_tick_exclusive"],chosen,
            evidence if evidence is not None else self.evidence,
            source_sample_count=count,
            original_pcm_sha256=pcm if pcm is not None else self.hashes[idx])

    def test_exact_source_clock_and_pcm_hash_accepted_as_derived_only(self):
        result=self.bound()
        self.assertTrue(result["original_pcm_unmodified"])
        self.assertFalse(result["synchronized_hardware_clock"])

    def test_tampered_pcm_or_unapproved_evidence_never_qualifies(self):
        with self.assertRaises(RuntimeError):
            self.bound(pcm="0"*64)
        with self.assertRaises(RuntimeError):
            self.bound(evidence={**self.evidence,"document_sha256":"f"*64})
        with self.assertRaises(RuntimeError):
            self.bound(count=COUNT-1)

    def test_cross_source_replay_and_unscoped_optional_fields_fail_closed(self):
        with self.assertRaises(RuntimeError):
            self.bound(source="MicClockB",mapping=self.maps[0])
        with self.assertRaises(RuntimeError):
            verified_original_clock(
                self.index,self.pid,"MicClockA",0,TICK,
                self.maps[0],None)


if __name__=="__main__":
    unittest.main()
