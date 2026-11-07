"""DA-02C/D native dual source and durable interruption acceptance.

A fake two-channel shared-clock OS device exercises actual frozen FilmIndex,
separate PCM source identities and the same recovery journal used in NVP.
It is not physical sound-card or drift-calibration acceptance.
"""
import array
import unittest

import test_nvp_native_live_take as fixture
from backend.nvp_capture_recovery import OriginalCaptureJournal
from backend.nvp_native_stereo_take import NativeStereoOriginalSession


class SharedClockDevice:
    def __init__(self,corrupt=False):
        self.generator=None;self.closed=False;self.stopped=False
        self.corrupt=corrupt
    def start(self,generator):
        self.generator=generator
        samples=array.array("h",[300,-600]*4000)
        if self.corrupt:samples.append(42)
        generator.send(samples)
    def stop(self):
        self.stopped=True
    def close(self):
        self.closed=True


class NativeSynchronizedSourceTests(unittest.TestCase):
    def setUp(self):
        fixture.LiveTakeMicTests.setUp(self)
        self.device=SharedClockDevice()
        self.journal=OriginalCaptureJournal(
            self.studio.db_path.parent/"native-original-capture-recovery")

    def _session(self,**options):
        arguments=dict(
            project_id=self.pid,take_id="DualSoundTake",
            scene_id="spatial_world",scene_revision=1,
            camera_timeline_id="LiveCamera",camera_timeline_revision=1,
            sound_timeline_id="DualEvents",
            source_id="DualMicrophoneA",
            emitter_path="/World/Actor",
            event_id="SpeechA",subject_id="Actor",
            second_source_id="DualMicrophoneB",
            second_emitter_path="/World/ListenerRight",
            second_event_id="SpeechB",second_subject_id="Anchor",
            native_approve_start=lambda scope:True,
            native_approve_freeze=lambda event,scope:True,
            device_factory=lambda:self.device)
        arguments.update(options)
        return NativeStereoOriginalSession(self.index,**arguments)

    def test_two_mono_sources_freeze_with_same_actual_sample_clock(self):
        mic=self._session()
        started=mic.begin()
        self.assertEqual(started["native_input_channels"],2)
        self.assertTrue(started["shared_capture_clock"])
        freeze=mic.finish()
        self.assertEqual(freeze["status"],"FROZEN_ORIGINAL_LIVE_TAKE")
        self.assertEqual(freeze["original_mono_source_count"],2)
        self.assertEqual(freeze["actual_recorded_samples"],4000)
        self.assertEqual(freeze["original_sound_count"],2)
        self.assertTrue(self.device.closed)
        a=self.index.read_revision(self.pid,"DualMicrophoneA",1)
        b=self.index.read_revision(self.pid,"DualMicrophoneB",1)
        self.assertEqual(a["data"]["sample_count"],4000)
        self.assertEqual(b["data"]["sample_count"],4000)
        self.assertNotEqual(a["document_sha256"],b["document_sha256"])
        self.assertNotEqual(self.sound.read(
            self.pid,"DualMicrophoneA",1,0,24),
            self.sound.read(self.pid,"DualMicrophoneB",1,0,24))
        events=self.index.read_revision(self.pid,"DualEvents",1)
        self.assertEqual(len([ev for ev in events["data"]["events"]
                              if ev["event_kind"]=="dialogue"]),2)
        self.assertEqual(self.journal.catalog(self.pid)["items"],[])
        self.assertEqual(self.index.read_revision(
            self.pid,"DualSoundTake",1)["document_sha256"],
            freeze["take_document_sha256"])

    def test_corrupt_interleave_never_claims_a_synced_take(self):
        self.device=SharedClockDevice(corrupt=True)
        mic=self._session()
        mic.begin()
        with self.assertRaises(RuntimeError):
            mic.finish()
        self.assertEqual(mic.status["state"],"FAILED")
        self.assertTrue(self.device.closed)
        with self.assertRaises(KeyError):
            self.index.read_revision(self.pid,"DualSoundTake",1)
        catalog=self.journal.catalog(self.pid)
        self.assertEqual(len(catalog["items"]),1)
        self.assertEqual(catalog["items"][0]["phase"],"FAILED_UNAPPROVED")
        self.assertFalse(catalog["items"][0]["take_approved"])

    def test_stereo_refuses_colliding_emitters(self):
        with self.assertRaises(ValueError):
            self._session(second_emitter_path="/World/Actor")
        with self.assertRaises(ValueError):
            self._session(second_source_id="DualMicrophoneA")


if __name__=="__main__":
    unittest.main()
