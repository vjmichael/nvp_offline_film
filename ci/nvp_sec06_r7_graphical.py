#!/usr/bin/env python3
"""Hosted diagnostic only: generated film/audio, real graphical input, read-only evidence.
Does not write approvals, scheduler records, resource samples, or worker state.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import time
import wave

RATE = 48000
HOME = Path.home()
ROOT = HOME / 'NVP_Projects'
RUNTIME = HOME / '.local/state/nvp/runtime'
TITLE_SHORT = 'CI Short Sound Preview'
TITLE_LONG = 'CI Long Sound Preview'


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def seed(root):
    from backend.nvp_film_index import FilmIndex
    from backend.nvp_imported_audio import OriginalAudioImport
    from backend.nvp_studio import Studio
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    index = FilmIndex(Studio(root / 'nvp_studio.sqlite3'))
    receipt = {}
    for name, title, seconds in [('short', TITLE_SHORT, 2), ('long', TITLE_LONG, 600)]:
        project = index.studio.create_project(title, 'Generated diagnostic audio only')['id']
        wav = root / (name + '.wav')
        frame = struct.pack('<hh', 100, -100)
        with wave.open(str(wav), 'wb') as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            for _ in range(seconds):
                w.writeframesraw(frame * RATE)
        h = digest(wav)
        OriginalAudioImport(index, trusted_native_picker=lambda: wav).register_from_picker(project, 'Voice')
        record = index.read_revision(project, 'Voice', 1)['data']
        assert record['source_media_sha256'] == h and record['native_frame_count'] == seconds * RATE
        path = index.verify_media_file(project, h, 'audio/wav')['path']
        assert digest(path) == h
        receipt[name] = {'project_id': project, 'title': title, 'sha256': h, 'samples': seconds * RATE, 'relative_media': str(Path(path).relative_to(root))}
        wav.unlink()
    (root / 'ci-generated-fixture.json').write_text(json.dumps(receipt, indent=2) + '\n')


def graphical(evidence, scope):
    import gi
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk
    import pyatspi
    evidence = Path(evidence)
    scope = Path(scope)
    assert scope.is_relative_to(Path('/sys/fs/cgroup')) and scope.is_dir()
    assert os.getuid() != 0 and os.environ.get('DISPLAY') == ':99'
    fixture = json.loads((ROOT / 'ci-generated-fixture.json').read_text())
    def save(name, value):
        (evidence / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n')
    def shot(name):
        w = Gdk.get_default_root_window()
        assert w is not None
        pix = Gdk.pixbuf_get_from_window(w, 0, 0, w.get_width(), w.get_height())
        assert pix is not None
        pix.savev(str(evidence / (name + '.png')), 'png', [], [])
    def until(fn, label, timeout=90, pause=.2):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            val = fn()
            if val:
                return val
            time.sleep(pause)
        raise AssertionError('Timed out: ' + label)
    def nodes():
        todo = [pyatspi.Registry.getDesktop(0)]
        count = 0
        while todo:
            n = todo.pop()
            count += 1
            if count > 8000:
                raise AssertionError('Unexpectedly large accessibility tree')
            yield n
            try:
                todo.extend(list(n))
            except Exception:
                continue
    def node_text(n):
        try:
            name = n.name or ''
            if name:
                return name
            if n.getRoleName() in ('label', 'text', 'paragraph', 'static'):
                t = n.queryText()
                return t.getText(0, t.characterCount)
        except Exception:
            pass
        return ''
    def text_present(wanted):
        return any(wanted in node_text(n) for n in nodes())
    def button_point(wanted, exact=False):
        for n in nodes():
            try:
                if n.getRoleName() not in ('push button', 'toggle button', 'button'):
                    continue
                name = node_text(n)
                if not name:
                    name = ' '.join(node_text(c) for c in n)
                if (name.strip() != wanted if exact else wanted not in name):
                    continue
                state = n.getState()
                if not state.contains(pyatspi.STATE_SHOWING) or not state.contains(pyatspi.STATE_SENSITIVE):
                    continue
                rect = n.queryComponent().getExtents(pyatspi.DESKTOP_COORDS)
                if rect.width > 0 and rect.height > 0:
                    x, y = rect.x + rect.width // 2, rect.y + rect.height // 2
                    screen = Gdk.get_default_root_window()
                    if 0 < x < screen.get_width() and 0 < y < screen.get_height():
                        return (x, y)
            except Exception:
                continue
        return None
    def click_point(p):
        subprocess.run(['xdotool', 'mousemove', '--sync', str(p[0]), str(p[1]), 'click', '1'], check=True, timeout=5)
    def click(wanted, exact=False):
        p = until(lambda: button_point(wanted, exact), 'visible graphical button: ' + wanted)
        click_point(p)
    def assert_dialog(title, tag):
        until(lambda: text_present('Prepare one sound preview for ' + title), 'native confirmation prompt for ' + title)
        shot(tag)
    def rows(db, statement, args=()):
        with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True, timeout=2) as conn:
            return conn.execute(statement, args).fetchall()
    activity = RUNTIME / 'task_activity.sqlite3'
    journal = RUNTIME / 'audio_native_journal.sqlite3'
    def tasks():
        return rows(activity, 'SELECT id,state,reserved FROM tasks ORDER BY created_at')
    def job_for(kind):
        for job_id, state, reserved in tasks():
            js = rows(journal, 'SELECT spec_json,state FROM audio_native_jobs WHERE job_id=?', (job_id,))
            if js:
                spec = json.loads(js[0][0])
                source = spec.get('project_source') or {}
                if source.get('project_id') == fixture[kind]['project_id']:
                    assert source['media_sha256'] == fixture[kind]['sha256'] and source['source_id'] == 'Voice' and source['revision'] == 1
                    assert spec['total_samples'] == fixture[kind]['samples']
                    return {'job': job_id, 'state': state, 'reserved': reserved, 'journal': js[0][1]}
        return None
    def stopped(kind, state, journal_state):
        x = job_for(kind)
        if not x:
            return None
        if x['state'] in ('SUCCEEDED', 'CANCELLED', 'FAILED', 'INTERRUPTED') and x['state'] != state:
            raise AssertionError('Unexpected terminal state: ' + str(x))
        return x if (x['state'], x['reserved'], x['journal']) == (state, 0, journal_state) else None
    def workers():
        return list(scope.rglob('nvp-worker-*'))
    def live_audio_worker():
        x = job_for('long')
        if not x:
            return None
        if x['state'] in ('SUCCEEDED', 'CANCELLED', 'FAILED', 'INTERRUPTED'):
            raise AssertionError('Worker stopped before a live cancellation was observed: ' + str(x))
        if x['state'] != 'ACTIVE' or x['reserved'] != 1 or x['journal'] != 'running':
            return None
        for cg in workers():
            try:
                for p in (cg / 'cgroup.procs').read_text().split():
                    cmd = (Path('/proc') / p / 'cmdline').read_bytes().split(b'\0')
                    exe = (Path('/proc') / p / 'exe').resolve(strict=True)
                    if b'--nvp-linux-audio-worker' in cmd and exe == Path('/opt/nvp/NVP'):
                        if 'populated 1' in (cg / 'cgroup.events').read_text():
                            return {**x, 'worker_pid': int(p), 'cgroup': str(cg)}
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
        return None
    def unchanged():
        for f in fixture.values():
            assert digest(ROOT / f['relative_media']) == f['sha256'], 'Generated original changed'
    try:
        # Existing installed read-only observation has navigated to Resume Working.
        until(lambda: button_point(TITLE_SHORT), 'installed movie picker', timeout=120)
        assert tasks() == [], 'Fixture unexpectedly contains tasks'
        click(TITLE_SHORT)
        click('Edit Film')
        click('Prepare preview', True)
        assert_dialog(TITLE_SHORT, '01-short-confirmation')
        click('OK', True)
        success = until(lambda: stopped('short', 'SUCCEEDED', 'completed'), 'completed protected preview', timeout=120)
        until(lambda: text_present('Sound preview prepared and checked. Your original is unchanged.'), 'success status')
        receipt = ROOT / '.native-production-runtime/audio-native' / success['job'] / 'worker_verified_receipt.json'
        v = json.loads(receipt.read_text())
        assert v['format'] == 'nvp.audio.native.worker_verified.v1' and v['job_id'] == success['job'] and v['samples'] == fixture['short']['samples'] and v['final_master'] is False
        assert not workers(), 'Worker cgroup retained after success'
        unchanged()
        save('02-completed', {**success, 'receipt_sha256': digest(receipt), 'originals_unchanged': True})
        shot('02-completed')
        # The sidebar switches to the second, independently generated project.
        click(TITLE_LONG)
        click('Edit Film')
        click('Prepare preview', True)
        assert_dialog(TITLE_LONG, '03-long-confirmation')
        click('OK', True)
        point = until(lambda: button_point('Cancel sound task', True), 'active Cancel sound task button', timeout=30)
        active = until(live_audio_worker, 'actual live installed audio worker in its delegated cgroup', timeout=180, pause=.025)
        save('04-live-before-cancel', active)
        click_point(point)
        cancelled = until(lambda: stopped('long', 'INTERRUPTED', 'recovery_required'), 'worker stopped with durable recovery record', timeout=90)
        until(lambda: text_present('Sound work stopped. Check saved work before restarting.'), 'explicit native cancellation status')
        stop = rows(activity, 'SELECT worker_reaped,stop_reason FROM audio_native_os_stop_receipts WHERE job_id=?', (cancelled['job'],))
        assert stop == [(1, 'owned_worker_closed')], 'Missing authentic owned cleanup record'
        assert not Path(active['cgroup']).exists() and not workers(), 'Original worker cgroup still exists'
        unchanged()
        assert len(tasks()) == 2 and all(x[2] == 0 for x in tasks())
        save('05-cancelled', {**cancelled, 'owned_stop_receipt': True, 'cgroup_removed': True, 'all_reservations_released': True, 'originals_unchanged': True, 'fixture_consent_not_human': True})
        shot('05-cancelled')
        save('result', {'status':'PASS', 'scope':'Ubuntu installed generated-media graphical diagnostic; not human or Debian release acceptance', 'source_sha':'7f33374a77082ebdc217f4fc4435a3e5be6cd49d', 'source_tree':'a64be51b19b06c881ddecfed3a6ab491bd6bbbd8', 'positive_admission':True, 'active_gui_cancellation':True})
    except BaseException:
        try:
            shot('failure')
            save('failure-state', {'tasks': tasks(), 'visible_accessible_names': [node_text(n) for n in nodes() if node_text(n)]})
        except Exception:
            pass
        raise


if __name__ == '__main__':
    if sys.argv[1] == 'seed':
        seed(sys.argv[2])
    elif sys.argv[1] == 'gui':
        graphical(sys.argv[2], sys.argv[3])
    else:
        raise ValueError('Unexpected mode')
