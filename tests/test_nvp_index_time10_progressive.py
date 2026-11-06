"""INDEX-TIME-10: native progressive authorization, successor and cancellation.

These deterministic tests exercise the real native coordinator methods with
fenced mock ledger/worker boundaries. The separate INDEX-TIME-09 suite uses
real camera VFR+AAC FFmpeg and verifies media originals byte-for-byte.
No test here claims gapless WebView2 playback or an installed Windows app.
"""
from contextlib import nullcontext
from pathlib import Path
from threading import Event,RLock
from unittest import TestCase,mock

from backend.nvp_index_time09_native_host import NativeAVProxyHost
from backend.nvp_temporal_ledger import TICKS_PER_SECOND

SESSION="progressive_"+"s"*35
CURRENT="current_"+"c"*35
NEXT="next_"+"n"*35
PID="a"*32
SHA="b"*64


class ProgressiveHostTests(TestCase):
    def setUp(self):
        self.host=NativeAVProxyHost.__new__(NativeAVProxyHost)
        self.host._lock=RLock()
        self.host._closed=False
        self.host._current=CURRENT
        self.host._session={
            "id":SESSION,"project_id":PID,"edit_id":"approved_edit",
            "edit_revision":3,"edit_sha":SHA,
            "start_tick":0,"end_tick":MAX_SECONDS*TICKS_PER_SECOND,
            "expires":10**20,"stopped":False,
            "current_ticket":CURRENT,"next_ticket":None,
            "expected_next_tick":None,
        }
        self.host._tickets={
            CURRENT:{
                "task":"task_current","progressive_session":SESSION,
                "stopped":False,"cancel":Event(),
                "future":mock.Mock(done=mock.Mock(return_value=True)),
                "plan":{"actual_start_tick":0,
                        "review_duration_tick":TICKS_PER_SECOND},
            },
        }
        self.host.poll=mock.Mock(return_value={"status":"READY"})
        self.host.start=mock.Mock(return_value={
            "format":"nvp.index_time09.native_av_host.v1",
            "status":"QUEUED","ticket_id":NEXT,
            "progressive_session_id":SESSION,
            "original_modified":False,"master_approved":False,
        })
        self.host._discard=mock.Mock()
        db=mock.MagicMock()
        self.host.ledger=mock.Mock()
        self.host.ledger._db=mock.Mock(side_effect=lambda:nullcontext(db))
        self.host.ledger.get_task=mock.Mock(return_value={"state":"SUCCEEDED"})
        self.host.owner="example-test-owner"
        self.host.desktop=mock.Mock()
        self.host.desktop._window.return_value=None

    def _successor(self):
        self.host._tickets[NEXT]={
            "task":"task_next","progressive_session":SESSION,
            "stopped":False,"cancel":Event(),
            "future":mock.Mock(done=mock.Mock(return_value=True)),
            "plan":{
                "actual_start_tick":TICKS_PER_SECOND-TICKS_PER_SECOND//24,
                "review_duration_tick":2*TICKS_PER_SECOND,
            },
        }
        self.host._session["next_ticket"]=NEXT

    def test_successor_is_host_derived_from_sealed_current_film_time(self):
        result=self.host.prepare_next_progressive(SESSION,CURRENT)
        self.assertEqual(result["status"],"QUEUED")
        self.host.start.assert_called_once_with({
            "project_id":PID,"edit_id":"approved_edit",
            "edit_revision":3,"edit_document_sha256":SHA,
            "start_tick":str(TICKS_PER_SECOND),
        },progressive=True,continuation=True)
        self.assertEqual(self.host._session["expected_next_tick"],
                         TICKS_PER_SECOND)

    def test_foreign_session_and_foreign_anchor_cannot_prepare(self):
        for sid,ticket in (("foreign",CURRENT),(SESSION,"foreign"),
                           (None,CURRENT),(SESSION,None)):
            with self.subTest(sid=sid,ticket=ticket):
                with self.assertRaises(PermissionError):
                    self.host.prepare_next_progressive(sid,ticket)
        self.host.start.assert_not_called()

    def test_never_prepare_more_than_one_successor(self):
        self.host._session["next_ticket"]=NEXT
        result=self.host.prepare_next_progressive(SESSION,CURRENT)
        self.assertEqual(result["status"],"ALREADY_QUEUED")
        self.host.start.assert_not_called()

    def test_no_new_preview_after_creator_grant_end(self):
        self.host._session["end_tick"]=TICKS_PER_SECOND
        result=self.host.prepare_next_progressive(SESSION,CURRENT)
        self.assertEqual(result["status"],"AT_END")
        self.host.start.assert_not_called()

    def test_denied_or_unverified_current_cannot_authorize_next(self):
        self.host.poll.return_value={"status":"PREPARING"}
        result=self.host.prepare_next_progressive(SESSION,CURRENT)
        self.assertEqual(result["status"],"NOT_READY")
        self.host.start.assert_not_called()

    def test_verified_successor_switch_revokes_old_ticket(self):
        self._successor()
        result=self.host.advance_progressive(SESSION,CURRENT,NEXT)
        self.assertEqual(result["status"],"ADVANCED")
        self.assertEqual(result["transition_tick"],str(TICKS_PER_SECOND))
        self.assertEqual(self.host._session["current_ticket"],NEXT)
        self.assertIsNone(self.host._session["next_ticket"])
        self.assertEqual(self.host._current,NEXT)
        self.assertTrue(self.host._discard.called)
        self.assertNotIn(CURRENT,self.host._tickets)

    def test_missing_interval_or_unverified_successor_blocks_handoff(self):
        self._successor()
        self.host._tickets[NEXT]["plan"]["actual_start_tick"]=(
            TICKS_PER_SECOND+1)
        with self.assertRaises(RuntimeError):
            self.host.advance_progressive(SESSION,CURRENT,NEXT)
        self.assertIn(CURRENT,self.host._tickets)
        self.host._tickets[NEXT]["plan"]["actual_start_tick"]=TICKS_PER_SECOND
        self.host.poll.return_value={"status":"PREPARING"}
        with self.assertRaises(RuntimeError):
            self.host.advance_progressive(SESSION,CURRENT,NEXT)
        self.assertEqual(self.host._session["current_ticket"],CURRENT)

    def test_crash_loses_session_authority_not_recoverable_from_ticket(self):
        self.host._session=None
        with self.assertRaises(PermissionError):
            self.host.prepare_next_progressive(SESSION,CURRENT)
        self.host.start.assert_not_called()

    def test_restarted_host_revokes_old_grants_without_replaying_workers(self):
        db=mock.MagicMock()
        db.execute.return_value.fetchall.return_value=[
            ("old_queued",),("old_running",)]
        self.host.ledger._db=mock.Mock(side_effect=lambda:nullcontext(db))
        self.host.ledger.get_task.side_effect=[
            {"state":"QUEUED"},{"state":"ACTIVE"},
        ]
        self.host._reconcile_restarted_grants()
        self.host.ledger.cancel_queued.assert_called_once_with(
            "old_queued",owner_key=self.host.owner)
        self.assertEqual(self.host._session["current_ticket"],CURRENT)
        self.assertTrue(any(
            "SET revoked=1" in str(call)
            for call in db.execute.call_args_list))
        # An ACTIVE task's reservation remains held. A kill signal or a
        # new desktop host is not proof that its OS process tree exited.

    def test_cancel_revokes_both_disposable_sessions_and_queue(self):
        self._successor()
        self.host.ledger.get_task.return_value={"state":"QUEUED"}
        receipt=self.host.stop_progressive(SESSION)
        self.assertEqual(receipt["status"],"CANCELLATION_REQUESTED")
        self.assertIsNone(self.host._session)
        self.assertIsNone(self.host._current)
        self.assertEqual(len(self.host._tickets),0)
        self.assertEqual(self.host.ledger.cancel_queued.call_count,2)
        self.assertFalse(receipt["original_modified"])
        self.assertFalse(receipt["master_approved"])


