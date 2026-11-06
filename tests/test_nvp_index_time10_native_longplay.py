"""INDEX-TIME-10 native 20-minute boundary acceptance, no media mocks.

Construct an original indexed assembly whose first 20 minutes are an authored
black/silent gap and whose following seconds contain a REAL camera recording
with embedded sound. The two genuinely encoded preview sections must be
independently verified by the native host, joined at the exact Film Time
boundary, and preserve all source recording bytes.

This is NOT installed WebView2 gapless/picture presentation acceptance.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import time
import unittest

from test_nvp_index_time09_av_proxy import SourceAudioVideoTests,T


class RealNativeTwentyMinuteBoundary(unittest.TestCase):
    def setUp(self):
        # Existing real FFmpeg long-GOP/VFR camera+tone fixture and the real
        # source provenance index, native source worker and containment.
        SourceAudioVideoTests.setUp(self)

    def ready(self,ticket):
        return SourceAudioVideoTests.ready(self,ticket)

    def test_host_approves_and_plays_two_real_sections_across_twenty_minutes(self):
        start_of_camera=(20*60+1)*T
        saved=self.publisher.publish(self.pid,"longfilm",[
            {"source_id":"sound","source_revision":1,
             "source_in_frame_zero":4,"source_out_frame_zero":28,
             "film_in_tick":start_of_camera,"rounding":"nearest"},
        ])
        request={
            "project_id":self.pid,"edit_id":"longfilm",
            "edit_revision":1,"edit_document_sha256":saved["document_sha256"],
            "start_tick":"0",
        }
        begun=self.desktop.start_progressive_av_review(request)
        self.assertEqual(begun["status"],"QUEUED",begun)
        self.assertEqual(self.window.prompts,1)
        self.assertFalse(begun["original_modified"])
        session=begun["progressive_session_id"]
        first=begun["ticket_id"]
        first_receipt=self.ready(first)
        self.assertEqual(first_receipt["status"],"READY",first_receipt)
        self.assertEqual(first_receipt["actual_start_tick"],"0")
        self.assertEqual(first_receipt["review_duration_tick"],str(1200*T))
        first_stream=self.desktop.get_synchronized_av_stream(first)
        self.assertEqual(first_stream["status"],"VERIFIED_STREAM",first_stream)
        self.assertLess(first_stream["total_size"],160*1024*1024)

        prepared=self.desktop.prepare_next_progressive_av_review(session,first)
        self.assertEqual(prepared["status"],"QUEUED",prepared)
        second=prepared["ticket_id"]
        self.assertNotEqual(first,second)
        self.assertEqual(self.window.prompts,1,
                         "A second section cannot request broader consent")
        next_receipt=self.ready(second)
        self.assertEqual(next_receipt["status"],"READY",next_receipt)
        self.assertEqual(next_receipt["actual_start_tick"],str(1200*T))
        second_stream=self.desktop.get_synchronized_av_stream(second)
        self.assertEqual(second_stream["status"],"VERIFIED_STREAM",second_stream)
        self.assertNotEqual(first_stream["url"],second_stream["url"])
        # Current + prepared are exactly two, and no third section is queued.
        host=self.desktop._get_av_host()
        self.assertEqual(len(host._tickets),2)
        again=self.desktop.prepare_next_progressive_av_review(session,first)
        self.assertEqual(again["status"],"ALREADY_QUEUED")

        advanced=self.desktop.advance_progressive_av_review(
            session,first,second)
        self.assertEqual(advanced["status"],"ADVANCED",advanced)
        self.assertEqual(advanced["transition_tick"],str(1200*T))
        self.assertEqual(advanced["ticket_id"],second)
        self.assertEqual(len(host._tickets),1)
        # Old output is physically removed, old opaque authority gone.
        self.assertEqual(self.desktop.get_synchronized_av_stream(first)[
            "status"],"RECOVERY_REQUIRED")
        self.assertEqual(self.desktop.get_synchronized_av_stream(second)[
            "status"],"VERIFIED_STREAM")
        self.assertEqual(sha256(self.audible.read_bytes()).hexdigest(),
                         self.source_hashes["sound"])
        self.assertEqual(sha256(self.silent.read_bytes()).hexdigest(),
                         self.source_hashes["silent"])
        closed=self.desktop.stop_progressive_av_review(session)
        self.assertEqual(closed["status"],"CANCELLATION_REQUESTED")
        self.assertFalse(closed["original_modified"])
        self.assertFalse(closed["master_approved"])


if __name__=="__main__":
    unittest.main()
