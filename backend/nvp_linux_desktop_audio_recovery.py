"""Per-window recovery controls for the installed managed Linux desktop.

This is a trusted-host projection, not a new recovery authority.  Browser
requests contain only expiring opaque selections, never paths, task seals,
stop records or creator events.  The original NativeAudioHost does the actual
reconciliation and enforces its existing lease, input and generation gates.
No new audio job is admitted or restarted by this recovery surface.
"""
from __future__ import annotations
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from backend.nvp_approved_tasks import canonical_bytes
from backend.nvp_audio01e3_native_host import NativeAudioHost
from backend.nvp_linux_service_recovery import SystemdRecoveryAuthority, digest
from backend.nvp_resource_ledger import TaskLedger

_SELECTION = re.compile(r"[0-9a-f]{48}\Z")
_JOB = re.compile(r"audiojob[0-9a-f]{24}\Z")
_PAGE = 24
_TTL = 300


class ManagedAudioRecoveryControls:
    """Native-only adapter for this desktop's audio host and task ledger."""

    def __init__(self, ledger, root, authority, native_window):
        if (type(authority) is not SystemdRecoveryAuthority or
                not isinstance(ledger, TaskLedger) or not callable(native_window)):
            raise PermissionError("Managed audio recovery requires installed host authority")
        authority.current()
        self._authority = authority
        self._window = native_window
        self._lock = threading.RLock()
        self._choices = {}
        self._pages = {}
        self._consent = None
        self._closed = False
        self._host = NativeAudioHost(ledger, root, verify_creator_action=self._approve,
                                     strict_linux_tree=True, systemd_recovery=authority)

    def _live(self):
        if self._closed:
            raise PermissionError("Recovery window closed")
        window = self._window()  # original native origin and protected-film gate
        self._authority.current()
        return window

    def _approve(self, event, scope):
        # Only a fresh native dialog can install this one-use exact grant.
        # A browser supplied event can never reach this callback.
        with self._lock:
            grant = self._consent
            self._consent = None
            if grant is None:
                return False
            try:
                self._live()
                return (event == grant[0] and time.monotonic() <= grant[2] and
                        canonical_bytes(scope) == grant[1])
            except (OSError, RuntimeError, TypeError, ValueError):
                return False

    def _snapshot(self, job):
        if type(job) is not str or not _JOB.fullmatch(job):
            raise PermissionError("Unknown recovery selection")
        host = self._host
        row = host.journal.read(job)
        grant = host._grant(job)
        with host.ledger._db() as db:
            binding = db.execute("""SELECT unit,invocation,start_sha,grant_sha,journal_sha,
                owner_key,approval_id,stop_sha FROM audio_native_service_bindings
                WHERE job_id=?""", (job,)).fetchone()
            if (not binding or binding[0] != self._authority.unit or
                    binding[3:7] != (grant['spec_sha'], row['spec_sha'], host.owner, grant['approval_id'])):
                raise PermissionError("No exact desktop recovery binding")
            original = host._verify_service_approved_document(db, job, row, grant)
            task = db.execute("SELECT state,reserved FROM tasks WHERE id=?", (job,)).fetchone()
            phase = db.execute("SELECT phase FROM audio_native_launch_boundaries WHERE job_id=?", (job,)).fetchone()
            lease = db.execute("SELECT job_id FROM audio_native_staging_leases WHERE directory=?", (row['spec']['directory'],)).fetchone()
            abandoned = db.execute("SELECT creator_event FROM audio_native_abandonments WHERE job_id=?", (job,)).fetchone()
            # Only active/interrupted state and the predecessor's own lease.
            # Journal failure with a remaining lease is a split-commit replay.
            if (task not in (('ACTIVE', 1), ('INTERRUPTED', 0)) or lease != (job,) or
                    row['state'] not in ('approved', 'running', 'recovery_required', 'failed')):
                raise PermissionError("Job not pending recovery")
            # Current generation and unauthenticated stop records are rejected
            # by the real systemd authority even on this read-only projection.
            stop = self._authority.stopped(binding[1], binding[2])
            stop_sha = digest(stop)
            if binding[7] not in (None, stop_sha):
                raise PermissionError("Recovery stop has changed")
            target = Path(row['spec']['directory'])
            missing = not target.exists() and not target.is_symlink()
            # The underlying host remains the final decision maker. This only
            # controls presentation of a potentially eligible review action.
            before_launch = (row['state'] == 'approved' and row['generation'] == 0 or
                             phase == ('reserved',) and row['state'] == 'running' and row['generation'] == 1)
            can_recover = (not missing or bool(abandoned) or
                           original.get('resume_from') is None and phase != ('launch-intent',) and
                           row['last_next_sample'] == 0 and (before_launch or row['state'] == 'failed'))
            can_abandon = (task == ('ACTIVE', 1) and row['state'] == 'running' and
                           phase == ('launch-intent',) and missing and
                           row['generation'] == 1 and row['last_next_sample'] == 0 and
                           not grant['revoked'] and abandoned is None and
                           original.get('resume_from') is None)
        snapshot = {
            'job': job, 'spec_sha': row['spec_sha'], 'generation': row['generation'],
            'state': row['state'], 'task': list(task), 'phase': list(phase or ()),
            'stop_sha': stop_sha, 'missing': missing, 'abandon': can_abandon, 'recover': can_recover,
            'approval_id': grant['approval_id'], 'stop_committed': binding[7],
            'abandon_committed': bool(abandoned),
        }
        scope = {'action': 'abandon_interrupted_audio', 'job_id': job,
                 'original_spec_sha256': row['spec_sha'], 'stop_sha256': stop_sha,
                 'directory': row['spec']['directory'], 'final_master': False}
        return snapshot, scope

    def catalog(self, page=None):
        with self._lock:
            self._live()
            after = ''
            if page is not None:
                if type(page) is not str or not _SELECTION.fullmatch(page):
                    raise PermissionError("Invalid recovery page")
                cursor = self._pages.get(page)
                if not cursor or cursor[1] < time.monotonic():
                    raise PermissionError("Review sound work again")
                after = cursor[0]
            self._choices.clear(); self._pages.clear()
            # Bound SQL work; only this exact managed host's earlier generation
            # and owned lease are considered. No project paths cross IPC.
            current = self._authority.current()['invocation']
            with self._host.ledger._db() as db:
                jobs = db.execute("""SELECT b.job_id FROM audio_native_service_bindings b
                    JOIN tasks t ON t.id=b.job_id
                    JOIN audio_native_staging_leases l ON l.job_id=b.job_id
                    WHERE b.unit=? AND b.owner_key=? AND b.invocation<>?
                      AND t.state IN ('ACTIVE','INTERRUPTED') AND b.job_id>?
                    ORDER BY b.job_id LIMIT ?""", (self._authority.unit, self._host.owner,
                                                    current, after, _PAGE + 1)).fetchall()
            items = []
            held = 0
            for (job,) in jobs[:_PAGE]:
                try:
                    state, _ = self._snapshot(job)
                except (OSError, RuntimeError, ValueError, KeyError, TypeError, sqlite3.Error):
                    held += 1
                    continue
                if not (state['recover'] or state['abandon']):
                    held += 1
                    continue
                token = secrets.token_hex(24)
                self._choices[token] = (state, time.monotonic() + _TTL)
                items.append({'selection': token, 'can_abandon': state['abandon'], 'can_recover': state['recover']})
            next_page = None
            if len(jobs) > _PAGE:
                next_page = secrets.token_hex(24)
                self._pages[next_page] = (jobs[_PAGE-1][0], time.monotonic() + _TTL)
            return {'available': True, 'items': items, 'held': held,
                    'more': next_page is not None, 'next_page': next_page}

    def act(self, selection, action):
        if (type(selection) is not str or not _SELECTION.fullmatch(selection) or
                type(action) is not str or action not in ('recover', 'abandon')):
            raise PermissionError("Invalid recovery request")
        with self._lock:
            window = self._live()
            choice = self._choices.pop(selection, None)
            if not choice or time.monotonic() > choice[1]:
                raise PermissionError("Review the current sound work again")
            snapshot, _ = self._snapshot(choice[0]['job'])
            if snapshot != choice[0] or not snapshot[action]:
                raise PermissionError("Recovery selection changed")
            if action == 'recover':
                message = ('Check and recover the saved audio checkpoint? '
                           'No new audio will be rendered or approved.')
            else:
                message = ('End this interrupted audio task without restarting it? '
                           'Its saved source material will not be deleted.')
            # Only the private native dialog sees the selected output and
            # source names; the JS client never receives filesystem paths.
            spec = self._host.journal.read(snapshot['job'])['spec']
            def safe_name(value):
                return ''.join(c if c.isprintable() else ' ' for c in Path(value).name)[:100]
            names = ', '.join(safe_name(p) for p in list(spec['sources'].values())[:8])
            message += '\n\nSaved work: ' + safe_name(spec['directory']) + '\nOriginal audio: ' + names
            if window.create_confirmation_dialog('NVP — Sound work', message) is not True:
                return {'status': 'CANCELLED'}
            # Verify origin, authority and exact selection again after the OS
            # dialog; the user may have changed navigation while it was open.
            self._live()
            after, scope = self._snapshot(snapshot['job'])
            if after != snapshot:
                raise PermissionError("Sound work changed during confirmation")
            try:
                if action == 'abandon':
                    event = 'desktop-audio-abandon-' + secrets.token_hex(24)
                    self._consent = (event, canonical_bytes(scope), time.monotonic() + 60)
                    result = self._host.abandon_systemd_missing_output(snapshot['job'], creator_event=event)
                else:
                    result = self._host.recover_systemd_interrupted(snapshot['job'])
                if result.get('abandoned'):
                    return {'status': 'ENDED'}
                if result.get('prelaunch_closed'):
                    return {'status': 'CLOSED'}
                if result.get('state') == 'reconciled':
                    return {'status': 'RECOVERED'}
                # Never present an unrecognized host result as completed media.
                return {'status': 'REVIEW_REQUIRED'}
            finally:
                self._consent = None
                self._choices.clear(); self._pages.clear()

    def close(self):
        with self._lock:
            self._closed = True
            self._consent = None
            self._choices.clear(); self._pages.clear()