class FilmTailGapTests(TestCase):
    def test_final_black_silent_gap_is_real_playable_film_time(self):
        from backend.nvp_index_time09_av_proxy import plan,_graph
        from backend.nvp_temporal_ledger import TICKS_PER_SECOND as T
        record={"revision":3,"document_sha256":SHA,
                "data":{"duration_tick":30*T,"clip_count":1}}
        reader=mock.Mock()
        reader.index.read_revision.return_value=record
        reader._publisher.verify_revision.return_value={
            "edit_document_sha256":SHA}
        reader._publisher.clips.return_value={
            "edit_document_sha256":SHA,
            "clips":[{"ordinal":0,"film_start_tick":"0",
                      "film_end_tick":str(5*T)}]}
        section=plan(mock.Mock(),reader,PID,"approved_edit",3,SHA,
                     6*T,ffprobe=Path("/not-needed/ffprobe"))
        self.assertEqual(section["actual_start_tick"],6*T)
        self.assertEqual(section["review_duration_tick"],24*T)
        self.assertEqual(section["sources"],{})
        self.assertEqual([p["kind"] for p in section["parts"]],["gap"])
        self.assertEqual(section["expected_review_frames"],24*24)
        paths,graph=_graph(section)
        self.assertEqual(paths,[])
        self.assertIn("color=c=black",graph)
        self.assertIn("anullsrc=r=48000",graph)


MAX_SECONDS=4*3600

if __name__=="__main__":
    import unittest
    unittest.main()
