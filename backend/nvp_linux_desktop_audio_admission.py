"""Managed desktop admission for a bounded, original project WAV preview.

The renderer selects an existing immutable project audio revision; neither
paths nor approval tokens are renderer inputs. The normal native audio host
owns admission, kernel work, verification and recovery. This is never a master.
"""
from __future__ import annotations

import secrets
import threading
from pathlib import Path

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_audio01e3_native_host import NativeAudioHost
from backend.nvp_audio01d_chunked_recovery import MAX_DURATION_SAMPLES, RATE
from backend.nvp_audio01_picture_follow import _wav
from backend.nvp_film_index import _require_pid, _id
from backend.nvp_imported_audio import OriginalAudioImport
from backend.nvp_linux_service_recovery import SystemdRecoveryAuthority
from backend.nvp_resource_supervisor import NativeCancelRequested


class ManagedAudioAdmission:
    def __init__(self, index, ledger, root, authority, native_window):
        if type(authority) is not SystemdRecoveryAuthority:
            raise PermissionError('Managed Linux authority required')
        self.index, self.ledger = index, ledger
        self.authority, self.window = authority, native_window
        self.root = Path(root).absolute()
        self.output_root = self.root.parent / 'audio-project-previews'
        self._lock = threading.Lock()
        self._active = None
        self._closed = False

    def _live(self):
        if self._closed:
            raise PermissionError('Sound window closed')
        window = self.window()
        self.authority.current()
        return window

    def _source(self, project_id, source_id, revision):
        _require_pid(project_id)
        _id(source_id, 'original sound')
        if type(revision) is not int or revision < 1:
            raise ValueError('Exact source revision required')
        head = self.index.read_revision(project_id, source_id)
        if head['revision'] != revision:
            raise PermissionError('Sound revision changed')
        record = OriginalAudioImport(self.index, trusted_native_picker=lambda: None).describe(project_id, source_id, revision)
        info = record['data']
        if (info['original_codec'] != 'wav' or info['source_media_type'] != 'audio/wav' or
                info['native_sample_rate'] != RATE or info['native_channels'] != 2):
            raise ValueError('Choose an original stereo 48 kHz PCM WAV')
        media = self.index.verify_media_file(project_id, info['source_media_sha256'], 'audio/wav')
        if media['size_bytes'] != info['source_bytes']:
            raise PermissionError('Original media size changed')
        n = _wav(media['path'])
        if n != info['native_frame_count'] or not 1 <= n <= MAX_DURATION_SAMPLES:
            raise ValueError('Original sound duration is outside this preview profile')
        # Retirement is checked on every fresh approval, not merely on the UI list.
        with self.index.studio._connection() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='nvp_film_source_retirements'").fetchone()
            if exists and db.execute("SELECT 1 FROM nvp_film_source_retirements WHERE project_id=? AND object_id=? AND state!='RESTORED'", (project_id, source_id)).fetchone():
                raise PermissionError('Original sound is retired')
        return {'project_id': project_id, 'source_id': source_id, 'revision': revision,
                'document_sha256': record['document_sha256'], 'media_sha256': media['sha256']}, media['path'], n

    def catalog(self, project_id, after=None):
        self._live()
        page = self.index.object_page(project_id, kind='audio', after=after, limit=32)
        items = []
        for x in page['items']:
            try:
                record = self.index.read_revision(project_id, x['object_id'], x['head_revision'])
                d = record['data']
                if (d.get('format') == 'nvp.imported_original_sound.v1' and
                        d.get('original_codec') == 'wav' and d.get('native_sample_rate') == RATE and
                        d.get('native_channels') == 2 and type(d.get('native_frame_count')) is int and
                        1 <= d['native_frame_count'] <= MAX_DURATION_SAMPLES):
                    items.append({'source_id': x['object_id'], 'revision': x['head_revision']})
            except (OSError, KeyError, ValueError, RuntimeError):
                continue
        return {'available': True, 'items': items, 'next_after': page['next_after']}

    def preview(self, project_id, source_id, revision):
        self._live()
        with self._lock:
            if self._active is not None or self._closed:
                raise PermissionError('Another sound task is being checked')
            cancel = threading.Event()
            self._active = (project_id, cancel)
        try:
            context, source, samples = self._source(project_id, source_id, revision)
            plan = {'stems': [{'stem_id': 'original', 'kind': 'dialogue', 'clips': [
                {'out_start': 0, 'out_end': samples, 'source_start': 0,
                 'fade_in': 0, 'fade_out': 0, 'gain_milli': 1000}]}]}
            target_parent = self.output_root / project_id
            for parent in (self.output_root, target_parent):
                if parent.is_symlink():
                    raise PermissionError('Unsafe preview directory')
                parent.mkdir(mode=0o700, exist_ok=True)
                if parent.resolve() != parent or not parent.is_dir():
                    raise PermissionError('Unsafe preview directory')
            target = target_parent / ('preview-' + secrets.token_hex(24))
            event = 'desktop-audio-preview-' + secrets.token_hex(24)
            accepted = None

            def approve(actual_event, scope):
                nonlocal accepted
                if actual_event != event:
                    return False
                if accepted is not None:
                    # Complete durable staging after consent, even if the
                    # window closes mid-transaction. Dispatch still requires
                    # a live window and the exact scheduler notice.
                    return canonical_bytes(scope) == accepted
                if cancel.is_set():
                    return False
                self._live()
                if (scope.get('project_source') != context or scope.get('plan') != plan or
                        scope.get('sources') != {'original': source} or scope.get('directory') != str(target) or
                        scope.get('source_sha256') != {'original': context['media_sha256']} or
                        scope.get('total_samples') != samples or scope.get('final_master') is not False or
                        scope.get('director_approved') is not False):
                    return False
                title = self.index.studio.get_project(project_id)['title']
                if self._live().create_confirmation_dialog('NVP — Prepare sound preview',
                    f'Prepare one sound preview for {title}?\nOriginal sound: {source_id}\n'
                    f'Duration: {samples / RATE:.1f} seconds.\nYour original remains unchanged. '
                    'This does not approve a final soundtrack.') is not True:
                    return False
                self._live()
                if cancel.is_set() or self._source(project_id, source_id, revision) != (context, source, samples):
                    return False
                accepted = canonical_bytes(scope)
                return True

            host = NativeAudioHost(self.ledger, self.root, verify_creator_action=approve,
                                   strict_linux_tree=True, systemd_recovery=self.authority)
            try:
                result = host.stage_and_approve(plan, {'original': source}, samples, target, event,
                                               project_source=context)
            except PermissionError:
                if accepted is None:
                    return {'status': 'CANCELLED'}
                raise
            # An approved job may only dispatch its exact scheduler notice.
            # If resources are unavailable, preserve the durable queue for review;
            # never run another job or report a completion.
            job = result['job_id']
            def stop_requested():
                try:
                    self._live()
                except (OSError, RuntimeError, ValueError):
                    return True
                return cancel.is_set()
            try:
                if stop_requested():
                    host.close_unclaimed_project_preview(job)
                    return {'status': 'CANCELLED'}
                result = host.run_next(expected_task_id=job, should_cancel=stop_requested)
            except NativeCancelRequested:
                task = self.ledger.get_task(job)
                return {'status': 'INTERRUPTED' if task['state'] == 'INTERRUPTED' and task['reserved'] == 0 else 'REVIEW_REQUIRED'}
            except PermissionError:
                task = self.ledger.get_task(job)
                if task and task['state'] == 'QUEUED':
                    host.close_unclaimed_project_preview(job)
                    return {'status': 'CANCELLED' if cancel.is_set() else 'REVIEW_REQUIRED'}
                raise
            if result and result.get('state') == 'SUCCEEDED' and result.get('job_id') == job:
                return {'status': 'PREVIEW_READY'}
            task = self.ledger.get_task(job)
            if task and task['state'] == 'QUEUED':
                host.close_unclaimed_project_preview(job)
            return {'status': 'REVIEW_REQUIRED'}
        finally:
            with self._lock:
                self._active = None

    def cancel(self, project_id):
        self._live()
        with self._lock:
            if self._active is None or self._active[0] != project_id:
                return {'status': 'NO_ACTIVE_TASK'}
            self._active[1].set()
            return {'status': 'CANCELLATION_REQUESTED'}

    def close(self):
        with self._lock:
            self._closed = True
            if self._active is not None:
                self._active[1].set()
