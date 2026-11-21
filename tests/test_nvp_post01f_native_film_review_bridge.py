"""Native review wiring source tests; synthetic services are not installed evidence."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'backend/nvp_post01f_native_film_review_bridge.py'
PID='a'*32
JOB='ltx_'+'b'*24

class BridgeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Review:
            def __init__(self): self.events=[]
            def review(self,pid,token,job):
                self.events.append(('reopen',pid,token,job))
                return {'status':'PICTURE_VERIFIED_UNAPPROVED'}
            def director_preview_bytes(self,pid,token,job,*,creator_event):
                self.events.append(('preview',pid,token,job,creator_event))
                return {'job_id':job,'media_type':'video/mp4', 'video_only':True,
                        'picture_bytes':b'source-test-media-not-LTX'}
            def decide(self,pid,token,job,*,action,creator_event):
                self.events.append(('decide',pid,token,job,action,creator_event))
                return {'status':'CREATOR_APPROVED' if action=='approve' else 'CREATOR_REJECTED'}
        cls.Review=Review
        backend=types.ModuleType('backend');backend.__path__=[]
        reviewmod=types.ModuleType('backend.nvp_post01f_encrypted_review')
        reviewmod.EncryptedLtxReview=Review
        with mock.patch.dict(sys.modules,{'backend':backend,
                                          'backend.nvp_post01f_encrypted_review':reviewmod}):
            spec=importlib.util.spec_from_file_location('native_review_bridge_test',SOURCE)
            cls.m=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.m)

    def setUp(self):
        self.review=self.Review()
        self.identity=lambda:(PID,'protected-session')
        self.clicks=[]
        self.events=lambda v,p,j,a:(self.clicks.append((v,p,j,a)) or b'installed-event-required')
        self.images=[]
        self.renderer=lambda raw,typ:(self.images.append((bytes(raw),typ)) or True)
        self.bridge=self.m.NativeFilmReviewBridge(self.review,live_session=self.identity,
                   native_creator_event=self.events,render_in_memory=self.renderer)

    def test_reopen_uses_internal_protected_session(self):
        self.assertEqual(self.bridge.reopen(JOB)['status'],'PICTURE_VERIFIED_UNAPPROVED')
        self.assertEqual(self.review.events,[('reopen',PID,'protected-session',JOB)])
        with self.assertRaises(TypeError):self.bridge.reopen(JOB, token='injected')

    def test_preview_returns_no_raw_media_and_does_not_approve(self):
        result=self.bridge.preview(JOB)
        self.assertTrue(result['preview_displayed'])
        self.assertTrue(result['decision_unchanged'])
        self.assertNotIn('picture_bytes',result)
        self.assertNotIn('url',result)
        self.assertEqual(self.images[0][1],'video/mp4')
        self.assertEqual(self.clicks,[('preview',PID,JOB,None)])
        self.assertEqual(len(self.review.events),1)

    def test_decision_separates_authenticated_action_from_preview(self):
        result=self.bridge.decide(JOB,action='reject')
        self.assertEqual(result['status'],'CREATOR_REJECTED')
        self.assertEqual(self.clicks,[('decision',PID,JOB,'reject')])
        with self.assertRaises(PermissionError):self.bridge.decide(JOB,action='retry')

    def test_invalid_session_or_event_refuses_before_unseal(self):
        cases=[(lambda:('invalid','token'),self.events),
               (lambda:(PID,''),self.events),
               (self.identity,lambda *a:b''),
               (self.identity,lambda *a:'unauthenticated')]
        for session,event in cases:
            with self.subTest(session=session,event=event):
                bridge=self.m.NativeFilmReviewBridge(self.review,live_session=session,
                         native_creator_event=event,render_in_memory=self.renderer)
                with self.assertRaises(PermissionError):bridge.preview(JOB)
        self.assertFalse(self.review.events)

    def test_session_revocation_before_display_refuses_without_media_release(self):
        identity=[(PID,'protected-session'),(PID,'revoked')]
        renderer=[]
        bridge=self.m.NativeFilmReviewBridge(self.review,
            live_session=lambda: identity.pop(0), native_creator_event=self.events,
            render_in_memory=lambda *_: (renderer.append(True) or True))
        with self.assertRaisesRegex(PermissionError,'before native playback'):
            bridge.preview(JOB)
        self.assertEqual(renderer,[])

    def test_session_revocation_during_display_refuses_success(self):
        identity=[(PID,'protected-session'),(PID,'protected-session'),(PID,'revoked')]
        bridge=self.m.NativeFilmReviewBridge(self.review,
            live_session=lambda: identity.pop(0), native_creator_event=self.events,
            render_in_memory=self.renderer)
        with self.assertRaisesRegex(PermissionError,'during native playback'):
            bridge.preview(JOB)
        self.assertEqual(len(self.images),1)

    def test_renderer_refusal_does_not_create_review_decision(self):
        bridge=self.m.NativeFilmReviewBridge(self.review,live_session=self.identity,
                 native_creator_event=self.events,render_in_memory=lambda *_:False)
        with self.assertRaises(PermissionError):bridge.preview(JOB)
        self.assertFalse(any(e[0]=='decide' for e in self.review.events))

    def test_no_foreign_job_or_caller_supplied_authorization(self):
        with self.assertRaises(PermissionError):self.bridge.preview('ltx_../foreign')
        with self.assertRaises(TypeError):self.bridge.preview(JOB,creator_event=b'fake')
        with self.assertRaises(TypeError):self.bridge.decide(JOB,action='approve',
                                                            token='foreign')

if __name__=='__main__':unittest.main()
