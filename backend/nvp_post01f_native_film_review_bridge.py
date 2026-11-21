"""Trusted desktop-only picture review bridge for POST-01F derived LTX media.

The native installed application owns the unlocked G03 session, OS-authenticated
creator event source and in-memory video renderer. An untrusted UI/worker does
not supply session tokens, credential material, media paths or plaintext URLs.
This bridge is NOT itself the installed native event source or movie decoder.
"""
from __future__ import annotations

import re

from backend.nvp_post01f_encrypted_review import EncryptedLtxReview

_PROJECT = re.compile(r'[0-9a-f]{32}\Z')
_JOB = re.compile(r'ltx_[0-9a-f]{24}\Z')


class NativeFilmReviewBridge:
    def __init__(self, review: EncryptedLtxReview, *, live_session,
                 native_creator_event, render_in_memory):
        if (not isinstance(review, EncryptedLtxReview) or
                not callable(live_session) or
                not callable(native_creator_event) or
                not callable(render_in_memory)):
            raise TypeError('Trusted Windows filmmaker review services are required')
        self._review = review
        self._session = live_session
        self._event = native_creator_event
        self._render = render_in_memory

    def _identity(self, job_id):
        if type(job_id) is not str or not _JOB.fullmatch(job_id):
            raise PermissionError('Only one exact LTX derived picture may be reviewed')
        identity = self._session()  # Not an argument supplied by the UI or model.
        if (type(identity) is not tuple or len(identity) != 2 or
                type(identity[0]) is not str or not _PROJECT.fullmatch(identity[0]) or
                type(identity[1]) is not str or not identity[1]):
            raise PermissionError('No authenticated, unlocked native project session')
        return identity

    def _native_event(self, verb, pid, job, action=None):
        # This must be backed by the installed OS/UI authenticated event broker.
        # A model-selected "click" or arbitrary network request is not authority.
        event = self._event(verb, pid, job, action)
        if type(event) is not bytes or not 1 <= len(event) <= 8192:
            raise PermissionError('Native creator interaction authority missing')
        return event

    def reopen(self, job_id: str) -> dict:
        pid, token = self._identity(job_id)
        return self._review.review(pid, token, job_id)

    def preview(self, job_id: str) -> dict:
        """Render authenticated picture only; never return plaintext to a UI request.

        The trusted installed renderer must not persist or remotely serve the
        transient bytes. Decode and actual playback require physical acceptance.
        """
        pid, token = self._identity(job_id)
        event = self._native_event('preview', pid, job_id)
        media = self._review.director_preview_bytes(pid, token, job_id,
                                                    creator_event=event)
        if (type(media) is not dict or media.get('media_type') != 'video/mp4' or
                media.get('video_only') is not True or media.get('job_id') != job_id or
                type(media.get('picture_bytes')) is not bytes):
            raise PermissionError('Authenticated encrypted picture decoder contract changed')
        # A revoked/unlocked-project swap after decrypt but before display must
        # not reach the renderer. Identity is checked again after rendering, too;
        # the installed renderer is separately responsible for immediate stop on
        # native session revocation during active playback.
        if self._identity(job_id) != (pid, token):
            raise PermissionError('Director session changed before native playback')
        # No preview path, base64 media, raw bytes, URL, or original audio in return.
        # Renderer must consume the view synchronously; no caching is authorized.
        if self._render(memoryview(media['picture_bytes']), 'video/mp4') is not True:
            raise PermissionError('Trusted native in-memory director playback refused')
        if self._identity(job_id) != (pid, token):
            raise PermissionError('Director session changed during native playback')
        return {'job_id': job_id, 'preview_displayed': True,
                'decision_unchanged': True, 'original_audio_modified': False}

    def decide(self, job_id: str, *, action: str) -> dict:
        if type(action) is not str or action not in ('approve', 'reject'):
            raise PermissionError('Filmmaker must explicitly approve or reject')
        pid, token = self._identity(job_id)
        event = self._native_event('decision', pid, job_id, action)
        return self._review.decide(pid, token, job_id, action=action,
                                   creator_event=event)
