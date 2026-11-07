"""DA-03D actual FilmIndex-measured original impulse DSP and seek parity.

Synthetic impulse arrays verify deterministic convolution, NOT certified
head-related measurement quality or physical cinema-room calibration.
"""
import base64
import struct
import unittest

import test_nvp_data_av_native as fixture
from backend.nvp_data_av_scene import FrozenSceneAV
from backend.nvp_native_hrir import NativeMeasuredBinauralIR


def responses():
    return [
        {"azimuth_deg":-90,"left":[0.8,0.0,0.2],
         "right":[0.2,0.0,0.0]},
        {"azimuth_deg":90,"left":[0.15,0.0,0.0],
         "right":[0.85,0.0,0.1]},
    ]


class NativeSourceBinauralIRTests(unittest.TestCase):
    def setUp(self):
        fixture.NativeDigitalTakeAudioTests.setUp(self)
        self.original_sha=self.index.read_revision(
            self.pid,"mic_signal",1)["document_sha256"]
        record=NativeMeasuredBinauralIR.publish(
            self.index,self.pid,"OriginalTestHRIR",
            measurement_kind="anechoic_hrir",
            measured_source_label="Native unit-test synthetic impulse fixture",
            license_notice="Synthetic original fixture; no redistribution restrictions",
            responses=responses(),native_creator_approval=lambda _:True)
        self.sha=record["document_sha256"]
        self.profile=NativeMeasuredBinauralIR(
            self.index,self.pid,"OriginalTestHRIR",self.sha)

    def test_measured_impulse_changes_two_ears_without_altering_original_take(self):
        original=FrozenSceneAV(
            self.index,self.pid,"frozen_audio_take",
            expected_take_sha256=self.sha_take(),
            listener_path="/World/ListenerLeft")
        measured=FrozenSceneAV(
            self.index,self.pid,"frozen_audio_take",
            expected_take_sha256=self.sha_take(),
            listener_path="/World/ListenerLeft",
            measured_binaural=self.profile)
        dry=original.audio_window(12000,512)
        a=measured.audio_window(12000,512)
        b=measured.audio_window(12000,512)
        self.assertEqual(a["pcm_base64"],b["pcm_base64"])
        self.assertNotEqual(a["pcm_base64"],dry["pcm_base64"])
        self.assertEqual(a["binaural_profile_sha256"],self.sha)
        self.assertEqual(a["binaural_profile_kind"],"anechoic_hrir")
        self.assertFalse(a["native_binaural_calibration_accepted"])
        vals=struct.unpack("<"+"h"*1024,
                           base64.b64decode(a["pcm_base64"]))
        self.assertNotEqual(vals[0::2],vals[1::2])
        self.assertEqual(self.index.read_revision(
            self.pid,"mic_signal",1)["document_sha256"],self.original_sha)
        self.assertFalse(a["source_modified"])

    def sha_take(self):
        return self.take["document_sha256"]

    def test_fir_continuous_history_equals_separate_seek_windows(self):
        # Sample-by-sample taps must match whether read as a 64-sample
        # window or as adjacent independent 32-sample Film Time windows.
        a=self.profile.response_for(90)
        signal=[100+i*10 for i in range(64)]
        h=[12,30]
        full=self.profile.convolve(signal,h,a)
        first=self.profile.convolve(signal[:32],h,a)
        last=self.profile.convolve(signal[32:],signal[30:32],a)
        self.assertEqual(full[0],first[0]+last[0])
        self.assertEqual(full[1],first[1]+last[1])

    def test_source_profile_deny_and_corrupted_profile_fail_closed(self):
        with self.assertRaises(PermissionError):
            NativeMeasuredBinauralIR.publish(
                self.index,self.pid,"UnapprovedIR",
                measurement_kind="room_brir",
                measured_source_label="Source room impulse evidence",
                license_notice="Fixture only",
                responses=responses(),native_creator_approval=lambda _:False)
        with self.assertRaises(RuntimeError):
            NativeMeasuredBinauralIR(
                self.index,self.pid,"OriginalTestHRIR","f"*64)
        with self.assertRaises(ValueError):
            NativeMeasuredBinauralIR.publish(
                self.index,self.pid,"UnboundedIR",
                measurement_kind="anechoic_hrir",
                measured_source_label="Overlong fixture impulse",
                license_notice="Fixture only",
                responses=[{**responses()[0],
                            "left":[1.0]*200,"right":[1.0]*200},
                           responses()[1]],native_creator_approval=lambda _:True)


if __name__=="__main__":
    unittest.main()
